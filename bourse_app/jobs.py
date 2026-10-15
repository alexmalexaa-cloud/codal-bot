"""
کارهای پس‌زمینه‌ی دریافت از کدال (برنامه‌ی وب)

- همه در یک صف و با یک کارگر اجرا می‌شوند؛ هم‌زمان فقط یکی (برای فشار نیاوردن به کدال و دوری از کپچا)
- کلید JOBS: (نوع، نماد) — نوع: monthly، financial، history، screener، mrank (نماد خالی = کل بازار)
- وضعیت: queued (در صف) ← running ← done | error | captcha (منتظر کد امنیتی اپراتور)
- کار تکراریِ زنده (در صف، در جریان یا منتظر کد) دوباره اضافه نمی‌شود
- کپچا: کار تمام نمی‌شود و همان‌جا منتظر کد می‌ماند (client.CAPTCHA_WAIT)؛ اگر کد در ۳۰ دقیقه وارد نشد،
  کار با resume متوقف و با کد درست اول صف دوباره اجرا می‌شود
- رتبه‌بندی ماهانه (mrank) تکه‌تکه اجرا می‌شود: هر نوبت MRANK_CHUNK گزارش، بعد اگر کار مانده دوباره ته صف می‌رود
  (کارهای دیگر مثل گزارش یک نماد بین تکه‌ها اجرا می‌شوند) تا همه‌ی گزارش‌های لازم ماه گرفته شود یا اپراتور
  توقف بزند (stop)
"""
import threading
from datetime import datetime

from codal import client, collect, db, mrank, screener
from codal.report import UnsupportedReport

JOBS = {}
_QUEUE = []                    # [(نوع، نماد، گزینه‌ها)]
_QLOCK = threading.Lock()
_worker = None
MRANK_CHUNK = 20               # گزارش در هر نوبت رتبه‌بندی ماهانه

KIND_LABEL = {"monthly": "گزارش ماهانه", "financial": "صورت مالی", "screener": "صورت مالی",
              "history": "سابقه‌ی", "mrank": "گزارش ماهانه"}
MARKET_LABEL = {"screener": "رتبه‌بندی رشد سود", "mrank": "رتبه‌بندی تغییر درآمد ماهانه"}
FA_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_digits(s):
    return str(s or "").translate(_FA)


def month_fa(ym):
    return f"{FA_MONTHS[ym[1] - 1]} {fa_digits(ym[0])}"


def job_name(kind, sym, opts=None):
    if kind == "mrank" and opts and opts.get("month"):
        return f"گزارش‌های ماهانه‌ی {month_fa(mrank.parse_month(opts['month']))}"
    return MARKET_LABEL.get(kind, "") if not sym else f"{KIND_LABEL.get(kind, '')} {sym}"


def get(kind, sym=""):
    return JOBS.get((kind, sym))


def alive(j):
    """در صف، در جریان، یا منتظر کد امنیتی (کار هنوز در کارگر است)"""
    return bool(j) and (j["state"] in ("queued", "running") or (j["state"] == "captcha" and not j.get("resume")))


def active(kind, sym=""):
    return alive(JOBS.get((kind, sym)))


def enqueue(kind, sym, opts, front=False):
    """افزودن کار به صف (کار تکراریِ زنده دوباره اضافه نمی‌شود)؛ front: اول صف (ادامه‌ی کار بعد از کپچا)"""
    global _worker
    key = (kind, sym)
    with _QLOCK:
        cur = JOBS.get(key)
        if alive(cur):
            return cur
        busy = next((k for k, j in JOBS.items() if alive(j) and j["state"] != "queued"), None)
        JOBS[key] = {"state": "queued", "fetched": 0, "skipped": 0, "name": job_name(kind, sym, opts),
                     "month": opts.get("month"),
                     "message": f"در صف: بعد از {JOBS[busy].get('name') or job_name(*busy)}" if busy else "شروع…"}
        if front:
            _QUEUE.insert(0, (kind, sym, opts))
        else:
            _QUEUE.append((kind, sym, opts))
        if _worker is None:
            _worker = threading.Thread(target=_work, daemon=True)
            _worker.start()
        return JOBS[key]


def _work():
    """کارگر صف: کارها را یکی‌یکی اجرا می‌کند و وقتی صف خالی شد تمام می‌شود"""
    global _worker
    while True:
        with _QLOCK:
            if not _QUEUE:
                _worker = None
                return
            kind, sym, opts = _QUEUE.pop(0)
        _run(kind, sym, opts)


