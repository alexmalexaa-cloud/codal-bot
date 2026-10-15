"""لیست نمادها و جستجوی اطلاعیه‌ها از API جستجوی کدال"""
import re
from datetime import date

from . import client
from .text import g2j, jdatetime, norm

# کد نوع اطلاعیه (LetterType) در کدال
LETTER_MONTHLY = 58      # ن-۳۰ گزارش فعالیت ماهانه
LETTER_FINANCIAL = 6     # ن-۱۰ اطلاعات و صورت‌های مالی

# مهلت حافظه‌ی پاسخ‌ها (ثانیه)
TTL_COMPANIES = 7 * 24 * 3600
TTL_SEARCH_FIRST = 3 * 3600
TTL_SEARCH_OLDER = 7 * 24 * 3600


def companies():
    """همه‌ی شرکت‌ها و نمادهای ثبت‌شده در کدال"""
    rows = client.get_json(client.SEARCH + "/api/search/v1/companies", ttl=TTL_COMPANIES)
    out = []
    for r in rows:
        sym = norm(r.get("sy"))
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "name": norm(r.get("n")),
            "isic": r.get("i") or "",
            "type": r.get("t"),
            "state": r.get("st"),
        })
    return out


def today_j():
    t = date.today()
    return "%04d/%02d/%02d" % g2j(t.year, t.month, t.day)


def letters(symbol, letter_type=-1, page=1, from_date=None, to_date=None):
    """
    یک صفحه (۲۰تایی) از اطلاعیه‌های یک نماد، جدیدترین اول.
    from_date / to_date: بازه‌ی تاریخ انتشار (شمسی «1405/07/01») — برای خواندن فقط اطلاعیه‌های یک ماه
    خروجی: (لیست اطلاعیه‌ها، تعداد کل صفحه‌ها)
    (فیلتر تلفیقی/غیرتلفیقی API عملاً کار نمی‌کند؛ این انتخاب در financial با برگه‌ی گزارش انجام می‌شود)
    """
    params = {
        "Symbol": symbol, "LetterType": letter_type, "PageNumber": page,
        "Audited": "true", "NotAudited": "true", "IsNotAudited": "false",
        "Mains": "true", "Childs": "false", "Publisher": "false",
        "Consolidatable": "true", "NotConsolidatable": "true",
        "Category": -1, "CompanyType": -1, "CompanyState": -1, "AuditorRef": -1,
        "Length": -1, "TracingNo": -1, "search": "true",
    }
    if not symbol:                      # بدون نماد = اطلاعیه‌های کل بازار
        del params["Symbol"]
    if from_date:
        params["FromDate"] = from_date
    if to_date:
        params["ToDate"] = to_date
    # صفحه‌ی اول (اطلاعیه‌های تازه) زود کهنه می‌شود؛ صفحه‌های بعدیِ یک نماد تقریباً ثابت‌اند.
    # خوراک کل بازار مدام جابه‌جا می‌شود ← همه‌ی صفحه‌هایش مهلت کوتاه دارند؛ مگر بازه‌ی تاریخِ تمام‌شده (ثابت)
    closed = bool(to_date) and to_date < today_j()
    data = client.get_json(client.SEARCH + "/api/search/v2/q", params,
                           ttl=TTL_SEARCH_OLDER if closed or (page > 1 and symbol) else TTL_SEARCH_FIRST)
    out = []
    for x in data.get("Letters") or []:
        url = x.get("Url") or ""
        m = re.search(r"[?&]let=(\d+)", url)
        title = norm(x.get("Title"))
        out.append({
            "tracing_no": x["TracingNo"],
            "symbol": norm(x.get("Symbol")),
            "company": norm(x.get("CompanyName")),
            "title": title,
            "letter_code": norm(x.get("LetterCode")),
            "letter_type": int(m.group(1)) if m else None,
            "sent": jdatetime(x.get("SentDateTime")),
            "published": jdatetime(x.get("PublishDateTime")),
            "url": client.absolute(url) if url else "",
            "excel_url": x.get("ExcelUrl") or "",
            "pdf_url": client.absolute(x["PdfUrl"]) if x.get("PdfUrl") else "",
            "attachment_url": client.absolute(x["AttachmentUrl"]) if x.get("AttachmentUrl") else "",
            "is_correction": "اصلاحیه" in title,
        })
    return out, int(data.get("Page") or 1)


def stored_letter(con, symbol, letter_type, period_end, months=None):
    """
    اول دیتابیس: اطلاعیه‌ای که قبلاً (در خوراک بازار یا جستجوی نماد) دیده شده و دوره‌اش period_end
    (و برای صورت مالی: دوره‌ی months ماهه) است؛ جدیدترین نسخه (اصلاحیه). None اگر نیست.
    """
    y, m, _ = period_end
    q = ("SELECT * FROM letters WHERE symbol=? AND letter_type=? AND period_end BETWEEN ? AND ?"
         + (" AND months=?" if months else "") + " ORDER BY published DESC LIMIT 1")
    args = [symbol, letter_type, "%04d/%02d/00" % (y, m), "%04d/%02d/99" % (y, m)] + ([months] if months else [])
    r = con.execute(q, args).fetchone()        # ستون period_end/months از عنوان، با شاخص (codal/db.py)
    return dict(r) if r else None


def iter_letters(symbol, letter_type=-1, max_pages=50):
    """همه‌ی اطلاعیه‌ها صفحه به صفحه (جدیدترین اول)"""
    page, pages = 1, 1
    while page <= min(pages, max_pages):
        rows, pages = letters(symbol, letter_type, page)
        yield from rows
        if not rows:
            break
        page += 1
