"""
پیش‌بینی با یادگیری ماشین و یادگیری تقویتی — فقط کتابخانه‌ی استاندارد پایتون

داده: سری‌های تاریخی همان نماد از کدال (فروش ماهانه، اقلام صورت سود و زیان فصلی)
تقسیم زمانی (بدون بُر زدن، مخصوص سری زمانی):
    ۷۰٪ اول آموزش | ۲۰٪ بعد اعتبارسنجی | ۱۰٪ آخر آزمون
- آموزش: مدل‌ها روی داده‌های گذشته برازش می‌شوند
- اعتبارسنجی: پیش‌بینی یک‌گام‌به‌جلو (walk-forward) ← انتخاب ابرپارامترهای هر مدل؛
  عامل یادگیری تقویتی هم در این بخش وزن مدل‌ها را یاد می‌گیرد
- آزمون: دقت نهایی روی داده‌ای که در انتخاب‌ها استفاده نشده
- پیش‌بینی آینده: مدل‌ها روی کل داده دوباره برازش می‌شوند

مدل‌ها (یادگیری ماشین):
  snaive_g   فصلی ساده با رشد سالانه: مقدار فصل/ماه مشابه پارسال × رشد ۱۲ ماه (یا ۴ فصل) اخیر
  holt       هولت-وینترز (هموارسازی نمایی با روند و فصل‌پذیری) روی لگاریتم ← مناسب تورم
  ridge      رگرسیون ریج روی وقفه‌ها (۱، ۲، ۳ و فصل قبل) و روند زمانی، روی لگاریتم
  naive      آخرین مقدار (مبنای مقایسه)
یادگیری تقویتی:
  عامل Hedge (راهزن چندبازویی با اطلاعات کامل): در هر گام، پیش‌بینی = میانگین وزنی مدل‌ها؛
  پس از دیدن مقدار واقعی، پاداش هر مدل = −خطای نسبی آن و وزن‌ها نمایی به‌روز می‌شوند.
  نرخ یادگیری η روی اعتبارسنجی انتخاب می‌شود.
معیار خطا: WAPE = Σ|خطا| ÷ Σ|واقعی| (درصد)
"""
import math

# ==================== تقسیم و معیار ====================
SPLIT = (0.7, 0.2, 0.1)


def split_idx(n):
    """مرز آموزش/اعتبارسنجی/آزمون: [0,t) [t,v) [v,n)؛ هر بخش دست‌کم یک نقطه"""
    t = max(1, round(n * SPLIT[0]))
    v = max(t + 1, round(n * (SPLIT[0] + SPLIT[1])))
    v = min(v, n - 1)
    return t, v


def wape(actual, pred):
    s = sum(abs(a) for a in actual)
    if not actual or s == 0:
        return None
    return sum(abs(a - p) for a, p in zip(actual, pred)) / s * 100


# ==================== جبر خطی کوچک (برای ریج) ====================
def _solve(A, b):
    """حل دستگاه خطی با حذف گاوسی (ماتریس‌های کوچک)"""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


# ==================== مدل‌ها ====================
# هر مدل: f(hist, h, m, **params) ← لیست h پیش‌بینی؛ hist مقادیر گذشته، m طول فصل (۱۲ ماهانه، ۴ فصلی)

def m_naive(hist, h, m):
    return [hist[-1]] * h


def m_mean(hist, h, m):
    k = hist[-m:]
    return [sum(k) / len(k)] * h


def m_snaive(hist, h, m):
    if len(hist) < m:
        return m_naive(hist, h, m)
    return [hist[-m + (i % m)] for i in range(h)]