def _requeue(kind, sym, opts):
    """ادامه‌ی کار طولانی در نوبت بعد: ته صف (کارهای دیگرِ در صف اول اجرا می‌شوند)؛ شمارنده‌ها جمع می‌شوند"""
    job = JOBS[(kind, sym)]
    with _QLOCK:
        job["base"] = (job.get("fetched", 0), job.get("skipped", 0))
        nxt = _QUEUE[0] if _QUEUE else None
        name = nxt and (JOBS[(nxt[0], nxt[1])].get("name") or job_name(nxt[0], nxt[1]))
        job.update(state="queued", message=f"ادامه بعد از {name}" if name else "ادامه‌ی دریافت…")
        _QUEUE.append((kind, sym, opts))


def stop(kind, sym=""):
    """
    توقف کار به درخواست اپراتور: در صف ← همین حالا؛ در جریان ← بعد از همین درخواست؛ منتظر کد امنیتی ← همین حالا.
    گزارش‌های گرفته‌شده در دیتابیس می‌مانند
    """
    key = (kind, sym)
    ended = False
    with _QLOCK:
        j = JOBS.get(key)
        if not j:
            return None
        if j["state"] == "queued":                  # از صف بیرون (کارگر دیگر اجرایش نمی‌کند)
            _QUEUE[:] = [q for q in _QUEUE if (q[0], q[1]) != key]
            ended = True
        elif alive(j):
            j.update(stop=True, message="در حال توقف…")
        elif j["state"] == "captcha":               # مهلت کد گذشته و منتظر ادامه بود
            j["resume"] = None
            ended = True
    if ended:
        _end_stopped(kind, j)
    client.wake()                                   # انتظار کد امنیتی همین کار تمام شود
    return j


def _stopped(kind, job, con=None):
    """رتبه‌بندی ماهانه‌ی متوقف‌شده تا مدتی خودکار دوباره شروع نشود (mrank.need_scan، «mrank_stop»)"""
    if kind != "mrank" or not job.get("month"):
        return
    own = con is None
    con = con or db.connect()
    try:
        db.mark_checked(con, "mrank_stop", job["month"])
    finally:
        if own:
            con.close()


def _end_stopped(kind, job, con=None):
    """پایان کار به خاطر توقف اپراتور (اول ثبت توقف، بعد وضعیت؛ تا صفحه پیش از ثبت، دوباره شروع خودکار نکند)"""
    _stopped(kind, job, con)
    job.update(state="done", message="دریافت متوقف شد", stopped=True, finished=datetime.now().isoformat(timespec="seconds"))


