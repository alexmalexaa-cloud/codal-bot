"""
قیمت‌های بازار از TSETMC (سایت مدیریت فناوری بورس تهران)
- دیده‌بان بازار: قیمت همه‌ی نمادها با یک درخواست (GetMarketWatch)
- نمای کلی بازار: تاریخ و ساعت آخرین معامله، وضعیت باز/بسته، شاخص کل (GetMarketOverview)
قیمت‌ها به ریال؛ در جدول prices دیتابیس bourse.db ذخیره می‌شوند (فقط آخرین قیمت هر نماد).
"""
import json
import urllib.error
import urllib.request
from datetime import datetime

from codal.text import g2j, norm

API = "https://cdn.tsetmc.com/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}
# نوع اوراق در دیده‌بان: ۱ و ۲ بورس و فرابورس، ۴ حق تقدم، ۸ بازار پایه، ۵ اوراق بدهی،
# ۳ و ۷ سایر؛ ۶ (اختیار معامله، بیش از ۱۶۰۰ ردیف) لازم نیست
PAPER_TYPES = [1, 2, 3, 4, 5, 7, 8]


class PriceError(RuntimeError):
    """دریافت قیمت ناموفق؛ پیام فارسی برای نمایش"""


def _get(path, timeout=60):
    try:
        req = urllib.request.Request(API + path, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
        raise PriceError(f"اتصال به TSETMC برقرار نشد ({e})") from e


def _jdate(deven):
    """20261007 ← «1405/07/15»"""
    if not deven:
        return ""
    s = str(int(deven))
    return "%04d/%02d/%02d" % g2j(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _time(heven):
    """123001 ← «12:30»"""
    if not heven:
        return ""
    s = "%06d" % int(heven)
    return f"{s[:2]}:{s[2:4]}"


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def market_watch():
    """قیمت همه‌ی نمادها؛ اگر نمادی چند ردیف داشت، ردیف پرحجم‌تر می‌ماند"""
    q = "".join(f"&paperTypes%5B{i}%5D={p}" for i, p in enumerate(PAPER_TYPES))
    data = _get("/ClosingPrice/GetMarketWatch?market=0&industrialGroup=&showTraded=false"
                "&withBestLimits=false&hEven=0&RefID=0" + q)
    rows = data.get("marketwatch") or []
    if not rows:
        raise PriceError("TSETMC دیده‌بان خالی برگرداند")
    out = {}
    for x in rows:
        sym = norm(x.get("lva"))
        if not sym:
            continue
        r = {
            "symbol": sym, "name": norm(x.get("lvc")), "ins_code": str(x.get("insCode") or ""),
            "last": _num(x.get("pdv")), "close": _num(x.get("pcl")), "yesterday": _num(x.get("py")),
            "first": _num(x.get("pf")), "low": _num(x.get("pmn")), "high": _num(x.get("pmx")),
            "volume": _num(x.get("qtj")), "value": _num(x.get("qtc")), "trades": _num(x.get("ztt")),
            "eps": _num(x.get("eps")), "pe": _num(x.get("pe")), "time": _time(x.get("hEven")),
        }
        if sym not in out or (r["volume"] or 0) > (out[sym]["volume"] or 0):
            out[sym] = r
    return list(out.values())


def overview():
    """تاریخ و ساعت آخرین فعالیت بازار، وضعیت و شاخص کل"""
    m = (_get("/MarketData/GetMarketOverview/1") or {}).get("marketOverview") or {}
    return {
        "date": _jdate(m.get("marketActivityDEven")),
        "time": _time(m.get("marketActivityHEven")),
        "state": norm(m.get("marketStateTitle")),
        "index": _num(m.get("indexLastValue")),
        "index_change": _num(m.get("indexChange")),
    }


# ---------- دیتابیس (جدول‌های prices و market در codal/db.py ساخته می‌شوند) ----------
COLS = ("symbol", "name", "ins_code", "last", "close", "yesterday", "first", "low", "high",
        "volume", "value", "trades", "eps", "pe", "time")


def refresh(con):
    """دریافت و ذخیره‌ی قیمت‌ها؛ خروجی وضعیت بازار"""
    rows = market_watch()
    try:
        ov = overview()
    except PriceError:   # نبودِ تاریخ بازار مانع ذخیره‌ی قیمت‌ها نمی‌شود
        ov = {"date": "", "time": "", "state": "", "index": None, "index_change": None}
    con.execute("DELETE FROM prices")
    con.executemany(f"INSERT INTO prices({','.join(COLS)}) VALUES({','.join('?' * len(COLS))})",
                    [tuple(r[c] for c in COLS) for r in rows])
    con.execute("INSERT OR REPLACE INTO market VALUES(1,?,?,?,?,?,?,?)",
                (ov["date"], ov["time"], ov["state"], ov["index"], ov["index_change"], len(rows),
                 datetime.now().isoformat(timespec="seconds")))
    con.commit()
    return status(con)


def status(con):
    """وضعیت آخرین دریافت؛ age = چند ثانیه پیش (None اگر هنوز دریافت نشده)"""
    m = con.execute("SELECT * FROM market WHERE id=1").fetchone()
    if not m:
        return {"updated_at": None, "age": None}
    out = dict(m)
    out["age"] = (datetime.now() - datetime.fromisoformat(m["updated_at"])).total_seconds()
    return out


def prices_for(con, symbols):
    """نماد ← قیمت (با درصد تغییر پایانی نسبت به دیروز)"""
    symbols = list(dict.fromkeys(symbols))
    out = {}
    for i in range(0, len(symbols), 500):          # سقف تعداد پارامتر SQLite
        part = symbols[i:i + 500]
        q = "SELECT * FROM prices WHERE symbol IN (%s)" % ",".join("?" * len(part))
        for r in con.execute(q, part):
            p = dict(r)
            p["change"] = (p["close"] / p["yesterday"] - 1) * 100 if p["close"] and p["yesterday"] else None
            out[p["symbol"]] = p
    return out
