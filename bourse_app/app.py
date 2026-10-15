"""
برنامه‌ی محلی بورس — اجرا روی سیستم شخصی
اجرا:  python app.py   سپس مرورگر: http://127.0.0.1:5000
(حالت توسعه با بارگذاری دوباره‌ی خودکار: set BOURSE_DEBUG=1)

ساختار:
  app.py       مسیرهای صفحه و API (این فایل)
  jobs.py      صف کارهای پس‌زمینه‌ی کدال و کپچا
  store.py     داده‌های کاربر (واچ‌لیست، پرتفوی‌ها) در data/user.db
  tsetmc.py    قیمت‌ها
  forecast.py  یادگیری ماشین و تقویتی
  codal/       دریافت، پردازش و ذخیره‌ی گزارش‌های کدال در data/bourse.db
"""
import atexit
import logging
import os
import sqlite3
import threading

from flask import Flask, g, jsonify, render_template, request, url_for

import forecast
import jobs
import store
import tsetmc
from codal import client, collect, db, fresh, mrank, screener
from codal.text import clean, jdate, norm, to_num

app = Flask(__name__)
try:                               # Flask 2.2 به بعد
    app.json.sort_keys = False     # ترتیب کلیدها مهم نیست؛ مرتب‌سازی فقط زمان می‌گیرد
    app.json.compact = True
except AttributeError:             # نسخه‌های قدیمی‌تر Flask
    app.config["JSON_SORT_KEYS"] = False
# فایل‌های static با نسخه (?v=زمان تغییر) لینک می‌شوند ← مرورگر یک سال نگه می‌دارد و بعد از به‌روزرسانی خودش تازه می‌گیرد
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 365 * 24 * 3600


class _QuietPolls(logging.Filter):
    """درخواست‌های دوره‌ای موفق صفحه‌ها (GET /api/… با 200) در خروجی چاپ نمی‌شوند؛ خطاها و POST‌ها می‌مانند"""
    def filter(self, record):
        msg = record.getMessage()
        return not (('"GET /api/' in msg or '"GET /static/' in msg) and ('" 200 ' in msg or '" 304 ' in msg))


logging.getLogger("werkzeug").addFilter(_QuietPolls())

# لیست پشتیبان وقتی دیتابیس نمادها هنوز ساخته نشده است
SYMBOLS = [
    {"symbol": "فولاد", "name": "فولاد مبارکه اصفهان"},
    {"symbol": "فملی", "name": "ملی صنایع مس ایران"},
    {"symbol": "خودرو", "name": "ایران خودرو"},
    {"symbol": "شپنا", "name": "پالایش نفت اصفهان"},
    {"symbol": "وبملت", "name": "بانک ملت"},
    {"symbol": "شستا", "name": "سرمایه گذاری تامین اجتماعی"},
    {"symbol": "خساپا", "name": "سایپا"},
    {"symbol": "کگل", "name": "معدنی و صنعتی گل گهر"},
    {"symbol": "اخابر", "name": "مخابرات ایران"},
    {"symbol": "رمپنا", "name": "گروه مپنا"},
]


# ---------- اتصال‌ها: یک اتصال برای هر درخواست (نه یکی برای هر تابع) ----------
def codal_db():
    if "codal_db" not in g:
        g.codal_db = db.connect()
    return g.codal_db


def user_db():
    if "user_db" not in g:
        g.user_db = store.connect()
    return g.user_db


@app.teardown_appcontext
def _close_dbs(exc):
    for name in ("codal_db", "user_db"):
        con = g.pop(name, None)
        if con is not None:
            con.close()


def _checkpoint():
    """هنگام بستن برنامه: فایل‌های -wal در دیتابیس‌ها ادغام می‌شوند (کپی/پشتیبان‌گیری امن)"""
    for fn in (db.checkpoint, client.cache_checkpoint):
        try:
            fn()
        except sqlite3.Error:
            pass


atexit.register(_checkpoint)


# ---------- فایل‌های static با نسخه ----------
_asset_v = {}


def asset(filename):
    """آدرس فایل static با ?v=زمان تغییر (بعد از به‌روزرسانی برنامه، Ctrl+F5 لازم نیست)"""
    path = os.path.join(app.static_folder, filename)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    if _asset_v.get(filename, (None,))[0] != mtime:
        _asset_v[filename] = (mtime, url_for("static", filename=filename, v=int(mtime)))
    return _asset_v[filename][1]


@app.context_processor
def _template_helpers():
    return {"asset": asset}


# ---------- کمک‌ها ----------
def _chunks(items, n=500):
    items = list(items)
    for i in range(0, len(items), n):
        yield items[i:i + n]


