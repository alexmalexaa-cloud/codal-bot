"""
داده‌های کاربر: واچ‌لیست و پرتفوی‌ها (یک پرتفوی برای هر مشتری)
در فایل جدای data/user.db تا پاک کردن یا ساختن دوباره‌ی دیتابیس کدال به آن‌ها آسیب نزند.
قیمت‌ها به ریال؛ هر پرتفوی جدا با روش میانگین موزون بهای خرید.
"""
import os
import sqlite3
from datetime import datetime

USER_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "user.db")
DEFAULT_NAME = "پرتفوی من"

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY, added_at TEXT
);
CREATE TABLE IF NOT EXISTS portfolios (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,               -- نام مشتری
    note TEXT,                               -- کد معاملاتی، تلفن، توضیح
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    portfolio_id INTEGER NOT NULL DEFAULT 1,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty REAL NOT NULL CHECK (qty > 0),
    price REAL NOT NULL CHECK (price > 0),   -- ریال برای هر سهم
    fee REAL NOT NULL DEFAULT 0,             -- کارمزد کل معامله، ریال
    date TEXT,                               -- تاریخ شمسی ۱۴۰۵/۰۷/۱۵
    note TEXT,
    created_at TEXT
);
"""


class StoreError(ValueError):
    """خطای ورودی کاربر؛ پیامش مستقیم نمایش داده می‌شود"""


_ready = set()          # ساختار و مهاجرت فقط بار اول در هر اجرای برنامه


def connect():
    os.makedirs(os.path.dirname(USER_DB), exist_ok=True)
    con = sqlite3.connect(USER_DB, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    if USER_DB not in _ready:
        con.executescript(SCHEMA)
        _migrate(con)
        _ready.add(USER_DB)
    return con


def _migrate(con):
    """
    دیتابیس نسخه‌ی قبل (یک پرتفوی) ستون portfolio_id نداشت:
    ستون اضافه و همه‌ی معاملات قبلی به پرتفوی شماره‌ی ۱ («پرتفوی من») داده می‌شوند.
    همیشه دست‌کم یک پرتفوی وجود دارد.
    """
    cols = [r["name"] for r in con.execute("PRAGMA table_info(trades)")]
    if "portfolio_id" not in cols:
        con.execute("ALTER TABLE trades ADD COLUMN portfolio_id INTEGER NOT NULL DEFAULT 1")
    con.execute("CREATE INDEX IF NOT EXISTS ix_trades_pf ON trades(portfolio_id, symbol)")
    if not con.execute("SELECT 1 FROM portfolios LIMIT 1").fetchone():
        con.execute("INSERT INTO portfolios(id, name, note, created_at) VALUES(1, ?, '', ?)",
                    (DEFAULT_NAME, _now()))
    con.commit()


def _now():
    return datetime.now().isoformat(timespec="seconds")


# ---------- واچ‌لیست ----------
def watch_symbols(con):
    return [r["symbol"] for r in con.execute("SELECT symbol FROM watchlist ORDER BY added_at")]


def watch_add(con, symbol):
    con.execute("INSERT OR IGNORE INTO watchlist VALUES(?, ?)", (symbol, _now()))
    con.commit()


def watch_remove(con, symbol):
    con.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))
    con.commit()


# ---------- پرتفوی‌ها (مشتری‌ها) ----------
def portfolios(con):
    return [dict(r) for r in con.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM trades t WHERE t.portfolio_id = p.id) AS trade_count "
        "FROM portfolios p ORDER BY p.id")]


def portfolio(con, pid):
    row = con.execute("SELECT * FROM portfolios WHERE id=?", (pid,)).fetchone()
    if not row:
        raise StoreError("پرتفوی پیدا نشد")
    return dict(row)


def _clean_name(name):
    name = (name or "").strip()
    if not name:
        raise StoreError("نام مشتری را وارد کنید")
    if len(name) > 80:
        raise StoreError("نام مشتری طولانی است")
    return name


def portfolio_add(con, name, note=""):
    name = _clean_name(name)
    try:
        cur = con.execute("INSERT INTO portfolios(name, note, created_at) VALUES(?,?,?)",
                          (name, (note or "").strip(), _now()))
    except sqlite3.IntegrityError:
        raise StoreError(f"پرتفوی «{name}» از قبل وجود دارد")
    con.commit()
    return cur.lastrowid


def portfolio_update(con, pid, name, note=""):
    portfolio(con, pid)
    name = _clean_name(name)
    try:
        con.execute("UPDATE portfolios SET name=?, note=? WHERE id=?", (name, (note or "").strip(), pid))
    except sqlite3.IntegrityError:
        raise StoreError(f"پرتفوی «{name}» از قبل وجود دارد")
    con.commit()


def portfolio_delete(con, pid):
    """حذف پرتفوی همراه همه‌ی معاملاتش؛ آخرین پرتفوی حذف نمی‌شود"""
    portfolio(con, pid)
    if con.execute("SELECT COUNT(*) FROM portfolios").fetchone()[0] <= 1:
        raise StoreError("دست‌کم یک پرتفوی باید بماند")
    con.execute("DELETE FROM trades WHERE portfolio_id=?", (pid,))
    con.execute("DELETE FROM portfolios WHERE id=?", (pid,))
    con.commit()


# ---------- معاملات و موجودی ----------
def trades(con, pid=None, symbol=None):
    """معاملات یک پرتفوی (یا همه وقتی pid=None) به ترتیب تاریخ"""
    where, args = [], []
    if pid is not None:
        where.append("portfolio_id=?")
        args.append(pid)
    if symbol:
        where.append("symbol=?")
        args.append(symbol)
    q = "SELECT * FROM trades" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY date, id"
    return [dict(r) for r in con.execute(q, args)]


def _positions_from(rows):
    """
    جمع معاملات هر نماد به روش میانگین موزون:
    خرید ← بهای تمام‌شده = تعداد × قیمت + کارمزد؛ فروش ← سود محقق‌شده = دریافتی − بهای میانگین
    """
    out = {}
    for t in rows:
        p = out.setdefault(t["symbol"], {"symbol": t["symbol"], "qty": 0.0, "cost": 0.0,
                                         "realized": 0.0, "trades": 0})
        p["trades"] += 1
        if t["side"] == "buy":
            p["qty"] += t["qty"]
            p["cost"] += t["qty"] * t["price"] + t["fee"]
        else:
            avg = p["cost"] / p["qty"] if p["qty"] else 0
            p["realized"] += t["qty"] * t["price"] - t["fee"] - avg * t["qty"]
            p["cost"] -= avg * t["qty"]
            p["qty"] -= t["qty"]
    for p in out.values():
        if abs(p["qty"]) < 1e-9:
            p["qty"], p["cost"] = 0.0, 0.0
        p["avg"] = p["cost"] / p["qty"] if p["qty"] else None
    return sorted(out.values(), key=lambda p: (-p["cost"], p["symbol"]))


def positions(con, pid):
    """موجودی یک پرتفوی"""
    return _positions_from(trades(con, pid))


def all_positions(con):
    """پرتفوی ← موجودی‌هایش (میانگین موزون هر پرتفوی جدا حساب می‌شود)"""
    by_pf = {}
    for t in trades(con):
        by_pf.setdefault(t["portfolio_id"], []).append(t)
    return {pid: _positions_from(rows) for pid, rows in by_pf.items()}


def held_totals(con):
    """نماد ← جمع تعداد سهم در همه‌ی پرتفوی‌ها"""
    out = {}
    for pos in all_positions(con).values():
        for p in pos:
            if p["qty"] > 0:
                out[p["symbol"]] = out.get(p["symbol"], 0) + p["qty"]
    return out


def trade_add(con, pid, symbol, side, qty, price, fee=0, date="", note=""):
    pf = portfolio(con, pid)
    if side not in ("buy", "sell"):
        raise StoreError("نوع معامله باید خرید یا فروش باشد")
    if not qty or qty <= 0:
        raise StoreError("تعداد سهم را وارد کنید")
    if not price or price <= 0:
        raise StoreError("قیمت را وارد کنید")
    if fee < 0:
        raise StoreError("کارمزد نمی‌تواند منفی باشد")
    cur = con.execute(
        "INSERT INTO trades(portfolio_id, symbol, side, qty, price, fee, date, note, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (pid, symbol, side, qty, price, fee, date, note, _now()))
    _check_or_rollback(con, pid, symbol,
                       f"در تاریخ {date or 'معامله'} این تعداد سهم {symbol} در پرتفوی «{pf['name']}» نیست")
    return cur.lastrowid


def trade_delete(con, trade_id):
    """حذف معامله؛ اگر بعد از حذف، فروشی بیشتر از موجودی بماند، حذف انجام نمی‌شود"""
    row = con.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    if not row:
        raise StoreError("معامله پیدا نشد")
    con.execute("DELETE FROM trades WHERE id=?", (trade_id,))
    _check_or_rollback(con, row["portfolio_id"], row["symbol"],
                       "با حذف این خرید، فروش‌های بعدی بیشتر از موجودی می‌شوند؛ اول آن‌ها را حذف کنید")


def _check_or_rollback(con, pid, symbol, msg):
    """موجودی نماد در پرتفوی به ترتیب تاریخ هیچ‌وقت نباید منفی شود؛ وگرنه تغییر برمی‌گردد"""
    qty = 0.0
    for t in trades(con, pid, symbol):
        qty += t["qty"] if t["side"] == "buy" else -t["qty"]
        if qty < -1e-9:
            con.rollback()
            raise StoreError(msg)
    con.commit()