def _run(kind, sym, opts):
    job = JOBS[(kind, sym)]
    job.update(state="running", message="جستجوی اطلاعیه‌ها در کدال…",
               started=job.get("started") or datetime.now().isoformat(timespec="seconds"))
    base_f, base_s = job.get("base", (0, 0))       # شمارنده‌های نوبت‌های قبلی همین کار

    def progress(fetched, skipped, last):
        msg = fa_digits(last) if str(last).startswith("فهرست") else f"گزارش {fa_digits(last)} دریافت شد"
        job.update(fetched=base_f + fetched, skipped=base_s + skipped, message=msg)

    def wait_captcha():
        # کپچا: کار تمام نمی‌شود؛ همین‌جا منتظر کد اپراتور می‌ماند و بعد از کد درست از همان گزارش ادامه می‌دهد
        job.update(state="captcha", message=client.CAPTCHA_MSG, captcha_at=datetime.now().isoformat(timespec="seconds"))
        ok = client.wait_captcha_solved(client.CAPTCHA_EXPIRE, cancel=lambda: job.get("stop"))
        if ok:
            job.update(state="running", message="کد تأیید شد؛ ادامه‌ی دریافت از همان‌جا…")
        return ok

    client.NOTIFY = lambda msg: job.update(message=msg)
    client.CAPTCHA_WAIT = wait_captcha
    con = None
    try:
        con = db.connect()       # داخل try: اگر دیتابیس لحظه‌ای قفل بود، کار با خطا تمام می‌شود و صف گیر نمی‌کند
        if kind == "screener":
            screener.scan(con, progress, **opts)
        elif kind == "mrank":
            # همه‌ی گزارش‌های لازم ماه (budget=None) یا حداکثر budget گزارش، تکه‌تکه
            left = opts.get("budget")
            st = mrank.scan(con, progress, budget=min(MRANK_CHUNK, left or MRANK_CHUNK), month=opts.get("month"),
                            until=lambda: job.get("stop"))
            if job.get("stop"):
                _end_stopped(kind, job, con)
                return
            left = None if left is None else left - st["fetched"] - st["skipped"]
            if not st["complete"] and (left is None or left > 0):
                _requeue(kind, sym, {**opts, "budget": left})
                return
            db.mark_checked(con, "mrank", opts.get("month") or "")   # تا مهلت بعدی از دیتابیس
            job["complete"] = st["complete"]
        elif kind == "history":
            # سابقه‌ی چندساله برای آموزش مدل‌های پیش‌بینی: اول گزارش‌های ماهانه، بعد صورت‌های مالی
            years = opts.get("years", 5)
            job["phase"] = "گزارش‌های ماهانه"
            collect.collect(con, sym, "monthly", progress, years=years)
            job["phase"] = "صورت‌های مالی"
            try:
                collect.collect(con, sym, "financial", progress, years=years)
            except UnsupportedReport:
                pass            # شرکت بدون صورت مالی استاندارد؛ گزارش ماهانه‌ها گرفته شد
        elif kind == "monthly":
            # سال مالی قبل کامل + سال جاری تا آخرین گزارش (فقط ماه‌های جاافتاده دانلود می‌شوند)
            collect.collect_monthly(con, sym, progress)
        else:
            collect.collect(con, sym, kind, progress, **opts)
        if kind in ("monthly", "financial", "screener"):
            db.mark_checked(con, kind, sym)    # تا مهلت بعدی، همین داده‌ها از دیتابیس کافی است (codal/fresh.py)
        job.update(state="done", message="", finished=datetime.now().isoformat(timespec="seconds"))
    except UnsupportedReport as e:
        job.update(state="error", message=f"{KIND_LABEL[kind]} این نماد پشتیبانی نمی‌شود: {e}")
    except client.Captcha as e:
        if job.get("stop"):                      # اپراتور هنگام انتظار کد، توقف زد
            _end_stopped(kind, job, con)
            return
        # کد در مهلت (۳۰ دقیقه) وارد نشد: کار متوقف است و با کد درست دوباره به صف می‌رود
        # (گزارش‌های گرفته‌شده در دیتابیس و حافظه‌اند و دوباره دانلود نمی‌شوند)
        job.update(state="captcha", message=str(e), resume={"kind": kind, "sym": sym, "opts": opts})
    except client.RateLimited as e:
        job.update(state="error", message=str(e))
    except Exception as e:   # خطای شبکه، دیتابیس و…
        job.update(state="error", message=f"خطا در دریافت از کدال: {e}")
    finally:
        if con is not None:
            con.close()
        client.NOTIFY = lambda msg: print("  … " + msg, flush=True)
        client.CAPTCHA_WAIT = None


# ==================== کپچا ====================
def _captcha_jobs():
    return [(k, j) for k, j in list(JOBS.items()) if j.get("state") == "captcha"]


def captcha_state():
    """
    برای پنجره‌ی کد امنیتی صفحه‌ها: pending، since (تغییرش = کپچای تازه)، jobs (نام کارهای منتظر)،
    throttle (محدودیت 429 جستجوی کدال که کپچا ندارد، با ثانیه‌های باقی‌مانده)
    """
    waiting = _captcha_jobs()
    since = client.captcha_since()
    if not since and waiting:
        since = max(j.get("captcha_at", "") for _, j in waiting)
    return {"pending": bool(since) or bool(waiting), "since": since,
            "jobs": [{"kind": k[0], "symbol": k[1], "name": j.get("name") or job_name(*k)} for k, j in waiting],
            "throttle": client.throttle_status()}


def resume_after_captcha():
    """
    بعد از کد درست: کار منتظر (در کارگر) خودش بلافاصله ادامه می‌دهد (client.wait_captcha_solved)؛
    کارهایی که مهلتشان تمام شده بود اول صف می‌روند. خروجی: تعداد کارهای ادامه‌یافته
    """
    waiting = _captcha_jobs()
    resumed = [j["resume"] for _, j in waiting if j.get("resume")]
    for r in reversed(resumed):
        enqueue(r["kind"], r["sym"], r["opts"], front=True)
    return len(waiting)
