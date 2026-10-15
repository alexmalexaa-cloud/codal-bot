"""
رتبه‌بندی نمادها بر اساس رشد سود خالص (آخرین صورت سود و زیان غیرتلفیقی هر نماد در کدال)

سه پارامتر:
  ۱. رشد سود خالص دوره نسبت به مدت مشابه سال قبل (گزارش ۳، ۶، ۹ یا ۱۲ ماهه)
  ۲. رشد سود خالص فصل آخر: نسبت به فصل مشابه سال قبل، و نسبت به فصل قبلِ همان سال
  ۳. درصد تحقق: سود خالص دوره ÷ سود خالص کل سال مالی قبل

داده‌ها:
  - هر گزارش خودش ستون «مدت مشابه سال قبل» و «کل سال قبل» را دارد ← پارامتر ۱ و ۳ با یک گزارش
  - فصل آخر = دوره‌ی جاری − دوره‌ی قبلی همان سال (مثلاً ۹ ماهه − ۶ ماهه)؛
    فصل مشابه سال قبل = ستون سال قبلِ همین دو گزارش؛ فصل قبل = دو دوره‌ی قبل‌تر
    (برای گزارش ۳ ماهه: فصل قبل = فصل چهارم سال قبل = کل سال قبل − ۹ ماهه‌ی سال قبل)

امتیاز: هر معیار به صدک (۰ تا ۱۰۰) میان نمادهای رتبه‌بندی‌شده تبدیل می‌شود؛
  پارامتر ۲ = میانگین دو معیار فصلی؛ پارامتر ۳ = تحقق نسبت به سهم زمان (تحقق ÷ ماه‌ها/۱۲)؛
  امتیاز = میانگین پارامترهای موجود (پارامتر ۱ الزامی است).
رشد با پایه‌ی منفی: (جاری − پایه) ÷ |پایه| (بهبود از زیان، رشد مثبت حساب می‌شود)
"""
import bisect

from . import collect, db, search
from .fresh import _shift, _ym, today_ym
from .text import title_period

STALE_MONTHS = 12   # گزارش قدیمی‌تر از این (نسبت به امروز) در رتبه‌بندی نمی‌آید


# ==================== کمک‌ها ====================
def _title_info(title):
    """عنوان اطلاعیه ← (ماه‌های دوره، (سال، ماه) پایان دوره)"""
    period, months = title_period(title)
    return months, _ym(period)


def eligible_symbols(con):
    """فقط شرکت‌ها (نوع ۱ در لیست کدال)، نه صندوق و کارگزاری و …"""
    return {r["symbol"] for r in con.execute("SELECT symbol FROM symbols WHERE type=1")}


_REPORTS_SQL = "SELECT * FROM fin_latest WHERE consolidated=0 AND months IN (3,6,9,12)"


def _reports(con, sym):
    """گزارش‌های غیرتلفیقی ذخیره‌شده‌ی نماد: (سال، ماه) پایان دوره ← آخرین نسخه"""
    return {_ym(r["period_end"]): r for r in con.execute(_REPORTS_SQL + " AND symbol=?", (sym,))}


def _all_reports(con):
    """همان _reports برای همه‌ی نمادها با یک پرس‌وجو (رتبه‌بندی کل بازار)"""
    out = {}
    for r in con.execute(_REPORTS_SQL):
        out.setdefault(r["symbol"], {})[_ym(r["period_end"])] = r
    return out


def _needed(latest):
    """دوره‌هایی که برای پارامتر ۲ لازم است: [(ماه‌ها، (سال، ماه) پایان)]"""
    n, ym = latest["months"], _ym(latest["period_end"])
    if n == 3:
        return [(9, _shift(ym, -6))]                       # ۹ ماهه‌ی سال قبل (برای فصل چهارم سال قبل)
    need = [(n - 3, _shift(ym, -3))]
    if n >= 9:
        need.append((n - 6, _shift(ym, -6)))
    return need


# ==================== محاسبه ====================
def growth(cur, base):
    if cur is None or base is None or base == 0:
        return None
    return (cur - base) / abs(base) * 100