def symbol_names(symbols):
    """نماد ← نام شرکت (از جدول symbols یا لیست پشتیبان)"""
    symbols = list(dict.fromkeys(symbols))
    names = {s["symbol"]: s["name"] for s in SYMBOLS}
    con = codal_db()
    for part in _chunks(symbols):
        q = "SELECT symbol, name FROM symbols WHERE symbol IN (%s)" % ",".join("?" * len(part))
        names.update({r["symbol"]: r["name"] for r in con.execute(q, part)})
    return {s: names.get(s, "") for s in symbols}


def known_symbol(sym):
    """
    نماد معتبر است؟ اگر لیست نمادهای کدال گرفته شده باشد باید در آن باشد؛
    وگرنه هر نمادی پذیرفته می‌شود (تا قبل از «python scrape.py symbols» هم کار کند)
    """
    con = codal_db()
    if con.execute("SELECT 1 FROM symbols WHERE symbol=?", (sym,)).fetchone():
        return True
    return any(s["symbol"] == sym for s in SYMBOLS) or not con.execute("SELECT 1 FROM symbols LIMIT 1").fetchone()


def monthly_summary(symbols):
    """آخرین فروش ماهانه‌ی هر نماد و تغییرش نسبت به همان ماه سال قبل (میلیون ریال)"""
    out = {}
    con = codal_db()
    for s in symbols:
        last = con.execute("SELECT period_end, fiscal_year, fiscal_month, total FROM monthly_latest "
                           "WHERE symbol=? ORDER BY period_end DESC LIMIT 1", (s,)).fetchone()
        if not last:
            continue
        prev = con.execute("SELECT total FROM monthly_latest WHERE symbol=? AND fiscal_year=? "
                           "AND fiscal_month=?", (s, last["fiscal_year"] - 1, last["fiscal_month"])).fetchone()
        out[s] = {
            "period_end": last["period_end"], "total": last["total"],
            "yoy": (last["total"] / prev["total"] - 1) * 100 if prev and prev["total"] else None,
        }
    return out


def prices_and_market(symbols):
    """قیمت آخرین دریافت از TSETMC برای نمادها + وضعیت بازار"""
    con = codal_db()
    return tsetmc.prices_for(con, symbols), tsetmc.status(con)


def body():
    return request.get_json(silent=True) or {}


def bad(msg, code=400):
    return jsonify({"error": msg}), code


@app.errorhandler(sqlite3.Error)
def _db_error(e):
    """خطای دیتابیس (مثلاً قفل طولانی) ← پیام فارسی به جای صفحه‌ی خطای ۵۰۰"""
    return bad(f"خطای دیتابیس: {e}", 503)


# ---------- صفحه‌ها ----------
@app.route("/")
def home():
    return render_template("index.html", active="home")


@app.route("/watchlist")
def watchlist():
    return render_template("watchlist.html", active="watchlist")


@app.route("/portfolio")
def portfolio():
    return render_template("portfolio.html", active="portfolio")


@app.route("/symbol/<name>")
def symbol(name):
    name = norm(name)
    return render_template("page.html", active="", title=f"نماد {name}", symbol=name,
                           company=symbol_names([name])[name])


@app.route("/screener")
def screener_page():
    return render_template("screener.html", active="screener")


# ---------- جستجو ----------
@app.route("/api/search")
def api_search():
    q = norm(request.args.get("q", ""))
    if not q:
        return jsonify([])
    # اگر لیست نمادها با «python scrape.py symbols» گرفته شده باشد، از دیتابیس
    hits = [dict(r) for r in codal_db().execute(
        "SELECT symbol, name FROM symbols WHERE symbol LIKE ? OR name LIKE ? "
        "ORDER BY (symbol = ?) DESC, (symbol LIKE ?) DESC, length(symbol) LIMIT 8",
        (f"%{q}%", f"%{q}%", q, f"{q}%"))]
    if not hits:
        hits = [dict(s) for s in SYMBOLS if q in s["symbol"] or q in s["name"]][:8]
    # وضعیت هر نماد در واچ‌لیست و پرتفوی
    con = user_db()
    watched = set(store.watch_symbols(con))
    held = store.held_totals(con)   # جمع همه‌ی پرتفوی‌ها
    prices, _ = prices_and_market([h["symbol"] for h in hits])
    rc = ranking_cached()
    ranks, n_ranked = rc["by_symbol"], rc["ranked"]
    for h in hits:
        rk = ranks.get(h["symbol"])
        h["growth"] = {"rank": rk["rank"], "of": n_ranked, "g_cum": rk["g_cum"], "score": rk["score"],
                       "months": rk["months"]} if rk and rk["rank"] else None
        h["watch"] = h["symbol"] in watched
        h["qty"] = held.get(h["symbol"], 0)
        p = prices.get(h["symbol"])
        h["price"] = {"close": p["close"], "change": p["change"]} if p else None
    return jsonify(hits)


