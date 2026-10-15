"""ذخیره‌ی داده‌های کدال و قیمت‌ها در SQLite (فایل data/bourse.db کنار app.py)"""
import os
import sqlite3
import threading
from datetime import datetime

from .text import title_period

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bourse.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
    symbol TEXT PRIMARY KEY, name TEXT, isic TEXT, type INTEGER, state INTEGER, updated TEXT
);
-- همه‌ی اطلاعیه‌های دیده‌شده (بدون محتوا)؛ period_end و months از عنوان (برای پیدا کردن اطلاعیه‌ی یک دوره بدون جستجو)
CREATE TABLE IF NOT EXISTS letters (
    tracing_no INTEGER PRIMARY KEY, symbol TEXT, company TEXT, title TEXT, letter_code TEXT,
    letter_type INTEGER, sent TEXT, published TEXT, url TEXT, excel_url TEXT, pdf_url TEXT,
    attachment_url TEXT, is_correction INTEGER, fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_letters_sym ON letters(symbol, published);

-- گزارش فعالیت ماهانه؛ مبالغ میلیون ریال
CREATE TABLE IF NOT EXISTS monthly_reports (
    id INTEGER PRIMARY KEY, tracing_no INTEGER UNIQUE, symbol TEXT, template TEXT,
    period_end TEXT, year_end TEXT, fiscal_year INTEGER, fiscal_month INTEGER,
    is_correction INTEGER, published TEXT, total REAL, discounts REAL, fetched_at TEXT
);
-- آخرین نسخه‌ی هر دوره (نمای monthly_latest) و فیلتر ماه (رتبه‌بندی ماهانه) با این دو شاخص سریع است
CREATE INDEX IF NOT EXISTS ix_monthly_sym ON monthly_reports(symbol, period_end, published);
CREATE INDEX IF NOT EXISTS ix_monthly_period ON monthly_reports(period_end);
CREATE TABLE IF NOT EXISTS monthly_items (
    report_id INTEGER REFERENCES monthly_reports(id) ON DELETE CASCADE,
    section TEXT, name TEXT, unit TEXT, made REAL, sold REAL, price REAL, amount REAL
);
CREATE INDEX IF NOT EXISTS ix_mitems ON monthly_items(report_id);

-- صورت سود و زیان؛ تجمعی از ابتدای سال، میلیون ریال، هزینه‌ها منفی، EPS ریال
CREATE TABLE IF NOT EXISTS fin_reports (
    id INTEGER PRIMARY KEY, tracing_no INTEGER, symbol TEXT, template TEXT,
    period_end TEXT, year_end TEXT, fiscal_year INTEGER, months INTEGER,
    consolidated INTEGER, audited INTEGER, is_correction INTEGER, published TEXT,
    rev REAL, cogs REAL, gross REAL, sga REAL, other_op REAL, op_profit REAL, fin REAL,
    non_op REAL, pretax REAL, tax REAL, net REAL, eps REAL, capital REAL, fetched_at TEXT,
    UNIQUE(tracing_no, consolidated)   -- یک اطلاعیه‌ی تلفیقی هر دو صورت را دارد
);
CREATE INDEX IF NOT EXISTS ix_fin_sym ON fin_reports(symbol, consolidated, period_end, months, published);
CREATE TABLE IF NOT EXISTS fin_lines (
    report_id INTEGER REFERENCES fin_reports(id) ON DELETE CASCADE,
    row_seq INTEGER, label TEXT, value REAL
);
CREATE INDEX IF NOT EXISTS ix_flines ON fin_lines(report_id);

-- گزارش‌هایی که خوانده نشدند (قالب قدیمی یا ناشناخته) تا دوباره درخواست نشوند
-- kind: monthly | financial | financial_cons
CREATE TABLE IF NOT EXISTS skipped (
    tracing_no INTEGER, symbol TEXT, kind TEXT, reason TEXT, at TEXT,
    PRIMARY KEY(tracing_no, kind)
);

-- آخرین بار که برای یک نوع داده‌ی نماد به کدال رجوع شد (اول دیتابیس، بعد کدال: codal/fresh.py)
-- kind: monthly | financial | mrank | screener | mrank_feed | screener_prev ؛ symbol خالی = کل بازار
CREATE TABLE IF NOT EXISTS checks (
    kind TEXT, symbol TEXT, checked_at TEXT, PRIMARY KEY(kind, symbol)
);

-- قیمت‌های TSETMC (tsetmc.py): فقط آخرین قیمت هر نماد + یک ردیف وضعیت بازار
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT PRIMARY KEY, name TEXT, ins_code TEXT,
    last REAL, close REAL, yesterday REAL, first REAL, low REAL, high REAL,
    volume REAL, value REAL, trades REAL, eps REAL, pe REAL, time TEXT
);
CREATE TABLE IF NOT EXISTS market (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    date TEXT, time TEXT, state TEXT, idx REAL, idx_change REAL, count INTEGER, updated_at TEXT
);

