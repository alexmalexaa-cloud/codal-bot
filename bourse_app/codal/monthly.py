"""
گزارش فعالیت ماهانه (ن-۳۰) — جدول «تولید و فروش»
ستون‌های «دوره یک ماهه» برای هر محصول خوانده می‌شود؛ مبالغ به میلیون ریال (همان واحد کدال).
از ستون‌های تجمعی فقط جمع مبلغ فروش (برای رتبه‌بندی تغییر درآمد بدون گزارش‌های دیگر):
  cum       از ابتدای سال مالی تا پایان همین ماه
  cum_prev  از ابتدای سال مالی تا پایان ماه قبل (نسخه‌ی اصلاح‌شده)
  cum_ly    مدت مشابه سال قبل
"""
import re

from .report import Grid, UnsupportedReport, fetch_datasource, find_table, meta
from .text import jdate, key, latin_digits, to_num

SECTIONS = {
    "فروشداخلی": "domestic",
    "فروشصادراتی": "export",
    "درآمدارائهخدمات": "service",
    "برگشتازفروش": "returns",
}
# عنوان زیرستون‌ها ← نام فیلد
SUBCOLS = [("تعدادتولید", "made"), ("تعدادفروش", "sold"), ("نرخفروش", "price"), ("مبلغفروش", "amount")]


def _month_columns(g, period_end):
    """ستون‌های گروه «دوره یک ماهه» را پیدا می‌کند: {made: col, sold: col, ...}"""
    heads = g.header_rows()
    if len(heads) < 2:
        raise UnsupportedReport("سرستون‌های جدول تولید و فروش شناخته نشد")
    top, sub = heads[0], heads[1]
    group = None
    for col, c in sorted(g.rows[top].items()):
        k = key(c["value"])
        if "یکماهه" in k or "1ماهه" in k:
            group = (col, c.get("colSpan") or 1)
            break
    if not group:   # قالب‌های دیگر: گروهی که تاریخش همین دوره است و تجمعی نیست
        for col, c in sorted(g.rows[top].items()):
            if (c.get("periodEndToDate") or "") == period_end and "ابتدای" not in key(c["value"]):
                group = (col, c.get("colSpan") or 1)
                break
    if not group:
        raise UnsupportedReport("ستون «دوره یک ماهه» در جدول پیدا نشد")
    start, span = group
    cols, unit_note = {}, ""
    for col in range(start, start + span):
        k = key(g.text(sub, col))
        for needle, field in SUBCOLS:
            if needle in k:
                cols[field] = col
                if field == "amount":
                    unit_note = g.text(sub, col)
    if "amount" not in cols:
        raise UnsupportedReport("ستون «مبلغ فروش» پیدا نشد")
    if "میلیونریال" not in key(unit_note):
        raise UnsupportedReport(f"واحد مبلغ فروش ناشناخته است: {unit_note}")
    return cols


def _cum_columns(g, info):
    """ستون «مبلغ فروش» گروه‌های تجمعی: {cum|cum_prev|cum_ly: ستون} (گروهی که نیست، نمی‌آید)"""
    heads = g.header_rows()
    top, sub = heads[0], heads[1]
    y, m = jdate(info["period_end"])[:2]
    prev_ym = (y, m - 1) if m > 1 else (y - 1, 12)
    out = {}
    for col, c in sorted(g.rows[top].items()):
        if "ابتدای" not in key(c["value"]):
            continue
        d = jdate(c.get("periodEndToDate") or "")
        if not d:
            found = re.search(r"\d{4}/\d{1,2}/\d{1,2}", latin_digits(c["value"]))
            d = jdate(found.group(0)) if found else None
        if not d:
            continue
        amt = next((x for x in range(col, col + (c.get("colSpan") or 1)) if "مبلغفروش" in key(g.text(sub, x))), None)
        if amt is None:
            continue
        if d[:2] == (y, m):
            out["cum"] = amt
        elif d[:2] == (y - 1, m):
            out["cum_ly"] = amt
        elif d[:2] == prev_ym and info["fiscal_month"] > 1:
            out["cum_prev"] = amt          # دو گروه هست (اصلی و اصلاح‌شده)؛ دومی (اصلاح‌شده) می‌ماند
    return out


def parse(ds):
    """datasource گزارش ماهانه ← {meta..., items: [...], total, cum, cum_prev, cum_ly}"""
    t = find_table(ds, alias="ProductionAndSales", title_has="تولید و فروش")
    if not t:
        raise UnsupportedReport("جدول «تولید و فروش» در گزارش نیست (احتمالاً شرکت خدماتی/مالی است)")
    info = meta(ds)
    g = Grid(t)
    cols = _month_columns(g, ds.get("periodEndToDate") or "")
    unit_col = 2 if "واحد" in key(g.text(g.header_rows()[1], 2)) else None
    cum_cols = _cum_columns(g, info)

    items, section, total, discounts = [], "domestic", None, 0.0
    cums = dict.fromkeys(("cum", "cum_prev", "cum_ly"))
    for r in g.body_rows():
        name = g.text(r, 1)
        k = key(name).rstrip(":")
        if not k:
            continue
        if k in SECTIONS:
            section = SECTIONS[k]
            continue
        vals = {f: to_num(g.text(r, c)) for f, c in cols.items()}
        if k == "جمع":
            total = vals.get("amount")
            cums.update({f: to_num(g.text(r, c)) for f, c in cum_cols.items()})
            continue
        if k.startswith("جمع"):
            continue
        if k.startswith("تخفیف"):
            discounts = vals.get("amount") or 0.0
            continue
        if not any(vals.values()):
            continue
        items.append({
            "section": section,
            "name": name,
            "unit": g.text(r, unit_col) if unit_col else "",
            **{f: vals.get(f) for f in ("made", "sold", "price", "amount")},
        })

    if total is None:   # بعضی قالب‌ها ردیف «جمع» نهایی ندارند
        total = sum((i["amount"] or 0) * (-1 if i["section"] == "returns" else 1) for i in items) - abs(discounts)
    info.update(items=items, total=total, discounts=discounts, **cums)
    return info


def fetch(url):
    return parse(fetch_datasource(url))