# ---------- واچ‌لیست ----------
@app.route("/api/watchlist")
def api_watchlist():
    con = user_db()
    syms = store.watch_symbols(con)
    held = store.held_totals(con)   # جمع همه‌ی پرتفوی‌ها
    names, monthly = symbol_names(syms), monthly_summary(syms)
    prices, market = prices_and_market(syms)
    return jsonify({
        "market": market,
        "items": [{"symbol": s, "name": names[s], "qty": held.get(s, 0), "monthly": monthly.get(s),
                   "price": prices.get(s)} for s in syms],
    })


@app.route("/api/watchlist", methods=["POST"])
def api_watch_add():
    sym = norm(body().get("symbol"))
    if not sym:
        return bad("نماد را وارد کنید")
    if not known_symbol(sym):
        return bad(f"نماد «{sym}» در لیست نمادهای کدال نیست")
    store.watch_add(user_db(), sym)
    return jsonify({"ok": True, "symbol": sym})


@app.route("/api/watchlist/<sym>", methods=["DELETE"])
def api_watch_remove(sym):
    store.watch_remove(user_db(), norm(sym))
    return jsonify({"ok": True})


# ---------- پرتفوی‌ها ----------
def valuate(pos, prices, names):
    """
    افزودن نام، قیمت، ارزش روز (با قیمت پایانی) و سود و زیان باز (بدون کارمزد فروش احتمالی)
    و تغییر امروز (تعداد × (پایانی − دیروز)) به موجودی‌ها
    """
    for p in pos:
        p["name"] = names.get(p["symbol"], "")
        pr = prices.get(p["symbol"])
        p["price"] = pr
        if pr and pr["close"] and p["qty"] > 0:
            p["market_value"] = p["qty"] * pr["close"]
            p["unrealized"] = p["market_value"] - p["cost"]
            p["day_change"] = p["qty"] * (pr["close"] - (pr["yesterday"] or pr["close"]))
        else:
            p["market_value"] = p["unrealized"] = p["day_change"] = None
    return pos


def summarize(pos):
    """جمع یک پرتفوی (فقط نمادهای دارای موجودی در ارزش و سود باز)"""
    open_ = [p for p in pos if p["qty"] > 0]
    priced = [p for p in open_ if p["market_value"] is not None]
    return {
        "symbols": len(open_),
        "cost": sum(p["cost"] for p in open_),
        "value": sum(p["market_value"] for p in priced) if priced else None,
        "priced_cost": sum(p["cost"] for p in priced),
        "unrealized": sum(p["unrealized"] for p in priced) if priced else None,
        "day_change": sum(p["day_change"] for p in priced) if priced else None,
        "realized": sum(p["realized"] for p in pos),
        "missing_prices": len(open_) - len(priced),
    }


@app.route("/api/portfolios")
def api_portfolios():
    """
    لیست پرتفوی‌ها (مشتری‌ها) با خلاصه‌ی هر کدام، جمع کل و جمع هر نماد در همه‌ی پرتفوی‌ها.
    ?brief=1 فقط شناسه و نام (برای فرم خرید سریع)
    """
    con = user_db()
    pfs = store.portfolios(con)
    if request.args.get("brief"):
        return jsonify([{"id": p["id"], "name": p["name"]} for p in pfs])
    allpos = store.all_positions(con)

    syms = {p["symbol"] for pos in allpos.values() for p in pos}
    names = symbol_names(syms)
    prices, market = prices_and_market(syms)
    exposure = {}
    for pf in pfs:
        pos = valuate(allpos.get(pf["id"], []), prices, names)
        pf["summary"] = summarize(pos)
        for p in pos:
            if p["qty"] <= 0:
                continue
            e = exposure.setdefault(p["symbol"], {
                "symbol": p["symbol"], "name": p["name"], "price": p["price"],
                "qty": 0, "cost": 0, "value": 0 if p["market_value"] is not None else None, "holders": []})
            e["qty"] += p["qty"]
            e["cost"] += p["cost"]
            if e["value"] is not None and p["market_value"] is not None:
                e["value"] += p["market_value"]
            e["holders"].append({"id": pf["id"], "name": pf["name"], "qty": p["qty"]})

    sums = [pf["summary"] for pf in pfs]
    add = lambda k: sum(s[k] for s in sums if s[k] is not None) if any(s[k] is not None for s in sums) else None
    totals = {k: add(k) for k in ("cost", "value", "priced_cost", "unrealized", "day_change", "realized")}
    totals["clients"] = len(pfs)
    totals["missing_prices"] = sum(s["missing_prices"] for s in sums)
    return jsonify({
        "market": market, "totals": totals, "portfolios": pfs,
        "exposure": sorted(exposure.values(), key=lambda e: -(e["value"] if e["value"] is not None else e["cost"])),
    })


