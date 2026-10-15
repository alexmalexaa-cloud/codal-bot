"""
رتبه‌بندی نمادها بر اساس تغییر درآمد در گزارش فعالیت ماهانه‌ی یک ماه (صفحه‌ی اول «عملکرد ماهانه»)

ماه = ماه تقویمی پایان دوره‌ی گزارش (مثلاً شهریور ۱۴۰۵ = گزارش‌های منتهی به ۱۴۰۵/۰۶/۳۱)؛ اپراتور ماه را انتخاب می‌کند.
از کدال فقط گزارش‌های لازمِ همان ماه گرفته می‌شود: گزارش‌های خود ماه و گزارش ماه قبلِ همان نمادها (پایه‌ی «نسبت
به ماه قبل»)، و از هر دو فقط آن‌هایی که در دیتابیس نیستند.

معیارها (فروش ماه = جمع مبلغ فروش «دوره یک ماهه»):
  g_mom  نسبت به ماه قبل        گزارش ماه قبل (ماه دوم سال مالی: ستون «تا پایان ماه قبل» همین گزارش = ماه اول)
  g_avg  نسبت به میانگین ماه‌های قبلِ همان سال مالی   (ستون «تا پایان ماه قبل» همین گزارش)
  g_yoy  نسبت به ماه مشابه سال قبل   گزارش همان ماه پارسال؛ وگرنه ستون «مدت مشابه سال قبل» همین گزارش منهای همان
         ستون در گزارش ماه قبل (هر دو تجمعیِ پارسال‌اند؛ ماه اول سال مالی: خود ستون)
  g_cum  تجمعی نسبت به مدت مشابه سال قبل  (ستون‌های تجمعی همین گزارش)

داده‌ی ناسازگار: اگر «مدت مشابه سال قبل» این گزارش از همان ستون گزارش ماه قبل کمتر باشد (تجمعی کم نمی‌شود؛ اشتباه
ورود داده در گزارش شرکت)، آن ستون کنار گذاشته می‌شود (bad_ly) و g_cum فقط با گزارش پارسال جایگزین حساب می‌شود.

همه از دیتابیس خوانده می‌شود (فقط ردیف‌های ماه‌های لازم، با شاخص period_end)؛ scan() فقط گزارش‌هایی را که
نداریم از کدال می‌گیرد.
"""
import json
import re

from . import client, collect, db, monthly, search
from .fresh import MARKET_RECHECK, MISSING_RECHECK, _ago, _shift, _ym, age, today_ym
from .report import UnsupportedReport
from .text import title_period

METRICS = ("g_mom", "g_avg", "g_yoy", "g_cum")
PUBLISH_MONTHS = 2        # گزارش ماه M معمولاً تا پایان ماه M+2 منتشر می‌شود (اصلاحیه‌ها هم)


def growth(cur, base):
    if cur is None or not base or base <= 0:
        return None
    return (cur - base) / base * 100


def eligible_filter(con):
    """
    شرط SQL «فقط شرکت‌ها» (نوع ۱ در لیست کدال، نه صندوق و …) روی ستون symbol؛
    اگر لیست نمادها هنوز گرفته نشده، بدون شرط
    """
    has = con.execute("SELECT 1 FROM symbols WHERE type=1 LIMIT 1").fetchone()
    return " AND symbol IN (SELECT symbol FROM symbols WHERE type=1)" if has else ""


def _eligible(con):
    """مجموعه‌ی نمادهای «شرکت» (نوع ۱) یا None اگر لیست نمادها هنوز گرفته نشده"""
    if not eligible_filter(con):
        return None
    return {r[0] for r in con.execute("SELECT symbol FROM symbols WHERE type=1")}


def month_key(ym):
    return "%04d-%02d" % ym


def parse_month(s):
    """«1405-06» یا «1405/06» ← (1405, 6)"""
    m = re.match(r"^\s*(\d{4})[-/](\d{1,2})\s*$", str(s or ""))
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return int(m.group(1)), int(m.group(2))


