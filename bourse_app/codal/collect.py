"""
جمع‌آوری گزارش‌های یک نماد برای سال مالی جاری و سال قبل (در پس‌زمینه‌ی app.py اجرا می‌شود)
- monthly:   گزارش فعالیت ماهانه (برای صفحه‌ی «عملکرد ماهانه»)
- financial: صورت‌های مالی میان‌دوره‌ای و سالانه، صورت سود و زیان غیرتلفیقی (برای «برآورد سود»)

- اطلاعیه‌ها جدیدترین اول خوانده می‌شوند
- اطلاعیه‌ای که قبلاً خوانده یا رد شده، یا نسخه‌ی جدیدترِ همان دوره را داریم، دانلود نمی‌شود
- وقتی تاریخ دوره (از عنوان اطلاعیه) به قبل از شروع سال مالی قبل برسد، کار تمام است
fetch_report: دانلود و ذخیره‌ی یک گزارش — مشترک همه‌ی بخش‌ها (این‌جا، screener و mrank)
"""
from . import db, financial, monthly, search
from .report import UnsupportedReport
from .text import jdate, title_period

KINDS = {
    "monthly": {
        "letter_type": search.LETTER_MONTHLY, "table": "monthly_reports", "extra": "",
        "fetch": monthly.fetch, "save": db.save_monthly,
    },
    "financial": {
        "letter_type": search.LETTER_FINANCIAL, "table": "fin_reports", "extra": " AND consolidated=0",
        "fetch": lambda url: financial.fetch(url, False), "save": db.save_financial,
    },
}


def fetch_report(con, kind, x, stats, progress=lambda **kw: None, with_symbol=False):
    """
    یک گزارش: صفحه‌ی گزارش اول از حافظه‌ی پاسخ‌ها (cache.db)، بعد کدال؛ نسخه‌ی قبلی همان اطلاعیه فقط بعد از
    دریافت موفق جایگزین می‌شود (کپچا وسط کار چیزی را پاک نمی‌کند). قالب پشتیبانی‌نشده ← skipped (دوباره خوانده نمی‌شود).
    stats: {"fetched", "skipped"} به‌روز می‌شود؛ خروجی: گزارش یا None
    """
    k = KINDS[kind]
    label = f"{x['symbol']} " if with_symbol else ""
    try:
        rep = k["fetch"](x["url"])
    except UnsupportedReport as e:
        db.save_skip(con, x, kind, e)
        stats["skipped"] += 1
        stats["last_error"] = str(e)
        progress(fetched=stats["fetched"], skipped=stats["skipped"], last=label + (title_period(x["title"])[0] or ""))
        return None
    con.execute("DELETE FROM skipped WHERE tracing_no=? AND kind=?", (x["tracing_no"], kind))
    k["save"](con, x, rep)
    stats["fetched"] += 1
    progress(fetched=stats["fetched"], skipped=stats["skipped"], last=label + rep["period_end"])
    return rep


def _cutoff(con, symbol, table, years):
    """پایان سال مالیِ years سال قبل از جدیدترین سال مالی ذخیره‌شده (دوره‌های قبل از آن لازم نیست)"""
    r = con.execute(f"SELECT year_end FROM {table} WHERE symbol=? ORDER BY period_end DESC LIMIT 1",
                    (symbol,)).fetchone()
    if not r:
        return None
    y, m, d = jdate(r["year_end"])
    return "%04d/%02d/%02d" % (y - years, m, d)


def collect(con, symbol, kind, progress=lambda **kw: None, years=2, max_reports=None, max_pages=None):
    """
    years: چند سال مالی (۲ = سال جاری و قبل؛ برای آموزش مدل‌های پیش‌بینی ۵)
    خروجی: تعداد گزارش‌های تازه‌ی ذخیره‌شده.
    progress(fetched=, skipped=, last=) بعد از هر گزارش صدا زده می‌شود.
    """
    k = KINDS[kind]
    max_reports = max_reports or 20 * years
    max_pages = max_pages or 3 * years
    st = {"fetched": 0, "skipped": 0}
    old_run = 0
    for x in search.iter_letters(symbol, k["letter_type"], max_pages=max_pages):
        db.save_letter(con, x)
        period = title_period(x["title"])[0]
        cutoff = _cutoff(con, symbol, k["table"], years)       # با گزارش سال مالی تازه جلو می‌رود
        # اطلاعیه‌ها به ترتیب انتشارند: اصلاحیه‌ی یک دوره‌ی قدیمی ممکن است وسط اطلاعیه‌های تازه بیاید،
        # پس فقط بعد از چند اطلاعیه‌ی قدیمیِ پشت سر هم متوقف می‌شویم
        if period and cutoff and period <= cutoff:
            old_run += 1
            if old_run >= 12:
                break
            continue
        old_run = 0
        if not _needs(con, k, kind, symbol, x, period):
            continue
        if st["fetched"] + st["skipped"] >= max_reports:
            break
        _fetch_one(con, kind, x, st, progress)
    con.commit()
    return st["fetched"]