@app.route("/api/portfolios", methods=["POST"])
def api_portfolio_add():
    b = body()
    try:
        pid = store.portfolio_add(user_db(), clean(b.get("name")), clean(b.get("note")))
    except store.StoreError as e:
        return bad(str(e))
    return jsonify({"ok": True, "id": pid})


@app.route("/api/portfolios/<int:pid>", methods=["PUT"])
def api_portfolio_update(pid):
    b = body()
    try:
        store.portfolio_update(user_db(), pid, clean(b.get("name")), clean(b.get("note")))
    except store.StoreError as e:
        return bad(str(e))
    return jsonify({"ok": True})


@app.route("/api/portfolios/<int:pid>", methods=["DELETE"])
def api_portfolio_delete(pid):
    try:
        store.portfolio_delete(user_db(), pid)
    except store.StoreError as e:
        return bad(str(e))
    return jsonify({"ok": True})


@app.route("/api/portfolio")
def api_portfolio():
    """یک پرتفوی: ?p=شناسه"""
    pid = int(to_num(request.args.get("p")) or 0)
    con = user_db()
    try:
        pf = store.portfolio(con, pid)
    except store.StoreError as e:
        return bad(str(e), 404)
    pos, trades = store.positions(con, pid), store.trades(con, pid)
    syms = {p["symbol"] for p in pos}
    prices, market = prices_and_market(syms)
    valuate(pos, prices, symbol_names(syms))
    trades.sort(key=lambda t: (t["date"] or "", t["id"]), reverse=True)
    return jsonify({"portfolio": pf, "summary": summarize(pos), "positions": pos,
                    "trades": trades, "market": market})


@app.route("/api/portfolio/trades", methods=["POST"])
def api_trade_add():
    b = body()
    sym = norm(b.get("symbol"))
    if not sym:
        return bad("نماد را وارد کنید")
    if not known_symbol(sym):
        return bad(f"نماد «{sym}» در لیست نمادهای کدال نیست")
    d = jdate(b.get("date") or "")
    if b.get("date") and not d:
        return bad("تاریخ را به شکل ۱۴۰۵/۰۷/۱۵ وارد کنید")
    pid = int(to_num(b.get("portfolio_id")) or 0)
    if not pid:
        return bad("پرتفوی (مشتری) را انتخاب کنید")
    try:
        tid = store.trade_add(user_db(), pid, sym, b.get("side", "buy"),
                              to_num(b.get("qty")) or 0, to_num(b.get("price")) or 0,
                              to_num(b.get("fee")) or 0,
                              "%04d/%02d/%02d" % d if d else "", clean(b.get("note")))
    except store.StoreError as e:
        return bad(str(e))
    return jsonify({"ok": True, "id": tid})


@app.route("/api/portfolio/trades/<int:tid>", methods=["DELETE"])
def api_trade_delete(tid):
    try:
        store.trade_delete(user_db(), tid)
    except store.StoreError as e:
        return bad(str(e))
    return jsonify({"ok": True})


# ---------- قیمت‌های بازار (TSETMC) ----------
_PRICE_LOCK = threading.Lock()


@app.route("/api/prices/refresh", methods=["POST"])
def api_prices_refresh():
    """
    دریافت قیمت همه‌ی نمادها از TSETMC.
    max_age (ثانیه): اگر آخرین دریافت تازه‌تر از این باشد، دوباره دریافت نمی‌شود.
    چند صفحه‌ی باز هم‌زمان ← فقط یک دریافت (بقیه نتیجه‌ی همان را می‌گیرند)
    """
    max_age = to_num(request.args.get("max_age")) or 0
    con = codal_db()
    st = tsetmc.status(con)
    if max_age and st["age"] is not None and st["age"] < max_age:
        return jsonify(st)
    with _PRICE_LOCK:
        st = tsetmc.status(con)                 # شاید درخواست هم‌زمان دیگری همین الان گرفته باشد
        if max_age and st["age"] is not None and st["age"] < max_age:
            return jsonify(st)
        try:
            return jsonify(tsetmc.refresh(con))
        except tsetmc.PriceError as e:
            return bad(str(e), 502)


@app.route("/api/price/<sym>")
def api_price(sym):
    sym = norm(sym)
    prices, market = prices_and_market([sym])
    return jsonify({"price": prices.get(sym), "market": market})