def default_month():
    """ماه پیش‌فرض: ماه گذشته (گزارش‌هایش در ماه جاری منتشر می‌شوند)"""
    return _shift(today_ym(), -1)


def _range(ym):
    """بازه‌ی رشته‌ای period_end یک ماه (برای استفاده از شاخص): «1405/06/00» تا «1405/06/99»"""
    return "%04d/%02d/00" % ym, "%04d/%02d/99" % ym


# ==================== محاسبه از دیتابیس ====================
def _rows_for(con, yms):
    """نماد ← {(سال، ماه): آخرین نسخه‌ی گزارش} فقط برای ماه‌های yms"""
    where = " OR ".join("period_end BETWEEN ? AND ?" for _ in yms)
    args = [v for ym in yms for v in _range(ym)]
    out = {}
    for r in con.execute(f"SELECT * FROM monthly_latest WHERE total IS NOT NULL AND ({where})"
                         + eligible_filter(con), args):
        out.setdefault(r["symbol"], {})[_ym(r["period_end"])] = r
    return out


def _prev_total(L, P):
    """فروش ماه قبل: گزارش خودش؛ ماه دوم سال مالی: ستون «تا پایان ماه قبل» همین گزارش (= فروش ماه اول)"""
    if P:
        return P["total"]
    return L["cum_prev"] if L["fiscal_month"] == 2 else None


def _same_period_ly(L, P):
    """
    ستون «مدت مشابه سال قبل» (تجمعی پارسال) این گزارش و گزارش ماه قبلِ همان سال مالی ←
    (فروش ماه مشابه پارسال یا None، ستون این گزارش ناسازگار است؟)
    """
    cl, fm = L["cum_ly"], L["fiscal_month"]
    if cl is None:
        return None, False
    if fm == 1:
        return cl, False                        # ماه اول سال مالی: تجمعیِ پارسال = همان یک ماه
    if P and P["fiscal_month"] == fm - 1 and P["cum_ly"] is not None:
        d = cl - P["cum_ly"]
        return (d, False) if d >= 0 else (None, True)
    return None, False


def metrics(by_ym, ym):
    L = by_ym[ym]
    fm, total = L["fiscal_month"], L["total"]
    P = by_ym.get(_shift(ym, -1))
    Y = by_ym.get(_shift(ym, -12))
    prev = _prev_total(L, P)
    ly_cum, bad_ly = _same_period_ly(L, P)
    ly = Y["total"] if Y else ly_cum
    cum_ly = L["cum_ly"]
    if bad_ly:      # تجمعی پارسال = تجمعی پارسالِ گزارش ماه قبل + همان ماه از گزارش پارسال (اگر هست)
        cum_ly = P["cum_ly"] + Y["total"] if Y and Y["total"] is not None else None
    avg_prev = L["cum_prev"] / (fm - 1) if fm and fm >= 2 and L["cum_prev"] else None
    return {
        "symbol": L["symbol"], "period_end": L["period_end"], "fiscal_month": fm, "published": L["published"],
        "total": total, "prev": prev, "avg_prev": avg_prev, "ly": ly, "cum": L["cum"], "bad_ly": bad_ly,
        "g_mom": growth(total, prev), "g_avg": growth(total, avg_prev),
        "g_yoy": growth(total, ly), "g_cum": growth(L["cum"], cum_ly),
    }


def ranking(con, ym=None):
    """
    گزارش ماه ym هر شرکت (پیش‌فرض: ماه گذشته) با چهار معیار؛ ردیفی که فروش ماه قبل ندارد prev_state دارد
    (wait | none | bad، prev_states)
    """
    ym = ym or default_month()
    by_sym = _rows_for(con, [ym, _shift(ym, -1), _shift(ym, -12)])
    rows, lacking = [], []
    for by in by_sym.values():
        if ym in by:
            rows.append(metrics(by, ym))
            if rows[-1]["prev"] is None:
                lacking.append(by[ym])
    states = prev_states(con, ym, lacking)
    for r in rows:
        if r["prev"] is None:
            r["prev_state"] = states[r["symbol"]]
    rows.sort(key=lambda r: (r["g_mom"] is None, -(r["g_mom"] or 0), r["symbol"]))
    return rows