-- آخرین نسخه‌ی هر دوره (اگر اصلاحیه آمده باشد، اصلاحیه)
CREATE VIEW IF NOT EXISTS monthly_latest AS
SELECT * FROM monthly_reports m WHERE m.published = (
    SELECT MAX(x.published) FROM monthly_reports x
    WHERE x.symbol = m.symbol AND x.period_end = m.period_end);

CREATE VIEW IF NOT EXISTS fin_latest AS
SELECT * FROM fin_reports f WHERE f.published = (
    SELECT MAX(x.published) FROM fin_reports x
    WHERE x.symbol = f.symbol AND x.period_end = f.period_end
      AND x.months = f.months AND x.consolidated = f.consolidated);
"""


def now():
    return datetime.now().isoformat(timespec="seconds")


# ستون‌هایی که بعداً اضافه شدند (دیتابیس قدیمی خودکار ستون می‌گیرد)
#   fin_reports — rev_ly, net_ly: مدت مشابه سال قبل | net_ly_full: کل سال مالی قبل (ارقام تجدید ارائه‌شده)
#   monthly_reports — جمع‌های تجمعی: تا همین ماه، تا ماه قبل (اصلاح‌شده)، مدت مشابه سال قبل
#   letters — پایان دوره و تعداد ماه‌های دوره از عنوان
FIN_EXTRA = {"rev_ly": "REAL", "net_ly": "REAL", "net_ly_full": "REAL", "ly_end": "TEXT", "ly_full_end": "TEXT"}
MONTHLY_EXTRA = {"cum": "REAL", "cum_prev": "REAL", "cum_ly": "REAL"}
LETTER_EXTRA = {"period_end": "TEXT", "months": "INTEGER"}

_ready = set()               # دیتابیس‌هایی که در این اجرا ساختار/مهاجرتشان بررسی شده
_ready_lock = threading.Lock()


def _prepare(con):
    """ساختار، ستون‌های تازه، شاخص‌ها و مقداردهی ستون‌های تازه — یک بار در هر اجرای برنامه"""
    con.executescript(SCHEMA)
    for table, extra in (("fin_reports", FIN_EXTRA), ("monthly_reports", MONTHLY_EXTRA), ("letters", LETTER_EXTRA)):
        cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        for c, t in extra.items():
            if c not in cols:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {c} {t}")
    con.execute("CREATE INDEX IF NOT EXISTS ix_letters_period ON letters(letter_type, period_end)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_letters_sym_period ON letters(symbol, letter_type, period_end)")
    # اطلاعیه‌های ذخیره‌شده قبل از ستون period_end
    rows = con.execute("SELECT tracing_no, title FROM letters WHERE period_end IS NULL AND title IS NOT NULL").fetchall()
    con.executemany("UPDATE letters SET period_end=?, months=? WHERE tracing_no=?",
                    [(*title_period(r["title"]), r["tracing_no"]) for r in rows])
    con.commit()


def connect(path=None):
    """
    اتصال سبک: ساختار و مهاجرت فقط بار اول در هر اجرا. حالت WAL ← خواندن صفحه‌ها هم‌زمان با نوشتن کار پس‌زمینه
    بدون قفل؛ timeout: اگر نوشتن دیگری در جریان است، تا ۳۰ ثانیه صبر به جای خطای «database is locked»
    """
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA synchronous = NORMAL")
    con.execute("PRAGMA temp_store = MEMORY")
    con.execute("PRAGMA cache_size = -16000")          # حدود ۱۶ مگابایت حافظه‌ی صفحه‌ها
    if path not in _ready:
        with _ready_lock:
            if path not in _ready:
                con.execute("PRAGMA journal_mode = WAL")
                _prepare(con)
                _ready.add(path)
    return con


def checkpoint(path=None):
    """ادغام فایل -wal در فایل اصلی (قبل از کپی/پشتیبان‌گیری از bourse.db)"""
    con = sqlite3.connect(path or DB_PATH, timeout=30)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()


def mark_checked(con, kind, symbol=""):
    """ثبت زمان رجوع به کدال (بعد از کار موفق)"""
    con.execute("INSERT OR REPLACE INTO checks VALUES(?,?,?)", (kind, symbol or "", now()))
    con.commit()


def checked_at(con, kind, symbol=""):
    r = con.execute("SELECT checked_at FROM checks WHERE kind=? AND symbol=?", (kind, symbol or "")).fetchone()
    return r["checked_at"] if r else None


def save_symbols(con, rows):
    t = now()
    con.executemany(
        "INSERT INTO symbols(symbol, name, isic, type, state, updated) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(symbol) DO UPDATE SET name=excluded.name, isic=excluded.isic, "
        "type=excluded.type, state=excluded.state, updated=excluded.updated",
        [(r["symbol"], r["name"], r["isic"], r["type"], r["state"], t) for r in rows])
    con.commit()


LETTER_COLS = ("tracing_no", "symbol", "company", "title", "letter_code", "letter_type", "sent", "published",
               "url", "excel_url", "pdf_url", "attachment_url", "is_correction", "fetched_at", "period_end", "months")


def save_letter(con, x):
    period, months = title_period(x["title"])
    con.execute(
        f"INSERT OR REPLACE INTO letters({','.join(LETTER_COLS)}) VALUES({','.join('?' * len(LETTER_COLS))})",
        (x["tracing_no"], x["symbol"], x["company"], x["title"], x["letter_code"], x["letter_type"],
         x["sent"], x["published"], x["url"], x["excel_url"], x["pdf_url"], x["attachment_url"],
         int(x["is_correction"]), now(), period, months))


def _target(kind):
    """نوع کار ← (جدول، شرط اضافه)"""
    if kind == "monthly":
        return "monthly_reports", ""
    return "fin_reports", f" AND consolidated={int(kind == 'financial_cons')}"


def is_done(con, tracing_no, kind):
    """این اطلاعیه برای این نوع کار قبلاً خوانده یا رد شده است؟"""
    table, extra = _target(kind)
    q = (f"SELECT 1 FROM {table} WHERE tracing_no=?{extra} UNION ALL "
         "SELECT 1 FROM skipped WHERE tracing_no=? AND kind=?")
    return con.execute(q, (tracing_no, tracing_no, kind)).fetchone() is not None


def forget(con, tracing_no, kind):
    """پاک کردن نتیجه‌ی قبلی برای خواندن دوباره (--force)"""
    table, extra = _target(kind)
    con.execute(f"DELETE FROM {table} WHERE tracing_no=?{extra}", (tracing_no,))
    con.execute("DELETE FROM skipped WHERE tracing_no=? AND kind=?", (tracing_no, kind))


def save_skip(con, letter, kind, reason):
    con.execute("INSERT OR REPLACE INTO skipped(tracing_no, symbol, kind, reason, at) VALUES(?,?,?,?,?)",
                (letter["tracing_no"], letter["symbol"], kind, str(reason), now()))
    con.commit()


def save_monthly(con, letter, rep):
    con.execute("DELETE FROM monthly_reports WHERE tracing_no=?", (letter["tracing_no"],))   # خواندن دوباره
    cur = con.execute(
        "INSERT INTO monthly_reports(tracing_no, symbol, template, period_end, year_end, fiscal_year, "
        "fiscal_month, is_correction, published, total, discounts, cum, cum_prev, cum_ly, fetched_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (letter["tracing_no"], letter["symbol"], rep["template"], rep["period_end"], rep["year_end"],
         rep["fiscal_year"], rep["fiscal_month"], int(letter["is_correction"]), letter["published"],
         rep["total"], rep["discounts"], rep.get("cum"), rep.get("cum_prev"), rep.get("cum_ly"), now()))
    con.executemany(
        "INSERT INTO monthly_items VALUES(?,?,?,?,?,?,?,?)",
        [(cur.lastrowid, i["section"], i["name"], i["unit"], i["made"], i["sold"], i["price"], i["amount"])
         for i in rep["items"]])
    con.commit()


FIN_FIELDS = ("rev", "cogs", "gross", "sga", "other_op", "op_profit", "fin",
              "non_op", "pretax", "tax", "net", "eps", "capital")


def save_financial(con, letter, rep):
    cols = ("tracing_no, symbol, template, period_end, year_end, fiscal_year, months, consolidated, "
            "audited, is_correction, published, " + ", ".join(FIN_FIELDS) + ", "
            + ", ".join(FIN_EXTRA) + ", fetched_at")
    vals = (letter["tracing_no"], letter["symbol"], rep["template"], rep["period_end"], rep["year_end"],
            rep["fiscal_year"], rep["months"], int(rep["consolidated"]), int(rep["audited"]),
            int(letter["is_correction"]), letter["published"],
            *[rep.get(f) for f in FIN_FIELDS], *[rep.get(f) for f in FIN_EXTRA], now())
    # خواندن دوباره (مثلاً برای ستون‌های مقایسه‌ای): نسخه‌ی قبلی بعد از دریافت موفق جایگزین می‌شود
    con.execute("DELETE FROM fin_reports WHERE tracing_no=? AND consolidated=?",
                (letter["tracing_no"], int(rep["consolidated"])))
    cur = con.execute(f"INSERT INTO fin_reports({cols}) VALUES({','.join('?' * len(vals))})", vals)
    con.executemany("INSERT INTO fin_lines VALUES(?,?,?,?)",
                    [(cur.lastrowid, l["row_seq"], l["label"], l["value"]) for l in rep["lines"]])
    con.commit()
