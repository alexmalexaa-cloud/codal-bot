"""ابزارهای متن فارسی: یکسان‌سازی حروف، ارقام و عددها"""
import re

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "أ": "ا", "إ": "ا"})


def latin_digits(s):
    """ارقام فارسی و عربی را لاتین می‌کند"""
    return str(s or "").translate(_FA_DIGITS)


def norm(s):
    """یکسان‌سازی برای نمایش: ی و ک فارسی، حذف نویسه‌های نامرئی، فاصله‌ی تکی"""
    s = latin_digits(s).translate(_LETTERS)
    s = re.sub(r"[‌‏‎ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def clean(s):
    """مثل norm ولی ارقام دست نمی‌خورند (برای نام مشتری و یادداشت‌های کاربر)"""
    s = str(s or "").translate(_LETTERS)
    s = re.sub(r"[‏‎ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def key(s):
    """یکسان‌سازی برای مقایسه: مثل norm و بدون هیچ فاصله‌ای"""
    return norm(s).replace(" ", "")


def to_num(s):
    """تبدیل مقدار سلول به عدد؛ خالی یا نامعتبر ← None. پرانتز یعنی منفی."""
    t = latin_digits(s).strip().replace(",", "").replace("٬", "").replace("٫", ".").replace("/", ".")
    if not t or t in ("-", "--"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def jdate(s):
    """«۱۴۰۵/۰۶/۳۱» ← (1405, 6, 31)؛ نامعتبر ← None"""
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", latin_digits(s))
    return tuple(int(x) for x in m.groups()) if m else None


def g2j(gy, gm, gd):
    """تبدیل تاریخ میلادی به شمسی ← (سال، ماه، روز)"""
    g_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
            + gd + g_days[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def jdatetime(s):
    """تاریخ‌زمان کدال به شکل قابل مرتب‌سازی «1405/07/07 18:55:34»"""
    return norm(s)


_PERIOD_RE = re.compile(r"منتهی به\s*(\d{4})/(\d{1,2})/(\d{1,2})")
_MONTHS_RE = re.compile(r"دوره\s*(\d+)\s*ماهه")


def title_period(title):
    """
    عنوان اطلاعیه ← (پایان دوره «1405/06/31»، تعداد ماه‌های دوره) یا (None, None)
    «… دوره ۶ ماهه منتهی به ۱۴۰۵/۰۶/۳۱» ← ("1405/06/31", 6)؛ «سال مالی منتهی به …» ← ۱۲
    """
    t = latin_digits(title)
    m = _PERIOD_RE.search(t)
    if not m:
        return None, None
    period = "%04d/%02d/%02d" % tuple(int(x) for x in m.groups())
    n = _MONTHS_RE.search(t)
    return period, int(n.group(1)) if n else (12 if "سال مالی" in t else None)