def m_snaive_g(hist, h, m):
    """فصلی ساده × رشد سالانه‌ی اخیر (برای سری‌های مثبت با تورم)"""
    if len(hist) < 2 * m:
        return m_snaive(hist, h, m)
    a, b = sum(hist[-m:]), sum(hist[-2 * m:-m])
    g = a / b if b > 0 and a > 0 else 1.0
    g = min(max(g, 0.3), 3.0)
    out = []
    for i in range(h):
        base = hist[-m + (i % m)]
        out.append(base * g ** (1 + i // m))
    return out


def m_ewma(hist, h, m, alpha=0.5):
    s = hist[0]
    for y in hist[1:]:
        s = alpha * y + (1 - alpha) * s
    return [s] * h


def m_holt(hist, h, m, alpha=0.5, beta=0.1, gamma=0.3):
    """هولت-وینترز جمعی روی لگاریتم (= ضربی روی مقدار)؛ بدون فصل اگر داده کمتر از دو دوره است"""
    if min(hist) <= 0:
        return m_naive(hist, h, m)
    y = [math.log(v) for v in hist]
    seasonal = len(y) >= 2 * m
    if seasonal:
        level = sum(y[:m]) / m
        trend = (sum(y[m:2 * m]) - sum(y[:m])) / (m * m)
        season = [y[i] - level for i in range(m)]
    else:
        level, trend, season = y[0], (y[-1] - y[0]) / max(len(y) - 1, 1), [0.0] * m
    for t in range(len(y)):
        s = season[t % m] if seasonal else 0.0
        prev = level
        level = alpha * (y[t] - s) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev) + (1 - beta) * trend
        if seasonal:
            season[t % m] = gamma * (y[t] - level) + (1 - gamma) * s
    n = len(y)
    out = []
    for i in range(1, h + 1):
        s = season[(n + i - 1) % m] if seasonal else 0.0
        out.append(math.exp(level + i * trend + s))
    return out


def _ridge_feats(y, t, m):
    return [1.0, t / 100.0, y[t - 1], y[t - 2], y[t - 3], y[t - m]]


def m_ridge(hist, h, m, lam=1.0):
    """رگرسیون ریج روی لگاریتم با وقفه‌های ۱ تا ۳ و وقفه‌ی فصلی؛ پیش‌بینی بازگشتی"""
    if min(hist) <= 0 or len(hist) < m + 6:
        return m_holt(hist, h, m)
    y = [math.log(v) for v in hist]
    X = [_ridge_feats(y, t, m) for t in range(m, len(y))]
    Y = [y[t] for t in range(m, len(y))]
    k = len(X[0])
    A = [[sum(X[r][i] * X[r][j] for r in range(len(X))) + (lam if i == j and i > 0 else 0) for j in range(k)]
         for i in range(k)]
    b = [sum(X[r][i] * Y[r] for r in range(len(X))) for i in range(k)]
    w = _solve(A, b)
    if not w:
        return m_holt(hist, h, m)
    ext = y[:]
    for _ in range(h):
        t = len(ext)
        ext.append(sum(wi * xi for wi, xi in zip(w, _ridge_feats(ext, t, m))))
    return [math.exp(v) for v in ext[len(y):]]


# مدل‌های هر نوع سری و شبکه‌ی ابرپارامترها
LEVEL_POSITIVE = {   # فروش و درآمد
    "snaive_g": (m_snaive_g, [{}]),
    "holt": (m_holt, [dict(alpha=a, beta=b, gamma=g) for a in (0.3, 0.6, 0.9) for b in (0.0, 0.1, 0.3) for g in (0.1, 0.4)]),
    "ridge": (m_ridge, [dict(lam=l) for l in (0.3, 3.0, 30.0)]),
    "naive": (m_naive, [{}]),
}
SIGNED = {           # نسبت‌ها و اقلام با علامت (سایر درآمدها، غیرعملیاتی، …)
    "mean": (m_mean, [{}]),
    "snaive": (m_snaive, [{}]),
    "ewma": (m_ewma, [dict(alpha=a) for a in (0.3, 0.6, 0.9)]),
    "naive": (m_naive, [{}]),
}
MODEL_LABEL = {
    "snaive_g": "فصلی با رشد سالانه", "holt": "هولت-وینترز", "ridge": "رگرسیون ریج (وقفه‌ها)",
    "naive": "آخرین مقدار", "mean": "میانگین یک سال", "snaive": "دوره‌ی مشابه سال قبل", "ewma": "هموارسازی نمایی",
}


def _one_step(f, hist, idx, m, params):
    """پیش‌بینی یک‌گام‌به‌جلو برای اندیس‌های idx (هر بار فقط با داده‌ی قبل از آن)"""
    return [f(hist[:i], 1, m, **params)[0] for i in idx]


def _min_hist(m, n):
    return max(3, min(m, n // 2))


# ==================== آموزش، اعتبارسنجی، آزمون و عامل RL ====================
def evaluate(series, m, kind="positive", horizon=0):
    """
    series: مقادیر گذشته به ترتیب زمان. خروجی: معیارهای هر مدل، عامل RL، پیش‌بینی h گام بعد.
    اگر داده برای تقسیم ۷۰/۲۰/۱۰ کافی نباشد، فقط مدل‌های ساده و بدون ارزیابی.
    """
    models = LEVEL_POSITIVE if kind == "positive" and min(series or [0]) > 0 else SIGNED
    n = len(series)
    out = {"n": n, "m": m, "split": None, "models": [], "agent": None, "forecast": [], "enough": False}
    if n < 6:
        if n:
            f, _ = models["naive"]
            out["forecast"] = [{"value": v, "lo": None, "hi": None} for v in f(series, horizon, m)]
        return out

    t, v = split_idx(n)
    start = max(t, _min_hist(m, n))
    t = start if start < v else t
    val_idx, test_idx = list(range(t, v)), list(range(v, n))
    out["split"] = {"train": t, "val": v - t, "test": n - v}
    out["enough"] = n >= 2 * m + 4

    # ---- انتخاب ابرپارامتر هر مدل روی اعتبارسنجی
    chosen = {}
    for name, (f, grid) in models.items():
        best = None
        for p in grid:
            pv = _one_step(f, series, val_idx, m, p)
            e = wape([series[i] for i in val_idx], pv)
            if e is not None and (best is None or e < best[0]):
                best = (e, p, pv)
        if not best:
            continue
        pt = _one_step(f, series, test_idx, m, best[1])
        chosen[name] = {"f": f, "params": best[1], "val": best[0],
                        "test": wape([series[i] for i in test_idx], pt),
                        "pred": dict(zip(val_idx + test_idx, best[2] + pt))}
    if not chosen:
        return out

    # ---- عامل یادگیری تقویتی (Hedge): η روی اعتبارسنجی انتخاب می‌شود
    def run_agent(eta):
        w = {k: 1.0 / len(chosen) for k in chosen}
        preds, hist_w = {}, []
        for i in val_idx + test_idx:
            preds[i] = sum(w[k] * chosen[k]["pred"][i] for k in chosen)
            y = series[i]
            for k in chosen:                                   # پاداش = −خطای نسبی (حداکثر ۱)
                loss = min(abs(y - chosen[k]["pred"][i]) / (abs(y) or 1), 1.0)
                w[k] *= math.exp(-eta * loss)
            s = sum(w.values())
            w = {k: x / s for k, x in w.items()}
            hist_w.append(dict(w))
        return preds, w, hist_w

    best_eta = None
    for eta in (0.5, 2.0, 6.0):
        p, w, hw = run_agent(eta)
        e = wape([series[i] for i in val_idx], [p[i] for i in val_idx])
        if best_eta is None or (e is not None and e < best_eta[0]):
            best_eta = (e, eta, p, w)
    e_val, eta, preds, weights = best_eta
    e_test = wape([series[i] for i in test_idx], [preds[i] for i in test_idx])
    base = chosen.get("naive", {}).get("test")
    out["agent"] = {"eta": eta, "val": e_val, "test": e_test, "weights": weights, "baseline_test": base}

    # ---- پیش‌بینی آینده: برازش دوباره روی کل داده، ترکیب با وزن‌های نهایی عامل
    if horizon > 0:
        fc = {k: c["f"](series, horizon, m, **c["params"]) for k, c in chosen.items()}
        err = (e_test if e_test is not None else e_val or 20) / 100
        for j in range(horizon):
            val = sum(weights[k] * fc[k][j] for k in chosen)
            band = abs(val) * err * math.sqrt(1 + j / m)          # بازه با فاصله‌ی زمانی بازتر می‌شود
            out["forecast"].append({"value": val, "lo": val - band, "hi": val + band,
                                    "by_model": {k: fc[k][j] for k in chosen}})

    out["models"] = [{"name": k, "label": MODEL_LABEL[k], "params": c["params"], "val": c["val"],
                      "test": c["test"], "weight": weights.get(k, 0)} for k, c in chosen.items()]
    out["models"].sort(key=lambda r: r["val"] if r["val"] is not None else 1e9)
    out["test_points"] = [{"i": i, "actual": series[i], "agent": preds[i]} for i in test_idx]
    out["_steps"] = preds          # پیش‌بینی یک‌گام عامل برای اعتبارسنجی و آزمون (برای ارزیابی ترکیبی)
    return out


# ==================== سری‌ها از دیتابیس کدال ====================
def _contiguous(points):
    """
    points: [(کلید زمانی عددی، مقدار)] مرتب. آخرین بخش پیوسته را برمی‌گرداند؛
    شکاف‌های تا ۲ واحدی با درون‌یابی خطی پر می‌شوند.
    """
    if not points:
        return [], [], 0
    seg = [points[-1]]
    filled = 0
    for k, v in reversed(points[:-1]):
        gap = seg[0][0] - k
        if gap == 1:
            seg.insert(0, (k, v))
        elif gap <= 3:
            nxt = seg[0][1]
            for j in range(gap - 1, 0, -1):
                seg.insert(0, (k + j, v + (nxt - v) * j / gap))
                filled += 1
            seg.insert(0, (k, v))
        else:
            break
    return [k for k, _ in seg], [v for _, v in seg], filled


def monthly_series(con, sym):
    """فروش ماهانه (میلیارد تومان) با کلید زمانی سال مالی×۱۲+ماه"""
    rows = con.execute("SELECT fiscal_year, fiscal_month, total FROM monthly_latest WHERE symbol=? "
                       "AND total IS NOT NULL ORDER BY fiscal_year, fiscal_month", (sym,)).fetchall()
    pts = [(r["fiscal_year"] * 12 + r["fiscal_month"] - 1, r["total"] / 10000) for r in rows if r["total"] > 0]
    return _contiguous(pts)


Q_FIELDS = {"rev": ("rev", 1), "cogs": ("cogs", -1), "sga": ("sga", -1), "otherOp": ("other_op", 1),
            "fin": ("fin", -1), "nonOp": ("non_op", 1), "tax": ("tax", -1), "net": ("net", 1)}


def quarterly_series(con, sym):
    """اقلام فصلی صورت سود و زیان (قرارداد مدل: هزینه‌ها مثبت) از دوره‌های تجمعی"""
    rows = con.execute("SELECT * FROM fin_latest WHERE symbol=? AND consolidated=0 AND months IN (3,6,9,12)",
                       (sym,)).fetchall()
    by = {}
    for r in rows:
        by.setdefault(r["fiscal_year"], {})[r["months"]] = r
    pts = []
    for fy in sorted(by):
        for q in range(1, 5):
            cur, prev = by[fy].get(q * 3), by[fy].get((q - 1) * 3) if q > 1 else None
            if not cur or (q > 1 and not prev):
                continue
            vals = {}
            for k, (f, sign) in Q_FIELDS.items():
                a, b = cur[f], (prev[f] if prev else 0)
                vals[k] = None if a is None or b is None else (a - b) * sign
            if vals["rev"] and vals["net"] is not None:
                pts.append((fy * 4 + q - 1, vals))
    # پیوستگی: فصل جاافتاده درون‌یابی نمی‌شود (صورت مالی)، فقط آخرین بخش پیوسته
    seg = pts[-1:] if pts else []
    for k, v in reversed(pts[:-1]):
        if seg[0][0] - k == 1:
            seg.insert(0, (k, v))
        else:
            break
    return [k for k, _ in seg], [v for _, v in seg]


def _label_m(key):
    return {"fy": key // 12, "month": key % 12 + 1}


# ==================== پیش‌بینی فروش ماهانه ====================
def monthly_forecast(con, sym):
    keys, ser, filled = monthly_series(con, sym)
    if not ser:
        return None
    last = keys[-1]
    fm = last % 12 + 1
    horizon = 12 - fm if fm < 12 else 12                     # تا پایان سال مالی (یا سال بعد اگر سال کامل است)
    res = evaluate(ser, 12, "positive", horizon)
    res.pop("_steps", None)
    for j, f in enumerate(res["forecast"]):
        f.update(_label_m(last + 1 + j))
    res["history"] = {"months": len(ser), "first": _label_m(keys[0]), "last": _label_m(last), "filled": filled}
    res["test_points"] = [dict(p, **_label_m(keys[p["i"]])) for p in res.get("test_points", [])]
    return res


# ==================== پیش‌بینی فصلی برای برآورد سود ====================
def _median(a):
    a = sorted(a)
    n = len(a)
    return None if not n else (a[n // 2] if n % 2 else (a[n // 2 - 1] + a[n // 2]) / 2)


def quarterly_forecast(con, sym):
    """
    فصل‌های باقی‌مانده‌ی سال مالی:
    - درآمد: اگر فروش ماهانه هست = ضریب کالیبره × (فروش واقعی ماه‌های گزارش‌شده + پیش‌بینی ماهانه)؛
      ضریب = میانه‌ی «درآمد فصل ÷ جمع فروش ماهانه‌ی همان فصل» در گذشته؛ وگرنه مدل‌های فصلی درآمد
    - بهای تمام‌شده و هزینه‌های فروش: نسبت به درآمد؛ سایر اقلام: مقدار؛ مالیات: نرخ مؤثر
    - ارزیابی ترکیبی: سود خالص ساخته‌شده از پیش‌بینی یک‌گام اقلام در بخش آزمون، در برابر سود واقعی
    """
    keys, qs = quarterly_series(con, sym)
    if not qs:
        return None
    n = len(qs)
    last = keys[-1]
    lq = last % 4 + 1
    H = 4 - lq if lq < 4 else 4
    fy_next = last // 4 if lq < 4 else last // 4 + 1

    rev = [q["rev"] for q in qs]
    ratio = lambda k: [(q[k] or 0) / q["rev"] for q in qs]
    pbt = [q["rev"] - (q["cogs"] or 0) - (q["sga"] or 0) + (q["otherOp"] or 0) - (q["fin"] or 0) + (q["nonOp"] or 0)
           for q in qs]
    rates, prev_rate = [], 0.0
    for p, q in zip(pbt, qs):
        prev_rate = min(max((q["tax"] or 0) / p, 0.0), 0.5) if p > 0 else prev_rate
        rates.append(prev_rate)

    comp = {
        "rev": evaluate(rev, 4, "positive", H),
        "cogs_r": evaluate(ratio("cogs"), 4, "signed", H),
        "sga_r": evaluate(ratio("sga"), 4, "signed", H),
        "otherOp": evaluate([q["otherOp"] or 0 for q in qs], 4, "signed", H),
        "fin": evaluate([q["fin"] or 0 for q in qs], 4, "signed", H),
        "nonOp": evaluate([q["nonOp"] or 0 for q in qs], 4, "signed", H),
        "tax_r": evaluate(rates, 4, "signed", H),
    }

    def build(rv, c_r, s_r, oth, fn, non, t_r):
        cogs, sga = rv * c_r, rv * s_r
        p = rv - cogs - sga + oth - fn + non
        tax = max(p, 0) * min(max(t_r, 0), 0.5)
        return {"rev": rv, "cogs": cogs, "sga": sga, "otherOp": oth, "fin": fn, "nonOp": non, "tax": tax, "net": p - tax}

    # ---- ارزیابی ترکیبی سود خالص روی بخش آزمون (پیش‌بینی یک‌گام همه‌ی اقلام)
    backtest = None
    if comp["rev"]["split"] and all(c.get("_steps") for c in comp.values()):
        t, v = split_idx(n)
        idx = [i for i in range(v, n) if all(i in c["_steps"] for c in comp.values())]
        if idx:
            pred = [build(*(comp[k]["_steps"][i] for k in ("rev", "cogs_r", "sga_r", "otherOp", "fin", "nonOp", "tax_r")))["net"]
                    for i in idx]
            act = [qs[i]["net"] for i in idx]
            backtest = {"net_test": wape(act, pred), "points": [
                {"fy": keys[i] // 4, "q": keys[i] % 4 + 1, "actual": a, "pred": p} for i, a, p in zip(idx, act, pred)]}

    # ---- درآمد از فروش ماهانه (اگر هست)
    rev_source = "quarterly"
    rev_fc = [f["value"] for f in comp["rev"]["forecast"]]
    if len(rev_fc) < H:                       # هیچ مدلی قابل ارزیابی نبود ← آخرین درآمد فصلی (پیش‌بینی ساده)
        rev_fc = (rev_fc + [rev[-1]] * H)[:H]
    mkeys, mser, _ = monthly_series(con, sym)
    mres = None
    if mser:
        month_val = dict(zip(mkeys, [x * 10000 for x in mser]))           # میلیون ریال
        ks = []
        for k, q in zip(keys, qs):
            fy, qq = k // 4, k % 4 + 1
            ms = [month_val.get(fy * 12 + (qq - 1) * 3 + j) for j in range(3)]
            if all(ms) and sum(ms) > 0:
                ks.append(q["rev"] / sum(ms))
        kcal = _median(ks)
        if kcal and 0.5 < kcal < 2:
            mres = monthly_forecast(con, sym)
            m_fc = {mkeys[-1] + 1 + j: f["value"] * 10000 for j, f in enumerate(mres["forecast"])} if mres else {}
            vals = []
            for j in range(H):
                kq = last + 1 + j
                fy, qq = kq // 4, kq % 4 + 1
                ms = [month_val.get(fy * 12 + (qq - 1) * 3 + i) or m_fc.get(fy * 12 + (qq - 1) * 3 + i) for i in range(3)]
                if not all(ms):
                    vals = None
                    break
                vals.append(kcal * sum(ms))
            if vals:
                rev_fc, rev_source = vals, "monthly"

    quarters = []
    for j in range(H):
        g = lambda k: comp[k]["forecast"][j]["value"] if comp[k]["forecast"] else 0.0
        q = build(rev_fc[j], g("cogs_r"), g("sga_r"), g("otherOp"), g("fin"), g("nonOp"), g("tax_r"))
        kq = last + 1 + j
        q.update(fy=kq // 4, q=kq % 4 + 1)
        quarters.append(q)

    for c in comp.values():
        c.pop("_steps", None)
    summ = lambda c: {"val": (c["agent"] or {}).get("val"), "test": (c["agent"] or {}).get("test"),
                      "best": c["models"][0]["label"] if c["models"] else None, "enough": c["enough"],
                      "weights": {m["label"]: m["weight"] for m in c["models"]}}
    return {
        "n": n, "split": comp["rev"]["split"], "history": {"quarters": n, "first": {"fy": keys[0] // 4, "q": keys[0] % 4 + 1},
                                                           "last": {"fy": last // 4, "q": lq}},
        "fy": fy_next, "quarters": quarters, "rev_source": rev_source, "calib_points": len(ks) if mser else 0,
        "components": {k: summ(c) for k, c in comp.items()}, "backtest": backtest,
        "monthly_test": (mres or {}).get("agent"),
    }
