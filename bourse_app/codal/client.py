"""درخواست HTTP به کدال با فاصله‌ی زمانی بین درخواست‌ها، تلاش دوباره و حافظه‌ی پاسخ‌ها"""
import http.cookiejar
import json
import os
import random
import sqlite3
import threading
import time
import zlib
import urllib.error
import urllib.parse
import urllib.request

CODAL = "https://codal.ir"
SEARCH = "https://search.codal.ir"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "fa-IR,fa;q=0.9",
}

# حداقل فاصله بین دو درخواست (ثانیه) — برای فشار نیاوردن به سرور کدال
# صفحه‌ی گزارش (سنگین، همان که کپچا را فعال می‌کند) با فاصله‌ی بیشتر.
# جستجو (search.codal.ir) با درخواست‌های پشت سر هم برای IP محدودیت 429 می‌گذارد ← ۲٫۵ ثانیه
DELAY = 2.5
DELAY_REPORT = 4.0
_last = 0.0

# کپچا: کاربر خودش کد را وارد می‌کند (برنامه کپچا را حل نمی‌کند). تا وارد کردن کد، صفحه‌ی گزارش تازه‌ای
# درخواست نمی‌شود (فقط دوباره کپچا می‌گیرد). اگر کاربر کد را وارد نکرد، بعد از این مدت (ثانیه) دوباره امتحان می‌شود.
CAPTCHA_EXPIRE = 1800
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
# زمان آخرین کپچا در فایل (تا برنامه‌ی وب و خط فرمان هر دو بدانند)
CAPTCHA_FILE = os.path.join(DATA_DIR, ".captcha_at")
# کوکی‌های نشست کدال در فایل: تأیید کپچا به نشست وابسته است و بین اجراها می‌ماند
COOKIE_FILE = os.path.join(DATA_DIR, "codal_cookies.txt")
_last_report_url = CODAL + "/"


def _wait(url=""):
    global _last
    base = DELAY_REPORT if "Decision.aspx" in url else DELAY
    gap = base + random.uniform(0, base / 2) - (time.time() - _last)
    if gap > 0:
        time.sleep(gap)
    _last = time.time()


def captcha_seen():
    """صفحه‌ی کپچا دیده شد ← منتظر کد کاربر (زمان کپچای در جریان عوض نمی‌شود)"""
    if captcha_pending():
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CAPTCHA_FILE, "w") as f:
        f.write(str(time.time()))