def prev_states(con, ym, lacking):
    """
    نمادهای بدون فروش ماه قبل (ردیف‌های گزارش ماه ym) ← وضعیت گزارش ماه قبلشان:
      wait  هنوز گرفته نشده: اطلاعیه‌اش شناخته شده، یا خوراک آن ماه بعد از رسیدن گزارش این نماد جستجو نشده
      none  خوراک کدال جستجو شد و گزارش ماه قبلی از این نماد منتشر نشده بود
            (تا بسته شدن بازه‌ی انتشار آن ماه، روزی یک بار دوباره جستجو می‌شود)
      bad   گزارش ماه قبل هست ولی قالبش خوانا نیست
    """
    if not lacking:
        return {}
    pm, key = _shift(ym, -1), month_key(ym)
    state = _Month(con, pm)
    known = {}
    for x in stored_month_letters(con, pm):            # جدیدترین نسخه‌ی هر نماد
        known.setdefault(x["symbol"], x)
    looked = db.checked_at(con, "mrank_prev", key)
    if looked and not publish_window(pm)[2] and (age(con, "mrank_prev", key) or 0) > MISSING_RECHECK:
        looked = None                                 # شاید دیرتر منتشر کرده باشد
    out = {}
    for L in lacking:
        x = known.get(L["symbol"])
        if x:
            out[L["symbol"]] = "wait" if state.need(x) else "bad"
        else:
            out[L["symbol"]] = "none" if looked and looked >= (L["fetched_at"] or "") else "wait"
    return out


def waiting_prev(con, ym):
    """نمادهای ماه ym که گزارش ماه قبلشان باید از کدال گرفته شود (وضعیت wait)"""
    pm = _shift(ym, -1)
    lacking = [by[ym] for by in _rows_for(con, [ym, pm]).values()
               if ym in by and _prev_total(by[ym], by.get(pm)) is None]
    return [s for s, v in prev_states(con, ym, lacking).items() if v == "wait"]


def months(con, back=12):
    """ماه‌های قابل انتخاب: ۱۲ ماه اخیر + ماه‌های دیگرِ دارای گزارش در دیتابیس، با تعداد شرکت‌ها"""
    count = {}
    for r in con.execute("SELECT substr(period_end, 1, 7) k, COUNT(DISTINCT symbol) n FROM monthly_reports "
                         "WHERE total IS NOT NULL" + eligible_filter(con) + " GROUP BY k"):
        y, m = r["k"].split("/") if r["k"] and "/" in r["k"] else (None, None)
        if y:
            count[(int(y), int(m))] = r["n"]
    last = default_month()
    yms = {_shift(last, -i) for i in range(back)} | set(count)
    done = {r["symbol"] for r in con.execute("SELECT symbol FROM checks WHERE kind='mrank_feed'")}
    # done: فهرست اطلاعیه‌های آن ماه کامل خوانده شده و بازه‌ی انتشارش تمام شده (دیگر جستجو لازم نیست)
    return [{"month": month_key(ym), "y": ym[0], "m": ym[1], "count": count.get(ym, 0),
             "done": month_key(ym) in done} for ym in sorted((y for y in yms if y <= last), reverse=True)]


# ==================== تکمیل ستون‌های تجمعی از حافظه‌ی پاسخ‌ها (بدون شبکه) ====================
_backfilled = set()


