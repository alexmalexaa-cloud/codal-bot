#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
codal_monthly.py  (نسخه ۴)
==========================
پایش سریع «گزارش فعالیت ماهانه» نمادهای بورس از کدال و ساخت گزارش HTML/JS
(قابل ذخیره به‌صورت تصویر PNG) بر اساس سه گروه شاخص:

  ۱) شاخص‌های فروش
       رشد ماهانه       = فروش ماه جاری ÷ فروش ماه قبل − ۱
       رشد فصلی         = فروش فصل جاری سال مالی (تا ماه گزارش) ÷ همان ماه‌های سال قبل − ۱
       رشد تجمعی        = فروش از ابتدای سال مالی ÷ مدت مشابه سال قبل − ۱
       پوشش درآمد       = فروش از ابتدای سال مالی ÷ کل فروش سال مالی قبل
  ۲) ترکیب تولید و فروش محصولات
       تولید، فروش و تغییر موجودی کالای ساخته‌شده (تولید − فروش) — ماه جاری و تجمعی
  ۳) اسپرد
       اسپرد = نرخ فروش محصول − ضریب تبدیل × نرخ ماده‌ی اولیه
       ضریب تبدیل: خودکار (مصرف ماده ÷ تولید محصول) یا از فایل spread.json

سرعت:
  • دانلود موازی با محدودکننده‌ی نرخ مشترک
  • کش دائمی گزارش‌ها (هر گزارش فقط یک‌بار دانلود می‌شود)
  • حالت سریع (--fast، پیش‌فرض برای --all): فقط ۳ گزارش برای هر نماد کافی است

نیازمندی: فقط Python 3.9+ (بدون کتابخانه‌ی جانبی).
برای ساخت خودکار PNG از خط فرمان: Edge یا Chrome نصب‌شده (روی ویندوز Edge همیشه هست).

نمونه:
  python codal_monthly.py فولاد فملی شپنا        ← گزارش کامل چند نماد
  python codal_monthly.py                        ← نمادهای watchlist.txt
  python codal_monthly.py --all                  ← همه‌ی نمادهایی که در ۴۵ روز اخیر گزارش داده‌اند (حالت سریع)
  python codal_monthly.py فولاد --png            ← به‌علاوه‌ی فایل PNG
  python codal_monthly.py --check فولاد          ← عیب‌یابی
  python codal_monthly.py --demo --png           ← گزارش نمونه با داده‌ی ساختگی
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import http.cookiejar
import json
import logging
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
log = logging.getLogger("codal")

SEARCH_URL = "https://search.codal.ir/api/search/v2/q"
BASE_URL = "https://codal.ir"
LETTER_TYPE_MONTHLY = 58
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "application/json, text/plain, text/html, */*",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip",
    "Referer": "https://www.codal.ir/",
    "Origin": "https://www.codal.ir",
}
JALALI_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                 "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
UNITS = {"میلیون ریال": 1, "میلیارد ریال": 1e3, "میلیارد تومان": 1e4}
UNIT_KEYS = {"mrial": "میلیون ریال", "brial": "میلیارد ریال", "btoman": "میلیارد تومان"}


# ═══════════════════════════════════════════════════════════════════════════
# ۱. ابزارها
# ═══════════════════════════════════════════════════════════════════════════
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
DATE_RE = re.compile(r"(1[34]\d\d)\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})")


def norm(s) -> str:
    s = str(s if s is not None else "").translate(_DIGITS)
    s = s.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک").replace("ة", "ه")
    s = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", s)
    s = re.sub(r"[\u200c\xa0]", " ", s)
    s = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def to_num(v):
    s = norm(v).replace(",", "").replace("٬", "").replace("٫", ".").replace(" ", "")
    if not s or s in {"-", "–", "—", "."}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if s.startswith(("-", "−")) and len(s) > 1:
        neg, s = True, s[1:]
    try:
        x = float(s)
    except ValueError:
        return None
    return (-x if neg else x) if math.isfinite(x) else None


def parse_jdate(s):
    m = DATE_RE.search(norm(s))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def jstr(t) -> str:
    return f"{t[0]:04d}/{t[1]:02d}/{t[2]:02d}"


def g2j(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
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


def jtoday():
    d = date.today()
    return g2j(d.year, d.month, d.day)


def mindex(t):
    return t[0] * 12 + t[1]


def months_ago(n):
    y, m, _ = jtoday()
    m -= n
    while m < 1:
        m, y = m + 12, y - 1
    return jstr((y, m, 1))


def safe(s) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s)


def ratio(a, b):
    return (a / b - 1) if (a is not None and b) else None


# ═══════════════════════════════════════════════════════════════════════════
# ۲. شبکه (thread-safe با محدودکننده‌ی نرخ مشترک)
# ═══════════════════════════════════════════════════════════════════════════
class CodalBlocked(Exception):
    pass


class RateLimited(CodalBlocked):
    pass


RATE_MSG = ("Codal has temporarily rate-limited this IP (HTTP 429). Wait 15-30 minutes and try again; "
            "already-downloaded reports are still used from the cache.")


class Http:
    """محدودکننده‌ی نرخ جدا برای جست‌وجو (سخت‌گیرتر) و صفحه‌ی گزارش؛ با توقف کامل بعد از 429 پایدار."""

    def __init__(self, timeout=30, rate=3.0, search_interval=2.0):
        self.timeout = timeout
        self.interval = {"search": search_interval, "report": 1.0 / max(rate, 0.2)}
        self._next = {"search": 0.0, "report": 0.0}
        self.blocked = {"search": False, "report": False}
        self._lock = threading.Lock()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _slot(self, kind):
        with self._lock:
            now = time.monotonic()
            t = max(now, self._next[kind])
            self._next[kind] = t + self.interval[kind]
        if t > now:
            time.sleep(t - now)

    def _pause(self, kind, sec):
        with self._lock:
            self._next[kind] = max(self._next[kind], time.monotonic() + sec)

    def get(self, url, params=None, retries=3, kind="report") -> str:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        last = ""
        for attempt in range(retries + 1):
            if self.blocked[kind]:
                raise RateLimited(RATE_MSG)
            self._slot(kind)
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with self.opener.open(req, timeout=self.timeout) as r:
                    raw = r.read()
                    if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                        raw = gzip.decompress(raw)
                    return raw.decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code == 429:
                    if attempt >= retries:
                        self.blocked[kind] = True
                        raise RateLimited(RATE_MSG)
                    try:
                        ra = float(e.headers.get("Retry-After") or 0)
                    except ValueError:
                        ra = 0
                    pause = min(max(ra, 15 * 2 ** attempt), 120)
                    log.info("  ... Codal rate limit (429) on %s; pausing %d s", kind, pause)
                    self._pause(kind, pause)
                    continue
                if e.code in (403, 451):
                    raise CodalBlocked(f"{last}: access denied (non-Iranian IP / VPN / firewall)")
                if e.code >= 500:
                    time.sleep(1.5 * 2 ** attempt + random.random())
                    continue
                raise RuntimeError(f"{last}: {url}")
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                last = f"{type(e).__name__}: {getattr(e, 'reason', e)}"
                time.sleep(1.5 * 2 ** attempt + random.random())
        raise CodalBlocked(f"{last} (after {retries + 1} attempts)")


# ═══════════════════════════════════════════════════════════════════════════
# ۳. کدال: جست‌وجو و دریافت
# ═══════════════════════════════════════════════════════════════════════════
def _search_page(http, page, from_j, to_j, symbol=None):
    p = {"Audited": "true", "AuditorRef": "-1", "Category": "-1", "Childs": "true", "CompanyState": "-1",
         "CompanyType": "-1", "Consolidatable": "true", "IsNotAudited": "false", "Length": "-1",
         "LetterType": str(LETTER_TYPE_MONTHLY), "Mains": "true", "NotAudited": "true",
         "NotConsolidatable": "true", "PageNumber": str(page), "Publisher": "false", "TracingNo": "-1",
         "search": "true", "FromDate": from_j, "ToDate": to_j}
    if symbol:
        p["Symbol"] = symbol
    text = http.get(SEARCH_URL, p, kind="search")
    try:
        return json.loads(text)
    except ValueError:
        raise CodalBlocked("Codal search did not return JSON (firewall page or IP block). Response starts with: "
                           + re.sub(r"\s+", " ", text[:200]))


def letter_info(L):
    title = norm(L.get("Title"))
    if "ماهانه" not in title:
        return None
    m = re.search(r"منتهی به\s*(1[34]\d\d/\d{1,2}/\d{1,2})", title)
    pe = parse_jdate(m.group(1) if m else title)
    url = L.get("Url") or ""
    sm = re.search(r"LetterSerial=([^&]+)", url)
    if not pe or not sm:
        return None
    return {"serial": urllib.parse.unquote(sm.group(1)), "symbol": norm(L.get("Symbol")),
            "company": norm(L.get("CompanyName")), "title": title, "period_end": jstr(pe),
            "publish": norm(L.get("PublishDateTime") or L.get("SentDateTime")),
            "url": BASE_URL + url if url.startswith("/") else url}


def search_symbol(http, symbol, from_j, to_j):
    variants = [symbol]
    alt = symbol.replace("ی", "ي").replace("ک", "ك")
    if alt != symbol:
        variants.append(alt)
    for v in variants:
        out, page, pages = [], 1, 1
        while page <= pages:
            data = _search_page(http, page, from_j, to_j, v)
            if page == 1:
                pages = min(int(data.get("Page") or 1), 20)
            out += [x for x in map(letter_info, data.get("Letters") or []) if x]
            page += 1
        out = [x for x in out if x["symbol"] == symbol] or out
        if out:
            return out
    return []


def search_all(http, from_j, to_j, workers):
    """همه‌ی اطلاعیه‌های فعالیت ماهانه‌ی یک بازه (برای --all)."""
    first = _search_page(http, 1, from_j, to_j)
    pages = min(int(first.get("Page") or 1), 200)
    letters = [x for x in map(letter_info, first.get("Letters") or []) if x]
    log.info("- Full listing: %d pages", pages)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for data in ex.map(lambda p: _search_page(http, p, from_j, to_j), range(2, pages + 1)):
            letters += [x for x in map(letter_info, data.get("Letters") or []) if x]
    return letters


def extract_datasource(html):
    i = html.find("var datasource")
    if i < 0:
        return None
    j = html.find("{", i)
    try:
        return json.JSONDecoder().raw_decode(html, j)[0]
    except ValueError:
        return None


def fetch_report(http, url):
    html = http.get(url)
    ds = extract_datasource(html)
    if ds is None:
        return []
    out = [ds]
    m = re.search(r'<select[^>]*id="ddlTable"[^>]*>(.*?)</select>', html, re.S)
    if m:
        for attrs, v in re.findall(r'<option([^>]*)value="(\d+)"', m.group(1))[:6]:
            if "selected" in attrs:
                continue
            try:
                d2 = extract_datasource(http.get(url + f"&sheetId={v}"))
                if d2:
                    out.append(d2)
            except Exception as e:
                log.debug("sheet %s: %s", v, e)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# ۴. کش
