"""
صورت‌های مالی (ن-۱۰) — صورت سود و زیان
مقادیر تجمعی از ابتدای سال مالی تا پایان دوره‌اند (۳، ۶، ۹ یا ۱۲ ماهه) و به میلیون ریال.
هزینه‌ها همان‌طور که در کدال آمده منفی ذخیره می‌شوند؛ EPS به ریال.
"""
from .report import Grid, UnsupportedReport, fetch_datasource, find_table, meta
from .text import jdate, key, to_num

# شماره‌ی برگه (SheetId) در صفحه‌ی گزارش. اطلاعیه‌های «تلفیقی» هر دو را دارند؛
# پرچم isConsolidated در datasource مال کل اطلاعیه است نه برگه، پس به آن تکیه نمی‌شود.
SHEET_INCOME = 1
SHEET_INCOME_CONSOLIDATED = 13


def _line_key(k):
    """عنوان ردیف (بدون فاصله) ← نام فیلد خلاصه؛ None اگر ردیف کلیدی نیست"""
    if k == "درآمدهایعملیاتی":
        return "rev"
    if k.startswith("بهایتمامشده"):
        return "cogs"
    if k.startswith("سود(زیان)ناخالص"):
        return "gross"
    if k.startswith("هزینههایفروش"):
        return "sga"
    if k in ("سایردرآمدها", "سایرهزینهها", "سایردرآمدهاوهزینههایعملیاتی") or k.startswith("هزینهکاهشارزش"):
        return "other_op"
    if k.startswith("سود(زیان)عملیاتی"):
        return "op_profit"
    if k.startswith("هزینههایمالی"):
        return "fin"
    if k.startswith("سایردرآمدهاوهزینههایغیرعملیاتی"):
        return "non_op"
    if "قبلازمالیات" in k:
        return "pretax"
    if k.startswith("سود(زیان)خالصعملیاتدرحالتداوم"):
        return "net_cont"
    if k == "سود(زیان)خالص":
        return "net"
    if k.startswith("سود(زیان)خالصهرسهم"):
        return "eps"
    if k == "سود(زیان)پایههرسهم":
        return "eps_basic"
    if k.startswith("سرمایه"):
        return "capital"
    return None


SUM_FIELDS = {"other_op", "non_op"}   # چند ردیف جمع زده می‌شوند


def _value_column(g, period_end):
    """ستون مقادیر دوره‌ی جاری (اولین سرستونی که تاریخش پایان همین دوره است)"""
    for r in g.header_rows():
        for col, c in sorted(g.rows[r].items()):
            if col > 1 and (c.get("periodEndToDate") or "") == period_end:
                return col
    raise UnsupportedReport("ستون دوره‌ی جاری در صورت سود و زیان پیدا نشد")


def parse(ds, consolidated=False):
    t = find_table(ds, alias=None if consolidated else "IncomeStatement",
                   title_has="سود و زیان", title_not="جامع")
    if not t or (consolidated and "تلفیقی" not in key(t.get("title_Fa"))):
        raise UnsupportedReport("جدول صورت سود و زیان " + ("تلفیقی " if consolidated else "") + "در گزارش نیست")
    info = meta(ds)
    info["consolidated"] = consolidated
    g = Grid(t)
    col = _value_column(g, ds.get("periodEndToDate") or "")

    lines, summary = [], {}
    for r in g.body_rows():
        label = g.text(r, 1)
        if not label:
            continue
        v = to_num(g.text(r, col))
        lines.append({"row_seq": r, "label": label, "value": v})
        f = _line_key(key(label))
        if not f or v is None:
            continue
        if f in SUM_FIELDS:
            summary[f] = summary.get(f, 0) + v
        elif f not in summary:
            summary[f] = v

    # مالیات = سود خالص عملیات در حال تداوم − سود قبل از مالیات (منفی، مثل بقیه‌ی هزینه‌ها)
    if "pretax" in summary and "net_cont" in summary:
        summary["tax"] = summary["net_cont"] - summary["pretax"]
    if "eps" not in summary and "eps_basic" in summary:
        summary["eps"] = summary["eps_basic"]
    if "rev" not in summary:
        raise UnsupportedReport("ردیف «درآمدهای عملیاتی» پیدا نشد (احتمالاً قالب بانک/بیمه/سرمایه‌گذاری)")
    info.update(lines=lines, **{k: summary.get(k) for k in
                ("rev", "cogs", "gross", "sga", "other_op", "op_profit", "fin",
                 "non_op", "pretax", "tax", "net", "eps", "capital")})
    info.update(_comparatives(g, col, info))
    return info


def _comparatives(g, cur_col, info):
    """
    ستون‌های مقایسه‌ای همان صورت سود و زیان (ارقام تجدید ارائه‌شده):
    - مدت مشابه سال قبل (rev_ly, net_ly) — برای گزارش ۱۲ ماهه همان سال قبل
    - کل سال مالی قبل (net_ly_full)
    ستون‌ها با تاریخ سرستون پیدا می‌شوند: سال − ۱ با همان ماه پایان دوره / پایان سال مالی.
    """
    py, pm, _ = jdate(info["period_end"])
    yy, ym, _ = jdate(info["year_end"])

    def col_for(y, m):
        """
        همه‌ی ستون‌های با این تاریخ؛ در گزارش سالانه دو ستون هم‌تاریخ هست
        («مدت مشابه» خالی/صفر و «کل سال قبل» پر) ← line() اولین مقدار غیرصفر را برمی‌دارد
        """
        cols, end = [], None
        for r in g.header_rows():
            for col, c in sorted(g.rows[r].items()):
                d = jdate(c.get("periodEndToDate") or "")
                if col > 1 and col != cur_col and d and d[0] == y and d[1] == m and col not in cols:
                    cols.append(col)
                    end = "%04d/%02d/%02d" % d
        return cols, end

    def line(cols, field):
        for r in g.body_rows():
            if _line_key(key(g.text(r, 1))) == field:
                vals = [to_num(g.text(r, c)) for c in cols]
                vals = [v for v in vals if v is not None]
                nonzero = [v for v in vals if v != 0]
                if nonzero or vals:
                    return (nonzero or vals)[0]
        return None

    ly_col, ly_end = col_for(py - 1, pm)
    full_col, full_end = col_for(yy - 1, ym)
    return {
        "rev_ly": line(ly_col, "rev"), "net_ly": line(ly_col, "net"), "ly_end": ly_end,
        "net_ly_full": line(full_col, "net"), "ly_full_end": full_end,
    }


def fetch(url, consolidated=False):
    sheet = SHEET_INCOME_CONSOLIDATED if consolidated else SHEET_INCOME
    return parse(fetch_datasource(url, sheet_id=sheet), consolidated)