def backfill(con):
    """گزارش‌های ذخیره‌شده‌ی قبل از این نسخه ستون تجمعی ندارند؛ از صفحه‌ی گزارشِ ذخیره‌شده در cache.db دوباره خوانده می‌شوند"""
    n = 0
    rows = con.execute("SELECT m.id, m.tracing_no, l.url FROM monthly_reports m JOIN letters l USING(tracing_no) "
                       "WHERE m.cum IS NULL").fetchall()
    for r in rows:
        if r["id"] in _backfilled or not r["url"]:
            continue
        _backfilled.add(r["id"])
        text, _ = client.cache_get(r["url"], client.FOREVER)
        m = re.search(r"var datasource\s*=\s*(\{.*?\});\s*\n", text or "", re.S)
        if not m:
            continue
        try:
            rep = monthly.parse(json.loads(m.group(1)))
        except (UnsupportedReport, ValueError, KeyError, TypeError):
            continue
        con.execute("UPDATE monthly_reports SET cum=?, cum_prev=?, cum_ly=? WHERE id=?",
                    (rep["cum"], rep["cum_prev"], rep["cum_ly"], r["id"]))
        n += 1
    if n:
        con.commit()
    return n


# ==================== جمع‌آوری از کدال: فقط گزارش‌های یک ماه ====================
def publish_window(ym):
    """بازه‌ی تاریخ انتشار گزارش‌های ماه ym: از روز اول ماه بعد تا پایان ماه ym+PUBLISH_MONTHS (حداکثر امروز)"""
    a = _shift(ym, 1)
    b = _shift(ym, PUBLISH_MONTHS)
    start = "%04d/%02d/01" % a
    end = min("%04d/%02d/31" % b, search.today_j())
    return start, end, end < search.today_j()


class _Month:
    """گزارش‌های یک ماه در دیتابیس (یک بار خوانده می‌شود): برای تصمیم «این اطلاعیه دانلود لازم دارد؟»"""

    def __init__(self, con, ym):
        lo, hi = _range(ym)
        self.have = {r["symbol"]: r for r in con.execute(
            "SELECT * FROM monthly_latest WHERE period_end BETWEEN ? AND ?", (lo, hi))}
        self.done = {r[0] for r in con.execute(
            "SELECT tracing_no FROM monthly_reports WHERE period_end BETWEEN ? AND ? "
            "UNION SELECT tracing_no FROM skipped WHERE kind='monthly'", (lo, hi))}

    def need(self, x):
        """نسخه‌ی هم‌تاریخ یا جدیدتر با ستون‌های تجمعی در دیتابیس نیست و قبلاً خوانده/رد نشده"""
        have = self.have.get(x["symbol"])
        if have and have["published"] >= x["published"] and have["cum"] is not None:
            return False
        if x["tracing_no"] in self.done and (not have or have["cum"] is not None):
            return False
        return True


def stored_month_letters(con, ym):
    """اطلاعیه‌های شناخته‌شده‌ی ماه ym در جدول letters (جدیدترین اول)"""
    lo, hi = _range(ym)
    return [dict(r) for r in con.execute(
        "SELECT * FROM letters WHERE letter_type=? AND period_end BETWEEN ? AND ?" + eligible_filter(con)
        + " ORDER BY published DESC", (search.LETTER_MONTHLY, lo, hi))]


def missing_known(con, ym):
    """نمادهایی که اطلاعیه‌ی ماه ym آن‌ها شناخته شده ولی گزارششان هنوز در دیتابیس نیست"""
    state, seen, out = _Month(con, ym), set(), []
    for x in stored_month_letters(con, ym):
        if x["symbol"] in seen:
            continue
        seen.add(x["symbol"])                    # فقط جدیدترین نسخه‌ی هر نماد
        if state.need(x):
            out.append(x["symbol"])
    return out