# ---------- کارهای پس‌زمینه‌ی کدال (jobs.py) ----------
def start_job(kind, sym, check=None, **opts):
    """
    اول دیتابیس، بعد کدال: check(con, user) می‌گوید داده‌های دیتابیس کافی است یا نه (codal/fresh.py).
    کافی باشد ← بدون هیچ درخواستی به کدال {"fresh": true, "message": …}؛ وگرنه کار به صف اضافه می‌شود
    (اگر کار دیگری در جریان است، این یکی «در صف» می‌ماند و بعد خودکار اجرا می‌شود).
    ?auto=1: درخواست خودکار صفحه (مهلت‌های بررسی دوباره رعایت می‌شود)؛ بدون آن = دکمه‌ی کاربر؛ ?force=1 بدون بررسی
    """
    if kind not in jobs.MARKET_LABEL and not known_symbol(sym):
        return bad(f"نماد «{sym}» در لیست نمادهای کدال نیست")
    if check and request.args.get("force") != "1" and not jobs.active(kind, sym):
        need, note = check(codal_db(), request.args.get("auto") != "1")
        if not need:
            return jsonify({"ok": True, "fresh": True, "message": note, "job": jobs.get(kind, sym)})
    return jsonify({"ok": True, "job": jobs.enqueue(kind, sym, opts)})


# ---------- عملکرد ماهانه (گزارش‌های ماهانه‌ی کدال) ----------
SECTION_LABEL = {"domestic": "", "export": "صادراتی", "service": "خدمات"}
TOP_PRODUCTS = 6


def monthly_payload(sym):
    """
    داده‌ی صفحه‌ی عملکرد ماهانه، هم‌شکل DATA در home.js؛ مبالغ میلیارد تومان.
    cur/prev: ۱۲ ماه سال مالی جاری و قبل (null = گزارش نشده)
    products: ترکیب فروش تجمعی سال جاری (برگشت از فروش حذف؛ بیش از ۶ محصول ← «سایر»)
    """
    con = codal_db()
    rows = con.execute("SELECT * FROM monthly_latest WHERE symbol=? ORDER BY period_end", (sym,)).fetchall()
    if not rows:
        return None
    fy = max(r["fiscal_year"] for r in rows)
    last = max((r for r in rows if r["fiscal_year"] == fy), key=lambda r: r["period_end"])
    cur, prev = [None] * 12, [None] * 12
    for r in rows:
        arr = cur if r["fiscal_year"] == fy else prev if r["fiscal_year"] == fy - 1 else None
        if arr is not None and r["total"] is not None:
            arr[r["fiscal_month"] - 1] = r["total"] / 10000
    # اقلام فقط از گزارش‌های همین سال (شناسه‌ها از ردیف‌های بالا؛ بدون پیوند دوباره با نمای monthly_latest)
    ids = [r["id"] for r in rows if r["fiscal_year"] == fy]
    items = con.execute(
        "SELECT section, name, MAX(unit) AS unit, SUM(amount) AS amt, SUM(sold) AS sold, SUM(made) AS made "
        f"FROM monthly_items WHERE report_id IN ({','.join('?' * len(ids))}) AND section != 'returns' "
        "GROUP BY section, name ORDER BY amt DESC", ids).fetchall()
    count = len([r for r in rows if r["fiscal_year"] >= fy - 1])

    products = []
    for it in items:
        if not it["amt"] or it["amt"] <= 0:
            continue
        label = SECTION_LABEL.get(it["section"], "")
        products.append({"name": it["name"] + (f" ({label})" if label else ""), "unit": it["unit"] or "",
                         "amt": it["amt"] / 10000, "sold": it["sold"], "made": it["made"]})
    if len(products) > TOP_PRODUCTS:
        rest = products[TOP_PRODUCTS - 1:]
        products = products[:TOP_PRODUCTS - 1] + [{
            "name": f"سایر محصولات ({len(rest)} قلم)", "unit": "", "amt": sum(p["amt"] for p in rest),
            "sold": None, "made": None}]

    # کامل بودن: سال قبل ۱۲ ماه، سال جاری تا آخرین گزارش (ماه‌های جاافتاده با شماره‌ی ماه سال مالی)
    cov = collect.monthly_coverage(con, sym)
    coverage = None
    if cov:
        idx = {m: i for i, m in enumerate(cov["need"])}
        coverage = {"prev_have": cov["prev_have"], "cur_have": cov["cur_have"], "cur_upto": cov["cur_upto"],
                    "missing_prev": [idx[m] + 1 for m in cov["missing"] if idx[m] < 12],
                    "missing_cur": [idx[m] - 11 for m in cov["missing"] if idx[m] >= 12]}

    ye = jdate(last["year_end"])
    pe = jdate(last["period_end"])
    return {
        "symbol": sym, "company": symbol_names([sym])[sym],
        "fy": fy, "yearEndMonth": ye[1], "lastPeriod": last["period_end"],
        "lastMonth": pe[1], "lastYear": pe[0],
        "cur": cur, "prev": prev, "products": products, "reports": count, "sample": False,
        "coverage": coverage,
    }