def captcha_since():
    """زمان کپچای فعلی (برای تشخیص «کپچای تازه» در صفحه‌ها)؛ 0 اگر کپچایی منتظر نیست"""
    try:
        with open(CAPTCHA_FILE) as f:
            at = float(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0.0
    return at if time.time() - at < CAPTCHA_EXPIRE else 0.0


def captcha_pending():
    """کدال کد امنیتی خواسته و هنوز وارد نشده؟"""
    return captcha_since() > 0


def _captcha_clear():
    try:
        os.remove(CAPTCHA_FILE)
    except OSError:
        pass


# کوکی‌های سرور (فایروال کدال و نشست ASP.NET) در فایل نگه داشته می‌شوند
_jar = http.cookiejar.LWPCookieJar(COOKIE_FILE)
try:
    _jar.load(ignore_discard=True, ignore_expires=True)
except (OSError, http.cookiejar.LoadError):
    pass
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_jar_lock = threading.Lock()


def _save_cookies():
    with _jar_lock:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            _jar.save(ignore_discard=True, ignore_expires=True)
        except OSError:
            pass


# ==================== کپچا: تصویر برای کاربر و ارسال کدی که کاربر وارد کرده ====================
def _captcha_post(method, body):
    req = urllib.request.Request(
        CODAL + "/ReportsCaptcha.aspx/" + method, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={**HEADERS, "Content-Type": "application/json; charset=UTF-8",
                 "Referer": _last_report_url, "Origin": CODAL})
    try:
        with _opener.open(req, timeout=40) as r:
            out = json.loads(r.read().decode("utf-8")).get("d")
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
        raise RuntimeError(f"ارتباط با کدال برای کد امنیتی برقرار نشد ({e})") from e
    _save_cookies()
    return out


def captcha_image():
    """تصویر کد امنیتی تازه (data URI) در نشست برنامه"""
    return _captcha_post("GetCaptchaImage", {})


def captcha_verify(code):
    """کدی که کاربر وارد کرده به کدال فرستاده می‌شود؛ True اگر درست بود (کار منتظر بلافاصله ادامه می‌دهد)"""
    global _solved
    ok = _captcha_post("VerifyCaptcha", {"code": (code or "").strip()}) is True
    if ok:
        _captcha_clear()
        with _solved_cv:
            _solved += 1
            _solved_cv.notify_all()
    return ok


# منتظر ماندن کار پس‌زمینه برای کد اپراتور (به جای تمام کردن کار): برنامه‌ی وب و خط فرمان CAPTCHA_WAIT را تنظیم می‌کنند
CAPTCHA_WAIT = None      # تابع بدون ورودی؛ True = کد درست وارد شد. None = فوراً Captcha (بدون انتظار)
CAPTCHA_ROUNDS = 6       # حداکثر کپچای پشت سر هم برای یک درخواست
_solved = 0
_solved_cv = threading.Condition()


def wait_captcha_solved(timeout, cancel=None):
    """
    تا وارد شدن کد درست (از هر جای برنامه) صبر می‌کند؛ True اگر در مهلت حل شد.
    cancel(): True ← انتظار تمام می‌شود (توقف کار به درخواست اپراتور؛ با wake() بیدار می‌شود)
    """
    with _solved_cv:
        start = _solved
        solved = lambda: _solved != start or not captcha_pending()
        _solved_cv.wait_for(lambda: solved() or bool(cancel and cancel()), timeout)
        return solved()


def wake():
    """بیدار کردن انتظارهای کد امنیتی تا شرط لغوشان را دوباره ببینند"""
    with _solved_cv:
        _solved_cv.notify_all()


# پیام‌های انتظار (429)؛ خط فرمان چاپ می‌کند، برنامه‌ی وب آن را به وضعیت کار پس‌زمینه می‌دهد
NOTIFY = lambda msg: print("  … " + msg, flush=True)


class RateLimited(RuntimeError):
    """کدال به خاطر تعداد زیاد درخواست (HTTP 429) موقتاً پاسخ نمی‌دهد"""


class Captcha(RateLimited):
    """
    کدال به جای گزارش صفحه‌ی «تأیید کاربر» (کپچا) داده است.
    برنامه کپچا را حل نمی‌کند؛ کار متوقف می‌شود تا کاربر کد را وارد کند (captcha_image / captcha_verify).
    """


CAPTCHA_MSG = "کدال کد امنیتی (کپچا) خواسته است؛ کد را وارد کنید تا دریافت ادامه پیدا کند"


class Throttled(RateLimited):
    """جستجوی کدال (search.codal.ir) برای این IP موقتاً HTTP 429 می‌دهد؛ کپچا ندارد و با کد امنیتی رفع نمی‌شود"""


# ==================== محدودیت جستجوی کدال (429 بر اساس IP) ====================
# به جای صبر بی‌صدا: زمان ادامه در THROTTLE نگه داشته می‌شود تا صفحه‌ها آن را نمایش دهند؛ در این مدت هیچ درخواست
# جستجویی فرستاده نمی‌شود (فرستادن، محدودیت را طولانی‌تر می‌کند). انتظار پله‌ای: ۱، ۲، ۴، ۸ و حداکثر ۱۰ دقیقه
THROTTLE = {"until": 0.0, "level": 0, "since": 0.0, "reason": ""}
THROTTLE_GIVE_UP = 30 * 60          # بعد از این مدت محدودیت پیوسته، کار با خطا تمام می‌شود
_throttle_lock = threading.Lock()


def throttle_status():
    left = THROTTLE["until"] - time.time()
    return {"active": left > 0, "seconds": max(0, int(left)), "until": THROTTLE["until"], "reason": THROTTLE["reason"]}


def _throttled(reason):
    """یک پاسخ 429 دیگر از جستجو: زمان ادامه‌ی بعدی را تعیین می‌کند (کار در _throttle_gate منتظر می‌ماند)"""
    with _throttle_lock:
        now = time.time()
        if not THROTTLE["since"]:
            THROTTLE["since"] = now
        if now - THROTTLE["since"] > THROTTLE_GIVE_UP:
            THROTTLE.update(until=0.0, level=0, since=0.0, reason="")
            raise RateLimited("جستجوی کدال بیش از ۳۰ دقیقه محدود ماند؛ کار متوقف شد. داده‌های گرفته‌شده محفوظ است؛ بعداً دوباره امتحان کنید.")
        wait = min(60 * 2 ** THROTTLE["level"], 600)
        THROTTLE.update(until=now + wait, level=THROTTLE["level"] + 1, reason=reason)


def _throttle_gate():
    """اگر جستجو محدود است، تا زمان ادامه صبر می‌کند (پیام با ساعت ادامه برای صفحه‌ها)"""
    left = THROTTLE["until"] - time.time()
    if left <= 0:
        return
    NOTIFY(f"{THROTTLE['reason'] or 'جستجوی کدال موقتاً محدود است'}؛ ادامه‌ی خودکار ساعت "
           f"{time.strftime('%H:%M:%S', time.localtime(THROTTLE['until']))}")
    while THROTTLE["until"] - time.time() > 0:
        time.sleep(min(1.0, THROTTLE["until"] - time.time() + 0.05))


def _throttle_ok():
    if THROTTLE["level"] or THROTTLE["since"]:
        with _throttle_lock:
            THROTTLE.update(until=0.0, level=0, since=0.0, reason="")


# ==================== حافظه‌ی پاسخ‌ها (data/cache.db) ====================
# هر پاسخ معتبر کدال فشرده ذخیره می‌شود تا دوباره درخواست نشود:
#   صفحه‌ی گزارش (Decision.aspx) هیچ‌وقت تغییر نمی‌کند ← برای همیشه (FOREVER)
#   جستجوی اطلاعیه‌ها و لیست شرکت‌ها تغییر می‌کنند ← با مهلت (ثانیه)
# کپچا و خطا ذخیره نمی‌شوند. اگر کدال محدودیت گذاشت و نسخه‌ی قدیمی‌تری در حافظه هست، همان برمی‌گردد.
FOREVER = float("inf")
CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache.db")
_cache_lock = threading.Lock()
_cache = None                                       # یک اتصال ماندگار (همه‌ی دسترسی‌ها زیر _cache_lock)
STATS = {"hits": 0, "network": 0, "stale": 0}       # آمار همین اجرا


def _cache_con():
    global _cache
    if _cache is None:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        _cache = sqlite3.connect(CACHE_PATH, timeout=30, check_same_thread=False)
        _cache.execute("PRAGMA journal_mode = WAL")
        _cache.execute("PRAGMA synchronous = NORMAL")
        _cache.execute("CREATE TABLE IF NOT EXISTS http_cache (url TEXT PRIMARY KEY, body BLOB, "
                       "fetched_at REAL, kind TEXT, size INTEGER)")
        _cache.commit()
    return _cache


def _kind(url):
    return "report" if "Decision.aspx" in url else "companies" if "companies" in url else "search"


def cache_get(url, ttl):
    """(متن، کهنه است؟) یا (None, None)"""
    with _cache_lock:
        row = _cache_con().execute("SELECT body, fetched_at FROM http_cache WHERE url=?", (url,)).fetchone()
    if not row:
        return None, None
    stale = ttl is not None and ttl != FOREVER and time.time() - row[1] > ttl
    return zlib.decompress(row[0]).decode("utf-8"), stale


def cache_put(url, text):
    raw = text.encode("utf-8")
    blob = zlib.compress(raw, 6)
    with _cache_lock:
        con = _cache_con()
        con.execute("INSERT OR REPLACE INTO http_cache VALUES(?,?,?,?,?)", (url, blob, time.time(), _kind(url), len(raw)))
        con.commit()


def cache_stats():
    with _cache_lock:
        rows = _cache_con().execute(
            "SELECT kind, COUNT(*), SUM(LENGTH(body)), SUM(size) FROM http_cache GROUP BY kind").fetchall()
    return {k: {"count": n, "stored_bytes": s or 0, "raw_bytes": r or 0} for k, n, s, r in rows}


def cache_clear(kind=None):
    """پاک کردن حافظه (همه یا یک نوع: report / search / companies)"""
    with _cache_lock:
        con = _cache_con()
        n = con.execute("DELETE FROM http_cache" + (" WHERE kind=?" if kind else ""), (kind,) if kind else ()).rowcount
        con.commit()
        con.execute("VACUUM")
    return n


def cache_checkpoint():
    """ادغام فایل -wal حافظه در cache.db (قبل از کپی/پشتیبان‌گیری)"""
    with _cache_lock:
        _cache_con().execute("PRAGMA wal_checkpoint(TRUNCATE)")


def looks_captcha(text):
    """صفحه‌ی «تأیید کاربر» کدال (به جای گزارش یا پاسخ جستجو)"""
    t = text or ""
    return "ReportsCaptcha.aspx" in t or 'id="captchaImage"' in t or ("captcha" in t.lower() and "var datasource" not in t
                                                                       and not t.lstrip().startswith(("{", "[")))


def await_captcha(reason=None):
    """
    کدال کد امنیتی خواسته: بدون وقفه‌ی زمانی، منتظر کد اپراتور می‌ماند (CAPTCHA_WAIT) و بعد همان درخواست
    از همان‌جا ادامه پیدا می‌کند. اگر منتظرماندن تعریف نشده یا کد در مهلت وارد نشد ← Captcha
    """
    captcha_seen()
    NOTIFY(reason or CAPTCHA_MSG)
    if CAPTCHA_WAIT is not None and CAPTCHA_WAIT():
        return
    raise Captcha(reason or CAPTCHA_MSG)


def get_text(url, params=None, tries=4, timeout=40, ttl=None, valid=None):
    """
    دریافت متن صفحه؛ در خطای شبکه یا 5xx با فاصله‌ی بیشتر دوباره تلاش می‌کند.
    کپچا (صفحه‌ی «تأیید کاربر») یا محدودیت 429/403 ← بدون صبر زمانی، پنجره‌ی کد امنیتی برای اپراتور
    (await_captcha) و بعد از کد درست همان درخواست دوباره.
    ttl: مهلت حافظه (ثانیه؛ FOREVER = همیشه؛ None = بدون حافظه)
    valid: تابعی که پاسخ را قبل از ذخیره تأیید می‌کند (مثلاً «کپچا نیست»)
    """
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    stale_text = None
    if ttl is not None:
        text, stale = cache_get(url, ttl)
        if text is not None and not stale:
            STATS["hits"] += 1
            return text
        stale_text = text
    is_search = url.startswith(SEARCH)
    rounds = 0
    while rounds < CAPTCHA_ROUNDS:
        if "Decision.aspx" in url:
            if captcha_pending():           # کد هنوز وارد نشده: درخواست تازه فقط کپچای تازه می‌گیرد
                rounds += 1
                await_captcha()
            global _last_report_url
            _last_report_url = url
        if is_search:
            _throttle_gate()                # جستجو محدود است ← تا زمان ادامه هیچ درخواست جستجویی نمی‌رود
        try:
            text = _fetch(url, tries, timeout)
        except Throttled as e:
            if stale_text is not None:      # نسخه‌ی حافظه هست؛ لازم نیست منتظر بمانیم
                STATS["stale"] += 1
                return stale_text
            _throttled(str(e))
            continue
        except Captcha as e:
            if stale_text is not None:      # جستجو در حافظه هست؛ نیازی به کپچا نیست
                STATS["stale"] += 1
                return stale_text
            rounds += 1
            await_captcha(str(e))
            continue
        except RuntimeError:
            if stale_text is not None:      # کدال در دسترس نیست ← نسخه‌ی قدیمی‌تر حافظه
                STATS["stale"] += 1
                NOTIFY("پاسخ از حافظه (قدیمی‌تر) استفاده شد؛ کدال فعلاً پاسخ نمی‌دهد")
                return stale_text
            raise
        STATS["network"] += 1
        if is_search:
            _throttle_ok()
        if looks_captcha(text):
            rounds += 1
            await_captcha()
            continue
        if ttl is not None and (valid is None or valid(text)):
            cache_put(url, text)
        return text
    raise Captcha("کدال پشت سر هم کد امنیتی خواست؛ چند دقیقه بعد دوباره امتحان کنید")


def _fetch(url, tries, timeout):
    err = None
    for i in range(tries):
        _wait(url)
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with _opener.open(req, timeout=timeout) as r:
                text = r.read().decode("utf-8", errors="replace")
            _save_cookies()
            return text
        except urllib.error.HTTPError as e:
            err = e
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            _save_cookies()
            # صفحه‌ی کپچا با کد خطا ← کد امنیتی از اپراتور
            if looks_captcha(body):
                raise Captcha(CAPTCHA_MSG)
            if e.code in (403, 429):
                # جستجوی کدال (search.codal.ir) محدودیت بر اساس IP دارد و کپچا ندارد ← انتظار آشکار با زمان ادامه
                if url.startswith(SEARCH):
                    raise Throttled(f"جستجوی کدال موقتاً محدود است (HTTP {e.code})")
                # صفحه‌ی گزارش ← کد امنیتی از اپراتور (به جای صبر ۳۰/۶۰/۱۲۰ ثانیه‌ای)
                raise Captcha(f"کدال درخواست گزارش‌ها را محدود کرده (HTTP {e.code})؛ کد امنیتی را وارد کنید تا دریافت ادامه پیدا کند")
            if e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            err = e
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"دریافت ناموفق: {url}\n{err}")


def _is_json(text):
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


def get_json(url, params=None, ttl=None):
    # صفحه‌ی کپچا به جای JSON در get_text شناخته و بعد از کد اپراتور دوباره درخواست می‌شود
    text = get_text(url, params, ttl=ttl, valid=_is_json)
    try:
        return json.loads(text)
    except ValueError:
        raise RuntimeError("پاسخ جستجوی کدال قابل خواندن نبود (احتمالاً محدودیت موقت کدال)")


def absolute(url):
    """آدرس نسبی گزارش (/Reports/...) را کامل می‌کند"""
    if url.startswith("http"):
        return url
    return CODAL + ("" if url.startswith("/") else "/") + url