# بازه‌ی انتشار یک ماه (دو ماه انتشار) در خوراک کل بازار بیش از ۱۲۰ صفحه است؛ سقف ۸۰ صفحه باعث می‌شد
# گزارش‌هایی که اوایل بازه منتشر شده‌اند (بیشترِ گزارش‌های ماه قبل) هرگز خوانده نشوند
def month_letters(con, ym, progress=lambda **kw: None, max_pages=400, until=None, out=None):
    """
    اطلاعیه‌های گزارش ماهانه‌ی ماه ym از خوراک کل بازار، فقط در بازه‌ی انتشار آن ماه (FromDate/ToDate).
    اگر همه‌ی صفحه‌های یک بازه‌ی تمام‌شده خوانده شده باشد (checks «mrank_feed»)، فقط از جدول letters (بدون جستجو).
    until(): وقتی True شود، خواندن صفحه‌ها متوقف می‌شود (بودجه پر شد یا اپراتور توقف زد).
    out: دیکشنری؛ out["complete"] = فهرست تا آخر خوانده شد
    """
    key = month_key(ym)
    start, end, closed = publish_window(ym)
    out = out if out is not None else {}
    out["complete"] = False
    if closed and db.checked_at(con, "mrank_feed", key):
        out["complete"] = True
        yield from stored_month_letters(con, ym)
        return
    page, pages = 1, 1
    while page <= max_pages:
        if until and until():
            return
        progress(last=f"فهرست اطلاعیه‌های ماه {ym[0]}/{ym[1]:02d}: صفحه {page}" + (f" از {pages}" if pages > 1 else ""))
        rows, pages = search.letters("", search.LETTER_MONTHLY, page, from_date=start, to_date=end)
        for x in rows:
            db.save_letter(con, x)
        con.commit()
        for x in rows:
            if _ym(title_period(x["title"])[0]) == ym:
                yield x
        # آخرین صفحه، یا (اگر API بازه را نادیده گرفت) رسیدن به اطلاعیه‌های قبل از بازه ← تمام
        if page >= pages or not rows or all((x["published"] or "")[:10] < start for x in rows):
            out["complete"] = True
            break
        page += 1
    if closed and out["complete"]:
        db.mark_checked(con, "mrank_feed", key)     # فهرست کامل این ماه ذخیره شد؛ دفعه‌ی بعد بدون جستجو


def need_scan(con, ym, user=False, missing=None, wait_prev=None):
    """
    اول دیتابیس، بعد کدال (برای یک ماه):
      فهرست اطلاعیه‌های ماه کامل خوانده شده، همه‌ی گزارش‌هایش و گزارش ماه قبلِ نمادهایش در دیتابیس است
        ← هیچ درخواستی لازم نیست
      ماه‌های گذشته (بازه‌ی انتشار تمام‌شده) ← فقط با دکمه‌ی اپراتور
      ماه جاری انتشار ← خودکار: گزارش ماه قبلِ نمادهای فهرست (پایه‌ی رشد) هر وقت کم باشد؛ گزارش‌های تازه‌ی ماه
        حداکثر هر MARKET_RECHECK. اپراتور دریافت را متوقف کرده ← تا MARKET_RECHECK بدون درخواست خودکار
    missing / wait_prev: نتیجه‌ی missing_known / تعداد waiting_prev اگر از قبل حساب شده
    """
    key = month_key(ym)
    _, _, closed = publish_window(ym)
    missing = missing if missing is not None else missing_known(con, ym)
    wait_prev = wait_prev if wait_prev is not None else len(waiting_prev(con, ym))
    if db.checked_at(con, "mrank_feed", key) and not missing and not wait_prev:
        return False, "همه‌ی گزارش‌های این ماه و گزارش ماه قبلِ نمادهایش در دیتابیس سیستم است؛ درخواستی به کدال لازم نیست"
    if user:
        return True, "دریافت گزارش‌های این ماه از کدال"
    if closed or ym < default_month():
        return False, "ماه‌های قبل‌تر فقط با دکمه‌ی «دریافت گزارش‌ها از کدال» گرفته می‌شوند (بدون درخواست خودکار)"
    s = age(con, "mrank_stop", key)
    if s is not None and s < MARKET_RECHECK:
        return False, "دریافت خودکار این ماه را متوقف کردید؛ برای ادامه دکمه‌ی دریافت را بزنید"
    if wait_prev:
        return True, f"گزارش ماه قبلِ {wait_prev} نماد برای محاسبه‌ی رشد لازم است"
    a = age(con, "mrank", key)
    if a is not None and a < MARKET_RECHECK:
        return False, f"از دیتابیس؛ گزارش‌های این ماه {_ago(a)} از کدال بررسی شد"
    return True, "بررسی گزارش‌های تازه‌ی این ماه"