def metrics(con, sym, reps=None):
    """معیارهای آخرین گزارش یک نماد؛ None اگر گزارشی نیست (reps: گزارش‌های نماد اگر از قبل خوانده شده)"""
    reps = _reports(con, sym) if reps is None else reps
    if not reps:
        return None
    L = max(reps.values(), key=lambda r: (r["period_end"], r["months"]))
    n, ym = L["months"], _ym(L["period_end"])
    net = L["net"]

    # فصل آخر و فصل مشابه سال قبل
    P = reps.get(_shift(ym, -3)) if n > 3 else None
    if n == 3:
        q, q_ly = net, L["net_ly"]
    elif P and P["months"] == n - 3:
        q = net - P["net"] if net is not None and P["net"] is not None else None
        q_ly = (L["net_ly"] - P["net_ly"]) if L["net_ly"] is not None and P["net_ly"] is not None else None
    else:
        q = q_ly = None

    # فصل قبل در همان سال (برای گزارش ۳ ماهه: فصل چهارم سال قبل)
    q_prev = None
    if n == 3:
        R = reps.get(_shift(ym, -6))
        if R and R["months"] == 9 and L["net_ly_full"] is not None and R["net"] is not None:
            q_prev = L["net_ly_full"] - R["net"]
    elif n == 6 and P and P["months"] == 3:
        q_prev = P["net"]
    elif n >= 9 and P and P["months"] == n - 3:
        P2 = reps.get(_shift(ym, -6))
        if P2 and P2["months"] == n - 6 and P["net"] is not None and P2["net"] is not None:
            q_prev = P["net"] - P2["net"]

    real = net / L["net_ly_full"] * 100 if net is not None and L["net_ly_full"] and L["net_ly_full"] > 0 else None
    return {
        "symbol": sym, "months": n, "period_end": L["period_end"], "fiscal_year": L["fiscal_year"],
        "published": L["published"], "audited": bool(L["audited"]), "tracing_no": L["tracing_no"],
        "net": net, "net_ly": L["net_ly"], "net_ly_full": L["net_ly_full"],
        "q": q, "q_ly": q_ly, "q_prev": q_prev,
        "g_cum": growth(net, L["net_ly"]),                 # پارامتر ۱
        "g_q_yoy": growth(q, q_ly),                        # پارامتر ۲-الف
        "g_q_qoq": growth(q, q_prev),                      # پارامتر ۲-ب
        "realization": real,                               # پارامتر ۳
        "pace": real / (n / 12) if real is not None else None,   # تحقق نسبت به سهم زمان
        "has_comparatives": L["net_ly"] is not None,
    }


def _percentiles(rows, field):
    """صدک هر مقدار میان مقادیر موجود (۰ تا ۱۰۰؛ برابرها صدک یکسان)"""
    vals = sorted(r[field] for r in rows if r[field] is not None)
    if not vals:
        return
    n = len(vals)
    for r in rows:
        v = r[field]
        if v is None:
            r["pct_" + field] = None
        elif n == 1:
            r["pct_" + field] = 100.0
        else:
            below = bisect.bisect_left(vals, v)                 # جستجوی دودویی (نه شمارش کل لیست برای هر ردیف)
            equal = bisect.bisect_right(vals, v) - below
            r["pct_" + field] = (below + (equal - 1) / 2) / (n - 1) * 100


def ranking(con):
    """همه‌ی نمادهای دارای گزارش، با امتیاز و رتبه (قدیمی‌ها رتبه ندارند)"""
    ok = eligible_symbols(con)
    stale_before = _shift(today_ym(), -STALE_MONTHS)
    rows = []
    for s, reps in _all_reports(con).items():           # همه‌ی گزارش‌ها با یک پرس‌وجو
        if s not in ok:
            continue
        m = metrics(con, s, reps)
        if not m:
            continue
        m["stale"] = _ym(m["period_end"]) < stale_before
        rows.append(m)

    ranked = [r for r in rows if not r["stale"] and r["g_cum"] is not None]
    ranked_ids = {id(r) for r in ranked}
    for f in ("g_cum", "g_q_yoy", "g_q_qoq", "pace"):
        _percentiles(ranked, f)
    for r in rows:
        if id(r) not in ranked_ids:
            r.update(score=None, rank=None, p1=None, p2=None, p3=None)
            continue
        r["p1"] = r["pct_g_cum"]
        q = [r[k] for k in ("pct_g_q_yoy", "pct_g_q_qoq") if r.get(k) is not None]
        r["p2"] = sum(q) / len(q) if q else None
        r["p3"] = r.get("pct_pace")
        parts = [p for p in (r["p1"], r["p2"], r["p3"]) if p is not None]
        r["score"] = sum(parts) / len(parts)
        r["params"] = len(parts)
    ranked.sort(key=lambda r: (-r["score"], -(r["g_cum"] or 0)))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, r["symbol"]))
    return rows