@app.route("/api/monthly/<sym>")
def api_monthly(sym):
    sym = norm(sym)
    return jsonify({"data": monthly_payload(sym), "job": jobs.get("monthly", sym),
                    "db": fresh.status(codal_db(), "monthly", sym)})


@app.route("/api/monthly/<sym>/fetch", methods=["POST"])
def api_monthly_fetch(sym):
    sym = norm(sym)
    return start_job("monthly", sym, check=lambda con, user: fresh.monthly(con, sym, user))


# ---------- برآورد سود: صورت سود و زیان فصلی تحقق‌یافته ----------
# فیلدهای مدل home.js با قرارداد آن: هزینه‌ها مثبت، اقلام خالص با علامت
MODEL_FIELDS = {"rev": ("rev", 1), "cogs": ("cogs", -1), "sga": ("sga", -1), "otherOp": ("other_op", 1),
                "fin": ("fin", -1), "nonOp": ("non_op", 1), "tax": ("tax", -1)}
DB_FIELDS = ("rev", "cogs", "sga", "other_op", "fin", "non_op", "tax", "net")


def quarters_payload(sym, fy=None):
    """
    فصل‌های تحقق‌یافته‌ی یک سال مالی از صورت‌های سود و زیان غیرتلفیقی:
    کدال تجمعی (۳، ۶، ۹، ۱۲ ماهه) گزارش می‌کند ← فصل n = دوره‌ی n×۳ ماهه − دوره‌ی قبلی.
    فصلی که دوره‌ی خودش یا دوره‌ی قبلش گزارش نشده، null است.
    """
    rows = codal_db().execute("SELECT * FROM fin_latest WHERE symbol=? AND consolidated=0 AND months IN (3,6,9,12) "
                              "ORDER BY period_end", (sym,)).fetchall()
    if not rows:
        return None
    years = sorted({r["fiscal_year"] for r in rows}, reverse=True)
    fy = fy if fy in years else years[0]
    by_months = {r["months"]: r for r in rows if r["fiscal_year"] == fy}

    quarters = []
    for q in range(1, 5):
        cur, prev = by_months.get(q * 3), by_months.get((q - 1) * 3) if q > 1 else None
        if not cur or (q > 1 and not prev) or cur["rev"] is None:
            quarters.append(None)
            continue
        vals = {}
        for f in DB_FIELDS:
            a, b = cur[f], (prev[f] if prev else 0)
            vals[f] = None if a is None or b is None else a - b
        quarters.append({
            "q": q, "months": cur["months"], "period_end": cur["period_end"], "published": cur["published"],
            "audited": bool(cur["audited"]), "tracing_no": cur["tracing_no"],
            "values": {k: (vals[db_f] * sign if vals[db_f] is not None else 0) for k, (db_f, sign) in MODEL_FIELDS.items()},
            "net": vals["net"],
        })
    stage = 0                                   # فصل‌های پشت سر هم از ابتدای سال
    while stage < 4 and quarters[stage]:
        stage += 1
    latest = max(by_months.values(), key=lambda r: r["months"])
    capital = latest["capital"]
    prices, _ = prices_and_market([sym])
    price = prices.get(sym)
    return {
        "symbol": sym, "company": symbol_names([sym])[sym], "fy": fy, "years": years,
        "year_end": latest["year_end"], "quarters": quarters, "stage": stage,
        "capital": capital, "shares": capital / 1000 if capital else None,   # میلیون سهم با اسمی ۱۰۰۰ ریال
        "eps_reported": latest["eps"], "eps_months": latest["months"],
        "price": price["close"] if price else None,
    }


@app.route("/api/quarters/<sym>")
def api_quarters(sym):
    sym = norm(sym)
    fy = int(to_num(request.args.get("fy")) or 0) or None
    return jsonify({"data": quarters_payload(sym, fy), "job": jobs.get("financial", sym),
                    "db": fresh.status(codal_db(), "financial", sym)})


@app.route("/api/quarters/<sym>/fetch", methods=["POST"])
def api_quarters_fetch(sym):
    sym = norm(sym)
    return start_job("financial", sym, check=lambda con, user: fresh.financial(con, sym, user))


# ---------- کد امنیتی (کپچا) کدال: اپراتور خودش وارد می‌کند ----------
@app.route("/api/captcha")
def api_captcha():
    """کدال کد امنیتی خواسته؟ (صفحه‌ها هر ۱٫۵ ثانیه می‌پرسند تا پنجره‌ی ورود کد را فوراً نشان دهند)"""
    return jsonify(jobs.captcha_state())


@app.route("/api/captcha/image")
def api_captcha_image():
    try:
        return jsonify({"image": client.captcha_image()})
    except RuntimeError as e:
        return bad(str(e), 502)