def _fetch_month(con, ym, stats, progress, say, stop, symbols=None):
    """
    گزارش‌های ماه ym که در دیتابیس نیستند (symbols: فقط این نمادها): اول اطلاعیه‌های شناخته‌شده در دیتابیس
    (بدون جستجو)، بعد خوراک کدال. True اگر تمام شد: همه‌ی نمادهای خواسته پیدا شدند یا فهرست ماه تا آخر خوانده شد
    """
    ok = _eligible(con)
    state = _Month(con, ym)
    best = {}                                     # هر نماد: جدیدترین نسخه (اصلاحیه) همان ماه

    def take(x):
        s = x["symbol"]
        if (ok is not None and s not in ok) or (symbols is not None and s not in symbols):
            return
        if s in best and best[s]["published"] >= x["published"]:
            return
        best[s] = x
        if state.need(x):
            collect.fetch_report(con, "monthly", x, stats, progress, with_symbol=True)

    found_all = lambda: symbols is not None and all(s in best for s in symbols)
    for x in stored_month_letters(con, ym):
        if stop():
            return False
        take(x)
    if found_all():
        return True
    feed = {}
    for x in month_letters(con, ym, say, until=stop, out=feed):
        if stop():
            return False
        take(x)
        if found_all():
            return True
    return feed["complete"]


def _fill_prev(con, ym, stats, progress, say, stop):
    """گزارش ماه قبلِ نمادهای ماه ym که ندارند (پایه‌ی «نسبت به ماه قبل»)؛ True اگر تمام شد"""
    wait = waiting_prev(con, ym)
    if not wait:
        return True
    done = _fetch_month(con, _shift(ym, -1), stats, progress, say, stop, symbols=set(wait))
    if done:
        db.mark_checked(con, "mrank_prev", month_key(ym))   # نمادهای پیدانشده ← «منتشر نشده» (prev_states)
    return done


def scan(con, progress=lambda **kw: None, budget=40, month=None, until=None):
    """
    گزارش‌های لازم برای رتبه‌بندی ماه month (پیش‌فرض ماه گذشته) که در دیتابیس نیستند، حداکثر budget گزارش:
      ۱) گزارش ماه قبلِ نمادهای فهرست (پایه‌ی «نسبت به ماه قبل» و «ماه مشابه سال قبل»)
      ۲) گزارش‌های تازه‌ی همین ماه
      ۳) گزارش ماه قبلِ نمادهایی که در مرحله‌ی ۲ اضافه شدند
    until(): توقف به درخواست اپراتور. خروجی: {fetched, skipped, complete}؛ complete=False یعنی بودجه پر شد
    (یا توقف) و شاید کار باقی مانده باشد
    """
    backfill(con)
    ym = parse_month(month) if isinstance(month, str) else (month or default_month())
    stats = {"fetched": 0, "skipped": 0}
    used = lambda: stats["fetched"] + stats["skipped"]
    stop = lambda: used() >= budget or bool(until and until())
    say = lambda **kw: progress(fetched=stats["fetched"], skipped=stats["skipped"], last=kw.get("last", ""))
    _fill_prev(con, ym, stats, progress, say, stop)
    if not stop():
        _fetch_month(con, ym, stats, progress, say, stop)
    if not stop():
        _fill_prev(con, ym, stats, progress, say, stop)
    con.commit()
    stats["complete"] = not stop()
    return stats
