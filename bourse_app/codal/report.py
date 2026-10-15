"""خواندن صفحه‌ی گزارش کدال (Decision.aspx) و جدول‌های داخل آن"""
import json
import re

from . import client
from .text import key, norm, jdate


class UnsupportedReport(Exception):
    """گزارش قالب جدید (datasource) ندارد یا جدول مورد نظر در آن نیست"""


def fetch_datasource(url, sheet_id=None):
    """
    صفحه‌ی گزارش را می‌گیرد و شیء «var datasource» را برمی‌گرداند.
    گزارش‌های خیلی قدیمی (قبل از قالب جدید کدال) این شیء را ندارند.
    """
    if sheet_id is not None:
        url = re.sub(r"[&?]SheetId=\d+", "", url) + f"&SheetId={sheet_id}"
    # گزارش منتشرشده تغییر نمی‌کند (اصلاحیه اطلاعیه‌ی جدا دارد) ← برای همیشه در حافظه؛ کپچا ذخیره نمی‌شود.
    # صفحه‌ی «تأیید کاربر» در client.get_text شناخته می‌شود: کار منتظر کد اپراتور می‌ماند و همین گزارش دوباره خوانده می‌شود
    for _ in range(client.CAPTCHA_ROUNDS):
        html = client.get_text(url, ttl=client.FOREVER, valid=lambda t: "var datasource" in t)
        m = re.search(r"var datasource\s*=\s*(\{.*?\});\s*\n", html, re.S)
        if m:
            return json.loads(m.group(1))
        if "captcha" not in html.lower():
            raise UnsupportedReport("گزارش قالب جدید کدال (datasource) را ندارد")
        client.await_captcha()          # کپچای ناشناخته‌تر: گزارش رد نمی‌شود؛ بعد از کد دوباره
    raise client.Captcha(client.CAPTCHA_MSG)


def find_table(ds, alias=None, title_has=None, title_not=None):
    """جدول را با aliasName یا بخشی از عنوان فارسی پیدا می‌کند"""
    for sh in ds.get("sheets") or []:
        for t in sh.get("tables") or []:
            if alias and (t.get("aliasName") or "").lower() == alias.lower():
                return t
    if title_has:
        for sh in ds.get("sheets") or []:
            for t in sh.get("tables") or []:
                k = key(t.get("title_Fa"))
                if key(title_has) in k and not (title_not and key(title_not) in k):
                    return t
    return None


class Grid:
    """جدول datasource به شکل ردیف/ستون: rows[شماره ردیف][شماره ستون] = سلول"""

    def __init__(self, table):
        self.rows = {}
        for c in table.get("cells") or []:
            self.rows.setdefault(c["rowSequence"], {})[c["columnSequence"]] = c
        self.order = sorted(self.rows)

    def header_rows(self):
        return [r for r in self.order if any(c.get("cellGroupName") == "Header" for c in self.rows[r].values())]

    def body_rows(self):
        return [r for r in self.order if all(c.get("cellGroupName") != "Header" for c in self.rows[r].values())]

    def text(self, r, col):
        c = self.rows.get(r, {}).get(col)
        return norm(c["value"]) if c else ""

    def cell(self, r, col):
        return self.rows.get(r, {}).get(col)


def meta(ds):
    """اطلاعات کلی گزارش: دوره، سال مالی، تلفیقی/حسابرسی"""
    pe, ye = jdate(ds.get("periodEndToDate")), jdate(ds.get("yearEndToDate"))
    if not pe or not ye:
        raise UnsupportedReport("تاریخ دوره‌ی گزارش مشخص نیست")
    # شماره‌ی ماه در سال مالی (برای سال مالی منتهی به اسفند همان ماه شمسی است)
    fiscal_month = (pe[1] - ye[1] - 1) % 12 + 1
    return {
        "template": norm(ds.get("title_Fa")),
        "period_end": "%04d/%02d/%02d" % pe,
        "year_end": "%04d/%02d/%02d" % ye,
        "fiscal_year": ye[0],
        "fiscal_month": fiscal_month,
        "months": ds.get("period"),
        "consolidated": bool(ds.get("isConsolidated")),
        "audited": bool(ds.get("isAudited")),
    }