def _needs(con, k, kind, symbol, x, period):
    """این اطلاعیه دانلود لازم دارد؟ (نه قبلاً خوانده/رد شده، نه نسخه‌ی جدیدترِ همان دوره موجود)"""
    if db.is_done(con, x["tracing_no"], kind):
        return False
    return not (period and con.execute(
        f"SELECT 1 FROM {k['table']} WHERE symbol=? AND period_end=? AND published>=?{k['extra']}",
        (symbol, period, x["published"])).fetchone())


def _fetch_one(con, kind, x, st, progress):
    rep = fetch_report(con, kind, x, st, progress)
    # سه گزارش اول هم رد شد ← قالب این شرکت (بانک، بیمه، …) پشتیبانی نمی‌شود
    if rep is None and st["skipped"] >= 3 and st["fetched"] == 0:
        raise UnsupportedReport(st.get("last_error", ""))
    return rep


# ==================== عملکرد ماهانه: سال قبل کامل + سال جاری تا آخرین گزارش ====================
def _ym(s):
    d = jdate(s or "")
    return (d[0], d[1]) if d else None


def fiscal_months(year_end, fy):
    """(سال، ماه) پایان دوره‌ی ۱۲ ماهِ سال مالی fy (فقط ماهِ year_end مهم است: ماه پایان سال مالی)"""
    ye_m = jdate(year_end)[1]
    out = []
    for i in range(1, 13):
        t = (fy - 1) * 12 + (ye_m - 1) + i          # ماه iام بعد از پایان سال مالی قبل
        out.append((t // 12, t % 12 + 1))
    return out


def monthly_coverage(con, symbol):
    """
    ماه‌های لازم برای صفحه‌ی عملکرد ماهانه و ماه‌های موجود:
    همه‌ی ۱۲ ماه سال مالی قبل + سال جاری از ابتدا تا آخرین گزارش منتشرشده
    """
    last = con.execute("SELECT * FROM monthly_reports WHERE symbol=? ORDER BY period_end DESC LIMIT 1",
                       (symbol,)).fetchone()
    if not last:
        return None
    fy, ye = last["fiscal_year"], last["year_end"]
    prev = fiscal_months(ye, fy - 1)
    cur = fiscal_months(ye, fy)[:last["fiscal_month"]]
    have = {_ym(r["period_end"]) for r in con.execute("SELECT period_end FROM monthly_reports WHERE symbol=?", (symbol,))}
    need = prev + cur
    return {"fy": fy, "need": need, "missing": [m for m in need if m not in have],
            "prev_have": sum(1 for m in prev if m in have), "cur_have": sum(1 for m in cur if m in have),
            "cur_upto": last["fiscal_month"]}


def collect_monthly(con, symbol, progress=lambda **kw: None, max_pages=8, max_reports=40):
    """
    گزارش‌های ماهانه تا کامل شدن: سال مالی قبل (۱۲ ماه) و سال جاری تا آخرین گزارش.
    اطلاعیه‌ها جدیدترین اول؛ فقط ماه‌های لازمی که نداریم دانلود می‌شوند (اصلاحیه‌ی جدیدتر جایگزین می‌شود).
    وقتی همه‌ی ماه‌های لازم موجود شد، جستجو تمام می‌شود.
    (سابقه‌ی چندساله برای آموزش مدل‌ها با collect(..., years=5))
    """
    k = KINDS["monthly"]
    st = {"fetched": 0, "skipped": 0}
    cov = monthly_coverage(con, symbol)
    for x in search.iter_letters(symbol, k["letter_type"], max_pages=max_pages):
        db.save_letter(con, x)
        period = title_period(x["title"])[0]
        ym = _ym(period)
        if cov is None:                              # هنوز هیچ گزارشی نداریم: جدیدترین را بگیر تا سال مالی معلوم شود
            if _needs(con, k, "monthly", symbol, x, period):
                _fetch_one(con, "monthly", x, st, progress)
                cov = monthly_coverage(con, symbol)
            continue
        # ماه‌های سال جاری که بعد از آخرین گزارش ذخیره‌شده منتشر شده‌اند هم لازم‌اند
        need = set(cov["need"])
        if ym and ym > max(need):
            need.add(ym)
        if ym in need and _needs(con, k, "monthly", symbol, x, period):
            if st["fetched"] + st["skipped"] >= max_reports:
                break
            if _fetch_one(con, "monthly", x, st, progress):
                cov = monthly_coverage(con, symbol)  # فقط وقتی گزارش تازه‌ای آمد دوباره حساب می‌شود
            continue
        if not cov["missing"] and ym and ym < min(need):
            break                                    # همه‌ی ماه‌های لازم موجود است
    con.commit()
    return st["fetched"]