# ==================== جمع‌آوری از کدال ====================
def _fetch_letter(con, x, stats, progress):
    """دانلود و ذخیره‌ی یک صورت مالی غیرتلفیقی (collect.fetch_report: اول حافظه‌ی پاسخ‌ها، جایگزینی امن)"""
    collect.fetch_report(con, "financial", x, stats, progress, with_symbol=True)


def scan(con, progress=lambda **kw: None, budget=40, feed_pages=5):
    """
    مرحله‌ی ۱: اطلاعیه‌های صورت مالی کل بازار (جدیدترین اول) ← آخرین گزارش هر شرکت که نداریم
    مرحله‌ی ۲: برای شرکت‌های دارای گزارش، دوره‌های قبلیِ لازم برای پارامتر ۲
               (و گزارش‌های قدیمی ذخیره‌شده‌ای که هنوز ستون‌های مقایسه‌ای ندارند)
    budget: حداکثر تعداد گزارش برای دانلود در این اجرا (هر گزارش یک درخواست)
    """
    ok = eligible_symbols(con)
    stats = {"fetched": 0, "skipped": 0}
    used = lambda: stats["fetched"] + stats["skipped"]

    # ---- مرحله‌ی ۱: خوراک کل بازار
    seen = set()
    for page in range(1, feed_pages + 1):
        if used() >= budget:
            break
        letters, pages = search.letters("", search.LETTER_FINANCIAL, page)
        for x in letters:
            s = x["symbol"]
            if used() >= budget:
                break
            if s not in ok or s in seen:
                continue
            n, ym = _title_info(x["title"])
            if n not in (3, 6, 9, 12) or not ym:
                continue
            seen.add(s)                                   # فقط جدیدترین اطلاعیه‌ی هر شرکت
            db.save_letter(con, x)
            reps = _reports(con, s)
            have = reps.get(ym)
            if have and have["published"] >= x["published"] and have["net_ly"] is not None:
                continue
            if reps and ym < max(reps):                   # از آخرین گزارش ذخیره‌شده قدیمی‌تر است
                continue
            if db.is_done(con, x["tracing_no"], "financial") and not have:
                continue                                  # قبلاً رد شده (قالب پشتیبانی‌نشده)
            _fetch_letter(con, x, stats, progress)
        if page >= pages:
            break

    # ---- مرحله‌ی ۲: دوره‌های قبلی برای پارامتر ۲ و تکمیل ستون‌های مقایسه‌ای
    syms = [r["symbol"] for r in con.execute(
        "SELECT symbol, MAX(published) p FROM fin_reports WHERE consolidated=0 GROUP BY symbol ORDER BY p DESC")]
    for s in syms:
        if used() >= budget:
            break
        if s not in ok:
            continue
        reps = _reports(con, s)
        L = max(reps.values(), key=lambda r: (r["period_end"], r["months"]))
        targets = {ym: n for n, ym in _needed(L) if not (reps.get(ym) and reps[ym]["net_ly"] is not None)}
        refresh_latest = L["net_ly"] is None
        if not targets and not refresh_latest:
            continue
        a = db.checked_at(con, "screener_prev", s)
        if a and a >= db.now()[:10]:              # امروز یک بار جستجو شد (گزارش لازم پیدا نشد یا رد شد)
            continue
        # اول دیتابیس: اطلاعیه‌های ذخیره‌شده (از خوراک بازار یا جستجوهای قبلی)؛ اگر نبود، جستجوی نماد در کدال
        wanted = dict(targets)
        if refresh_latest:
            wanted[_ym(L["period_end"])] = L["months"]
        best = {ym: x for ym, n in wanted.items()
                if (x := search.stored_letter(con, s, search.LETTER_FINANCIAL, (*ym, 1), n))}
        if len(best) < len(wanted):
            progress(fetched=stats["fetched"], skipped=stats["skipped"], last=f"{s}: گزارش‌های قبلی")
            for x in search.iter_letters(s, search.LETTER_FINANCIAL, max_pages=2):
                n, ym = _title_info(x["title"])
                if wanted.get(ym) == n and (ym not in best or x["published"] > best[ym]["published"]):
                    best[ym] = x
        for x in best.values():
            if used() >= budget:
                break
            if con.execute("SELECT 1 FROM skipped WHERE tracing_no=? AND kind='financial'",
                           (x["tracing_no"],)).fetchone():
                continue                                  # قبلاً رد شده
            db.save_letter(con, x)
            _fetch_letter(con, x, stats, progress)
        if used() < budget:
            db.mark_checked(con, "screener_prev", s)
    con.commit()
    return stats