# ═══════════════════════════════════════════════════════════════════════════
class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _dir(self, sym):
        d = self.root / safe(sym)
        (d / "raw").mkdir(parents=True, exist_ok=True)
        return d

    def letters(self, sym):
        p = self._dir(sym) / "letters.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                pass
        return {}

    def add_letters(self, sym, letters):
        with self._lock:
            cur = self.letters(sym)
            for L in letters:
                cur[L["serial"]] = L
            (self._dir(sym) / "letters.json").write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")

    def recently_searched(self, sym, hours):
        p = self._dir(sym) / "searched_at.txt"
        try:
            return hours > 0 and time.time() - float(p.read_text()) < hours * 3600
        except (OSError, ValueError):
            return False

    def mark_searched(self, sym):
        (self._dir(sym) / "searched_at.txt").write_text(str(time.time()))

    def _rpath(self, L):
        h = hashlib.md5(L["serial"].encode()).hexdigest()[:10]
        return self._dir(L["symbol"]) / "raw" / f"{L['period_end'].replace('/', '-')}__{h}.json.gz"

    def has_raw(self, L):
        return self._rpath(L).exists()

    def raw(self, L):
        p = self._rpath(L)
        return json.loads(gzip.decompress(p.read_bytes())) if p.exists() else None

    def save_raw(self, L, ds):
        self._rpath(L).write_bytes(gzip.compress(json.dumps(ds, ensure_ascii=False).encode()))


def latest_per_period(letters):
    best = {}
    for L in letters:
        k = L["period_end"]
        if k not in best or (L.get("publish") or "") >= (best[k].get("publish") or ""):
            best[k] = L
    return [best[k] for k in sorted(best)]


# ═══════════════════════════════════════════════════════════════════════════
# ۵. پارس جدول‌ها
# ═══════════════════════════════════════════════════════════════════════════
def build_grid(cells):
    G = {}
    for c in cells or []:
        r, k = c.get("rowSequence"), c.get("columnSequence")
        if r is None or k is None:
            m = re.match(r"([A-Z]+)(\d+)$", str(c.get("address") or ""))
            if not m:
                continue
            k = 0
            for ch in m.group(1):
                k = k * 26 + ord(ch) - 64
            r = int(m.group(2))
        try:
            span = max(1, int(c.get("colSpan") or 1))
        except (TypeError, ValueError):
            span = 1
        G[(int(r), int(k))] = {"v": norm(c.get("value")), "span": span, "grp": str(c.get("cellGroupName") or "")}
    return G


def iter_tables(ds_list):
    for ds in ds_list or []:
        for sh in ds.get("sheets") or []:
            for t in sh.get("tables") or []:
                yield norm(t.get("title_Fa") or t.get("titleFa")), build_grid(t.get("cells"))


def period_of(h, pe):
    if any(w in h for w in ("برآورد", "پیش بینی", "توضیح")):
        return None
    if "اصلاح شده" in h:
        return "prev_ytd"
    if "اصلاحات" in h:
        return "adj"
    if re.search(r"(یک|1)\s*ماهه|ماه جاری", h):
        return "month"
    d = parse_jdate(h)
    if d and pe:
        diff = mindex(d) - mindex(pe)
        if "ابتدا" not in h and "سال مالی" in h and "منتهی" in h and diff < 0:
            return "fy_ly"
        return {0: "ytd", -12: "ytd_ly", -1: "prev_ytd_raw"}.get(diff)
    if "سال مالی قبل" in h:
        return "fy_ly"
    if "سال قبل" in h or "مدت مشابه" in h:
        return "ytd_ly"
    if "ابتدای سال" in h:
        return "ytd"
    return None


def metric_prod(last, h):
    for s in (last, h):
        if "مبلغ" in s or "درآمد" in s:
            return "amount"
        if "نرخ" in s:
            return "rate"
        if "تولید" in s:
            return "prod"
        if "فروش" in s:
            return "sale"
    return None


def metric_mat(last, h):
    if "موجودی" in last:
        return None
    pre = "use_" if ("مصرف" in last or ("مصرف" in h and "خرید" not in last)) else "buy_"
    for s in (last, h):
        if "مبلغ" in s:
            return pre + "amount"
        if "نرخ" in s:
            return pre + "rate"
        if "مقدار" in s or "تعداد" in s:
            return pre + "qty"
    return None


def analyse_table(G, pe, metric):
    if not G:
        return None
    rows = sorted({r for r, _ in G})
    cols = sorted({k for _, k in G})
    hdr = {r for (r, _), c in G.items() if c["grp"].lower() == "header"}
    if hdr:
        first = next((r for r in rows if r not in hdr), None)
    else:
        first = next((r for r in rows if sum(to_num(G.get((r, k), {}).get("v")) is not None for k in cols) >= 2), None)
    if first is None:
        return None
    wide = max(3, int(len(cols) * 0.6))
    heads = defaultdict(list)
    for r in rows:
        if r >= first:
            break
        for k in cols:
            c = G.get((r, k))
            if c and c["v"] and c["span"] < wide:
                for j in range(k, k + c["span"]):
                    if not heads[j] or heads[j][-1] != c["v"]:
                        heads[j].append(c["v"])
    data = [r for r in rows if r >= first]
    text = defaultdict(int)
    for r in data:
        for k in cols:
            v = G.get((r, k), {}).get("v")
            if v and to_num(v) is None and not parse_jdate(v):
                text[k] += 1
    unit_cols = {k for k in cols if heads.get(k) and "واحد" in heads[k][-1]}
    name_col = min((k for k in cols if k not in unit_cols), key=lambda k: (-text[k], k))
    colmap = {}
    for k in cols:
        if k == name_col:
            continue
        hs = heads.get(k, [])
        h, last = " | ".join(hs), (hs[-1] if hs else "")
        if k in unit_cols:
            colmap[k] = (None, "unit")
            continue
        met = metric(last, h)
        per = period_of(h, pe) if met else None
        if per:
            colmap[k] = (per, met)
    out = []
    for r in data:
        name = G.get((r, name_col), {}).get("v", "")
        unit, vals = "", {}
        for k, (per, met) in colmap.items():
            c = G.get((r, k))
            if not c:
                continue
            if met == "unit":
                unit = unit or c["v"]
                continue
            x = to_num(c["v"])
            if x is not None:
                vals.setdefault(per, {})[met] = x
        out.append((name, unit, vals))
    return {"colmap": colmap, "heads": dict(heads), "rows": out}


def _acc(dst, vals, sign=1.0):
    for per, mets in vals.items():
        for met, x in mets.items():
            if met.endswith("rate"):
                continue
            d = dst.setdefault(per, {})
            d[met] = d.get(met, 0.0) + sign * x


def _fill_month(p, keys):
    """اگر ستون «یک ماهه» نبود، از تفاضل تجمعی‌ها ساخته می‌شود."""
    if "month" in p or "ytd" not in p:
        return
    base = p.get("prev_ytd") or p.get("prev_ytd_raw")
    if base is None:
        return
    adj = p.get("adj", {}) if "prev_ytd" not in p else {}
    p["month"] = {k: p["ytd"][k] - base.get(k, 0) - adj.get(k, 0) for k in keys if k in p["ytd"]}


def _rates(p, q, a, r):
    for mets in p.values():
        if mets.get(q) and mets.get(a) is not None:
            mets[r] = mets[a] * 1e6 / mets[q]


def parse_report(ds_list, period_end):
    pe = parse_jdate(period_end)
    year_end = None
    for ds in ds_list or []:
        year_end = year_end or parse_jdate(ds.get("yearEndToDate") or "")
    tables = list(iter_tables(ds_list))

    best, best_score, best_title = None, -1, ""
    for title, G in tables:
        if any(w in title for w in ("ارز", "انرژی", "مواد", "خرید", "مصرف")):
            continue
        a = analyse_table(G, pe, metric_prod)
        if not a:
            continue
        mets = {m for _, m in a["colmap"].values()}
        pers = {p for p, m in a["colmap"].values() if m == "amount"}
        if "amount" not in mets or not ({"month", "ytd"} & pers):
            continue
        score = (10 * ("تولید" in title and "فروش" in title) + 5 * ("فروش" in title or "درآمد" in title)
                 + 3 * ("month" in pers) + 3 * ("ytd" in pers) + 2 * ("prod" in mets) + 2 * ("sale" in mets))
        if score > best_score:
            best, best_score, best_title = a, score, title
    if not best:
        return None

    products, totals, section, returns = {}, [], "", {}
    for name, unit, vals in best["rows"]:
        nonzero = any(x for m in vals.values() for x in m.values())
        if name and not nonzero and "جمع" not in name:
            section = name
            continue
        if not name or not vals:
            continue
        if "جمع" in name:
            totals.append((name, vals))
            continue
        if any(w in (name + " " + section) for w in ("برگشت", "تخفیف")):
            neg = {per: {k: -abs(v) for k, v in m.items() if k in ("amount", "sale")} for per, m in vals.items()}
            _acc(products[name]["p"] if name in products else returns, neg)
            continue
        p = products.setdefault(name, {"name": name, "unit": unit, "p": {}})
        p["unit"] = p["unit"] or unit
        _acc(p["p"], vals)
    for p in products.values():
        _fill_month(p["p"], ("prod", "sale", "amount"))
        _rates(p["p"], "sale", "amount", "rate")

    total = {}
    grand = next((v for n, v in totals if n.replace(" ", "") in ("جمع", "جمعکل", "جمعکلفروش", "جمعدرآمد")), None)
    if grand is None and totals:
        grand = max(totals, key=lambda t: abs((t[1].get("ytd") or t[1].get("month") or {}).get("amount") or 0))[1]
    if grand:
        total = {per: m["amount"] for per, m in grand.items() if m.get("amount") is not None}
    if not total.get("ytd") and not total.get("month"):
        for src in list(products.values()) + [{"p": returns}]:
            for per, m in src["p"].items():
                if m.get("amount") is not None:
                    total[per] = total.get(per, 0.0) + m["amount"]
    if "month" not in total and "ytd" in total:
        if "prev_ytd" in total:
            total["month"] = total["ytd"] - total["prev_ytd"]
        elif "prev_ytd_raw" in total:
            total["month"] = total["ytd"] - total["prev_ytd_raw"] - total.get("adj", 0.0)
    if not total:
        return None

    materials = {}
    for title, G in tables:
        if not any(w in title for w in ("مواد", "مصرف", "خرید")) or "انرژی" in title or "ارز" in title:
            continue
        a = analyse_table(G, pe, metric_mat)
        if not a or not a["colmap"]:
            continue
        for name, unit, vals in a["rows"]:
            if not name or not vals or "جمع" in name:
                continue
            m = materials.setdefault(name, {"name": name, "unit": unit, "p": {}})
            m["unit"] = m["unit"] or unit
            _acc(m["p"], vals)
    for m in materials.values():
        _fill_month(m["p"], ("use_qty", "use_amount", "buy_qty", "buy_amount"))
        _rates(m["p"], "use_qty", "use_amount", "use_rate")
        _rates(m["p"], "buy_qty", "buy_amount", "buy_rate")

    return {"period_end": period_end, "year_end": jstr(year_end) if year_end else None, "table": best_title,
            "total": total, "products": list(products.values()), "materials": list(materials.values())}


# ═══════════════════════════════════════════════════════════════════════════
# ۶. محاسبه‌ی شاخص‌ها
# ═══════════════════════════════════════════════════════════════════════════
def fiscal_pos(period_end, ye):
    """(فاصله‌ی سال مالی از سال جاری: ۰ یا −۱ …، شماره‌ی ماه ۱..۱۲)"""
    k = 12 - (mindex(ye) - mindex(parse_jdate(period_end)))
    off = 0
    while k <= 0:
        k, off = k + 12, off - 1
    return off, k


def year_end_of(latest_rec, fy_end_month):
    if latest_rec and latest_rec.get("year_end"):
        return parse_jdate(latest_rec["year_end"])
    pe = parse_jdate(latest_rec["period_end"])
    y = pe[0] if pe[1] <= fy_end_month else pe[0] + 1
    return (y, fy_end_month, 29)


