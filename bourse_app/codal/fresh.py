"""
اول دیتابیس، بعد کدال: آیا برای یک نوع داده‌ی نماد اصلاً لازم است به کدال رجوع شود؟

- داده‌ای در دیتابیس نیست ← بله
- دوره‌های لازم جاافتاده است ← بله (اگر کمتر از MISSING_RECHECK پیش بررسی شده و کاربر نخواسته، نه:
  شاید شرکت آن گزارش را منتشر نکرده)
- ممکن است گزارش جدیدتری منتشر شده باشد ← بله (اگر کمتر از RECHECK پیش بررسی شده و کاربر نخواسته، نه)
- وگرنه داده‌ی دیتابیس کامل و به‌روز است ← نه (هیچ درخواستی به کدال نمی‌رود)

«گزارش جدیدتر ممکن است»:
  ماهانه: آخرین ماه ذخیره‌شده قبل از ماه گذشته است (گزارش ماه گذشته در ماه جاری منتشر می‌شود)
  صورت مالی: آخرین دوره‌ی ذخیره‌شده قبل از آخرین پایان فصلِ گذشته‌ی سال مالی شرکت است
"""
from datetime import date, datetime

from . import collect, db
from .text import g2j, jdate

RECHECK = 3 * 3600            # همان مهلت حافظه‌ی صفحه‌ی اول جستجو
MISSING_RECHECK = 24 * 3600
MARKET_RECHECK = 6 * 3600     # خوراک کل بازار برای رتبه‌بندی‌ها (بررسی خودکار)


def _ym(s):
    d = jdate(s or "")
    return (d[0], d[1]) if d else None


def _shift(ym, months):
    t = ym[0] * 12 + (ym[1] - 1) + months
    return t // 12, t % 12 + 1


def today_ym():
    t = date.today()
    y, m, _ = g2j(t.year, t.month, t.day)
    return y, m


def age(con, kind, symbol=""):
    """ثانیه از آخرین رجوع به کدال؛ None = هرگز"""
    at = db.checked_at(con, kind, symbol)
    if not at:
        return None
    try:
        return (datetime.now() - datetime.fromisoformat(at)).total_seconds()
    except ValueError:
        return None


def _ago(sec):
    if sec < 3600:
        return f"{max(1, int(sec // 60))} دقیقه پیش"
    if sec < 86400:
        return f"{int(sec // 3600)} ساعت پیش"
    return f"{int(sec // 86400)} روز پیش"


def _decide(con, kind, symbol, missing, newer, user):
    """(لازم است؟، توضیح)"""
    a = age(con, kind, symbol)
    if missing:
        if user or a is None or a > MISSING_RECHECK:
            return True, missing
        return False, f"{missing}؛ کدال {_ago(a)} بررسی شد و پیدا نشد"
    if newer:
        if user or a is None or a > RECHECK:
            return True, newer
        return False, f"اطلاعات از دیتابیس؛ کدال {_ago(a)} بررسی شد"
    return False, "اطلاعات دیتابیس کامل و به‌روز است؛ گزارش جدیدتری هنوز موعد انتشار ندارد"


def monthly(con, symbol, user=False):
    cov = collect.monthly_coverage(con, symbol)
    if not cov:
        return True, "گزارش ماهانه‌ای از این نماد در دیتابیس نیست"
    missing = f"{len(cov['missing'])} ماه جاافتاده" if cov["missing"] else ""
    latest = cov["need"][-1]
    newer = "ممکن است گزارش ماه جدیدی منتشر شده باشد" if latest < _shift(today_ym(), -1) else ""
    return _decide(con, "monthly", symbol, missing, newer, user)


def financial(con, symbol, user=False):
    rows = con.execute("SELECT * FROM fin_latest WHERE symbol=? AND consolidated=0 AND months IN (3,6,9,12)",
                       (symbol,)).fetchall()
    if not rows:
        return True, "صورت مالی از این نماد در دیتابیس نیست"
    L = max(rows, key=lambda r: (r["period_end"], r["months"]))
    # دوره‌های قبلیِ همان سال مالی (برای جدا کردن فصل‌ها)
    have = {r["months"] for r in rows if r["fiscal_year"] == L["fiscal_year"]}
    gaps = [m for m in range(3, L["months"], 3) if m not in have]
    missing = f"گزارش {'، '.join(str(m) for m in gaps)} ماهه‌ی سال جاری نیست" if gaps else ""
    # آخرین پایان فصلِ گذشته (ماه‌های پایان فصل از ماه پایان سال مالی شرکت)
    ye_m = jdate(L["year_end"])[1]
    q_months = {(ye_m + 3 * k - 1) % 12 + 1 for k in range(1, 5)}
    t = _shift(today_ym(), -1)
    while t[1] not in q_months:
        t = _shift(t, -1)
    newer = "ممکن است صورت مالی دوره‌ی جدیدی منتشر شده باشد" if _ym(L["period_end"]) < t else ""
    return _decide(con, "financial", symbol, missing, newer, user)


def market(con, kind, user=False):
    """رتبه‌بندی‌های کل بازار (screener، mrank): بررسی خوراک کدال حداکثر هر MARKET_RECHECK"""
    a = age(con, kind)
    if user or a is None or a > MARKET_RECHECK:
        return True, "بررسی گزارش‌های تازه‌ی کدال"
    return False, f"از دیتابیس؛ گزارش‌های تازه‌ی کدال {_ago(a)} بررسی شد"


def status(con, kind, symbol=""):
    """برای نمایش: {checked: زمان آخرین رجوع به کدال، note: توضیح وضعیت دیتابیس}"""
    fn = {"monthly": monthly, "financial": financial}.get(kind)
    need, note = fn(con, symbol) if fn else market(con, kind)
    return {"checked": db.checked_at(con, kind, symbol), "need": need, "note": note}