@app.route("/api/captcha/verify", methods=["POST"])
def api_captcha_verify():
    code = (body().get("code") or "").strip()
    if not code:
        return bad("کد امنیتی را وارد کنید")
    try:
        ok = client.captcha_verify(code)
    except RuntimeError as e:
        return bad(str(e), 502)
    if not ok:
        return jsonify({"ok": False, "error": "کد امنیتی درست نیست؛ تصویر جدید را ببینید و دوباره وارد کنید"})
    return jsonify({"ok": True, "resumed": jobs.resume_after_captcha()})


# ---------- حافظه‌ی پاسخ‌های کدال ----------
@app.route("/api/cache")
def api_cache():
    """وضعیت data/cache.db و آمار همین اجرا (از حافظه / از شبکه)"""
    return jsonify({"stats": client.cache_stats(), "session": client.STATS})


# ---------- پیش‌بینی با یادگیری ماشین / تقویتی ----------
# نتیجه تا تغییر داده‌های همان نماد نگه داشته می‌شود (آموزش مدل‌ها در هر بار باز شدن صفحه تکرار نمی‌شود)
_ML_CACHE = {}
_ML_LOCK = threading.Lock()


def _ml(fn, sym):
    con = codal_db()
    sig = (tuple(con.execute("SELECT COUNT(*), MAX(id) FROM monthly_reports WHERE symbol=?", (sym,)).fetchone()),
           tuple(con.execute("SELECT COUNT(*), MAX(id) FROM fin_reports WHERE symbol=?", (sym,)).fetchone()))
    key = (fn.__name__, sym)
    hit = _ML_CACHE.get(key)
    if hit and hit[0] == sig:
        return hit[1]
    res = fn(con, sym)
    with _ML_LOCK:
        if len(_ML_CACHE) > 300:
            _ML_CACHE.clear()
        _ML_CACHE[key] = (sig, res)
    return res


@app.route("/api/ml/monthly/<sym>")
def api_ml_monthly(sym):
    sym = norm(sym)
    return jsonify({"result": _ml(forecast.monthly_forecast, sym), "job": jobs.get("history", sym)})


@app.route("/api/ml/quarters/<sym>")
def api_ml_quarters(sym):
    sym = norm(sym)
    return jsonify({"result": _ml(forecast.quarterly_forecast, sym), "job": jobs.get("history", sym)})


@app.route("/api/ml/<sym>/history", methods=["POST"])
def api_ml_history(sym):
    """دریافت سابقه‌ی چندساله از کدال برای داده‌ی آموزش (پیش‌فرض ۵ سال)"""
    years = int(to_num(request.args.get("years")) or 5)
    return start_job("history", norm(sym), years=max(2, min(years, 8)))


# ---------- رتبه‌بندی رشد سود خالص ----------
_RANK_CACHE = {"key": None, "rows": [], "by_symbol": {}, "ranked": 0}
_RANK_LOCK = threading.Lock()
# فیلدهای داخلی محاسبه که صفحه لازم ندارد (حجم پاسخ کمتر)
_RANK_DROP = ("pct_g_cum", "pct_g_q_yoy", "pct_g_q_qoq", "pct_pace", "tracing_no", "fiscal_year", "net_ly_full")


def ranking_cached():
    """رتبه‌بندی فقط وقتی گزارش تازه‌ای ذخیره شده دوباره حساب می‌شود (برای جستجو و صفحه‌ی رتبه‌بندی)"""
    con = codal_db()
    key = tuple(con.execute("SELECT COUNT(*), MAX(id), MAX(fetched_at) FROM fin_reports").fetchone())
    if _RANK_CACHE["key"] != key:
        with _RANK_LOCK:
            if _RANK_CACHE["key"] != key:
                rows = screener.ranking(con)
                for r in rows:
                    for f in _RANK_DROP:
                        r.pop(f, None)
                _RANK_CACHE.update(key=key, rows=rows, by_symbol={r["symbol"]: r for r in rows},
                                   ranked=sum(1 for r in rows if r["rank"]))
    return _RANK_CACHE


@app.route("/api/screener")
def api_screener():
    """رتبه‌بندی رشد سود؛ ?top=N فقط N رتبه‌ی اول (پنجره‌ی جستجو) — نام و قیمت فقط برای ردیف‌های خروجی"""
    cache = ranking_cached()
    rows = cache["rows"]
    top = int(to_num(request.args.get("top")) or 0)
    out = [dict(r) for r in ([r for r in rows if r["rank"]][:top] if top else rows)]
    names = symbol_names(r["symbol"] for r in out)
    prices, market = prices_and_market([r["symbol"] for r in out])
    for r in out:
        r["name"] = names.get(r["symbol"], "")
        p = prices.get(r["symbol"])
        r["price"] = {"close": p["close"], "change": p["change"], "pe": p["pe"]} if p else None
    return jsonify({
        "rows": out, "market": market, "job": jobs.get("screener"),
        "db": fresh.status(codal_db(), "screener"),
        "meta": {"count": len(rows), "ranked": cache["ranked"], "stale": sum(1 for r in rows if r["stale"]),
                 "latest": max((r["published"] for r in rows), default=None)},
    })