def find(items, key):
    if not key:
        return None
    key = norm(key)
    return next((i for i in items if i["name"] == key), None) or next((i for i in items if key in i["name"]), None)


def compute(symbol, company, recs, spread_cfg=None, fy_end_month=12, urls=None):
    recs = sorted(recs, key=lambda r: r["period_end"])
    latest = recs[-1]
    ye = year_end_of(latest, fy_end_month)
    cur_fy = ye[0]
    by = {0: {}, -1: {}}
    for r in recs:
        off, k = fiscal_pos(r["period_end"], ye)
        if off in by:
            by[off][k] = r
    L = fiscal_pos(latest["period_end"], ye)[1]
    tv = lambda off, k, key: (by[off][k]["total"].get(key) if k in by[off] else None)

    # فروش ماهانه‌ی سال جاری و سال قبل
    cur = [tv(0, k, "month") for k in range(1, 13)]
    prev = [tv(-1, k, "month") for k in range(1, 13)]
    for k in range(1, 13):
        if cur[k - 1] is None and tv(0, k, "ytd") is not None:
            base = 0 if k == 1 else tv(0, k - 1, "ytd")
            cur[k - 1] = tv(0, k, "ytd") - base if base is not None else None
        if prev[k - 1] is None:
            a = tv(0, k, "ytd_ly") if tv(0, k, "ytd_ly") is not None else tv(-1, k, "ytd")
            b = 0 if k == 1 else (tv(0, k - 1, "ytd_ly") if tv(0, k - 1, "ytd_ly") is not None else tv(-1, k - 1, "ytd"))
            prev[k - 1] = a - b if (a is not None and b is not None) else None
    cur = [v if i < L else None for i, v in enumerate(cur)]

    T = latest["total"]
    month = cur[L - 1]
    prev_month = cur[L - 2] if L > 1 else prev[11]
    if prev_month is None and T.get("prev_ytd") is not None and L > 2 and tv(0, L - 2, "ytd") is not None:
        prev_month = T["prev_ytd"] - tv(0, L - 2, "ytd")

    qs = ((L - 1) // 3) * 3 + 1
    ytd = T.get("ytd") if T.get("ytd") is not None else (sum(cur[:L]) if None not in cur[:L] else None)
    ytd_ly = T.get("ytd_ly") if T.get("ytd_ly") is not None else (sum(prev[:L]) if None not in prev[:L] else None)
    if qs == 1:
        q_cur, q_prev = ytd, ytd_ly
    else:
        yc, yl = tv(0, qs - 1, "ytd"), tv(0, qs - 1, "ytd_ly")
        q_cur = ytd - yc if (ytd is not None and yc is not None) else (
            sum(cur[qs - 1:L]) if None not in cur[qs - 1:L] else None)
        q_prev = ytd_ly - yl if (ytd_ly is not None and yl is not None) else (
            sum(prev[qs - 1:L]) if None not in prev[qs - 1:L] else None)
    fy_ly = T.get("fy_ly")
    if fy_ly is None and tv(-1, 12, "ytd") is not None:
        fy_ly = tv(-1, 12, "ytd")
    if fy_ly is None and None not in prev:
        fy_ly = sum(prev)
    month_names = [JALALI_MONTHS[(ye[1] + i) % 12] for i in range(12)]
    q_months = month_names[qs - 1:L]
    q_label = f"فصل {['اول', 'دوم', 'سوم', 'چهارم'][(qs - 1) // 3]}" + (
        f" ({q_months[0]} تا {q_months[-1]})" if len(q_months) > 1 else f" ({q_months[0]})")

    # ترکیب تولید و فروش
    items = []
    for p in latest["products"]:
        m, y = p["p"].get("month") or {}, p["p"].get("ytd") or {}
        if not (y.get("amount") or m.get("amount") or y.get("prod") or m.get("prod")):
            continue
        inv = lambda d: (d["prod"] - d["sale"]) if (d.get("prod") is not None and d.get("sale") is not None) else None
        items.append({"name": p["name"], "unit": p["unit"], "m_prod": m.get("prod"), "m_sale": m.get("sale"),
                      "m_inv": inv(m), "m_rate": m.get("rate"), "m_amount": m.get("amount"),
                      "y_prod": y.get("prod"), "y_sale": y.get("sale"), "y_inv": inv(y),
                      "y_rate": y.get("rate"), "y_amount": y.get("amount")})
    items.sort(key=lambda x: -(x["y_amount"] or x["m_amount"] or 0))
    tot = sum(max(i["y_amount"] or 0, 0) for i in items)
    for i in items:
        i["share"] = (i["y_amount"] or 0) / tot if tot else None

    return {
        "symbol": symbol, "company": company, "period_end": latest["period_end"], "table": latest["table"],
        "fy_cur": cur_fy, "fy_prev": cur_fy - 1, "fy_end": jstr(ye), "months": month_names, "last_k": L,
        "sales": {"cur": cur, "prev": prev},
        "kpi": {"month": month, "prev_month": prev_month, "mom": ratio(month, prev_month),
                "month_ly": prev[L - 1], "yoy": ratio(month, prev[L - 1]),
                "q_label": q_label, "q_cur": q_cur, "q_prev": q_prev, "season": ratio(q_cur, q_prev),
                "ytd": ytd, "ytd_ly": ytd_ly, "cumulative": ratio(ytd, ytd_ly),
                "fy_ly": fy_ly, "coverage": (ytd / fy_ly) if (ytd is not None and fy_ly) else None},
        "products": items, "spread": compute_spread(latest, by, L, spread_cfg or {}),
        "reports_used": len(recs), "months_found": sorted(by[0]), "urls": urls or {},
    }


def compute_spread(latest, by, L, cfg):
    """اسپرد = نرخ فروش محصول − ضریب × نرخ ماده‌ی اولیه (ریال بر واحد محصول)."""
    prods, mats = latest["products"], latest["materials"]
    main = find(prods, cfg.get("product")) or max(
        (p for p in prods if (p["p"].get("ytd") or p["p"].get("month") or {}).get("rate")),
        key=lambda p: (p["p"].get("ytd") or p["p"].get("month") or {}).get("amount") or 0, default=None)
    if not main:
        return {"ok": False, "reason": "نرخ فروش محصول در گزارش نیست (تعداد فروش گزارش نشده)."}
    mat = find(mats, cfg.get("material")) or max(
        mats, key=lambda m: (m["p"].get("ytd") or {}).get("use_amount") or (m["p"].get("ytd") or {}).get("buy_amount") or 0,
        default=None)
    manual = {norm(k)[:7]: v for k, v in (cfg.get("material_rates") or {}).items()}
    if not mat and not manual:
        return {"ok": False, "product": main["name"],
                "reason": "جدول مواد اولیه در گزارش ماهانه‌ی این شرکت نیست؛ نرخ ماده و ضریب تبدیل را در spread.json وارد کنید."}
    factor, fsrc = cfg.get("factor"), "spread.json"
    if factor is None and mat:
        y_m, y_p = mat["p"].get("ytd") or {}, main["p"].get("ytd") or {}
        q = y_m.get("use_qty") or y_m.get("buy_qty")
        if q and y_p.get("prod"):
            factor = q / y_p["prod"]
            fsrc = ("مصرف" if y_m.get("use_qty") else "خرید") + " ماده ÷ تولید محصول (تجمعی)"
    if not factor:
        return {"ok": False, "product": main["name"], "material": mat["name"] if mat else "",
                "reason": "ضریب تبدیل قابل محاسبه نیست (مقدار مصرف/تولید گزارش نشده)؛ factor را در spread.json وارد کنید."}

    def point(r):
        p = find(r["products"], main["name"])
        pr = (p["p"].get("month") or {}).get("rate") if p else None
        mr = manual.get(r["period_end"][:7])
        if mr is None and mat:
            m = find(r["materials"], mat["name"])
            if m:
                mm = m["p"].get("month") or {}
                mr = mm.get("use_rate") or mm.get("buy_rate")
        sp = pr - factor * mr if (pr is not None and mr is not None) else None
        return {"prate": pr, "mrate": mr, "cost": factor * mr if mr is not None else None, "spread": sp,
                "margin": sp / pr if (sp is not None and pr) else None}

    series = [point(by[0][k]) if k in by[0] else None for k in range(1, 13)]
    series = [s if i < L else None for i, s in enumerate(series)]
    last = series[L - 1] or {}
    before = next((series[i] for i in range(L - 2, -1, -1) if series[i] and series[i]["spread"] is not None), None)
    if last.get("spread") is None:
        return {"ok": False, "product": main["name"], "material": mat["name"] if mat else "",
                "reason": "نرخ ماه جاری محصول یا ماده‌ی اولیه در گزارش نیست."}
    return {"ok": True, "product": main["name"], "unit": main["unit"], "material": mat["name"] if mat else cfg.get("material", ""),
            "mat_unit": mat["unit"] if mat else "", "factor": factor, "factor_src": fsrc, "series": series, "last": last,
            "change": ratio(last["spread"], before["spread"]) if before else None}


# ═══════════════════════════════════════════════════════════════════════════
# ۷. HTML / JS
# ═══════════════════════════════════════════════════════════════════════════
CSS = r"""
*{box-sizing:border-box}
html,body{margin:0;background:#fff}
.toolbar{position:sticky;top:0;z-index:5;display:flex;gap:10px;justify-content:center;padding:10px;background:rgba(255,255,255,.92);font-family:Vazirmatn,Vazir,Tahoma,"Segoe UI",sans-serif}
.toolbar button,.toolbar a{font:inherit;font-size:14px;border:0;border-radius:12px;padding:9px 18px;background:#2F6BFF;color:#fff;cursor:pointer;text-decoration:none}
.toolbar a{background:#EEF2FF;color:#2F6BFF}
#report{width:1480px;margin:0 auto 30px;padding:34px 36px 38px;background:#E6E9F0;color:#16181D;direction:rtl;
 border:2px solid #16181D;border-radius:44px;font-family:Vazirmatn,Vazir,Tahoma,"Segoe UI",sans-serif;font-size:14px;line-height:1.55}
html.shot body{direction:ltr}
html.shot #report{margin:8px 0 8px 8px}
.n{direction:ltr;unicode-bidi:isolate;display:inline-block}
.mut{color:#6B7280}.pos{color:#22B35E}.neg{color:#E5484D}
/* header */
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}
.brand{display:flex;align-items:center;gap:20px}
.logo{width:74px;height:74px;border-radius:50%;background:#2F6BFF;display:flex;align-items:center;justify-content:center;box-shadow:0 10px 24px rgba(47,107,255,.35)}
.brand h1{margin:0;font-size:42px;font-weight:900;line-height:1.1}
.brand .co{font-size:19px;color:#374151;margin-top:4px}
.datepill{display:flex;align-items:center;gap:10px;background:#fff;border-radius:999px;padding:10px 22px;font-size:16px;font-weight:600}
/* grid */
.grid{display:grid;grid-template-columns:340px 1fr;gap:26px;align-items:start}
.col{display:flex;flex-direction:column;gap:26px}
.card{background:#fff;border-radius:30px;padding:26px 28px}
.card h2{margin:0;font-size:24px;font-weight:900}
.card .sub{color:#4B5563;font-size:14.5px;margin-top:4px}
.title{padding:6px 4px 0}
.title h1{margin:0;font-size:50px;font-weight:900;line-height:1.15}
.title .sub{color:#4B5563;font-size:17px;margin:6px 0 14px}
.blackpill{display:inline-block;background:#16181D;color:#fff;border-radius:999px;padding:7px 20px;font-size:15px;font-weight:600}
.headrow{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}
.legend{display:flex;gap:16px;align-items:center;font-size:13.5px;color:#4B5563;white-space:nowrap;padding-top:6px}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-left:6px;vertical-align:-1px}
.legend i.ln{height:3px;width:18px;border-radius:2px;vertical-align:3px}
.legend .u{color:#9CA3AF}
/* KPI */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px 0 10px}
.kpis.k5{grid-template-columns:repeat(5,1fr)}
.kpi{background:#F1F3F8;border-radius:22px;padding:18px 22px}
.kpi .t{font-size:15px;color:#374151;font-weight:600}
.kpi .v{font-size:44px;font-weight:900;line-height:1.25;margin:6px 0 4px}
.kpi .d{font-size:13px;color:#4B5563}
.kpi.dark{background:#16181D;color:#fff}
.kpi.dark .t,.kpi.dark .d{color:#E5E7EB}
/* products */
.donut{display:flex;justify-content:center;margin:18px 0 10px}
.prod{padding:12px 0 6px}
.prod .row{display:flex;justify-content:space-between;align-items:baseline}
.prod .nm{font-size:17px;font-weight:700}
.prod .nm i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-left:8px}
.prod .pc{font-size:17px;font-weight:900}
.prod .am{font-size:13.5px;color:#374151}
.prod .bar{height:6px;background:#EEF0F4;border-radius:9px;margin:8px 0 6px;overflow:hidden;direction:ltr}
.prod .bar b{display:block;height:100%;border-radius:9px}
.prod .q{font-size:12.5px;color:#9CA3AF}
.badge{display:inline-block;font-size:12px;font-weight:700;border-radius:8px;padding:1px 10px;margin-top:4px}
.badge.up{background:#FEF3C7;color:#B45309}.badge.dn{background:#DBEAFE;color:#1D4ED8}.badge.eq{background:#F3F4F6;color:#6B7280}
.pq{text-align:left}
/* mom */
.foot2{display:flex;justify-content:space-between;align-items:center;margin-top:6px}
.avgpill{background:#F1F3F8;border-radius:999px;padding:8px 18px;font-size:15px;font-weight:600}
.empty{padding:26px;text-align:center;color:#6B7280;background:#F7F8FB;border:1px dashed #D1D5DB;border-radius:18px;margin-top:16px}
.formula{color:#374151;font-size:15px;margin-top:6px}
.srcline{text-align:center;color:#6B7280;font-size:12.5px;margin-top:20px}
.srcline a{color:#2F6BFF}
svg text{font-family:Vazirmatn,Vazir,Tahoma,"Segoe UI",sans-serif}
/* index */
.tbl{width:100%;border-collapse:separate;border-spacing:0;font-size:15px}
.tbl th{background:#F1F3F8;color:#374151;font-weight:700;padding:12px 10px;white-space:nowrap;cursor:pointer}
.tbl th:first-child{border-radius:0 14px 14px 0}.tbl th:last-child{border-radius:14px 0 0 14px}
.tbl td{padding:12px 10px;border-bottom:1px solid #EEF0F4;text-align:center;white-space:nowrap;font-weight:600}
.tbl td.nm{text-align:right}
.tbl a{color:#2F6BFF;font-weight:900;text-decoration:none;font-size:17px}
"""

COMMON_JS = r"""
const FA=new Intl.NumberFormat('fa-IR',{maximumFractionDigits:0});
const nf=(x,d=0)=>(x==null||!isFinite(x))?'—':new Intl.NumberFormat('fa-IR',{minimumFractionDigits:d,maximumFractionDigits:d}).format(x).replace(/\u066B/g,'/');
const N=s=>`<span class="n">${s}</span>`;
const pf=(x,sign=true)=>(x==null||!isFinite(x))?'—':N((sign&&x>0?'+':'')+nf(x*100,1)+'٪');
const cls=x=>(x==null||!isFinite(x))?'mut':(x>=0?'pos':'neg');
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function savePNG(name){
  try{await document.fonts.ready;}catch(e){}
  const node=document.getElementById('report');
  const w=node.offsetWidth,h=node.offsetHeight,s=2;
  const clone=node.cloneNode(true);clone.style.margin='0';
  const css=[...document.querySelectorAll('style')].map(x=>x.textContent).join('\n');
  const xhtml=new XMLSerializer().serializeToString(clone);
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${w*s}" height="${h*s}" viewBox="0 0 ${w} ${h}">`+
    `<foreignObject x="0" y="0" width="${w}" height="${h}"><div xmlns="http://www.w3.org/1999/xhtml">`+
    `<style>${css}</style>${xhtml}</div></foreignObject></svg>`;
  const img=new Image();
  img.onload=()=>setTimeout(()=>{
    const c=document.createElement('canvas');c.width=w*s;c.height=h*s;
    const g=c.getContext('2d');g.fillStyle='#FFFFFF';g.fillRect(0,0,c.width,c.height);g.drawImage(img,0,0);
    try{c.toBlob(b=>{const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=(name||'report')+'.png';
      document.body.appendChild(a);a.click();a.remove();},'image/png');}
    catch(e){alert('مرورگر اجازه‌ی ذخیره نداد؛ از گزینه‌ی --png اسکریپت یا ابزار Snipping استفاده کنید.');}
  },400);
  img.onerror=()=>alert('ساخت تصویر ناموفق بود؛ از گزینه‌ی --png اسکریپت استفاده کنید.');
  img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
}
if(location.search.includes('shot')){document.documentElement.classList.add('shot');}
"""

REPORT_JS = r"""
const D=JSON.parse(document.getElementById('data').textContent);
const K=D.kpi, L=D.last_k, M=D.months, S=D.spread;
const fd=s=>String(s).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);
const yC=fd(D.fy_cur), yP=fd(D.fy_prev), mname=M[L-1], repY=fd(D.period_end.slice(0,4));
const C={cur:'#2F6BFF',prev:'#2FBF62',red:'#E5484D',org:'#F97316',gray:'#94A3B8',grid:'#EEF0F4',ink:'#16181D'};
const avg=a=>{const v=a.filter(x=>x!=null&&isFinite(x));return v.length?v.reduce((s,x)=>s+x,0)/v.length:null;};

// ── واحدها (خودکار: اگر اعداد خیلی بزرگ باشند یک پله بزرگ‌تر)
let U=D.unit, DIV=D.unit_div;
const maxS=Math.max(0,...[...D.sales.cur,...D.sales.prev].filter(v=>v!=null).map(Math.abs));
if(U.includes('میلیارد')&&maxS/DIV>=1000){DIV*=1000;U='هزار '+U;}
const amt=x=>x==null?null:x/DIV;
const f1=x=>(x==null||!isFinite(x))?'—':nf(x,Math.abs(x)<100?1:0);
let RU=D.rate_unit, RDIV=D.rate_div;
if(S&&S.ok){const rr=[];S.series.forEach(p=>p&&['prate','cost','spread'].forEach(k=>p[k]!=null&&rr.push(Math.abs(p[k]))));
  const mr=Math.max(0,...rr)/RDIV; if(mr>=1e6){RDIV*=1e6;RU='میلیون '+RU;} else if(mr>=1e4){RDIV*=1e3;RU='هزار '+RU;}}
const rt=x=>x==null?null:x/RDIV;
const sgn=x=>(x==null||!isFinite(x))?'—':(x>0?'+':x<0?'−':'')+nf(Math.abs(x)*100,1)+'٪';
function niceMax(v){if(!v||v<=0)return 1;const p=Math.pow(10,Math.floor(Math.log10(v)));const m=v/p;return (m<=1?1:m<=1.5?1.5:m<=2?2:m<=3?3:m<=5?5:10)*p;}
const pill=(x,y,w,txt,fill)=>`<rect x="${x}" y="${y-16}" width="${w}" height="32" rx="16" fill="${fill}"/><text x="${x+w/2}" y="${y+5}" text-anchor="middle" direction="rtl" font-size="15" font-weight="800" fill="#fff">${txt}</text>`;

// ── نمودار میله‌ای فروش (راست‌به‌چپ)
function salesChart(){
  const W=1000,H=360,pt=34,pb=46,pr=44,pl=150,ph=H-pt-pb,pw=W-pl-pr,gw=pw/12;
  const cur=D.sales.cur.map(amt),prev=D.sales.prev.map(amt);
  const max=niceMax(Math.max(0,...[...cur,...prev].filter(v=>v!=null))*1.12);
  const Y=v=>pt+ph-ph*v/max,X=i=>W-pr-gw*(i+.5),bw=Math.min(22,gw*.3);
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" style="direction:ltr">`;
  for(let t=0;t<=3;t++){const v=max*t/3;s+=`<line x1="${pl}" x2="${W-pr+6}" y1="${Y(v)}" y2="${Y(v)}" stroke="${C.grid}"/><text x="${W-6}" y="${Y(v)+4}" text-anchor="end" font-size="12" fill="#9CA3AF">${f1(v)}</text>`;}
  const ac=avg(cur.slice(0,L)),ap=avg(prev);
  for(let i=0;i<12;i++){const cx=X(i),gx=cx+bw*.65,bx=cx-bw*.65;
    if(prev[i]!=null)s+=`<rect x="${gx-bw/2}" y="${Y(prev[i])}" width="${bw}" height="${Y(0)-Y(prev[i])}" rx="${bw/2}" fill="${C.prev}"/>`;
    if(i<L&&cur[i]!=null){s+=`<rect x="${bx-bw/2}" y="${Y(cur[i])}" width="${bw}" height="${Y(0)-Y(cur[i])}" rx="${bw/2}" fill="${C.cur}"/>`+
      `<text x="${bx}" y="${Y(cur[i])-9}" text-anchor="middle" font-size="14" font-weight="800" fill="${C.ink}">${f1(cur[i])}</text>`;}
    else if(i>=L){const hv=prev[i]??ac??0;s+=`<rect x="${bx-bw/2}" y="${Y(hv)}" width="${bw}" height="${Y(0)-Y(hv)}" rx="${bw/2}" fill="none" stroke="#C9CED8" stroke-dasharray="4 3" stroke-width="1.5"/>`;}
    s+=`<text x="${cx}" y="${H-12}" text-anchor="middle" font-size="14.5" ${i===L-1?'font-weight="900" fill="#16181D"':'fill="#4B5563"'}>${M[i]}</text>`;}
  let ya=ac!=null?Y(ac):null,yp=ap!=null?Y(ap):null;
  if(ya!=null&&yp!=null&&Math.abs(ya-yp)<36){if(ya<yp)yp=ya+36;else ya=yp+36;}
  if(ac!=null)s+=`<line x1="${pl-10}" x2="${W-pr}" y1="${Y(ac)}" y2="${Y(ac)}" stroke="${C.cur}" stroke-dasharray="6 5" stroke-width="1.6"/>`+pill(6,ya,124,'میانگین '+f1(ac),C.cur);
  if(ap!=null)s+=`<line x1="${pl-10}" x2="${W-pr}" y1="${Y(ap)}" y2="${Y(ap)}" stroke="${C.prev}" stroke-dasharray="6 5" stroke-width="1.6"/>`+pill(6,yp,124,'میانگین '+f1(ap),C.prev);
  return s+'</svg>';}

// ── نمودار رشد ماهانه
const mom=D.sales.cur.map((v,i)=>{const p=i?D.sales.cur[i-1]:D.sales.prev[11];return (i<L&&v!=null&&p)?v/p-1:null;});
function momChart(){
  const W=1000,H=300,pt=10,pb=46,ph=H-pt-pb,gw=(W-20)/12,z=pt+ph/2;
  const mx=Math.max(.05,...mom.filter(v=>v!=null).map(Math.abs)),sc=(ph/2-34)/mx,X=i=>W-10-gw*(i+.5);
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" style="direction:ltr">`;
  for(let i=0;i<12;i++)s+=`<rect x="${X(i)-19}" y="${pt}" width="38" height="${ph}" rx="19" fill="${i===L-1?'#DCE6FF':'#F1F3F8'}"/>`;
  s+=`<line x1="10" x2="${W-10}" y1="${z}" y2="${z}" stroke="#D4D8E0"/>`;
  for(let i=0;i<12;i++){const v=mom[i],x=X(i);
    if(v==null){s+=`<circle cx="${x}" cy="${z}" r="4" fill="#C4C9D4"/>`;}
    else{const h=Math.abs(v)*sc,col=v>=0?C.cur:C.red,lab=(v>0?'+':'')+nf(v*100,1)+'٪';
      if(h<14)s+=`<circle cx="${x}" cy="${z+(v>=0?-6:6)}" r="9" fill="${col}"/>`;
      else s+=`<rect x="${x-9}" y="${v>=0?z-h:z}" width="18" height="${h}" rx="9" fill="${col}"/>`;
      const hh=Math.max(h,20);
      s+=`<text x="${x}" y="${v>=0?z-hh-9:z+hh+19}" text-anchor="middle" font-size="13.5" font-weight="800" fill="${col}" direction="ltr">${lab}</text>`;}
    s+=`<text x="${x}" y="${H-12}" text-anchor="middle" font-size="14.5" ${i===L-1?'font-weight="900" fill="#16181D"':'fill="#4B5563"'}>${M[i]}</text>`;}
  return s+'</svg>';}

// ── دونات ترکیب فروش
const PAL=['#2F6BFF','#2FBF62','#FBD34D','#16181D','#F97316','#94A3B8'];
const P=(D.products||[]).filter(p=>(p.y_amount||0)>0);
let items=P.slice(0,5).map((p,i)=>({...p,color:PAL[i]}));
if(P.length>5){const rest=P.slice(5);items.push({name:'سایر محصولات',other:true,color:PAL[5],y_amount:rest.reduce((s,p)=>s+p.y_amount,0),share:rest.reduce((s,p)=>s+(p.share||0),0)});}
const totY=P.reduce((s,p)=>s+p.y_amount,0);
function donut(){
  const R=86,SW=38,Cc=2*Math.PI*R;let off=0,s=`<svg width="250" height="250" viewBox="0 0 250 250" style="direction:ltr"><g transform="rotate(-90 125 125)">`;
  items.forEach(it=>{const len=(it.share||0)*Cc;if(len<=0)return;
    s+=`<circle cx="125" cy="125" r="${R}" fill="none" stroke="${it.color}" stroke-width="${SW}" stroke-dasharray="${Math.max(len-4,1)} ${Cc}" stroke-dashoffset="${-off}"/>`;off+=len;});
  s+=`</g><text x="125" y="122" text-anchor="middle" font-size="40" font-weight="900" fill="${C.ink}">${f1(amt(totY))}</text>`+
     `<text x="125" y="148" text-anchor="middle" direction="rtl" font-size="13" fill="#4B5563">${U}</text>`+
     `<text x="125" y="168" text-anchor="middle" direction="rtl" font-size="13" fill="#4B5563">${fd(P.length)} محصول</text></svg>`;
  return s;}
function prodRow(it){
  let q='';
  if(!it.other&&(it.y_prod!=null||it.y_sale!=null)){
    const inv=it.y_inv,b=inv==null?'':inv>0?`<span class="badge up">افزایش موجودی ${N(nf(inv))}</span>`:inv<0?`<span class="badge dn">کاهش موجودی ${N(nf(-inv))}</span>`:`<span class="badge eq">بدون تغییر موجودی</span>`;
    q=`<div class="pq"><div class="q">تولید ${N(nf(it.y_prod))} / فروش ${N(nf(it.y_sale))} ${esc(it.unit||'')}</div>${b}</div>`;}
  return `<div class="prod"><div class="row"><div class="nm"><i style="background:${it.color}"></i>${esc(it.name)}</div><div class="pc">${N(nf((it.share||0)*100,1)+'٪')}</div></div>
   <div class="am">${N(f1(amt(it.y_amount)))} ${U}</div><div class="bar"><b style="width:${Math.min(100,(it.share||0)/((items[0]&&items[0].share)||1)*100)}%;background:${it.color}"></b></div>${q}</div>`;}

// ── اسپرد
function spreadChart(){
  const cur=S.series.map(p=>p&&p.spread!=null?rt(p.spread):null);
  const prev=(S.prev_series||[]).map(p=>p==null?null:rt(typeof p==='object'?p.spread:p));
  const W=1400,H=440,pt=50,pb=50,pr=70,pl=200,ph=H-pt-pb,pw=W-pl-pr,gw=pw/12;
  const vals=[...cur,...prev].filter(v=>v!=null);if(!vals.length)return '';
  let mn=Math.min(...vals),mx=Math.max(...vals);const st=niceMax(Math.max((mx-mn)/3,Math.abs(mx)*.05));
  mn=Math.floor((mn-st*.5)/st)*st;mx=Math.ceil((mx+st*.5)/st)*st;
  const X=i=>W-pr-gw*(i+.5),Y=v=>pt+ph-ph*(v-mn)/(mx-mn);
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" style="direction:ltr"><defs><linearGradient id="og" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${C.org}" stop-opacity=".38"/><stop offset="1" stop-color="${C.org}" stop-opacity="0"/></linearGradient></defs>`;
  for(let v=mn;v<=mx+1e-9;v+=st)s+=`<line x1="${pl-20}" x2="${W-pr+10}" y1="${Y(v)}" y2="${Y(v)}" stroke="${C.grid}"/><text x="${W-10}" y="${Y(v)+5}" text-anchor="end" font-size="14" fill="#9CA3AF">${f1(v)}</text>`;
  const pts=a=>a.map((v,i)=>v==null?null:[X(i),Y(v)]).filter(Boolean);
  const pp=pts(prev),cp=pts(cur);
  if(pp.length>1)s+=`<polyline points="${pp.map(p=>p.join(',')).join(' ')}" fill="none" stroke="${C.gray}" stroke-width="3"/>`;
  prev.forEach((v,i)=>{if(v!=null)s+=`<circle cx="${X(i)}" cy="${Y(v)}" r="6" fill="#fff" stroke="${C.gray}" stroke-width="2.5"/><text x="${X(i)}" y="${Y(v)+28}" text-anchor="middle" font-size="15" font-weight="700" fill="#6B7280">${f1(v)}</text>`;});
  if(cp.length>1){s+=`<polygon points="${cp.map(p=>p.join(',')).join(' ')} ${cp[cp.length-1][0]},${pt+ph} ${cp[0][0]},${pt+ph}" fill="url(#og)"/>`+
    `<polyline points="${cp.map(p=>p.join(',')).join(' ')}" fill="none" stroke="${C.org}" stroke-width="3.5"/>`;}
  cur.forEach((v,i)=>{if(v==null)return;const big=i===L-1;
    if(big)s+=`<circle cx="${X(i)}" cy="${Y(v)}" r="17" fill="${C.org}" opacity=".22"/>`;
    s+=`<circle cx="${X(i)}" cy="${Y(v)}" r="${big?10:6.5}" fill="${big?C.org:'#fff'}" stroke="${C.org}" stroke-width="3"/>`+
       `<text x="${X(i)}" y="${Y(v)-(big?24:18)}" text-anchor="middle" font-size="17" font-weight="900" fill="#EA580C">${f1(v)}</text>`;});
  const a=avg(cur);if(a!=null)s+=`<line x1="${pl-20}" x2="${W-pr}" y1="${Y(a)}" y2="${Y(a)}" stroke="${C.org}" stroke-dasharray="8 6" stroke-width="2"/>`+
    `<rect x="16" y="${Y(a)-21}" width="170" height="42" rx="21" fill="${C.org}"/><text x="101" y="${Y(a)+7}" text-anchor="middle" direction="rtl" font-size="19" font-weight="900" fill="#fff">میانگین ${f1(a)}</text>`;
  M.forEach((m,i)=>s+=`<text x="${X(i)}" y="${H-10}" text-anchor="middle" font-size="18" ${i===L-1?'font-weight="900" fill="#16181D"':'fill="#4B5563"'}>${m}</text>`);
  return s+'</svg>';}

// ── چیدمان
const qm=(K.q_label||'').match(/\((.*)\)/);
const calIcon=`<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#16181D" stroke-width="2"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>`;
const bolt=`<svg width="40" height="40" viewBox="0 0 24 24"><path d="M13.5 2 5 13.5h6L10 22l9-12.5h-6.2L13.5 2z" fill="#fff"/></svg>`;
let h=`<div class="top"><div class="brand"><div class="logo">${bolt}</div><div><h1>${esc(D.symbol)}</h1></div><div class="co">(${esc(D.company)})</div></div>
<div class="datepill">${calIcon}<span>${esc(String(D.generated).split('—')[0].trim())}</span></div></div><div class="grid">`;

// ستون راست
h+=`<div class="col"><div class="title"><h1>عملکرد ماهانه</h1><div class="sub">بر اساس گزارش‌های فعالیت ماهانه کدال</div><span class="blackpill">سال مالی منتهی به ${M[11]}</span></div>
<div class="card"><h2>ترکیب فروش محصولات</h2><div class="sub">تجمعی ${fd(L)} ماهه سال مالی ${yC}</div>`;
if(items.length){h+=`<div class="donut">${donut()}</div>`+items.map(prodRow).join('');}
else h+=`<div class="empty">جدول محصولات در گزارش پیدا نشد.</div>`;
h+=`</div></div>`;

// ستون چپ
h+=`<div class="col"><div class="card"><div class="headrow"><div><h2>نمودار میله‌ای مبالغ فروش</h2>
<div class="sub">مقایسه ماه‌به‌ماه سال مالی ${yC} با ${yP} — آخرین گزارش: ${mname} ${repY}</div></div>
<div class="legend"><span><i style="background:${C.prev}"></i>سال مالی ${yP}</span><span><i style="background:${C.cur}"></i>سال مالی ${yC}</span><span class="u">ارقام: ${U}</span></div></div>
<div class="kpis">
 <div class="kpi"><div class="t">درصد تغییرات فروش ماهانه</div><div class="v ${cls(K.yoy)}">${N(sgn(K.yoy))}</div><div class="d">${mname} ${repY} نسبت به ${mname} ${fd(+D.period_end.slice(0,4)-1)}</div></div>
 <div class="kpi"><div class="t">درصد تغییرات فروش فصلی</div><div class="v ${cls(K.season)}">${N(sgn(K.season))}</div><div class="d">${qm?qm[1]:esc(K.q_label||'')} نسبت به مدت مشابه ${yP}</div></div>
 <div class="kpi"><div class="t">درصد تغییرات فروش تجمعی</div><div class="v ${cls(K.cumulative)}">${N(sgn(K.cumulative))}</div><div class="d">${fd(L)} ماهه ${yC} نسبت به مدت مشابه ${yP}</div></div>
 <div class="kpi"><div class="t">درصد فروش سال گذشته (پوشش درآمد)</div><div class="v">${N(K.coverage==null?'—':nf(K.coverage*100,1)+'٪')}</div><div class="d">فروش ${fd(L)} ماهه از کل فروش سال مالی ${yP}</div></div>
</div>${salesChart()}</div>`;
const am=avg(mom);
h+=`<div class="card"><h2>درصد رشد مبلغ فروش نسبت به ماه گذشته</h2><div class="sub">سال مالی ${yC} — ماه اول با آخرین ماه سال مالی قبل مقایسه شده است</div>
<div style="margin-top:18px">${momChart()}</div><div class="foot2"><div class="legend"><span><i style="background:${C.cur}"></i>رشد</span><span><i style="background:${C.red}"></i>افت</span><span><i style="background:#DCE6FF"></i>آخرین ماه</span></div>
<div class="avgpill">میانگین رشد ماهانه: <b class="${cls(am)}">${N(sgn(am))}</b></div></div></div></div></div>`;

// اسپرد (تمام‌عرض)
h+=`<div class="card" style="margin-top:26px">`;
if(!S||!S.ok){h+=`<h2>اسپرد محصولات به مواد</h2><div class="empty">${esc((S&&S.reason)||'اطلاعات اسپرد موجود نیست.')}<br><span style="font-size:12.5px">نمونه‌ی تنظیم در spread.json:
 {"${esc(D.symbol)}": {"product": "${esc((S&&S.product)||'نام محصول')}", "material": "نام ماده", "factor": 1.1}}</span></div>`;}
else{const l=S.last,prevName=L>1?M[L-2]:'ماه آخر سال قبل',sa=avg(S.series.map(p=>p&&p.spread!=null?rt(p.spread):null));
  const per=`${RU} بر ${esc(S.unit||'واحد')}`;
  h+=`<h2>اسپرد محصولات به مواد</h2><div class="formula">اسپرد = نرخ فروش محصول − (ضریب تبدیل × نرخ مواد اولیه) ؛ ضریب تبدیل = ${esc(S.factor_src)}</div>
  <div class="legend" style="margin-top:6px"><span><i class="ln" style="background:${C.org}"></i>سال مالی ${yC}</span>${S.prev_series?`<span><i class="ln" style="background:${C.gray}"></i>سال مالی ${yP}</span>`:''}<span class="u">${esc(S.product)} به ${esc(S.material)} — واحد: ${per}</span></div>
  <div class="kpis k5">
   <div class="kpi"><div class="t">ضریب تبدیل</div><div class="v">${N(nf(S.factor,2))}</div><div class="d">${esc(S.mat_unit||'واحد')} مواد به ازای هر ${esc(S.unit||'واحد')} محصول</div></div>
   <div class="kpi"><div class="t">اسپرد ${mname} ${repY}</div><div class="v">${N(f1(rt(l.spread)))}</div><div class="d">${per}</div></div>
   <div class="kpi"><div class="t">حاشیه اسپرد</div><div class="v ${cls(l.margin)}">${N(l.margin==null?'—':nf(l.margin*100,1)+'٪')}</div><div class="d">اسپرد ÷ نرخ فروش محصول</div></div>
   <div class="kpi"><div class="t">تغییر نسبت به ماه قبل</div><div class="v ${cls(S.change)}">${N(sgn(S.change))}</div><div class="d">در مقایسه با ${prevName}</div></div>
   <div class="kpi"><div class="t">میانگین سال مالی جاری</div><div class="v">${N(f1(sa))}</div><div class="d">${per} — ${yC}</div></div>
  </div><div style="margin-top:14px">${spreadChart()}</div>`;}
h+=`</div><div class="srcline">منبع: کدال — جدول «${esc(D.table)}» — ${fd(D.reports_used)} گزارش ماهانه — تهیه: ${esc(D.generated)}${D.url?` — <a href="${esc(D.url)}">گزارش ${mname} در کدال</a>`:''}</div>`;
const R=document.getElementById('report');R.innerHTML=h;
document.documentElement.setAttribute('data-h',R.offsetHeight+4);
document.documentElement.setAttribute('data-w',R.offsetWidth+60);
"""

INDEX_JS = r"""
const D=JSON.parse(document.getElementById('data').textContent);
const fd=s=>String(s).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);
const sgn=x=>(x==null||!isFinite(x))?'—':N((x>0?'+':x<0?'−':'')+nf(Math.abs(x)*100,1)+'٪');
const cols=[['symbol','نماد'],['company','شرکت'],['period','دوره'],['month','فروش ماه'],['mom','رشد ماهانه'],['season','رشد فصلی'],
 ['cumulative','رشد تجمعی'],['coverage','پوشش درآمد'],['inv_up','افزایش موجودی'],['margin','حاشیه اسپرد'],['spread_chg','تغییر اسپرد']];
let sortK='cumulative',asc=false;
const bolt=`<svg width="40" height="40" viewBox="0 0 24 24"><path d="M13.5 2 5 13.5h6L10 22l9-12.5h-6.2L13.5 2z" fill="#fff"/></svg>`;
function draw(){
  const rows=[...D.rows].sort((a,b)=>{const x=a[sortK],y=b[sortK];if(x==null)return 1;if(y==null)return -1;return (x>y?1:x<y?-1:0)*(asc?1:-1);});
  let h=`<div class="top"><div class="brand"><div class="logo">${bolt}</div><div><h1>خلاصه‌ی عملکرد ماهانه</h1><div class="co">${fd(D.rows.length)} نماد — برای مرتب‌سازی روی عنوان ستون کلیک کنید</div></div></div>
  <div class="datepill">${esc(String(D.generated).split('—')[0].trim())} — ارقام: ${D.unit}</div></div><div class="card"><table class="tbl"><thead><tr>`;
  cols.forEach(([k,t])=>h+=`<th onclick="sortBy('${k}')">${t}${k===sortK?(asc?' ▲':' ▼'):''}</th>`);
  h+=`</tr></thead><tbody>`;
  rows.forEach(r=>{h+=`<tr><td class="nm"><a href="${r.file}">${esc(r.symbol)}</a></td><td class="nm" style="font-weight:400">${esc(r.company)}</td><td>${N(r.period_fa)}</td><td>${N(nf(r.month/D.unit_div))}</td>`;
    ['mom','season','cumulative'].forEach(k=>h+=`<td class="${cls(r[k])}">${sgn(r[k])}</td>`);
    h+=`<td>${r.coverage==null?'—':N(nf(r.coverage*100,1)+'٪')}</td><td>${r.inv_up==null?'—':N(nf(r.inv_up))+' از '+N(nf(r.n_products))}</td><td class="${cls(r.margin)}">${r.margin==null?'—':N(nf(r.margin*100,1)+'٪')}</td><td class="${cls(r.spread_chg)}">${sgn(r.spread_chg)}</td></tr>`;});
  const R=document.getElementById('report');R.innerHTML=h+`</tbody></table></div>`;
  document.documentElement.setAttribute('data-h',R.offsetHeight+4);
  document.documentElement.setAttribute('data-w',R.offsetWidth+60);
}
function sortBy(k){if(sortK===k)asc=!asc;else{sortK=k;asc=false;}draw();}
draw();
"""


# ── فونت وزیرمتن: داخل خود HTML جاسازی می‌شود تا همه‌جا (و در PNG) یکسان دیده شود
FONT_DIR = HERE / "fonts"
FONT_URLS = [  # فایل متغیر (همه‌ی وزن‌ها در یک فایل)
    "https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/webfonts/Vazirmatn%5Bwght%5D.woff2",
    "https://raw.githubusercontent.com/rastikerdar/vazirmatn/v33.003/fonts/webfonts/Vazirmatn%5Bwght%5D.woff2",
    "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/webfonts/Vazirmatn%5Bwght%5D.woff2",
]
_WEIGHTS = {"thin": 100, "extralight": 200, "light": 300, "regular": 400, "medium": 500,
            "semibold": 600, "extrabold": 800, "bold": 700, "black": 900}
_font_css_cache = None


def _font_files():
    """فایل‌های وزیرمتن: پوشه‌ی fonts کنار اسکریپت، فونت‌های نصب‌شده‌ی ویندوز."""
    dirs = [FONT_DIR, Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts",
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
    for d in dirs:
        if not d.is_dir():
            continue
        found = [f for f in d.iterdir() if f.suffix.lower() in (".woff2", ".ttf")
                 and f.name.lower().startswith("vazirmatn") and "-ui" not in f.name.lower()
                 and "-rd" not in f.name.lower() and "-nl" not in f.name.lower()]
        var = [f for f in found if "[wght]" in f.name.lower() or "wght" in f.name.lower()]
        if var:
            return [(var[0], None)]
        stat = []
        for f in found:
            low = f.stem.lower().replace("vazirmatn", "").strip("-_ ")
            w = next((v for k, v in sorted(_WEIGHTS.items(), key=lambda kv: -len(kv[0])) if low == k), None)
            if w:
                stat.append((f, w))
        if stat:
            return stat
    return []


def _download_font():
    FONT_DIR.mkdir(exist_ok=True)
    dest = FONT_DIR / "Vazirmatn[wght].woff2"
    for url in FONT_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            if data[:4] == b"wOF2" and len(data) > 30000:
                dest.write_bytes(data)
                log.info("- Font: Vazirmatn downloaded -> %s", dest)
                return True
        except Exception as e:
            log.debug("font download %s: %s", url, e)
    return False


def font_css():
    """@font-face با داده‌ی base64؛ اگر فونت نبود رشته‌ی خالی (مرورگر از Tahoma استفاده می‌کند)."""
    global _font_css_cache
    if _font_css_cache is not None:
        return _font_css_cache
    files = _font_files()
    if not files and _download_font():
        files = _font_files()
    if not files:
        log.warning("! Vazirmatn font not found and could not be downloaded; numbers will use Tahoma.\n"
                    "  Fix: download Vazirmatn (github.com/rastikerdar/vazirmatn/releases), and copy the\n"
                    "  .ttf files from fonts/ttf into a folder named 'fonts' next to this script.")
        _font_css_cache = ""
        return ""
    import base64
    css = []
    for f, w in files:
        fmt, mime = ("woff2", "font/woff2") if f.suffix.lower() == ".woff2" else ("truetype", "font/ttf")
        b64 = base64.b64encode(f.read_bytes()).decode()
        weight = "100 900" if w is None else str(w)
        css.append(f"@font-face{{font-family:'Vazirmatn';src:url(data:{mime};base64,{b64}) format('{fmt}');"
                   f"font-weight:{weight};font-style:normal;font-display:block}}")
    log.info("- Font: Vazirmatn embedded (%s)", ", ".join(f.name for f, _ in files))
    _font_css_cache = "".join(css)
    return _font_css_cache


def html_page(title, data, js, toolbar_name):
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>'
            f'<style>{font_css()}{CSS}html.shot .toolbar{{display:none}}</style></head><body>'
            f'<div class="toolbar"><button onclick="savePNG(\'{toolbar_name}\')">ذخیره به‌صورت تصویر PNG</button>'
            f'<a href="index.html">فهرست نمادها</a></div><div id="report"></div>'
            f'<script id="data" type="application/json">{payload}</script>'
            f'<script>{COMMON_JS}{js}</script></body></html>')


def fa_digits(s):
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def jalali_now_str():
    y, m, d = jtoday()
    return fa_digits(f"{d} {JALALI_MONTHS[m - 1]} {y} — {time.strftime('%H:%M')}")


def write_report(d, outdir: Path, unit):
    data = dict(d, unit=unit, unit_div=UNITS[unit], rate_unit="تومان" if "تومان" in unit else "ریال",
                rate_div=10 if "تومان" in unit else 1, generated=jalali_now_str(),
                period_end_fa=fa_digits(d["period_end"]), fy_end_fa=fa_digits(d["fy_end"]),
                url=d["urls"].get(d["period_end"], ""))
    name = f"{safe(d['symbol'])}_{d['period_end'].replace('/', '-')}"
    f = outdir / f"{safe(d['symbol'])}.html"
    f.write_text(html_page(f"{d['symbol']} — عملکرد ماهانه", data, REPORT_JS, name), encoding="utf-8")
    return f


def write_index(results, outdir: Path, unit):
    rows = []
    for d in results:
        k, s = d["kpi"], d["spread"] or {}
        with_inv = [p for p in d["products"] if p["m_inv"] is not None]
        rows.append({"symbol": d["symbol"], "company": d["company"], "period": d["period_end"],
                     "period_fa": fa_digits(d["period_end"]), "file": f"{safe(d['symbol'])}.html",
                     "month": k["month"], "mom": k["mom"], "season": k["season"], "cumulative": k["cumulative"],
                     "coverage": k["coverage"], "inv_up": sum(p["m_inv"] > 0 for p in with_inv) if with_inv else None,
                     "n_products": len(with_inv), "margin": (s.get("last") or {}).get("margin") if s.get("ok") else None,
                     "spread_chg": s.get("change") if s.get("ok") else None})
    data = {"rows": rows, "unit": unit, "unit_div": UNITS[unit], "generated": jalali_now_str()}
    (outdir / "index.html").write_text(html_page("خلاصه‌ی عملکرد ماهانه", data, INDEX_JS, "summary"), encoding="utf-8")
    with open(outdir / "summary.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["نماد", "شرکت", "دوره", "فروش ماه (میلیون ریال)", "رشد ماهانه٪", "رشد فصلی٪", "رشد تجمعی٪",
                    "پوشش درآمد٪", "محصولات با افزایش موجودی", "حاشیه اسپرد٪", "تغییر اسپرد٪"])
        p = lambda x: "" if x is None else round(x * 100, 1)
        for r in rows:
            w.writerow([r["symbol"], r["company"], r["period"], r["month"] or "", p(r["mom"]), p(r["season"]),
                        p(r["cumulative"]), p(r["coverage"]), "" if r["inv_up"] is None else r["inv_up"],
                        p(r["margin"]), p(r["spread_chg"])])