@app.route("/api/screener/scan", methods=["POST"])
def api_screener_scan():
    budget = int(to_num(request.args.get("budget")) or 40)
    return start_job("screener", "", check=lambda con, user: fresh.market(con, "screener", user),
                     budget=max(5, min(budget, 200)))


# ---------- رتبه‌بندی تغییر درآمد ماهانه (صفحه‌ی اول «عملکرد ماهانه») ----------
_MRANK_BACKFILLED = []


def _req_month():
    return mrank.parse_month(request.args.get("month")) or mrank.default_month()


@app.route("/api/mrank")
def api_mrank():
    """رتبه‌بندی تغییر درآمد یک ماه (?month=1405-06؛ پیش‌فرض ماه گذشته) + فهرست ماه‌ها با تعداد شرکت‌ها"""
    ym = _req_month()
    key = mrank.month_key(ym)
    con = codal_db()
    if not _MRANK_BACKFILLED:          # ستون‌های تجمعی گزارش‌های قدیمی‌تر از حافظه‌ی پاسخ‌ها — یک بار در هر اجرا
        mrank.backfill(con)
        _MRANK_BACKFILLED.append(True)
    rows = mrank.ranking(con, ym)
    missing = mrank.missing_known(con, ym)
    prev_count = {s: sum(1 for r in rows if r.get("prev_state") == s) for s in ("wait", "none", "bad")}
    need, note = mrank.need_scan(con, ym, missing=missing, wait_prev=prev_count["wait"])
    names = symbol_names(r["symbol"] for r in rows)
    prices, market = prices_and_market([r["symbol"] for r in rows])
    for r in rows:
        r["name"] = names.get(r["symbol"], "")
        p = prices.get(r["symbol"])
        r["price"] = {"close": p["close"], "change": p["change"]} if p else None
    job = jobs.get("mrank")
    prev = fresh._shift(ym, -1)
    return jsonify({
        "month": key, "month_fa": jobs.month_fa(ym), "prev_month": mrank.month_key(prev),
        "prev_month_fa": jobs.month_fa(prev), "months": mrank.months(con),
        "rows": rows, "market": market, "job": job, "job_month": job and job.get("month"),
        "db": {"checked": db.checked_at(con, "mrank", key), "need": need, "note": note},
        "meta": {"count": len(rows), "known_missing": len(missing), "prev": prev_count,
                 "ranked": sum(1 for r in rows if r["g_mom"] is not None),
                 "latest": max((r["published"] for r in rows), default=None)},
    })


@app.route("/api/mrank/scan", methods=["POST"])
def api_mrank_scan():
    """
    دریافت گزارش‌های لازم همان ماه از کدال (فقط آنچه در دیتابیس نیست): گزارش‌های ماه و گزارش ماه قبلِ همان
    نمادها (پایه‌ی رشد). ?budget=N حداکثر N گزارش؛ بدون آن یا all = همه‌ی گزارش‌های لازم (تکه‌تکه، jobs.MRANK_CHUNK)
    """
    ym = _req_month()
    b = request.args.get("budget")
    budget = None if b in (None, "", "all") else max(5, min(int(to_num(b) or 40), 400))
    return start_job("mrank", "", check=lambda con, user: mrank.need_scan(con, ym, user),
                     month=mrank.month_key(ym), budget=budget)


@app.route("/api/mrank/stop", methods=["POST"])
def api_mrank_stop():
    """توقف دریافت رتبه‌بندی ماهانه (گزارش‌های گرفته‌شده می‌مانند؛ تا ۶ ساعت بدون شروع خودکار)"""
    return jsonify({"ok": True, "job": jobs.stop("mrank")})


# ---------- دستیار ----------
@app.route("/api/ai", methods=["POST"])
def api_ai():
    # جای اتصال به مدل هوش مصنوعی؛ فعلاً پاسخ نمونه
    msg = body().get("message", "")
    return jsonify({"reply": f"پیام شما دریافت شد: «{msg}». اتصال دستیار هنوز تنظیم نشده است."})


if __name__ == "__main__":
    # حالت عادی: بدون Debug (سریع‌تر، بدون اجرای دوباره‌ی برنامه با هر تغییر فایل و بدون از دست رفتن کارهای در جریان)
    debug = os.environ.get("BOURSE_DEBUG") == "1"
    app.run(host="127.0.0.1", port=int(os.environ.get("BOURSE_PORT", 5000)), debug=debug, threaded=True)