# ── PNG با مرورگر نصب‌شده (بدون نیاز به اینترنت؛ صفحه کاملاً مستقل است)
def find_browser():
    env = os.environ
    cands = [Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
             Path(env.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
             Path(env.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
             Path(env.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
             Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
             Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    for c in cands:
        if c.exists():
            return str(c)
    for n in ("msedge", "google-chrome", "chrome", "chromium", "chromium-browser"):
        if shutil.which(n):
            return shutil.which(n)
    return None


def export_png(files, browser=None):
    browser = browser or find_browser()
    if not browser:
        log.warning("! Edge/Chrome not found; use the 'Save as PNG' button inside the report.")
        return []

    def one(f: Path):
        png = f.with_suffix(".png")
        prof = tempfile.mkdtemp(prefix="codal_png_")
        base = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                "--no-default-browser-check", f"--user-data-dir={prof}", "--force-device-scale-factor=2",
                "--virtual-time-budget=4000", "--allow-file-access-from-files"]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            base.append("--no-sandbox")
        url = f.resolve().as_uri() + "?shot=1"
        try:
            dom = subprocess.run(base + ["--window-size=1560,1000", "--dump-dom", url],
                                 capture_output=True, timeout=90).stdout
            m = re.search(rb'data-h="(\d+)"', dom)
            hgt = (int(m.group(1)) if m else 2400) + 120
            mw = re.search(rb'data-w="(\d+)"', dom)
            wid = int(mw.group(1)) if mw else 1560
            png.unlink(missing_ok=True)
            subprocess.run(base + [f"--window-size={wid},{hgt}", f"--screenshot={png}", url],
                           capture_output=True, timeout=90)
            return png if png.exists() and png.stat().st_size > 20000 else None
        except (subprocess.TimeoutExpired, OSError) as e:
            log.debug("PNG %s: %s", f.name, e)
            return None
        finally:
            shutil.rmtree(prof, ignore_errors=True)

    made = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        for f, png in zip(files, ex.map(one, files)):
            if png:
                made.append(png)
            else:
                log.warning("! PNG export failed for %s (use the button inside the report)", f.name)
    return made


# ═══════════════════════════════════════════════════════════════════════════
# ۸. خط لوله‌ی اصلی
# ═══════════════════════════════════════════════════════════════════════════
def needed_periods(letters, latest_rec, fast, fy_end_month):
    """کدام گزارش‌ها لازم‌اند؟ حالت سریع: ماه جاری، ماه قبل، پایان فصل قبل."""
    ye = year_end_of(latest_rec, fy_end_month)
    L = fiscal_pos(latest_rec["period_end"], ye)[1]
    qs = ((L - 1) // 3) * 3 + 1
    want = {(0, L), (0, L - 1) if L > 1 else (-1, 12)}
    if qs > 1:
        want.add((0, qs - 1))
    if not fast:
        want |= {(0, k) for k in range(1, L + 1)} | {(-1, 12)}
    return [x for x in letters if fiscal_pos(x["period_end"], ye) in want]


def run(symbols, args, store, http, spread_cfg):
    t0 = time.time()
    from_j, to_j = months_ago(args.months), jstr(jtoday())
    letters_by = {}

    # مرحله ۱: جست‌وجو (ترتیبی و آهسته؛ نمادهایی که اخیراً جست‌وجو شده‌اند از کش)
    if http:
        todo = [s for s in symbols if args.refresh or not store.recently_searched(s, args.search_ttl)]
        if len(todo) < len(symbols):
            log.info("- Search: %d symbol(s) were searched in the last %g h; using cache (--refresh to force)",
                     len(symbols) - len(todo), args.search_ttl)
        for s in todo:
            try:
                found = search_symbol(http, s, from_j, to_j)
                store.add_letters(s, found)
                if found:
                    store.mark_searched(s)
            except RateLimited as e:
                log.error("x %s", e)
                break
            except CodalBlocked as e:
                log.error("x %s: %s", s, e)
    for s in symbols:
        lets = [L for L in latest_per_period(store.letters(s).values()) if L["period_end"] >= from_j]
        if lets:
            letters_by[s] = lets
        else:
            log.warning("! %s: no monthly activity reports found%s", s, " (cache is empty)" if not http else "")
    log.info("- Search: %d symbol(s) with reports (%.1f s)", len(letters_by), time.time() - t0)

    def download(Ls):
        need = [L for L in Ls if not store.has_raw(L)]
        if not need or not http:
            return 0
        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(fetch_report, http, L["url"]): L for L in need}
            for fu in as_completed(futs):
                L = futs[fu]
                try:
                    store.save_raw(L, fu.result())
                except Exception as e:
                    log.debug("download %s %s: %s", L["symbol"], L["period_end"], e)
                done += 1
                if done % 5 == 0 or done == len(need):
                    print(f"\r  Downloading reports: {done}/{len(need)}", end="", flush=True)
        print()
        if getattr(http, "blocked", {}).get("report"):
            log.error("x %s", RATE_MSG)
        return len(need)

    # مرحله ۲: آخرین گزارش هر نماد (برای تشخیص سال مالی)
    t1 = time.time()
    n = download([lets[-1] for lets in letters_by.values()])
    latest = {}
    for s, lets in letters_by.items():
        ds = store.raw(lets[-1])
        r = parse_report(ds, lets[-1]["period_end"]) if ds else None
        if r:
            latest[s] = r
        else:
            log.warning("! %s: latest report (%s) could not be parsed -> run with --check", s, lets[-1]["period_end"])

    # مرحله ۳: گزارش‌های لازم دیگر
    plan = {s: needed_periods(letters_by[s], latest[s], args.fast, args.fy_end_month) for s in latest}
    n += download([L for Ls in plan.values() for L in Ls])
    log.info("- Download: %d new report(s) (%.1f s)", n, time.time() - t1)

    # مرحله ۴: محاسبه و خروجی
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    results, files = [], []
    for s in symbols:
        if s not in latest:
            continue
        recs = []
        for L in plan[s]:
            ds = store.raw(L)
            try:
                r = parse_report(ds, L["period_end"]) if ds else None
            except Exception:
                log.debug(traceback.format_exc())
                r = None
            if r:
                recs.append(r)
        try:
            urls = {L["period_end"]: L["url"] for L in plan[s]}
            d = compute(s, letters_by[s][-1]["company"] or s, recs, spread_cfg.get(s), args.fy_end_month, urls)
        except Exception:
            log.error("x %s: calculation error\n%s", s, traceback.format_exc())
            continue
        if d["kpi"]["month"] is None and d["kpi"]["ytd"] is None:
            log.error("x %s: sales could not be extracted -> run with --check", s)
            continue
        (outdir / "data").mkdir(exist_ok=True)
        (outdir / "data" / f"{safe(s)}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        files.append(write_report(d, outdir, args.unit))
        results.append(d)
        k = d["kpi"]
        log.info("  OK %-8s %s  MoM %s  Quarter %s  YTD %s  Coverage %s", s, d["period_end"],
                 *(("—" if v is None else f"{v * 100:+.1f}%") for v in (k["mom"], k["season"], k["cumulative"])),
                 "—" if k["coverage"] is None else f"{k['coverage'] * 100:.0f}%")
    if results:
        write_index(results, outdir, args.unit)
    pngs = export_png(files + ([outdir / "index.html"] if results else [])) if (args.png and files) else []
    log.info("Done: %d report(s)%s in %.1f s -> %s", len(files), f" and {len(pngs)} image(s)" if pngs else "",
             time.time() - t0, (outdir / "index.html").resolve())
    return results


def load_spread_cfg(path: Path):
    if not path.exists():
        return {}
    try:
        return {norm(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    except ValueError as e:
        log.warning("! spread.json could not be read: %s", e)
        return {}


# ── عیب‌یابی
def check_symbol(sym, store, http, args):
    print(f"\n════════ {sym} ════════")
    from_j = months_ago(args.months)
    if http:
        try:
            store.add_letters(sym, search_symbol(http, sym, from_j, jstr(jtoday())))
        except CodalBlocked as e:
            print("x Codal access:", e)
    lets = [L for L in latest_per_period(store.letters(sym).values()) if L["period_end"] >= from_j]
    print(f"Reports found: {len(lets)}")
    for L in lets[-6:]:
        if http and not store.has_raw(L):
            try:
                store.save_raw(L, fetch_report(http, L["url"]))
            except Exception as e:
                print("  download failed:", e)
        ds = store.raw(L)
        if not ds:
            print(f"  {L['period_end']}  {'not downloaded' if ds is None else 'page has no datasource'}  {L['url']}")
            continue
        r = parse_report(ds, L["period_end"])
        if not r:
            print(f"  {L['period_end']}  sales table not found; tables: {len(list(iter_tables(ds)))}")
            continue
        t = r["total"]
        g = lambda k: f"{t[k]:,.0f}" if t.get(k) is not None else "—"
        print(f"  {L['period_end']}  month={g('month')} ytd={g('ytd')} ytd_last_year={g('ytd_ly')} full_last_year={g('fy_ly')} "
              f"products={len(r['products'])} materials={len(r['materials'])}")
    if lets and store.raw(lets[-1]):
        pe = parse_jdate(lets[-1]["period_end"])
        print("\nColumn mapping in latest report (table titles are Codal's own Persian text):")
        for title, G in iter_tables(store.raw(lets[-1])):
            for metric in (metric_prod, metric_mat):
                a = analyse_table(G, pe, metric)
                if a and a["colmap"]:
                    print(f"  ┌ {title}  [{metric.__name__}]")
                    for col, (per, met) in sorted(a["colmap"].items()):
                        print(f"  │ {col:>3}: {per}/{met} ← {' | '.join(a['heads'].get(col, []))}")


# ── داده‌ی نمونه با ساختار کدال (برای --demo و تست)
def _demo_ds(pe, ye, prods, mats, vals):
    """vals: {دوره: ضریب مبلغ} ؛ هر محصول (نام، واحد، نرخ ریال، سهم، نسبت فروش به تولید)"""
    cells = []

    def add(r, k, v, span=1, grp="Body"):
        cells.append({"rowSequence": r, "columnSequence": k, "colSpan": span, "cellGroupName": grp, "value": v})
    py, pm, pd = pe
    prv = (py, pm - 1, 31) if pm > 1 else (py - 1, 12, 29)
    heads = {"prev_ytd_raw": f"از ابتدای سال مالی تا تاریخ {jstr(prv)}", "month": f"دوره یک ماهه منتهی به {jstr(pe)}",
             "ytd": f"از ابتدای سال مالی تا تاریخ {jstr(pe)}", "ytd_ly": f"از ابتدای سال مالی تا تاریخ {jstr((py - 1, pm, pd))}",
             "fy_ly": f"وضعیت محصول- سال مالی منتهی به {jstr((ye[0] - 1, ye[1], 29))}"}
    leaf = ["تعداد تولید", "تعداد فروش", "نرخ فروش (ریال)", "مبلغ فروش (میلیون ریال)"]
    add(1, 1, "شرح محصول", 1, "Header")
    add(1, 2, "واحد", 1, "Header")
    for g, per in enumerate(heads):
        add(1, 3 + g * 4, heads[per], 4, "Header")
        for j, t in enumerate(leaf):
            add(2, 3 + g * 4 + j, t, 1, "Header")
    r, tot = 3, defaultdict(float)
    add(r, 1, "فروش داخلی:")
    for name, unit, rate, share, sr in prods:
        r += 1
        add(r, 1, name)
        add(r, 2, unit)
        for g, per in enumerate(heads):
            a = vals[per][0] * share
            rr = rate * vals[per][1]
            q = a * 1e6 / rr
            add(r, 3 + g * 4, f"{q / sr:,.0f}")
            add(r, 4 + g * 4, f"{q:,.0f}")
            add(r, 5 + g * 4, f"{rr:,.0f}")
            add(r, 6 + g * 4, f"{a:,.0f}")
            tot[per] += a
    r += 1
    add(r, 1, "جمع")
    for g, per in enumerate(heads):
        add(r, 6 + g * 4, f"{tot[per]:,.0f}")
    t1 = {"title_Fa": "تولید و فروش", "cells": cells}
    mc = []
    add2 = lambda r, k, v, span=1, grp="Body": mc.append({"rowSequence": r, "columnSequence": k, "colSpan": span,
                                                          "cellGroupName": grp, "value": v})
    add2(1, 1, "شرح", 1, "Header")
    add2(1, 2, "واحد", 1, "Header")
    for g, per in enumerate(("month", "ytd")):
        add2(1, 3 + g * 3, heads[per] + " - مصرف", 3, "Header")
        for j, t in enumerate(["مقدار مصرف", "نرخ مصرف (ریال)", "مبلغ مصرف (میلیون ریال)"]):
            add2(2, 3 + g * 3 + j, t, 1, "Header")
    for i, (name, unit, rate, per_prod) in enumerate(mats):
        add2(3 + i, 1, name)
        add2(3 + i, 2, unit)
        for g, per in enumerate(("month", "ytd")):
            pq = sum(vals[per][0] * p[3] * 1e6 / (p[2] * vals[per][1]) / p[4] for p in prods[:1])
            q = pq * per_prod
            rr = rate * vals[per][2]
            add2(3 + i, 3 + g * 3, f"{q:,.0f}")
            add2(3 + i, 4 + g * 3, f"{rr:,.0f}")
            add2(3 + i, 5 + g * 3, f"{q * rr / 1e6:,.0f}")
    t2 = {"title_Fa": "مصرف مواد اولیه", "cells": mc}
    return [{"yearEndToDate": jstr(ye), "sheets": [{"title_Fa": "فعالیت ماهانه", "tables": [t1, t2]}]}]


def demo_records():
    random.seed(11)
    prods = [("ورق گرم", "تن", 4.1e8, 0.46, 1.04), ("ورق سرد", "تن", 4.9e8, 0.22, 0.97), ("اسلب", "تن", 3.3e8, 0.17, 1.08),
             ("ورق گالوانیزه", "تن", 5.6e8, 0.09, 0.93), ("ورق قلع‌اندود", "تن", 6.2e8, 0.06, 1.0)]
    mats = [("آهن اسفنجی", "تن", 1.35e8, 1.12), ("قراضه", "تن", 1.1e8, 0.15)]
    recs, ytd, ly = [], 0.0, [0.0]
    lymonth = [9.0e6 * (1 + 0.12 * math.sin(m / 2)) for m in range(1, 13)]
    for m in range(1, 7):
        amount = lymonth[m - 1] * 1.32 * random.uniform(0.9, 1.12)
        prev, ytd = ytd, ytd + amount
        pr, mr = 1 + 0.03 * m + random.uniform(-.02, .02), 1 + 0.045 * m
        vals = {"prev_ytd_raw": (prev or 1, pr, mr), "month": (amount, pr, mr), "ytd": (ytd, pr, mr),
                "ytd_ly": (sum(lymonth[:m]), 0.8, 0.8), "fy_ly": (sum(lymonth), 0.85, 0.85)}
        pe = (1405, m, 31)
        recs.append(parse_report(_demo_ds(pe, (1405, 12, 29), prods, mats, vals), jstr(pe)))
    return recs


# ── راه‌اندازی
def setup_logging(verbose):
    log.setLevel(logging.DEBUG)
    fh = logging.FileHandler(HERE / "run.log", mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s"))
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    log.handlers[:] = [fh, ch]


def main():
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Codal monthly activity report monitor")
    ap.add_argument("symbols", nargs="*", help="symbol(s) in Persian, e.g. فولاد")
    ap.add_argument("--all", action="store_true", help="all symbols that published a monthly report recently")
    ap.add_argument("--fast", action="store_true", help="only 3 reports per symbol (12-month chart will be partial)")
    ap.add_argument("--png", action="store_true", help="also export PNG using installed Edge/Chrome")
    ap.add_argument("--check", action="store_true", help="diagnose symbol(s)")
    ap.add_argument("--offline", action="store_true", help="use cache only, no internet")
    ap.add_argument("--demo", action="store_true", help="sample report with synthetic data")
    ap.add_argument("--workers", type=int, default=4, help="parallel downloads (default 4)")
    ap.add_argument("--rate", type=float, default=3.0, help="max report downloads per second (default 3)")
    ap.add_argument("--search-ttl", type=float, default=6.0, help="skip re-searching a symbol for N hours (default 6)")
    ap.add_argument("--refresh", action="store_true", help="always search Codal again (ignore --search-ttl)")
    ap.add_argument("--months", type=int, default=15, help="search window in months (default 15)")
    ap.add_argument("--unit", choices=list(UNIT_KEYS), default="btoman", help="mrial | brial | btoman")
    ap.add_argument("--fy-end-month", type=int, default=12)
    ap.add_argument("--spread", default=str(HERE / "spread.json"))
    ap.add_argument("--data", default=str(HERE / "data"))
    ap.add_argument("--out", default=str(HERE / "reports"))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    args.unit = UNIT_KEYS[args.unit]
    setup_logging(args.verbose)

    if args.demo:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        d = compute("فولاد", "نمونه‌ی ساختگی (دمو) — داده‌ها واقعی نیستند", demo_records())
        f = write_report(d, out, args.unit)
        write_index([d], out, args.unit)
        log.info("✓ %s", f)
        if args.png:
            for p in export_png([f, out / "index.html"]):
                log.info("✓ %s", p)
        return 0

    store = Store(Path(args.data))
    http = None if args.offline else Http(rate=args.rate)
    if ".zip" in str(HERE).lower() or "\\temp\\" in str(HERE).lower():
        log.warning("! You are running the script from inside a zip / temp folder:\n  %s\n"
                    "  Extract it to a normal folder (e.g. Documents) - otherwise the cache and font are lost after\n"
                    "  every run and every run re-downloads everything (which triggers Codal's rate limit).", HERE)
    symbols = [norm(s) for s in args.symbols if norm(s)]
    if args.check and not symbols:
        symbols = read_watchlist()
    if args.all:
        if not http:
            symbols = sorted(p.name for p in Path(args.data).iterdir() if p.is_dir())
        else:
            try:
                letters = search_all(http, months_ago(1)[:8] + "01", jstr(jtoday()), args.workers)
            except CodalBlocked as e:
                log.error("✗ %s", e)
                return 1
            by = defaultdict(list)
            for L in letters:
                by[L["symbol"]].append(L)
            for s, ls in by.items():
                store.add_letters(s, ls)
            symbols = sorted(by)
            log.info("- %d symbols published monthly reports recently", len(symbols))
        args.fast = True
    spread_cfg = load_spread_cfg(Path(args.spread))
    if symbols:                                   # نماد در خط فرمان داده شده
        symbols = list(dict.fromkeys(symbols))
        if args.check:
            for s in symbols:
                check_symbol(s, store, http, args)
            return 0
        res = run(symbols, args, store, http, spread_cfg)
        if res and len(symbols) == 1:
            open_file(Path(args.out) / f"{safe(symbols[0])}.html")
        return 0 if res else 2
    return interactive(args, store, http, spread_cfg)


def read_watchlist():
    wl = HERE / "watchlist.txt"
    return [norm(s) for s in wl.read_text(encoding="utf-8").split() if norm(s)] if wl.exists() else []


def open_file(p: Path):
    """باز کردن گزارش در مرورگر پیش‌فرض."""
    try:
        if sys.platform == "win32":
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)])
        else:
            subprocess.run(["xdg-open", str(p)], capture_output=True)
    except Exception:
        pass


def interactive(args, store, http, spread_cfg):
    """حالت پرسشی: نام نماد با input گرفته می‌شود و گزارش باز می‌شود."""
    print("\n" + "═" * 60)
    print("  Codal monthly activity report")
    print("  Enter symbol name(s) in Persian, separated by spaces")
    print("  w = run watchlist.txt  |  q or empty Enter = quit")
    print("═" * 60)
    while True:
        try:
            ans = input("\nSymbol: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not ans or ans.lower() in ("q", "exit") or ans == "خروج":
            break
        symbols = read_watchlist() if ans.lower() == "w" else [norm(x) for x in ans.split() if norm(x)]
        symbols = list(dict.fromkeys(symbols))
        if not symbols:
            print("watchlist.txt is empty or missing.")
            continue
        try:
            res = run(symbols, args, store, http, spread_cfg)
        except Exception:
            log.error("Error:\n%s", traceback.format_exc())
            continue
        if res:
            out = Path(args.out)
            open_file(out / (f"{safe(symbols[0])}.html" if len(symbols) == 1 else "index.html"))
    print("Bye.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
