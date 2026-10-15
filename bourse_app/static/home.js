/* ===================== ابزارهای مشترک ===================== */
const FA = "۰۱۲۳۴۵۶۷۸۹", AR = "٠١٢٣٤٥٦٧٨٩";
function faNum(n, d = 0) {
  if (!isFinite(n)) return "—";
  const s = Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  return s.replace(/[0-9]/g, x => "۰۱۲۳۴۵۶۷۸۹"[x]).replace(".", "/");
}
const nf0 = { format: n => faNum(n, 0) };
const nf1 = { format: n => faNum(n, 1) };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function num(s) {
  if (s === null || s === undefined) return 0;
  const t = String(s)
    .replace(/[۰-۹]/g, d => FA.indexOf(d))
    .replace(/[٠-٩]/g, d => AR.indexOf(d))
    .replace(/[,٬\s]/g, "").replace("٫", ".");
  const n = parseFloat(t);
  return isFinite(n) ? n : 0;
}
function fmt(n) {
  if (!isFinite(n)) return "—";
  const r = Math.round(n);
  if (r === 0) return "۰";
  return r < 0 ? "(" + nf0.format(-r) + ")" : nf0.format(r);
}
function pct(n) {
  if (!isFinite(n)) return "—";
  return n < 0 ? "(" + nf1.format(-n) + "٪)" : nf1.format(n) + "٪";
}
function dec(n) { return isFinite(n) && n > 0 ? nf1.format(n) : "—"; }
function faDigits(s) { return String(s).replace(/[0-9]/g, d => FA[d]); }
function load(key, fallback) {
  try { const raw = localStorage.getItem(key); if (raw) return JSON.parse(raw); } catch (e) {}
  return fallback;
}
function save(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {} }
const ICON_X = '<svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>';
const ICON_TRASH = '<svg viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>';

/* رندر دوباره بدون گم شدن فوکوس */
function rerender(root, html) {
  const active = document.activeElement;
  const key = active && root.contains(active) ? active.dataset.k : null;
  root.innerHTML = html;
  if (key) {
    const el = root.querySelector(`[data-k="${CSS.escape(key)}"]`);
    if (el) el.focus();
  }
}

/* ===================== پیش‌بینی یادگیری ماشین (مشترک دو زبانه) ===================== */
const ML = {
  // درصد خطا (WAPE) با رنگ: زیر ۱۰٪ خوب، تا ۲۵٪ متوسط، بیشتر ضعیف
  err(v) {
    if (v === null || v === undefined) return '<span class="muted">—</span>';
    const cls = v < 10 ? "good" : v < 25 ? "mid" : "bad";
    return `<span class="err ${cls}">${faNum(v, 1)}٪</span>`;
  },

  splitTxt(s) {
    return s ? `آموزش ${faNum(s.train)} · اعتبارسنجی ${faNum(s.val)} · آزمون ${faNum(s.test)}` : "";
  },

  // جدول مدل‌ها + عامل یادگیری تقویتی
  modelsTable(res) {
    if (!res || !res.models || !res.models.length) return "";
    const a = res.agent;
    const rows = res.models.map(m => `<tr>
      <td class="lbl">${esc(m.label)}</td><td>${ML.err(m.val)}</td><td>${ML.err(m.test)}</td>
      <td><span class="w-track"><span style="width:${(m.weight * 100).toFixed(0)}%"></span></span>${faNum(m.weight * 100, 0)}٪</td></tr>`).join("");
    return `<div class="tbl-wrap"><table class="tbl ml-tbl">
      <thead><tr><th>مدل</th><th>خطای اعتبارسنجی</th><th>خطای آزمون</th><th>وزن عامل RL</th></tr></thead>
      <tbody>${rows}
        <tr class="total"><td class="lbl">عامل یادگیری تقویتی (ترکیب وزنی، η=${faNum(a.eta, 1)})</td>
          <td>${ML.err(a.val)}</td><td>${ML.err(a.test)}</td><td>۱۰۰٪</td></tr>
      </tbody></table></div>`;
  },

  // دکمه/وضعیت دریافت سابقه‌ی چندساله
  historyBox(job, need, have, unit) {
    if (Bourse.jobActive(job)) {
      return `<div class="ml-hist running"><span>دریافت سابقه از کدال${job.phase ? " — " + esc(job.phase) : ""}:</span>
        ${Bourse.jobLine(job)}</div>`;
    }
    const err = job && job.state === "error" ? `<div class="warn">${faDigits(esc(job.message))}</div>` : "";
    const low = have < need;
    return `${err}<div class="ml-hist ${low ? "low" : ""}">
      <span>${low ? `داده‌ی آموزش کم است: ${faNum(have)} ${unit} (برای مدل قابل اتکا دست‌کم ${faNum(need)} ${unit}).`
                  : `سابقه‌ی آموزش: ${faNum(have)} ${unit}.`}</span>
      <button type="button" class="pill-btn" data-ml-history>دریافت سابقه‌ی ۵ ساله از کدال</button></div>`;
  },

  methodNote() {
    return `<details class="ml-method"><summary>روش: یادگیری ماشین، یادگیری تقویتی و تقسیم ۷۰/۲۰/۱۰</summary>
      <p>داده‌ها به ترتیب زمان (بدون بُر زدن) تقسیم می‌شوند: ۷۰٪ اول برای آموزش، ۲۰٪ بعد برای اعتبارسنجی و ۱۰٪ آخر برای آزمون.
      در اعتبارسنجی، هر مدل ماه‌به‌ماه (یا فصل‌به‌فصل) فقط با داده‌ی گذشته پیش‌بینی می‌کند و بهترین ابرپارامترهایش انتخاب می‌شود.
      مدل‌ها: «فصلی با رشد سالانه»، «هولت-وینترز» (هموارسازی نمایی با روند و فصل، روی لگاریتم برای تورم) و «رگرسیون ریج» روی وقفه‌ها.</p>
      <p>عامل یادگیری تقویتی (راهزن چندبازویی، الگوریتم Hedge) در هر گام پیش‌بینی مدل‌ها را با وزن ترکیب می‌کند؛
      پس از دیدن مقدار واقعی، پاداش هر مدل = منفیِ خطای نسبی آن و وزن‌ها به‌روز می‌شوند. «خطای آزمون» روی داده‌ای است که در هیچ انتخابی استفاده نشده.
      برای پیش‌بینی آینده، مدل‌ها روی کل داده دوباره آموزش می‌بینند. خطا = WAPE (مجموع قدر مطلق خطا ÷ مجموع مقادیر واقعی).</p></details>`;
  },

  async startHistory(sym) {
    await Bourse.api(`/api/ml/${encodeURIComponent(sym)}/history?years=5`, "POST");
  },
};

/* ===================== تاریخ امروز ===================== */
try {
  document.getElementById("today").textContent =
    new Date().toLocaleDateString("fa-IR-u-ca-persian", { day: "numeric", month: "long", year: "numeric" });
} catch (e) {}

/* ===================== زبانه‌ها ===================== */
const tabs = [...document.querySelectorAll(".home-tab")];
/* هر زبانه فقط وقتی دیده می‌شود داده‌اش را می‌گیرد (درخواست کمتر به سرور و به کدال):
   whenVisible(زبانه، تابع) ← اگر زبانه باز است همین حالا، وگرنه با اولین باز شدنش (فقط آخرین درخواست هر زبانه) */
const pendingTab = {};
const tabVisible = name => !document.getElementById("pane-" + name).hidden;
function whenVisible(name, fn) {
  if (tabVisible(name)) { delete pendingTab[name]; fn(); }
  else pendingTab[name] = fn;
}
function showTab(name) {
  if (!["monthly", "estimate", "notes"].includes(name)) name = "monthly";
  tabs.forEach(t => t.setAttribute("aria-selected", String(t.dataset.tab === name)));
  document.querySelectorAll(".home-pane").forEach(p => { p.hidden = p.id !== "pane-" + name; });
  history.replaceState(null, "", location.search + "#" + name);
  if (window.syncRail) window.syncRail();   // هماهنگی با نوار کناری
  const run = pendingTab[name];
  if (run) { delete pendingTab[name]; run(); }
}
tabs.forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));
// کلیک روی «عملکرد ماهانه» یا «برآورد سود» در نوار کناری
window.addEventListener("hashchange", () => showTab(location.hash.slice(1)));
showTab(location.hash.slice(1));

/* ===================== ۱. عملکرد ماهانه ===================== */
(function monthly() {
  const root = document.getElementById("pane-monthly");
  // ماه‌های شمسی؛ ماه‌های سال مالی از ماه بعد از پایان سال مالی شروع می‌شوند
  const CAL = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  const COLORS = ["#2F6BFF", "#1FAF55", "#F8CF4A", "#16181D", "#E5484D", "#8B5CF6"];
  const SYM_KEY = "bourse-monthly-symbol";

  // ---- داده‌ی نمونه (میلیارد تومان) — وقتی نمادی انتخاب نشده ----
  const SAMPLE = {
    symbol: "نماد نمونه", company: "شرکت نمونه", sample: true,
    fy: 1405, yearEndMonth: 12, lastYear: 1405, lastPeriod: "", reports: 6,
    cur:  [426, 453, 341, 388, 471, 485, null, null, null, null, null, null],   // سال جاری
    prev: [230, 248, 242, 236, 201, 262, 255, 240, 228, 231, 232, 329],         // سال قبل
    products: [
      { name: "محصول الف صادراتی", unit: "تن", amt: 1942, sold: 307297, made: 290450 },
      { name: "محصول الف داخلی",   unit: "تن", amt: 277,  sold: 78980,  made: 81200 },
      { name: "محصول ب صادراتی",   unit: "تن", amt: 216,  sold: 38523,  made: 36100 },
      { name: "محصول ب داخلی",     unit: "تن", amt: 129,  sold: 50554,  made: 50554 },
    ],
  };
  let DATA = SAMPLE, current = null, pollTimer = null;
  // وضعیت دیتابیس/کدال نماد فعلی؛ کار در جریان؛ نمادهایی که در این بارگذاری صفحه بررسی خودکار شدند
  let dbInfo = null, curJob = null;
  const autoChecked = new Set();
  // پیش‌بینی یادگیری ماشین: نتیجه، وضعیت کار دریافت سابقه، نمایش در نمودار
  let mlRes = null, mlFor = null, mlJob = null, mlTimer = null, showFc = true;

  async function loadML(sym) {
    clearTimeout(mlTimer);
    let r;
    try { r = await Bourse.api("/api/ml/monthly/" + encodeURIComponent(sym)); }
    catch (e) { return; }
    if (sym !== current) return;
    const wasRunning = Bourse.jobActive(mlJob);
    mlRes = r.result; mlFor = sym; mlJob = r.job;
    if (Bourse.jobActive(mlJob)) mlTimer = setTimeout(() => loadML(sym), 3000);
    else if (wasRunning) { load(sym, false); return; }           // سابقه رسید ← داده و مدل از نو
    if (!DATA.sample && DATA.symbol === sym) render();
  }

  const signed = (n, d = 1) => !isFinite(n) ? "—" : (n > 0 ? "+" : n < 0 ? "-" : "") + faNum(Math.abs(n), d) + "٪";
  const sum = a => a.reduce((s, x) => s + (x || 0), 0);
  const has = v => v !== null && v !== undefined;

  function setIdentity(sym = DATA.symbol, co = DATA.company) {
    // هویت نماد از نوار بالا حذف شده؛ فقط اگر عنصرش باشد پر می‌شود
    const s = document.getElementById("id-sym"), c = document.getElementById("id-co");
    if (s) s.textContent = sym;
    if (c) c.textContent = co ? "(" + co + ")" : "";
  }

  // ---------- انتخاب نماد ----------
  const symForm = document.getElementById("sym-search");
  const symInput = document.getElementById("sym-input");
  Bourse.picker(symInput, s => choose(s.symbol));
  symForm.addEventListener("submit", e => { e.preventDefault(); if (symInput.value.trim()) choose(symInput.value.trim()); });

  function choose(sym) {
    symInput.value = "";
    symInput.blur();
    try { localStorage.setItem(SYM_KEY, sym); } catch (e) {}
    history.replaceState(null, "", "?symbol=" + encodeURIComponent(sym) + location.hash);
    clearTimeout(listTimer);
    setIdentity(sym, "");
    whenVisible("monthly", () => load(sym));       // اگر زبانه‌ی دیگری باز است، با باز شدن عملکرد ماهانه
    // نماد مشترک صفحه: بخش برآورد سود هم همین نماد را می‌گیرد
    document.dispatchEvent(new CustomEvent("bourse:symbol", { detail: sym }));
  }

  /* اول دیتابیس، بعد کدال: داده‌ی ذخیره‌شده فوراً نمایش داده می‌شود؛ سپس یک بار از سرور پرسیده می‌شود
     آیا ماه جاافتاده یا گزارش جدیدتری ممکن است باشد (codal/fresh.py). فقط در آن صورت به کدال رجوع می‌شود. */
  async function load(sym, autoFetch = true) {
    current = sym;
    clearTimeout(pollTimer);
    let r;
    try { r = await Bourse.api("/api/monthly/" + encodeURIComponent(sym)); }
    catch (e) { Bourse.toast(e.message, "err"); return; }
    if (sym !== current) return;   // در این فاصله نماد دیگری انتخاب شده
    const job = r.job;
    curJob = job; dbInfo = r.db;
    if (mlFor !== sym) { mlRes = null; mlJob = null; }
    if (r.data) {
      DATA = r.data; setIdentity(); render(job);
      if (!Bourse.jobActive(job)) {
        if (autoFetch && !autoChecked.has(sym)) { autoChecked.add(sym); fetchFromCodal(sym, true); }
        loadML(sym);
      }
    }
    if (Bourse.jobActive(job)) {
      if (!r.data) renderStatus(sym, job);
      pollTimer = setTimeout(() => load(sym, false), 2000);
      return;
    }
    if (!r.data) {
      if (job && job.state === "error") renderStatus(sym, job);
      else if (autoFetch) fetchFromCodal(sym, true);
      else renderStatus(sym, { state: "error", message: "گزارش ماهانه‌ای برای این نماد ذخیره نشد." });
    }
  }

  // auto: بررسی خودکار صفحه؛ بدون آن = دکمه‌ی کاربر. اگر دیتابیس کافی باشد سرور کاری به کدال نمی‌فرستد (fresh)
  async function fetchFromCodal(sym, auto = false) {
    try {
      const r = await Bourse.api(`/api/monthly/${encodeURIComponent(sym)}/fetch${auto ? "?auto=1" : ""}`, "POST");
      if (sym !== current) return;
      if (r.fresh) {
        if (!auto) Bourse.toast(r.message, "ok");
        return;
      }
      load(sym, false);
    } catch (e) {
      if (sym !== current) return;
      if (!DATA.sample && DATA.symbol === sym) Bourse.toast(e.message, "err");
      else renderStatus(sym, { state: "error", message: e.message });
    }
  }

  // وضعیت دریافت از کدال (وقتی هنوز داده‌ای در دیتابیس نیست)
  function renderStatus(sym, job) {
    DATA = { ...SAMPLE, symbol: sym, company: "" };
    setIdentity();
    const running = Bourse.jobActive(job), cap = job && job.state === "captcha";
    root.innerHTML = `
      <div class="box fetch-state">
        ${running && !cap ? '<span class="spinner" aria-hidden="true"></span>' : ""}
        <h2>${cap ? "منتظر کد امنیتی کدال" : running ? `دریافت گزارش‌های ماهانه‌ی ${esc(sym)} از کدال` : "گزارش ماهانه نمایش داده نمی‌شود"}</h2>
        <div class="sub">${running
          ? `گزارش ماهانه‌ای از ${esc(sym)} در دیتابیس سیستم نیست؛ سال مالی قبل و سال جاری از کدال خوانده و ذخیره می‌شود.
             به خاطر محدودیت کدال بین درخواست‌ها فاصله هست و ممکن است یکی دو دقیقه طول بکشد.`
          : faDigits(esc(job.message || ""))}</div>
        ${running ? `<div>${Bourse.jobLine(job)}</div>` : ""}
        <div class="row-acts" style="justify-content:center">
          ${running ? "" : '<button type="button" class="btn" id="m-retry">تلاش دوباره</button>'}
          <button type="button" class="btn ghost" data-m-list>فهرست رتبه‌بندی نمادها</button></div>
      </div>`;
    document.getElementById("m-retry")?.addEventListener("click", () => fetchFromCodal(sym));
    root.querySelector("[data-m-list]").addEventListener("click", showList);
  }

  /* ---------- صفحه‌ی اول: نمادها به ترتیب بیشترین تغییر درآمد در گزارش‌های یک ماه ----------
     اپراتور ماه گزارش را انتخاب می‌کند؛ از کدال فقط گزارش‌های لازمِ همان ماه گرفته می‌شود: گزارش‌های خود ماه و
     گزارش ماه قبلِ همان نمادها (پایه‌ی رشد)، هر دو فقط اگر در دیتابیس نباشند */
  const METRICS = [
    ["g_mom", "نسبت به ماه قبل", "فروش این ماه نسبت به ماه قبلش"],
    ["g_avg", "نسبت به میانگین ماه‌های قبل", "فروش این ماه نسبت به میانگین ماه‌های قبلِ همان سال مالی (از همین گزارش)"],
    ["g_yoy", "نسبت به ماه مشابه سال قبل", "فروش این ماه نسبت به همان ماه سال قبل (از ستون «مدت مشابه سال قبل» این گزارش و گزارش ماه قبل)"],
    ["g_cum", "تجمعی نسبت به مدت مشابه", "فروش از ابتدای سال مالی نسبت به مدت مشابه سال قبل (از همین گزارش)"],
  ];
  const METRIC_KEY = "bourse-mrank-metric", MONTH_KEY = "bourse-mrank-month", BUDGET_KEY = "bourse-mrank-budget";
  const BUDGETS = [["20", "۲۰ گزارش"], ["40", "۴۰ گزارش"], ["80", "۸۰ گزارش"], ["all", "همه‌ی گزارش‌های لازم"]];
  let listData = null, listTimer = null, listQ = "";
  const listAuto = new Set();                         // ماه‌هایی که در این بارگذاری صفحه بررسی خودکار شدند
  let metric = "g_mom", listMonth = null, listBudget = "all";
  try {
    metric = localStorage.getItem(METRIC_KEY) || metric; listMonth = localStorage.getItem(MONTH_KEY);
    listBudget = localStorage.getItem(BUDGET_KEY) || listBudget;
  } catch (e) {}
  if (!METRICS.some(m => m[0] === metric)) metric = "g_mom";
  if (!BUDGETS.some(b => b[0] === listBudget)) listBudget = "all";
  const monthLabel = m => `${CAL[m.m - 1]} ${faDigits(m.y)}`;

  function showList() {
    current = null;
    clearTimeout(pollTimer); clearTimeout(mlTimer);
    history.replaceState(null, "", location.pathname + location.hash);
    setIdentity("عملکرد ماهانه", "رتبه‌بندی تغییر درآمد");
    if (listData) renderList();
    else root.innerHTML = `<div class="box fetch-state"><span class="spinner" aria-hidden="true"></span><h2>خواندن گزارش‌های ماهانه از دیتابیس…</h2></div>`;
    loadList();
  }

  async function loadList() {
    clearTimeout(listTimer);
    let r;
    try { r = await Bourse.api("/api/mrank" + (listMonth ? "?month=" + encodeURIComponent(listMonth) : "")); }
    catch (e) { Bourse.toast(e.message, "err"); return; }
    if (current !== null) return;                    // در این فاصله نمادی انتخاب شده
    listData = r;
    listMonth = r.month;
    renderList();
    if (Bourse.jobActive(r.job)) { listTimer = setTimeout(loadList, 2000); return; }
    // اول دیتابیس: فقط ماه جاری انتشار و فقط اگر مدتی بررسی نشده، گزارش‌های تازه‌اش (نه همه) گرفته می‌شوند
    if (!listAuto.has(r.month)) { listAuto.add(r.month); scanList(true); }
  }

  function setMonth(m) {
    listMonth = m;
    try { localStorage.setItem(MONTH_KEY, m); } catch (e) {}
    loadList();
  }

  // دریافت از کدال: گزارش‌های ماه + گزارش ماه قبلِ نمادها (سرور فقط آنچه در دیتابیس نیست می‌گیرد)
  async function scanList(auto = false) {
    const budget = auto ? "all" : listBudget;
    try {
      const r = await Bourse.api(`/api/mrank/scan?month=${encodeURIComponent(listMonth || "")}&budget=${budget}${auto ? "&auto=1" : ""}`, "POST");
      if (r.fresh) { if (!auto) Bourse.toast(r.message, "ok"); return; }
      if (current === null) loadList();
    } catch (e) { Bourse.toast(e.message, "err"); }
  }

  async function stopList() {
    try { await Bourse.api("/api/mrank/stop", "POST"); } catch (e) { Bourse.toast(e.message, "err"); }
    if (current === null) loadList();
  }

  function renderList() {
    const d = listData, job = d.job, running = Bourse.jobActive(job);
    const mdef = METRICS.find(m => m[0] === metric);
    const pctTxt = v => v === null || v === undefined ? "—" : signed(v, Math.abs(v) >= 100 ? 0 : 1);
    const pcell = v => `<span class="g ${v > 0 ? "pos" : v < 0 ? "neg" : "muted"}" dir="ltr">${pctTxt(v)}</span>`;
    const bn = v => has(v) ? faNum(v / 10000, 0) : "—";
    const mNow = d.months.find(m => m.month === d.month) || { y: +d.month.slice(0, 4), m: +d.month.slice(5), count: d.meta.count };
    const mName = monthLabel(mNow);
    const pName = esc(d.prev_month_fa);
    // چرا معیار این ردیف خالی است (به جای «—» بی‌توضیح)
    const waitTxt = running ? `در حال دریافت گزارش ${pName}` : `منتظر گزارش ${pName}`;
    const PREV_WHY = { wait: waitTxt, none: `گزارش ${pName} منتشر نشده`, bad: `گزارش ${pName} خوانا نیست` };
    const zero = v => has(v) && v <= 0;                // پایه‌ی صفر: درصد تغییر معنا ندارد
    const why = r => {
      if (!has(r.total)) return "فروش این ماه در گزارش نیست";
      if (metric === "g_mom") return zero(r.prev) ? "فروش ماه قبل صفر بوده" : PREV_WHY[r.prev_state] || "";
      if (metric === "g_yoy") return zero(r.ly) ? "فروش ماه مشابه پارسال صفر بوده"
        : r.prev_state === "wait" ? waitTxt : "پایه‌ی سال قبل در دسترس نیست";
      if (!has(r.cum)) return "ستون‌های تجمعی در گزارش نیست";
      if (metric === "g_cum") return r.bad_ly ? "ستون سال قبلِ گزارش ناسازگار است" : "پایه‌ی سال قبل در دسترس نیست";
      return r.fiscal_month === 1 ? "ماه اول سال مالی" : "فروش ماه‌های قبل صفر بوده";
    };
    const q = listQ.trim();
    let rows = d.rows.filter(r => !q || r.symbol.includes(q) || (r.name || "").includes(q));
    rows = [...rows].sort((a, b) => {
      const va = a[metric], vb = b[metric];
      if (!has(va)) return has(vb) ? 1 : 0;
      if (!has(vb)) return -1;
      return vb - va;
    });
    const ranked = d.rows.filter(r => has(r[metric])).sort((a, b) => b[metric] - a[metric]);
    const rankOf = new Map(ranked.map((r, i) => [r.symbol, i + 1]));
    const maxAbs = Math.max(50, ...ranked.slice(0, 50).map(r => Math.min(Math.abs(r[metric]), 300)));
    const top = ranked[0], bottom = ranked[ranked.length - 1];

    const body = rows.map(r => {
      const v = r[metric], rk = rankOf.get(r.symbol);
      const w = has(v) ? Math.min(Math.abs(v), 300) / maxAbs * 100 : 0;
      const others = METRICS.filter(m => m[0] !== metric).map(([k, l]) => `<span title="${l}">${l.replace("نسبت به ", "")}: ${pcell(r[k])}</span>`).join("");
      return `<tr data-sym="${esc(r.symbol)}" tabindex="0">
        <td>${rk ? `<span class="rank ${rk <= 3 ? "top" : ""}">${faNum(rk)}</span>` : '<small class="muted">—</small>'}</td>
        <td><b class="sym-link">${esc(r.symbol)}</b><small class="co">${esc(r.name || "")}</small></td>
        <td>${faDigits((r.published || "").slice(0, 10))}<small class="co">ماه ${faNum(r.fiscal_month)} سال مالی</small></td>
        <td><b>${bn(r.total)}</b><small class="co">${metric === "g_mom" && has(r.prev) ? "ماه قبل " + bn(r.prev)
          : metric === "g_avg" && has(r.avg_prev) ? "میانگین " + bn(r.avg_prev)
          : metric === "g_yoy" && has(r.ly) ? "پارسال " + bn(r.ly)
          : metric === "g_cum" && has(r.cum) ? "تجمعی " + bn(r.cum) : ""}</small></td>
        <td class="mr-chg">${has(v) ? `${pcell(v)}<span class="mr-track ${v < 0 ? "neg" : ""}"><span style="width:${w}%"></span></span>`
          : `<small class="mr-why ${r.prev_state === "wait" && metric !== "g_avg" ? "wait" : ""}">${why(r) || "—"}</small>`}</td>
        <td class="mr-others">${others}</td>
        <td>${Bourse.priceCell(r.price)}</td>
        <td class="row-acts"><button type="button" class="mini-btn" data-open="${esc(r.symbol)}">گزارش ماهانه</button></td>
      </tr>`;
    }).join("");

    // انتخاب ماه گزارش (تعداد شرکت‌های موجود در دیتابیس کنار هر ماه)
    const monthSel = `<label class="mr-month" title="ماه گزارش">
      <svg class="icon" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>
      <select id="mr-month" aria-label="ماه گزارش">${d.months.map(m =>
        `<option value="${m.month}" ${m.month === d.month ? "selected" : ""}>${monthLabel(m)} — ${m.count ? faNum(m.count) + " شرکت" : "بدون گزارش"}${m.done ? " ✓" : ""}</option>`).join("")}
      </select>
      <svg class="icon chev" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg></label>`;
    const otherJob = running && d.job_month && d.job_month !== d.month;
    // گزارش ماه قبل (پایه‌ی رشد): در حال دریافت / هنوز گرفته نشده / منتشر نشده
    const pc = d.meta.prev || {};
    const prevNeeded = (metric === "g_mom" || metric === "g_yoy") && d.rows.length;
    const prevHint = prevNeeded && (pc.wait || pc.none || pc.bad) ? `<div class="${pc.wait ? "warn" : "info"} mr-prev">${pc.wait ? (running && !otherJob
        ? `گزارش ${pName} برای ${faNum(pc.wait)} نماد در حال دریافت است تا رشد و رتبه‌ی آن‌ها حساب شود؛ جدول با رسیدن هر گزارش به‌روز می‌شود.`
        : `برای محاسبه‌ی رشد ${faNum(pc.wait)} نماد، گزارش ${pName} آن‌ها لازم است که هنوز در دیتابیس نیست.
           ${running ? "" : `<button type="button" class="pill-btn" id="mr-prev">دریافت از کدال</button>`}`) : ""}
        ${pc.none ? `<span>${faNum(pc.none)} نماد گزارش ${pName} را در کدال منتشر نکرده‌اند.</span>` : ""}
        ${pc.bad ? `<span>قالب گزارش ${pName} در ${faNum(pc.bad)} نماد خوانا نیست.</span>` : ""}</div>` : "";
    const budgetSel = `<select id="mr-budget" aria-label="تعداد گزارش">${BUDGETS.map(([v, l]) =>
      `<option value="${v}" ${v === listBudget ? "selected" : ""}>${l}</option>`).join("")}</select>`;

    root.innerHTML = `
      <div class="mr">
        <div class="mr-head">
          <div class="mr-title">
            <span class="mr-eyebrow">رتبه‌بندی تغییر درآمد · گزارش فعالیت ماهانه</span>
            <h1>عملکرد ماهانه <span class="mr-dash">—</span> <span class="mr-mname">${mName}</span></h1>
            <div class="sub">نمادها به ترتیب بیشترین تغییر درآمد در گزارش‌های ${mName}. روی هر ردیف بزنید تا گزارش کامل نماد باز شود.</div>
          </div>
          <div class="mr-ctrl">
            <div class="mr-ctrl-row">
              ${monthSel}
              ${running ? "" : `<div class="mr-fetch">${budgetSel}
                <button type="button" class="mr-go" id="mr-scan">
                  <svg class="icon" viewBox="0 0 24 24"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>دریافت از کدال</button></div>`}
            </div>
            <div class="mr-status">
              ${running ? `<span class="mr-live">${otherJob ? `<span class="muted">${esc(job.name || "")}:</span>` : ""}${Bourse.jobLine(job)}
                ${job.stop ? "" : '<button type="button" class="mr-stop" id="mr-stop">توقف</button>'}</span>` : ""}
              ${!running && job && job.state === "error" ? `<span class="neg">${faDigits(esc(job.message))}</span>` : ""}
              ${!running && job && job.stopped && job.month === d.month ? `<span class="muted">${faNum(job.fetched || 0)} گزارش گرفته شد و دریافت متوقف شد</span>` : ""}
              ${Bourse.dbNote(d.db)}
            </div>
          </div>
        </div>

        <div class="kpis mr-kpis">
          <div class="kpi"><span class="lbl">شرکت‌های ${mName} در دیتابیس</span><span class="val">${faNum(d.meta.count)}</span>
            <span class="note">${d.meta.known_missing ? `${faNum(d.meta.known_missing)} گزارش شناخته‌شده‌ی دیگر هنوز دریافت نشده` : mNow.done ? "همه‌ی گزارش‌های این ماه دریافت شده" : "با هر دریافت، شرکت‌های بیشتری اضافه می‌شوند"}</span></div>
          <div class="kpi"><span class="lbl">بیشترین رشد (${mdef[1]})</span>
            <span class="val up">${top ? signed(top[metric]) : "—"}</span><span class="note">${top ? esc(top.symbol) + " — " + esc(top.name || "") : "هنوز داده‌ای نیست"}</span></div>
          <div class="kpi"><span class="lbl">بیشترین افت</span>
            <span class="val ${bottom && bottom[metric] < 0 ? "down" : ""}">${bottom && ranked.length > 1 ? signed(bottom[metric]) : "—"}</span>
            <span class="note">${bottom && ranked.length > 1 ? esc(bottom.symbol) + " — " + esc(bottom.name || "") : ""}</span></div>
          <div class="kpi"><span class="lbl">آخرین انتشار در این ماه</span><span class="val sm">${d.meta.latest ? faDigits(d.meta.latest.slice(0, 10)) : "—"}</span>
            <span class="note">تاریخ انتشار در کدال</span></div>
        </div>

        <div class="box">
          <div class="mr-filters">
            <div class="seg" role="group" aria-label="معیار تغییر درآمد">${METRICS.map(([k, l, t]) =>
              `<button type="button" data-metric="${k}" aria-pressed="${k === metric}" title="${t}">${l}</button>`).join("")}</div>
          </div>
          ${prevHint}
          ${d.rows.length ? `<div class="tbl-wrap"><table class="tbl mr-tbl">
            <thead><tr><th>رتبه</th><th>نماد</th><th>انتشار</th><th>فروش ${CAL[mNow.m - 1]} (میلیارد تومان)</th>
              <th>تغییر ${mdef[1]}</th><th class="mr-others">معیارهای دیگر</th><th>قیمت</th><th></th></tr></thead>
            <tbody>${body || '<tr><td colspan="8" class="muted">نتیجه‌ای با این فیلتر نیست.</td></tr>'}</tbody>
          </table></div>
          <div class="source">${faNum(rows.length)} ردیف، ${faNum(ranked.length)} رتبه‌دار — ${mdef[2]}. فروش ماه = جمع مبلغ فروش «دوره یک ماهه» در جدول تولید و فروش.
            پایه‌ی «نسبت به ماه قبل» گزارش ماه قبل است که همراه گزارش‌های همین ماه خودکار از کدال گرفته می‌شود؛ «ماه مشابه سال قبل» از ستون
            «مدت مشابه سال قبل» همین گزارش منهای همان ستون در گزارش ماه قبل.</div>`
          : `<div class="empty-state">هنوز گزارش ${mName} در دیتابیس سیستم نیست.<br>
              <span class="sub">«دریافت گزارش‌های ${mName} از کدال» فقط گزارش‌های همین ماه را می‌خواند و ذخیره می‌کند؛
              هر بار فقط گزارش‌هایی که در دیتابیس نیستند گرفته می‌شوند. یا ماه دیگری انتخاب کنید یا نماد را در کادر بالا جستجو کنید.</span></div>`}
        </div>
      </div>`;

    document.getElementById("mr-month").addEventListener("change", e => setMonth(e.target.value));
    document.getElementById("mr-scan")?.addEventListener("click", () => scanList(false));
    document.getElementById("mr-prev")?.addEventListener("click", () => scanList(false));
    document.getElementById("mr-stop")?.addEventListener("click", stopList);
    document.getElementById("mr-budget")?.addEventListener("change", e => {
      listBudget = e.target.value;
      try { localStorage.setItem(BUDGET_KEY, listBudget); } catch (err) {}
    });
    root.querySelectorAll("[data-metric]").forEach(b => b.addEventListener("click", () => {
      metric = b.dataset.metric;
      try { localStorage.setItem(METRIC_KEY, metric); } catch (e) {}
      renderList();
    }));
    root.querySelectorAll("tr[data-sym]").forEach(tr => {
      const open = () => choose(tr.dataset.sym);
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", e => { if (e.key === "Enter") open(); });
    });
  }

  // ---------- نمایش ----------
  function render(job = curJob) {
    const cur = DATA.cur, prev = DATA.prev;
    const M = i => CAL[(DATA.yearEndMonth + i) % 12];             // نام ماه iام سال مالی
    let L = -1;
    cur.forEach((v, i) => { if (has(v)) L = i; });                // آخرین ماه گزارش‌شده
    const n = L + 1;
    const lastName = M(L);
    const fy = faDigits(DATA.fy), fyPrev = faDigits(DATA.fy - 1);
    const prevFull = prev.every(has);
    const sample = DATA.sample;
    const badge = sample ? '<span class="badge sample">داده‌ی نمونه</span>' : '<span class="badge outline">کدال</span>';
    const yearEnd = CAL[DATA.yearEndMonth - 1];
    const lastReport = sample ? "شهریور ۱۴۰۵" : `${lastName} ${faDigits(DATA.lastYear)}`;

    // شاخص‌ها (ماه‌های بدون گزارش در سال قبل ← «—»)
    const chg = (a, b) => b ? (a / b - 1) * 100 : NaN;
    const mChg = has(prev[L]) ? chg(cur[L], prev[L]) : NaN;
    const qStart = Math.floor(L / 3) * 3;
    const qIdx = [...Array(L - qStart + 1).keys()].map(k => qStart + k);
    const qOk = qIdx.every(i => has(cur[i]) && has(prev[i]));
    const qChg = qOk ? chg(sum(qIdx.map(i => cur[i])), sum(qIdx.map(i => prev[i]))) : NaN;
    const cumIdx = [...Array(n).keys()];
    const cumOk = cumIdx.every(i => has(cur[i]) && has(prev[i]));
    const cum = sum(cur.slice(0, n)), cumPrev = sum(prev.slice(0, n));
    const cumChg = cumOk ? chg(cum, cumPrev) : NaN;
    const coverage = prevFull ? cum / sum(prev) * 100 : NaN;
    const missingCur = cumIdx.filter(i => !has(cur[i])).length;
    const kpi = (lbl, v, cls, note) =>
      `<div class="kpi"><span class="lbl">${lbl}</span><span class="val ${cls}">${v}</span><span class="note">${note}</span></div>`;
    const tone = v => !isFinite(v) ? "" : v >= 0 ? "up" : "down";
    const kpis = [
      kpi("درصد تغییرات فروش ماهانه", signed(mChg), tone(mChg),
        has(prev[L]) ? `${lastName} ${fy} نسبت به ${lastName} ${fyPrev}` : `گزارش ${lastName} ${fyPrev} موجود نیست`),
      kpi("درصد تغییرات فروش فصلی", signed(qChg), tone(qChg),
        qOk ? `${M(qStart)} تا ${lastName} نسبت به مدت مشابه ${fyPrev}` : "گزارش‌های فصل در یکی از دو سال کامل نیست"),
      kpi("درصد تغییرات فروش تجمعی", signed(cumChg), tone(cumChg),
        cumOk ? `${faNum(n, 0)} ماهه ${fy} نسبت به مدت مشابه ${fyPrev}` : "گزارش‌های دوره در یکی از دو سال کامل نیست"),
      kpi("درصد فروش سال گذشته (پوشش درآمد)", isFinite(coverage) ? faNum(coverage, 1) + "٪" : "—", "",
        prevFull ? `فروش ${faNum(n, 0)} ماهه از کل فروش سال مالی ${fyPrev}` : `گزارش‌های سال مالی ${fyPrev} کامل نیست`),
    ].join("");

    // پیش‌بینی مدل برای ماه‌های گزارش‌نشده‌ی همین سال مالی
    const ml = !sample && mlRes && mlFor === DATA.symbol ? mlRes : null;
    const fc = {};
    if (ml) ml.forecast.filter(f => f.fy === DATA.fy).forEach(f => { fc[f.month - 1] = f; });
    const fcOn = showFc && Object.keys(fc).length > 0;

    // نمودار میله‌ای
    const vals = [...cur, ...prev, ...(fcOn ? Object.values(fc).map(f => f.value) : [])].filter(has);
    const maxV = Math.max(...vals, 1);
    const step = Math.pow(10, Math.floor(Math.log10(maxV * 1.2 / 3)));
    const top = Math.ceil(maxV * 1.2 / 3 / step) * step * 3;      // سقف محور با تقسیم‌های گرد
    const h = v => (v / top) * 100;
    const curVals = cur.slice(0, n).filter(has);
    const avgCur = curVals.length ? sum(curVals) / curVals.length : 0;
    const prevShown = prev.filter(has);                           // سال قبل: همه‌ی ۱۲ ماه
    const avgPrev = prevShown.length ? sum(prevShown) / prevShown.length : null;
    const grid = [0, 1, 2, 3].map(i => {
      const v = top * i / 3;
      return `<div class="grid-line" style="bottom:${(i / 3) * 100}%"><span>${faNum(v, 0)}</span></div>`;
    }).join("");
    const months = cur.map((c, i) => {
      const p = has(prev[i]) ? prev[i] : null;
      const f = fcOn && !has(c) ? fc[i] : null;
      const curBar = has(c)
        ? `<div class="bar cur" style="height:${h(c)}%"><b>${faNum(c, 0)}</b></div>`
        : f ? `<div class="bar fc" style="height:${h(f.value)}%" title="پیش‌بینی مدل: ${faNum(f.value, 0)} (بازه ${faNum(f.lo, 0)} تا ${faNum(f.hi, 0)})"><b>${faNum(f.value, 0)}</b></div>`
        : `<div class="bar ghost"></div>`;
      const prevBar = p !== null ? `<div class="bar prev" style="height:${h(p)}%"></div>` : "";
      return `<div class="month">${curBar}${prevBar}<span class="mlabel ${i === L ? "last" : ""}">${M(i)}</span></div>`;
    }).join("");

    // نمودار رشد ماهانه
    const growth = cur.map((c, i) => {
      const before = i === 0 ? prev[11] : cur[i - 1];
      return has(c) && has(before) && before ? (c / before - 1) * 100 : null;
    });
    const gVals = growth.filter(has);
    const gMax = Math.max(30, ...gVals.map(Math.abs));
    const gCols = cur.map((c, i) => {
      const g = growth[i];
      let inner;
      if (g === null) inner = `<span class="g-dot none"></span>`;
      else {
        const len = Math.abs(g) / gMax * 44;            // درصد از ارتفاع ستون
        const pos = g >= 0, cls = pos ? "pos" : "neg";
        if (len < 8) {
          inner = `<span class="g-dot ${pos ? "" : "neg"}"></span>
            <span class="g-val ${cls}" style="${pos ? "bottom" : "top"}:calc(50% + 16px)">${signed(g)}</span>`;
        } else {
          inner = `<span class="g-bar ${cls}" style="height:${len}%"></span>
            <span class="g-val ${cls}" style="${pos ? "bottom" : "top"}:calc(50% + ${len}% + 6px)">${signed(g)}</span>`;
        }
      }
      return `<div class="g-col ${i === L ? "last" : ""}"><div class="g-track">${inner}</div><span class="g-label">${M(i)}</span></div>`;
    }).join("");
    const gAvg = gVals.length ? sum(gVals) / gVals.length : NaN;

    // ترکیب فروش محصولات
    const products = DATA.products.map((p, i) => ({ ...p, color: COLORS[i % COLORS.length] }));
    const pTotal = sum(products.map(p => p.amt));
    const R = 100, C = 2 * Math.PI * R, GAP = 7;
    let offset = 0;
    const segs = products.map(p => {
      const len = pTotal ? p.amt / pTotal * C : 0;
      const seg = `<circle cx="135" cy="135" r="${R}" fill="none" stroke="${p.color}" stroke-width="48"
        stroke-dasharray="${Math.max(len - GAP, 0)} ${C}" stroke-dashoffset="${-offset}"/>`;
      offset += len;
      return seg;
    }).join("");
    const prods = products.map(p => {
      const share = pTotal ? p.amt / pTotal * 100 : 0;
      let meta = "", chip = "";
      if (has(p.sold) && has(p.made)) {
        const diff = p.made - p.sold, u = esc(p.unit || "");
        meta = `<div class="prod-meta">تولید ${faNum(p.made, 0)} / فروش ${faNum(p.sold, 0)} ${u}</div>`;
        chip = diff < 0
          ? `<span class="chip">کاهش موجودی ${faNum(-diff, 0)}</span>`
          : diff > 0 ? `<span class="chip green">افزایش موجودی ${faNum(diff, 0)}</span>` : `<span class="chip" style="background:#F2F3F7;color:#6B7180">بدون تغییر موجودی</span>`;
      }
      return `<div class="prod">
        <div class="prod-head"><span class="prod-name"><i style="background:${p.color}"></i>${esc(p.name)}</span><span class="prod-pct">${faNum(share, 1)}٪</span></div>
        <div class="prod-amt">${faNum(p.amt, 0)} میلیارد تومان</div>
        <div class="prod-track"><span style="width:${share}%;background:${p.color}"></span></div>
        ${meta}${chip ? `<div>${chip}</div>` : ""}
      </div>`;
    }).join("");

    // ---- پنل پیش‌بینی یادگیری ماشین
    let mlPanel = "";
    if (!sample) {
      if (!ml) {
        mlPanel = `<div class="box ml-box"><h2>پیش‌بینی فروش با یادگیری ماشین</h2>
          ${Bourse.jobActive(mlJob) ? ML.historyBox(mlJob, 36, 0, "ماه") : '<div class="sub"><span class="spinner sm"></span>آموزش مدل‌ها روی سابقه‌ی نماد…</div>'}</div>`;
      } else {
        const hist = ml.history;
        const rest = Object.entries(fc).map(([i, f]) => ({ i: +i, ...f })).sort((a, b) => a.i - b.i);
        const yearFc = cum + rest.reduce((s, f) => s + f.value, 0);
        const coversYear = n + rest.length === 12 && !missingCur;
        const yearG = coversYear && prevFull ? (yearFc / sum(prev) - 1) * 100 : NaN;
        const a = ml.agent;
        const fcRows = (rest.length ? rest : ml.forecast.map(f => ({ ...f, i: f.month - 1, next: true }))).map(f => `<tr>
          <td class="lbl">${CAL[(DATA.yearEndMonth + f.i) % 12]} ${faDigits(f.fy)}</td>
          <td><b>${faNum(f.value, 0)}</b></td>
          <td class="muted">${f.lo !== null ? `${faNum(Math.max(f.lo, 0), 0)} تا ${faNum(f.hi, 0)}` : "—"}</td>
          <td>${has(prev[f.i]) && f.fy === DATA.fy ? signed((f.value / prev[f.i] - 1) * 100) : "—"}</td></tr>`).join("");
        const tile = (l, v, note) => `<div class="kpi"><span class="lbl">${l}</span><span class="val">${v}</span><span class="note">${note}</span></div>`;
        mlPanel = `<div class="box ml-box">
          <div class="box-head">
            <div><h2>پیش‌بینی فروش با یادگیری ماشین <span class="badge outline">مدل</span></h2>
              <div class="sub">آموزش روی ${faNum(hist.months)} ماه سابقه‌ی ${esc(DATA.symbol)} در کدال
                (${CAL[(DATA.yearEndMonth + hist.first.month - 1) % 12]} ${faDigits(hist.first.fy)} تا ${CAL[(DATA.yearEndMonth + hist.last.month - 1) % 12]} ${faDigits(hist.last.fy)})
                · ${ML.splitTxt(ml.split)}${hist.filled ? ` · ${faNum(hist.filled)} ماه جاافتاده درون‌یابی شد` : ""}</div></div>
          </div>
          ${a ? `<div class="kpis">
            ${coversYear ? tile(`پیش‌بینی فروش کل سال ${fy}`, faNum(yearFc, 0), `میلیارد تومان — ${faNum(n)} ماه واقعی + ${faNum(rest.length)} ماه پیش‌بینی`) : ""}
            ${isFinite(yearG) ? tile(`رشد پیش‌بینی‌شده نسبت به ${fyPrev}`, signed(yearG), "فروش کل سال") : ""}
            ${tile("خطای آزمون عامل RL", a.test !== null ? faNum(a.test, 1) + "٪" : "—", `روی ${faNum(ml.split.test)} ماه آخر که در آموزش نبود`)}
            ${tile("خطای مبنا (آخرین مقدار)", a.baseline_test !== null && a.baseline_test !== undefined ? faNum(a.baseline_test, 1) + "٪" : "—", "برای مقایسه با پیش‌بینی ساده")}
          </div>` : ""}
          <div class="ml-grid">
            <div><div class="sec-title">پیش‌بینی ماه‌های آینده (میلیارد تومان)</div>
              <div class="tbl-wrap"><table class="tbl">
                <thead><tr><th>ماه</th><th>پیش‌بینی</th><th>بازه‌ی خطا</th><th>نسبت به پارسال</th></tr></thead>
                <tbody>${fcRows || '<tr><td colspan="4" class="muted">ماهی برای پیش‌بینی نمانده است.</td></tr>'}</tbody>
              </table></div></div>
            <div><div class="sec-title">دقت مدل‌ها (خطای کمتر بهتر)</div>${a ? ML.modelsTable(ml) : '<div class="warn">داده برای تقسیم آموزش/اعتبارسنجی/آزمون کافی نیست؛ فقط پیش‌بینی ساده نمایش داده شد.</div>'}</div>
          </div>
          ${ML.historyBox(mlJob, 36, hist.months, "ماه")}
          ${ML.methodNote()}
        </div>`;
      }
    }

    const notes = [];
    if (sample || !DATA.coverage) {
      if (missingCur) notes.push(`گزارش ${faNum(missingCur)} ماه از سال ${fy} پیدا نشد (ستون خط‌چین)`);
      if (!sample && !prevFull) notes.push(`گزارش‌های سال مالی ${fyPrev} کامل نیست`);
    }

    // نوار کامل بودن داده‌ها: سال قبل ۱۲ ماه، سال جاری تا آخرین گزارش، بقیه پیش‌بینی مدل
    let covBar = "";
    const cv = !sample && DATA.coverage;
    if (cv) {
      const mName = k => CAL[(DATA.yearEndMonth + k - 1) % 12];
      const miss = [...cv.missing_prev.map(k => `${mName(k)} ${fyPrev}`), ...cv.missing_cur.map(k => `${mName(k)} ${fy}`)];
      const restN = 12 - cv.cur_upto;
      const ok = (have, total) => `<b class="${have >= total ? "pos" : "neg"}">${faNum(have)} از ${faNum(total)}</b>`;
      covBar = `<div class="cov-bar ${miss.length ? "missing" : ""}">
        <span>سال مالی ${fyPrev}: ${ok(cv.prev_have, 12)} ماه</span>
        <span>سال مالی ${fy}: ${ok(cv.cur_have, cv.cur_upto)} ماه تا ${mName(cv.cur_upto)} (آخرین گزارش)</span>
        ${restN > 0 ? `<span class="fc-note"><i class="fc-swatch"></i>${faNum(restN)} ماه تا پایان سال: پیش‌بینی مدل</span>` : ""}
        ${miss.length ? `<span class="neg">جاافتاده: ${miss.join("، ")}</span>
          <button type="button" class="pill-btn" id="m-fill" ${Bourse.jobActive(job) ? "disabled" : ""}>تکمیل از کدال</button>` : ""}
      </div>`;
    }
    const running = Bourse.jobActive(job);

    root.innerHTML = `
      <div class="monthly">
        <aside class="m-side">
          <div class="m-title">
            <h1>عملکرد ماهانه</h1>
            <div class="sub">بر اساس گزارش‌های فعالیت ماهانه کدال</div>
            <div class="m-title-acts">
              <span class="pill-black">سال مالی منتهی به ${yearEnd}</span>
              ${sample ? "" : `<button type="button" class="pill-btn" id="m-update" ${running ? "disabled" : ""}
                title="اول دیتابیس سیستم بررسی می‌شود؛ فقط اگر گزارشی کم باشد یا گزارش جدیدتری ممکن باشد، از کدال گرفته می‌شود">
                ${running ? '<span class="spinner sm"></span>در حال دریافت…' : "بررسی گزارش‌های جدید"}</button>`}
              <button type="button" class="pill-btn" data-m-list>فهرست نمادها</button>
            </div>
            ${running ? `<div class="m-job">${Bourse.jobLine(job)}</div>` : ""}
            ${!sample && dbInfo ? `<div>${Bourse.dbNote(dbInfo)}</div>` : ""}
          </div>
          <div class="box">
            <div>
              <h2>ترکیب فروش محصولات</h2>
              <div class="sub">تجمعی ${faNum(n, 0)} ماهه سال مالی ${fy}${missingCur ? " (ماه‌های گزارش‌شده)" : ""}</div>
            </div>
            <div class="donut-wrap">
              <svg viewBox="0 0 270 270" aria-hidden="true">${segs}</svg>
              <div class="donut-center"><b class="${pTotal >= 100000 ? "long" : ""}">${faNum(pTotal, 0)}</b><span>میلیارد تومان<br>${faNum(products.length, 0)} ردیف</span></div>
            </div>
            <div class="prod-list">${prods}</div>
          </div>
        </aside>

        <div class="m-main">
          <div class="box">
            <div class="box-head">
              <div>
                <h2>نمودار میله‌ای مبالغ فروش</h2>
                <div class="sub">مقایسه ماه‌به‌ماه سال مالی ${fy} با ${fyPrev} — آخرین گزارش: ${lastReport}</div>
              </div>
              <div class="legend">
                <span><i style="background:var(--primary)"></i>سال مالی ${fy}</span>
                <span><i style="background:var(--green)"></i>سال مالی ${fyPrev}</span>
                ${Object.keys(fc).length ? `<label class="fc-toggle"><input type="checkbox" id="m-fc" ${showFc ? "checked" : ""}>
                  <i class="fc-swatch"></i>پیش‌بینی مدل</label>` : ""}
                <span>ارقام: میلیارد تومان</span>
                ${badge}
              </div>
            </div>
            ${notes.length ? `<div class="warn">${notes.join("؛ ")}.</div>` : ""}
            ${covBar}
            <div class="kpis">${kpis}</div>
            <div class="barchart">
              <div class="plot">
                ${grid}
                <div class="months">${months}</div>
                <div class="avg blue" style="bottom:${h(avgCur)}%"><span>میانگین ${faNum(avgCur, 0)}</span></div>
                ${avgPrev !== null ? `<div class="avg green" style="bottom:${h(avgPrev)}%"><span>میانگین ${faNum(avgPrev, 0)}</span></div>` : ""}
              </div>
            </div>
          </div>

          <div class="box">
            <div>
              <h2>درصد رشد مبلغ فروش نسبت به ماه گذشته</h2>
              <div class="sub">سال مالی ${fy} — ماه اول با آخرین ماه سال مالی قبل مقایسه شده است</div>
            </div>
            <div class="growth">${gCols}</div>
            <div class="growth-foot">
              <div class="legend">
                <span><i style="background:var(--primary)"></i>رشد</span>
                <span><i style="background:var(--red)"></i>افت</span>
                <span><i style="background:var(--primary-soft)"></i>آخرین ماه</span>
              </div>
              <span class="avg-pill">میانگین رشد ماهانه: <b>${signed(gAvg)}</b></span>
            </div>
          </div>
        </div>
      </div>

      ${mlPanel}

      <div class="box" style="margin-top:12px">
        <h2>اسپرد محصولات به مواد</h2>
        <div class="dashed-note">
          ضریب تبدیل مواد اولیه به محصول هنوز تعریف نشده است؛ بعد از اتصال به جدول «مصرف مواد» گزارش‌های کدال، اسپرد هر محصول اینجا نمایش داده می‌شود.
        </div>
      </div>
      <div class="source" style="margin-top:8px">منبع: کدال — جدول «تولید و فروش» — ${faNum(DATA.reports, 0)} گزارش ماهانه${
        sample ? ' — <span class="badge sample">داده‌ی نمونه</span> — برای داده‌ی واقعی نماد را در کادر بالا جستجو کنید'
               : ` — آخرین دوره ${faDigits(DATA.lastPeriod)}${DATA.company ? "" : ""}`}</div>`;

    document.getElementById("m-update")?.addEventListener("click", () => fetchFromCodal(DATA.symbol));
    document.getElementById("m-fill")?.addEventListener("click", () => fetchFromCodal(DATA.symbol));
    root.querySelector("[data-m-list]")?.addEventListener("click", showList);
    document.getElementById("m-fc")?.addEventListener("change", e => { showFc = e.target.checked; render(); });
    root.querySelector("[data-ml-history]")?.addEventListener("click", async () => {
      const s = DATA.symbol;
      try { await ML.startHistory(s); mlJob = { state: "running", fetched: 0 }; render(); loadML(s); }
      catch (e) { Bourse.toast(e.message, "err"); }
    });
  }

  // آغاز: نماد در آدرس (?symbol=) ← گزارش همان نماد؛ وگرنه فهرست نمادها به ترتیب بیشترین تغییر درآمد
  const start = new URLSearchParams(location.search).get("symbol");
  if (start) {
    setIdentity(start, "");
    root.innerHTML = `<div class="box fetch-state"><span class="spinner" aria-hidden="true"></span><h2>خواندن گزارش‌های ماهانه‌ی ${esc(start)} از دیتابیس…</h2></div>`;
    whenVisible("monthly", () => load(start));
  } else whenVisible("monthly", showList);
  // «عملکرد ماهانه» در نوار کناری وقتی همین صفحه باز است ← بازگشت به فهرست
  document.querySelectorAll('a[href="/#monthly"]').forEach(a => a.addEventListener("click", e => {
    if (location.pathname === "/" && current !== null) { e.preventDefault(); showTab("monthly"); showList(); }
  }));
})();

/* ===================== ۲. برآورد سود (مدل فصلی EPS و P/E) ===================== */
(function estimate() {
  const root = document.getElementById("eps-model");
  const STORE_KEY = "eps-quarterly-model-v1";
  const Q_NAMES = ["فصل اول", "فصل دوم", "فصل سوم", "فصل چهارم"];
  const STAGES = ["ابتدای سال", "۳ ماهه", "۶ ماهه", "۹ ماهه", "۱۲ ماهه"];
  const ACT_LINES = [
    ["rev", "درآمدهای عملیاتی", "مثبت"],
    ["cogs", "بهای تمام‌شده درآمدهای عملیاتی", "مثبت وارد شود"],
    ["sga", "هزینه‌های فروش، اداری و عمومی", "مثبت وارد شود"],
    ["otherOp", "سایر درآمدها و هزینه‌های عملیاتی", "خالص، با علامت"],
    ["fin", "هزینه‌های مالی", "مثبت وارد شود"],
    ["nonOp", "سایر درآمدها و هزینه‌های غیرعملیاتی", "خالص، با علامت"],
    ["tax", "هزینه مالیات بر درآمد", "مثبت وارد شود"],
  ];
  const blankActual = () => ({ rev: "", cogs: "", sga: "", otherOp: "", fin: "", nonOp: "", tax: "" });
  const defaults = () => ({
    company: "شرکت نمونه", ticker: "نماد", fy: "1405",
    price: "6500", targetPE: "7",
    stage: 0, nextId: 4, snaps: [],
    products: [
      { id: 1, name: "محصول الف", unit: "تن", qty: "30000", price: "45", mat: "28" },
      { id: 2, name: "محصول ب", unit: "تن", qty: "20000", price: "62", mat: "41" },
      { id: 3, name: "محصول ج", unit: "تن", qty: "6250", price: "110", mat: "70" },
    ],
    sc: { labor: "162500", overhead: "225000", dep: "80000", inv: "0", sga: "4", otherOp: "12500", debt: "3000000", rate: "23", nonOp: "30000", tax: "25", shares: "2000" },
    actuals: [
      { rev: "3050000", cogs: "2420000", sga: "120000", otherOp: "10000", fin: "170000", nonOp: "25000", tax: "90000" },
      blankActual(), blankActual(), blankActual(),
    ],
  });

  /* مفروضات جدا برای هر فصل: st.qa[i] = {products, sc} (تعداد سهام مشترک در st.sc.shares)
     st.mode: "manual" (ورود دستی مفروضات) | "ml" (پیش‌بینی یادگیری ماشین به‌عنوان مفروضات)
     st.qaSel: فصلی که مفروضاتش ویرایش می‌شود | st.isView: نمای صورت سود و زیان (q | cum | 3 | 6 | 9 | 12) */
  const SC_KEYS = ["labor", "overhead", "dep", "inv", "sga", "otherOp", "debt", "rate", "nonOp", "tax"];
  const clone = o => JSON.parse(JSON.stringify(o));
  const pickSc = sc => Object.fromEntries(SC_KEYS.map(k => [k, sc[k] ?? "0"]));
  function normalize(m) {
    // مدل‌های ذخیره‌شده‌ی نسخه‌ی قبل (یک مجموعه مفروضات برای همه‌ی فصل‌ها) ← همان برای هر فصل
    if (!Array.isArray(m.qa) || m.qa.length !== 4) {
      m.qa = [0, 1, 2, 3].map(() => ({ products: clone(m.products), sc: pickSc(m.sc) }));
    }
    if (!m.mode) m.mode = m.useML ? "ml" : "manual";
    if (!m.isView) m.isView = "q";
    if (m.qaSel === undefined) m.qaSel = m.stage;
    return m;
  }

  // هر نماد مدل جدای خودش را دارد؛ بدون نماد = مدل نمونه (کلید قدیمی)
  let sym = null;
  const keyFor = s => s ? STORE_KEY + ":" + s : STORE_KEY;
  function loadModel(s) {
    const m = defaults();
    const saved = load(keyFor(s), null);
    if (saved && saved.products && saved.sc && saved.actuals) return { st: normalize(Object.assign(m, saved)), fresh: false };
    return { st: normalize(m), fresh: true };
  }
  let st = loadModel(null).st;
  // رندر بعد از جابه‌جا شدن فوکوس (Tab) انجام می‌شود تا فوکوس حفظ شود
  const commit = () => { save(keyFor(sym), st); setTimeout(render, 0); };

  /* ---------- اتصال به کدال: فصل‌های تحقق‌یافته جای پیش‌بینی را می‌گیرند ---------- */
  let codal = null;          // وضعیت لحظه‌ای: {state: loading|running|ok|error|none, job, data}
  let pollTimer = null;
  // پیشنهاد یادگیری ماشین برای فصل‌های پیش‌بینی (لحظه‌ای؛ اعمال‌شده‌اش در st.mlQ ذخیره می‌شود)
  let mlq = null, mlqFor = null, mlqJob = null, mlqTimer = null, mlqLoading = false;

  async function loadMLQ(s) {
    clearTimeout(mlqTimer);
    let r;
    try { r = await Bourse.api("/api/ml/quarters/" + encodeURIComponent(s)); }
    catch (e) { return; }
    if (s !== sym) return;
    const wasRunning = Bourse.jobActive(mlqJob);
    mlq = r.result; mlqFor = s; mlqJob = r.job;
    // حالت «پیش‌بینی یادگیری ماشین»: آخرین پیشنهاد مدل همان مفروضات فصل‌های گزارش‌نشده است
    if (st.mode === "ml" && mlq && mlq.quarters && mlq.quarters.length) {
      st.mlQ = { fy: mlq.fy, quarters: clone(mlq.quarters) };
      save(keyFor(sym), st);
    }
    if (Bourse.jobActive(mlqJob)) mlqTimer = setTimeout(() => loadMLQ(s), 3000);
    else if (wasRunning) { sync(s, { autoFetch: false }); }       // سابقه رسید ← فصل‌های واقعی هم به‌روز
    render();
  }

  const ML_LINES = [["rev", "درآمدهای عملیاتی", 1], ["cogs", "بهای تمام‌شده", -1], ["sga", "هزینه‌های فروش، اداری و عمومی", -1],
    ["otherOp", "سایر درآمدها و هزینه‌های عملیاتی", 1], ["fin", "هزینه‌های مالی", -1], ["nonOp", "سایر غیرعملیاتی", 1],
    ["tax", "مالیات", -1], ["net", "سود خالص", 1]];
  const COMP_LABEL = { rev: "درآمد (مدل فصلی)", cogs_r: "نسبت بهای تمام‌شده به درآمد", sga_r: "نسبت هزینه‌های فروش و اداری به درآمد",
    otherOp: "سایر درآمدها و هزینه‌های عملیاتی", fin: "هزینه‌های مالی", nonOp: "سایر غیرعملیاتی", tax_r: "نرخ مؤثر مالیات" };

  function mlPanelQ() {
    if (!sym || !codal || codal.state !== "ok") return "";
    const shares = num(st.sc.shares);
    if (!mlq || mlqFor !== sym) {
      return `<div class="panel ml-box"><h2>پیشنهاد یادگیری ماشین</h2>
        ${Bourse.jobActive(mlqJob) ? ML.historyBox(mlqJob, 12, 0, "فصل") : '<div class="sub"><span class="spinner sm"></span>آموزش مدل‌ها روی سابقه‌ی نماد…</div>'}</div>`;
    }
    const r = mlq, qs = r.quarters;
    const applied = st.mode === "ml" && st.mlQ && String(st.mlQ.fy) === String(r.fy);
    const head = qs.map(q => `<th>${Q_NAMES[q.q - 1]} ${faDigits(q.fy)}</th>`).join("");
    const rows = ML_LINES.map(([k, l, sign]) => `<tr class="${k === "net" ? "total" : ""}"><td class="lbl">${l}</td>${
      qs.map(q => `<td>${fmt(sign * q[k])}</td>`).join("")}</tr>`).join("")
      + `<tr class="eps-row"><td class="lbl">سود هر سهم (ریال)</td>${qs.map(q => `<td>${shares > 0 ? fmt(q.net / shares) : "—"}</td>`).join("")}</tr>`;
    const comps = Object.entries(r.components).map(([k, c]) => `<tr>
      <td class="lbl">${COMP_LABEL[k]}${k === "rev" && r.rev_source === "monthly" ? "<small>جایگزین‌شده با فروش ماهانه</small>" : ""}</td>
      <td class="muted">${c.best ? esc(c.best) : "—"}</td><td>${ML.err(c.val)}</td><td>${ML.err(c.test)}</td></tr>`).join("");
    const bt = r.backtest;
    const fyNote = String(r.fy) !== String(st.fy) ? `<div class="warn">این پیشنهاد برای سال مالی ${faDigits(r.fy)} است؛ مدل فعلاً سال ${faDigits(st.fy)} را نشان می‌دهد.</div>` : "";
    return `<div class="panel ml-box">
      <div class="row-between">
        <div><h2>پیشنهاد یادگیری ماشین برای فصل‌های پیش‌بینی <span class="badge outline">مدل</span></h2>
          <div class="sub">آموزش روی ${faNum(r.history.quarters)} فصل سابقه‌ی کدال (${Q_NAMES[r.history.first.q - 1]} ${faDigits(r.history.first.fy)} تا ${Q_NAMES[r.history.last.q - 1]} ${faDigits(r.history.last.fy)})
            ${r.split ? "· " + ML.splitTxt(r.split) : ""} · مبالغ میلیون ریال</div></div>
        ${qs.length ? (applied
          ? `<button type="button" class="btn ghost" data-a="mode:manual">ورود دستی مفروضات</button>`
          : `<button type="button" class="btn" data-a="mode:ml">استفاده به‌عنوان مفروضات مدل</button>`) : ""}
      </div>
      ${fyNote}
      ${applied ? `<div class="ok-note">مفروضات فصل‌های گزارش‌نشده = پیش‌بینی یادگیری ماشین؛ کارت‌ها و صورت سود و زیان با برچسب «پیشنهاد مدل» مشخص‌اند.</div>` : ""}
      <div class="ml-grid">
        <div><div class="sec-title">اقلام پیشنهادی هر فصل</div>
          <div class="tbl-wrap"><table class="tbl"><thead><tr><th>قلم</th>${head}</tr></thead><tbody>${rows}</tbody></table></div>
          <div class="sub">درآمد: ${r.rev_source === "monthly"
            ? `پیش‌بینی فروش ماهانه (زبانه‌ی عملکرد ماهانه) × ضریب کالیبره‌ی «درآمد صورت مالی ÷ فروش ماهانه» از ${faNum(r.calib_points)} فصل گذشته`
            : "مدل‌های فصلی درآمد"}؛ بهای تمام‌شده و هزینه‌ها به‌صورت نسبت به درآمد، مالیات با نرخ مؤثر.</div></div>
        <div><div class="sec-title">دقت مدل هر قلم (عامل RL)</div>
          <div class="tbl-wrap"><table class="tbl ml-tbl"><thead><tr><th>قلم</th><th>مدل با بیشترین وزن</th><th>خطای اعتبارسنجی</th><th>خطای آزمون</th></tr></thead>
          <tbody>${comps}</tbody></table></div>
          ${bt ? `<div class="sub">خطای سود خالص ساخته‌شده از پیش‌بینی اقلام در بخش آزمون: ${ML.err(bt.net_test)} (${faNum(bt.points.length)} فصل)</div>`
               : `<div class="warn">برای آزمون ترکیبی سود خالص، سابقه‌ی فصلی کافی نیست.</div>`}</div>
      </div>
      ${ML.historyBox(mlqJob, 12, r.history.quarters, "فصل")}
      ${ML.methodNote()}
    </div>`;
  }
  const r0 = v => String(Math.round(v || 0));

  // مفروضات اولیه برای مدل تازه = تکرار یک فصل واقعی (نقطه‌ی شروع خنثی؛ کاربر جایگزین می‌کند)
  // اقلام یک فصل (درآمد، بهای تمام‌شده، …) ← مفروضات معادل (یک ردیف فروش + نسبت‌ها) که دقیقاً همان سود را می‌سازد
  function assumpFrom(v, name) {
    const pbt = v.rev - v.cogs - v.sga + v.otherOp - v.fin + v.nonOp;
    return {
      products: [{ id: st.nextId++, name, unit: "فصل", qty: "1", price: r0(v.rev), mat: r0(v.cogs) }],
      sc: {
        labor: "0", overhead: "0", dep: "0", inv: "0",
        sga: v.rev ? (v.sga / v.rev * 100).toFixed(2) : "0",
        otherOp: r0(v.otherOp), rate: "23", debt: r0(v.fin * 4 / 0.23), nonOp: r0(v.nonOp),
        tax: pbt > 0 ? (v.tax / pbt * 100).toFixed(2) : "0",
      },
    };
  }
  function seedFrom(v, label) {
    for (let i = 0; i < 4; i++) st.qa[i] = assumpFrom(v, "فروش فصلی (تکرار " + label + ")");
    st.seededFrom = label;
  }

  async function applyCodal(d, fresh) {
    const sameYear = String(st.fy) === String(d.fy) && st.codal;
    st.ticker = d.symbol;
    if (d.company) st.company = d.company;
    st.fy = String(d.fy);
    for (let i = 0; i < d.stage; i++) {
      const v = d.quarters[i].values;
      st.actuals[i] = Object.fromEntries(Object.entries(v).map(([k, x]) => [k, r0(x)]));
    }
    // مرحله: با کدال جلو می‌رود؛ اگر کاربر دستی جلوتر رفته (همان سال)، دست نمی‌خورد
    st.stage = sameYear ? Math.max(st.stage, d.stage) : d.stage;
    if (d.shares) st.sc.shares = r0(d.shares);
    if (d.price) st.price = r0(d.price);
    st.codal = {
      fy: d.fy, stage: d.stage, years: d.years, eps_reported: d.eps_reported, eps_months: d.eps_months,
      quarters: d.quarters.map(q => q && { period_end: q.period_end, audited: q.audited, net: q.net }),
    };
    if (fresh) {
      if (d.stage > 0) seedFrom(d.quarters[d.stage - 1].values, Q_NAMES[d.stage - 1] + " " + d.fy);
      else {
        // سال تازه شروع شده: فصل چهارم سال قبل
        const prevFy = d.years.find(y => y < d.fy);
        if (prevFy) {
          const p = await Bourse.api(`/api/quarters/${encodeURIComponent(d.symbol)}?fy=${prevFy}`).catch(() => null);
          const q4 = p && p.data && p.data.quarters[3];
          if (q4) seedFrom(q4.values, "فصل چهارم " + prevFy);
        }
      }
    }
    save(keyFor(sym), st);
  }

  async function sync(s, { autoFetch = true, fy = null } = {}) {
    clearTimeout(pollTimer);
    if (s !== sym) return;
    let r;
    try { r = await Bourse.api(`/api/quarters/${encodeURIComponent(s)}${fy ? "?fy=" + fy : ""}`); }
    catch (e) { codal = { state: "error", message: e.message }; render(); return; }
    if (s !== sym) return;
    const job = r.job;
    if (Bourse.jobActive(job)) {
      // داده‌ی دیتابیس (اگر هست) نمایش داده می‌شود و وضعیت دریافت از کدال کنارش
      if (r.data) {
        await applyCodal(r.data, freshModel);
        freshModel = false;
        codal = { state: "ok", data: r.data, job, db: r.db };
        // پیش‌بینی یادگیری ماشین از داده‌ی همین دیتابیس؛ منتظر تمام شدن کار کدال نمی‌ماند (بعد از آن دوباره ساخته می‌شود)
        if (mlqFor !== s && !mlqLoading && !Bourse.jobActive(mlqJob)) {
          mlqLoading = true;
          loadMLQ(s).finally(() => { mlqLoading = false; });
        }
      } else codal = { state: "running", job };
      render();
      pollTimer = setTimeout(() => sync(s, { autoFetch: false, fy }), 2000);
      return;
    }
    if (r.data) {
      await applyCodal(r.data, freshModel);
      freshModel = false;
      codal = { state: "ok", data: r.data, job, db: r.db };
      if (!Bourse.jobActive(mlqJob)) loadMLQ(s);
    } else if (job && job.state === "error") {
      codal = { state: "error", message: job.message };
    } else if (autoFetch) {
      return fetchCodal(s, true);
    } else {
      codal = { state: "error", message: "صورت مالی میان‌دوره‌ای برای این نماد ذخیره نشد." };
    }
    if (codal.state === "ok" && job && job.state === "error") codal.warn = job.message;
    render();
    // اول دیتابیس، بعد کدال: یک بار پرسیده می‌شود آیا دوره‌ای کم است یا صورت مالی جدیدتری ممکن است منتشر شده باشد
    if (codal.state === "ok" && autoFetch && !autoChecked.has(s)) { autoChecked.add(s); fetchCodal(s, true); }
  }

  // auto: بررسی خودکار؛ بدون آن = دکمه‌ی کاربر. اگر دیتابیس کافی باشد سرور به کدال رجوع نمی‌کند (fresh)
  const autoChecked = new Set();
  async function fetchCodal(s, auto = false) {
    try {
      const r = await Bourse.api(`/api/quarters/${encodeURIComponent(s)}/fetch${auto ? "?auto=1" : ""}`, "POST");
      if (s !== sym) return;
      if (r.fresh) {
        if (!auto) Bourse.toast(r.message, "ok");
        return;
      }
      if (!(codal && codal.data)) codal = { state: "running", job: r.job };
      else codal = { ...codal, job: r.job };
      render();
      pollTimer = setTimeout(() => sync(s, { autoFetch: false }), 1500);
    } catch (e) {
      codal = { state: codal && codal.data ? "ok" : "error", data: codal && codal.data, db: codal && codal.db, message: e.message, warn: e.message };
      render();
    }
  }

  let freshModel = false;
  function setSymbol(s) {
    if (s === sym) return;
    clearTimeout(pollTimer);
    sym = s;
    const m = loadModel(s);
    st = m.st;
    freshModel = m.fresh;
    if (s && m.fresh) { st.ticker = s; st.company = ""; }
    codal = s ? { state: "loading" } : null;
    mlq = null; mlqFor = null; mlqJob = null; clearTimeout(mlqTimer);
    render();
    // داده‌ی کدال فقط وقتی زبانه‌ی برآورد سود باز است (یا با اولین باز شدنش) گرفته می‌شود
    if (s) whenVisible("estimate", () => { if (s === sym) sync(s); });
  }
  // نماد مشترک صفحه‌ی خانه (کادر جستجوی بالا) — از بخش عملکرد ماهانه
  document.addEventListener("bourse:symbol", e => setSymbol(e.detail || null));

  function codalPanel() {
    if (!codal) return `<div class="panel codal-panel sample"><div class="row-between"><div>
      <h2>اتصال به کدال</h2><div class="sub">این مدل نمونه است. نماد را در کادر جستجوی بالای صفحه انتخاب کنید تا
      فصل‌های گزارش‌شده‌ی صورت‌های مالی کدال خودکار جای پیش‌بینی را بگیرند.</div></div>
      <span class="badge sample">داده‌ی نمونه</span></div></div>`;
    const s = esc(sym);
    if (codal.state === "loading") return `<div class="panel codal-panel"><div class="sub"><span class="spinner sm"></span>خواندن صورت‌های مالی ${s}…</div></div>`;
    if (codal.state === "running") {
      const j = codal.job || {};
      return `<div class="panel codal-panel"><div class="row-between"><div>
        <h2>${j.state === "captcha" ? "منتظر کد امنیتی کدال" : `<span class="spinner sm"></span>دریافت صورت‌های مالی ${s} از کدال`}</h2>
        <div class="sub">صورت مالی‌ای از ${s} در دیتابیس سیستم نیست؛ صورت سود و زیان گزارش‌های میان‌دوره‌ای سال جاری و سال قبل از کدال خوانده و ذخیره می‌شود.</div></div>
        <div>${Bourse.jobLine(j)}</div></div></div>`;
    }
    if (codal.state === "error") return `<div class="panel codal-panel"><div class="row-between"><div>
      <h2>اتصال به کدال</h2><div class="warn">${faDigits(esc(codal.message || ""))}</div></div>
      <button type="button" class="btn" data-a="codalRefresh">تلاش دوباره</button></div></div>`;

    const d = codal.data, c = st.codal;
    const done = d.quarters.filter(Boolean);
    const list = done.length
      ? done.map(q => `<span class="chip ${q.audited ? "green" : ""}">${Q_NAMES[q.q - 1]} — ${nf0.format(q.months)} ماهه منتهی به ${faDigits(q.period_end)}${q.audited ? " (حسابرسی‌شده)" : ""}</span>`).join(" ")
      : `<span class="muted">هنوز صورت مالی میان‌دوره‌ای سال ${faDigits(d.fy)} منتشر نشده است</span>`;
    // کنترل: جمع سود فصل‌های واقعی ÷ تعداد سهام ≈ EPS گزارش‌شده‌ی کدال برای همان دوره
    const epsCheck = d.eps_months === d.stage * 3 && d.stage > 0 && d.shares
      ? `EPS تجمعی گزارش‌شده‌ی کدال (${nf0.format(d.eps_months)} ماهه): <b>${fmt(d.eps_reported)}</b> ریال · محاسبه‌ی مدل: <b>${fmt(done.slice(0, d.stage).reduce((a, q) => a + q.net, 0) / d.shares)}</b> ریال`
      : "";
    const fySel = d.years.length > 1
      ? `<label class="field">سال مالی<select class="inp" data-k="codalFy">${d.years.map(y =>
          `<option value="${y}" ${y === d.fy ? "selected" : ""}>${faDigits(y)}</option>`).join("")}</select></label>` : "";
    const gap = d.quarters.some((q, i) => !q && d.quarters.slice(i + 1).some(Boolean));
    return `<div class="panel codal-panel ok">
      <div class="row-between">
        <div><h2>فصل‌های تحقق‌یافته از کدال <span class="badge outline">کدال</span></h2>
          <div class="sub">صورت سود و زیان غیرتلفیقی؛ کدال تجمعی گزارش می‌کند و هر فصل = دوره‌ی آن − دوره‌ی قبل.
          تعداد سهام از سرمایه (اسمی ۱,۰۰۰ ریال) و قیمت بازار از TSETMC.</div></div>
        <div class="fields">${fySel}<button type="button" class="btn ghost" data-a="codalRefresh" ${Bourse.jobActive(codal.job) ? "disabled" : ""}
          title="اول دیتابیس سیستم بررسی می‌شود؛ فقط اگر دوره‌ای کم باشد یا صورت مالی جدیدتری ممکن باشد، از کدال گرفته می‌شود">بررسی گزارش‌های جدید</button></div>
      </div>
      ${Bourse.jobActive(codal.job) ? `<div>${Bourse.jobLine(codal.job)}</div>` : ""}
      <div class="codal-list">${list}</div>
      ${codal.db ? `<div>${Bourse.dbNote(codal.db)}</div>` : ""}
      ${epsCheck ? `<div class="sub">${epsCheck}</div>` : ""}
      ${gap ? `<div class="warn">گزارش یکی از دوره‌ها پیدا نشد؛ فصل‌های بعد از آن هم قابل جداسازی نیستند.</div>` : ""}
      ${codal.warn ? `<div class="warn">${faDigits(esc(codal.warn))}</div>` : ""}
      ${st.seededFrom ? `<div class="sub">مفروضات اولیه = تکرار «${faDigits(esc(st.seededFrom))}»؛ برای پیش‌بینی دقیق‌تر محصولات و هزینه‌ها را جایگزین کنید.</div>` : ""}
    </div>`;
  }

  // پیش‌بینی یادگیری ماشین برای فصل i (همان سال مالی مدل) — فقط در حالت «پیش‌بینی یادگیری ماشین»
  function mlQuarter(i) {
    if (st.mode !== "ml" || !st.mlQ || String(st.mlQ.fy) !== String(st.fy)) return null;
    return st.mlQ.quarters.find(q => q.q === i + 1) || null;
  }

  const IS_KEYS = ["rev", "cogs", "gp", "sga", "otherOp", "op", "fin", "nonOp", "pbt", "tax", "ni"];

  // ارقام یک فصل از مفروضات دستی همان فصل
  function fromAssump(a) {
    const sc = a.sc;
    const lines = a.products.map(p => ({ rev: num(p.qty) * num(p.price), mat: num(p.qty) * num(p.mat) }));
    const fRev = lines.reduce((s, l) => s + l.rev, 0);
    const fMat = lines.reduce((s, l) => s + l.mat, 0);
    return {
      lines, fRev, fMat,
      v: {
        rev: fRev, cogs: fMat + num(sc.labor) + num(sc.overhead) + num(sc.dep) - num(sc.inv),
        sga: fRev * num(sc.sga) / 100, otherOp: num(sc.otherOp),
        fin: num(sc.debt) * num(sc.rate) / 100 / 4, nonOp: num(sc.nonOp),
      },
      taxRate: num(sc.tax),
    };
  }

  // محاسبات مدل — برای ثبت برآورد هم استفاده می‌شود
  function compute() {
    const stage = st.stage, shares = num(st.sc.shares);
    const build = (v, taxFn, src) => {
      const gp = v.rev - v.cogs, op = gp - v.sga + v.otherOp, pbt = op - v.fin + v.nonOp, tax = taxFn(pbt), ni = pbt - tax;
      return { ...v, gp, op, pbt, tax, ni, eps: shares > 0 ? ni / shares : NaN, actual: src === "act", ml: src === "ml", src };
    };
    const assump = st.qa.map(fromAssump);
    const quarters = [0, 1, 2, 3].map(i => {
      if (i < stage) {
        const a = st.actuals[i];
        return build({ rev: num(a.rev), cogs: num(a.cogs), sga: num(a.sga), otherOp: num(a.otherOp), fin: num(a.fin), nonOp: num(a.nonOp) },
          () => num(a.tax), "act");
      }
      // فصل گزارش‌نشده: پیش‌بینی یادگیری ماشین (در آن حالت) وگرنه مفروضات دستی همان فصل
      const q = mlQuarter(i);
      if (q) return build(q, () => q.tax, "ml");
      const f = assump[i];
      return Object.assign(build(f.v, pbt => (pbt > 0 ? pbt * f.taxRate / 100 : 0), "manual"), { mlMissing: st.mode === "ml" });
    });
    const sumOf = qs => {
      const o = {};
      IS_KEYS.forEach(k => { o[k] = qs.reduce((s, q) => s + q[k], 0); });
      o.eps = shares > 0 ? o.ni / shares : NaN;
      o.actual = qs.every(q => q.actual);
      o.partial = !o.actual && qs.some(q => q.actual);
      o.ml = qs.some(q => q.ml);
      return o;
    };
    // تجمعی: ۳، ۶، ۹ و ۱۲ ماهه (مثل گزارش‌های کدال)
    const cum = [1, 2, 3, 4].map(n => sumOf(quarters.slice(0, n)));
    const Y = cum[3];
    const realizedNi = quarters.filter(q => q.actual).reduce((s, q) => s + q.ni, 0);
    return { assump, quarters, cum, Y, realizedEps: shares > 0 ? realizedNi / shares : NaN };
  }

  // فصل iام از کدال آمده؟ (همان سال مالی مدل)
  const fromCodal = i => st.codal && String(st.codal.fy) === String(st.fy) && i < st.codal.stage
    ? st.codal.quarters[i] : null;

  function render() {
    if (st.stage < 4 && (st.qaSel < st.stage || st.qaSel > 3)) st.qaSel = st.stage;   // فقط فصل‌های گزارش‌نشده
    const { assump, quarters, cum, Y, realizedEps } = compute();
    const stage = st.stage, remaining = 4 - stage;
    const sel = st.qaSel, qa = st.qa[sel], sc = qa.sc;
    const { lines, fRev, fMat } = assump[sel];
    const srcLabel = q => q.actual ? "واقعی" : q.ml ? "پیشنهاد مدل" : "مفروضات دستی";
    const fyTxt = faDigits(esc(st.fy));
    const price = num(st.price), tpe = num(st.targetPE);
    const val = (eps, prevEps) => {
      const target = eps * tpe;
      return {
        eps: fmt(eps), pe: dec(price / eps), target: fmt(target),
        upside: price > 0 && isFinite(target) ? pct((target / price - 1) * 100) : "—",
        chg: isFinite(prevEps) && prevEps !== 0 ? pct((eps - prevEps) / Math.abs(prevEps) * 100) : "—",
      };
    };
    const lastSnapEps = st.snaps.length ? st.snaps[st.snaps.length - 1].eps : NaN;
    const cur = val(Y.eps, lastSnapEps);
    const target = Y.eps * tpe;

    // مراحل
    const stagesHtml = STAGES.map((l, k) =>
      `<button type="button" data-a="stage:${k}" aria-pressed="${k === stage}">${l}</button>`).join("");

    // کارت فصل‌ها
    const qCards = quarters.map((q, k) => `
      <div class="qcard ${q.actual ? "act" : "fc"}">
        <div class="t">${Q_NAMES[k]}<span class="badge ${q.actual ? "solid" : q.ml ? "ml" : "outline"}">${srcLabel(q)}</span></div>
        <div class="sub">سود هر سهم فصل (ریال)</div>
        <div class="big">${fmt(q.eps)}</div>
        <div class="sub">سود خالص ${fmt(q.ni)}</div>
      </div>`).join("");

    // شاخص‌ها
    const kpis = [
      ["سود هر سهم برآوردی سال " + fyTxt, fmt(Y.eps), "ریال · " + nf0.format(stage) + " فصل واقعی + " + nf0.format(remaining) + " فصل پیش‌بینی"],
      ["سود هر سهم تحقق‌یافته", fmt(realizedEps), "ریال · " + (isFinite(Y.eps) && Y.eps !== 0 ? pct(realizedEps / Y.eps * 100) + " از برآورد سال" : "—")],
      ["P/E آتی در قیمت بازار", dec(price / Y.eps), "قیمت " + fmt(price) + " ریال"],
      ["قیمت هدف", fmt(target), "ریال · P/E هدف " + dec(tpe)],
      ["پتانسیل بازدهی", cur.upside, "نسبت به قیمت بازار"],
    ].map(k => `<div class="kpi"><span class="lbl">${k[0]}</span><span class="val">${k[1]}</span><span class="note">${k[2]}</span></div>`).join("");

    // داده‌های واقعی
    const missing = [];
    for (let i = 0; i < stage; i++) if (!num(st.actuals[i].rev)) missing.push(Q_NAMES[i]);
    const actualsHtml = stage === 0 ? "" : `
      <div class="panel">
        <div><h2>۱. داده‌های واقعی گزارش‌شده</h2>
        <div class="sub">ارقام هر فصل به‌صورت مجزا (مثلاً فصل دوم = ۶ ماهه منهای ۳ ماهه) · هزینه‌ها مثبت وارد شوند · اقلام خالص با علامت</div></div>
        ${missing.length ? `<div class="warn">برای ${missing.join("، ")} هنوز درآمد واقعی وارد نشده است.</div>` : ""}
        <div class="tbl-wrap"><table class="tbl">
          <thead><tr><th>قلم</th>${Q_NAMES.map((n, i) => {
            const cq = fromCodal(i);
            return `<th>${n}${cq ? `<br><span class="src-tag">کدال · ${faDigits(cq.period_end)}</span>` : i < stage ? `<br><span class="src-tag manual">ورود دستی</span>` : ""}</th>`;
          }).join("")}</tr></thead>
          <tbody>${ACT_LINES.map(L => `<tr>
            <td class="lbl">${L[1]}<small>${L[2]}</small></td>
            ${[0, 1, 2, 3].map(i => i < stage
              ? `<td><input class="inp num" inputmode="decimal" aria-label="${L[1]} ${Q_NAMES[i]}" data-k="act:${i}:${L[0]}" value="${esc(st.actuals[i][L[0]])}"></td>`
              : `<td class="muted">پیش‌بینی</td>`).join("")}
          </tr>`).join("")}</tbody>
        </table></div>
      </div>`;

    // ---------- مفروضات فصل‌های گزارش‌نشده: دو حالت ----------
    const unreported = [0, 1, 2, 3].filter(i => i >= stage);
    const mlReady = !!(st.mlQ && String(st.mlQ.fy) === String(st.fy) && st.mlQ.quarters.length);
    const modeSeg = `<div class="seg" role="group" aria-label="منبع مفروضات">
        <button type="button" data-a="mode:ml" aria-pressed="${st.mode === "ml"}">پیش‌بینی یادگیری ماشین</button>
        <button type="button" data-a="mode:manual" aria-pressed="${st.mode === "manual"}">ورود دستی مفروضات</button></div>`;
    let assumpBody;
    if (stage >= 4) {
      assumpBody = `<div class="sub">سال مالی کامل شده و برآورد سال تماماً بر داده‌ی واقعی است؛ مفروضاتی لازم نیست.</div>`;
    } else if (st.mode === "ml") {
      // حالت ۱: پیش‌بینی یادگیری ماشین به‌عنوان مفروضات (فقط نمایش؛ برای تغییر ← «ویرایش دستی همین ارقام»)
      const mlNote = !sym ? "برای پیش‌بینی یادگیری ماشین، نماد را در کادر بالای صفحه انتخاب کنید."
        : !mlReady ? (mlq && mlqFor === sym && String(mlq.fy) !== String(st.fy)
            ? `پیش‌بینی مدل برای سال مالی ${faDigits(mlq.fy)} است و مدل فعلاً سال ${faDigits(st.fy)} را نشان می‌دهد.`
            : "پیش‌بینی مدل هنوز آماده نیست (آموزش روی سابقه‌ی کدال نماد…).")
        : "";
      const missingQ = quarters.filter(q => q.mlMissing).length;
      const head = unreported.map(i => `<th>${Q_NAMES[i]}<br><span class="src-tag ${quarters[i].ml ? "" : "manual"}">${quarters[i].ml ? "پیشنهاد مدل" : "مفروضات دستی"}</span></th>`).join("");
      const body = ML_LINES.map(([k, l, sign]) => `<tr class="${k === "net" ? "total" : ""}"><td class="lbl">${l}</td>${
        unreported.map(i => `<td>${fmt(sign * (k === "net" ? quarters[i].ni : quarters[i][k]))}</td>`).join("")}</tr>`).join("")
        + `<tr class="eps-row"><td class="lbl">سود هر سهم (ریال)</td>${unreported.map(i => `<td>${fmt(quarters[i].eps)}</td>`).join("")}</tr>`;
      assumpBody = `
        ${mlNote ? `<div class="warn">${mlNote}${missingQ ? " تا آن زمان فصل‌ها با مفروضات دستی محاسبه می‌شوند." : ""}</div>` : ""}
        ${mlReady && missingQ ? `<div class="warn">مدل برای ${faNum(missingQ)} فصل پیشنهادی نداد؛ آن فصل‌ها با مفروضات دستی محاسبه شده‌اند.</div>` : ""}
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>قلم (یک فصل)</th>${head}</tr></thead><tbody>${body}</tbody></table></div>
        <div class="row-between">
          <div class="sub">درآمد، بهای تمام‌شده و هزینه‌ها از مدل‌های یادگیری ماشین و عامل یادگیری تقویتی (جزئیات و دقت در پنل «پیشنهاد یادگیری ماشین»).</div>
          ${mlReady ? `<button type="button" class="btn ghost" data-a="mlToManual">ویرایش دستی همین ارقام</button>` : ""}
        </div>`;
    } else {
      // حالت ۲: ورود دستی — هر فصل گزارش‌نشده مفروضات جدای خودش را دارد
      const qTabs = unreported.map(i => `<button type="button" data-a="qsel:${i}" aria-pressed="${i === sel}">${Q_NAMES[i]}
        <small>${fmt(quarters[i].eps)} ریال</small></button>`).join("");
      const prodRows = qa.products.map((p, k) => {
        const l = lines[k];
        const f = (field, cls, label) => `<input class="inp ${cls}" aria-label="${label}" data-k="prod:${p.id}:${field}" value="${esc(p[field])}"${cls ? ' inputmode="decimal"' : ""}>`;
        return `<tr>
          <td>${f("name", "", "نام محصول")}</td>
          <td style="width:80px">${f("unit", "", "واحد")}</td>
          <td>${f("qty", "num", "مقدار فروش فصلی")}</td>
          <td>${f("price", "num", "نرخ فروش")}</td>
          <td>${f("mat", "num", "بهای مواد هر واحد")}</td>
          <td><b>${fmt(l.rev)}</b></td>
          <td class="muted">${pct(l.rev ? (l.rev - l.mat) / l.rev * 100 : NaN)}</td>
          <td><button type="button" class="icon-btn" aria-label="حذف محصول" data-a="delProd:${p.id}">${ICON_TRASH}</button></td>
        </tr>`;
      }).join("");
      const item = (key, label, unit) => `<div class="sc-row"><div><div class="l">${label}</div><div class="u">${unit}</div></div>
        <input class="inp num" inputmode="decimal" aria-label="${label} ${Q_NAMES[sel]}" data-k="sc:${key}" value="${esc(sc[key])}"></div>`;
      const groups = [
        ["بهای تمام‌شده (به‌جز مواد)", [
          item("labor", "دستمزد مستقیم فصل", "میلیون ریال"),
          item("overhead", "سربار تولید فصل (بدون استهلاک)", "میلیون ریال"),
          item("dep", "استهلاک فصل", "میلیون ریال"),
          item("inv", "افزایش (کاهش) موجودی ساخته‌شده", "میلیون ریال · افزایش، بهای تمام‌شده را کم می‌کند")]],
        ["هزینه‌ها و درآمدهای عملیاتی", [
          item("sga", "هزینه‌های فروش، اداری و عمومی", "درصد از درآمد"),
          item("otherOp", "سایر درآمدها و هزینه‌های عملیاتی فصل", "میلیون ریال، خالص")]],
        ["تأمین مالی و غیرعملیاتی", [
          item("debt", "میانگین مانده تسهیلات", "میلیون ریال"),
          item("rate", "نرخ سالانه سود تسهیلات", "درصد · هزینه فصل = یک‌چهارم"),
          item("nonOp", "سایر درآمدها و هزینه‌های غیرعملیاتی فصل", "میلیون ریال، خالص")]],
        ["مالیات", [
          item("tax", "نرخ مؤثر مالیات", "درصد از سود قبل از مالیات")]],
      ].map(g => `<div><div class="group-title">${g[0]}</div>${g[1].join("")}</div>`).join("");
      const later = unreported.filter(i => i > sel);
      assumpBody = `
        <div class="row-between">
          <div class="seg q-tabs" role="group" aria-label="فصل">${qTabs}</div>
          <div class="fields">
            ${later.length ? `<button type="button" class="btn ghost" data-a="copyNext">کپی مفروضات ${Q_NAMES[sel]} به ${later.length === 1 ? Q_NAMES[later[0]] : "فصل‌های بعد"}</button>` : ""}
            <button type="button" class="btn" data-a="addProd">+ افزودن محصول</button>
          </div>
        </div>
        <div class="sec-title">فروش و مواد مستقیم ${Q_NAMES[sel]} (ارقام یک فصل)</div>
        <div class="tbl-wrap"><table class="tbl">
          <thead><tr><th>محصول</th><th>واحد</th><th>مقدار فروش فصلی</th><th>نرخ فروش (م.ریال)</th><th>بهای مواد هر واحد (م.ریال)</th><th>درآمد فصلی</th><th>حاشیه مواد ٪</th><th></th></tr></thead>
          <tbody>${prodRows || `<tr><td colspan="8" class="muted">محصولی تعریف نشده است.</td></tr>`}</tbody>
          <tfoot><tr><td>جمع ${Q_NAMES[sel]}</td><td></td><td></td><td></td><td></td><td>${fmt(fRev)}</td><td class="muted">${pct(fRev ? (fRev - fMat) / fRev * 100 : NaN)}</td><td></td></tr></tfoot>
        </table></div>
        <div class="groups">${groups}</div>`;
    }
    const assumpNote = stage >= 4 ? ""
      : st.mode === "ml" ? `فصل‌های گزارش‌نشده (${unreported.map(i => Q_NAMES[i]).join("، ")}) با پیش‌بینی یادگیری ماشین`
      : `هر فصل گزارش‌نشده (${unreported.map(i => Q_NAMES[i]).join("، ")}) مفروضات جدای خودش را دارد · ارقام برای یک فصل · میلیون ریال`;

    // ---------- صورت سود و زیان: فصلی، تجمعی (۳/۶/۹/۱۲ ماهه) یا یک دوره‌ی تجمعی با فصل‌هایش ----------
    const CUM_LBL = { 3: "۳ ماهه", 6: "۶ ماهه", 9: "۹ ماهه", 12: "۱۲ ماهه" };
    const view = String(st.isView || "q");
    const tag = c => c.actual ? "واقعی" : c.partial ? "واقعی + پیش‌بینی" : c.ml ? "پیشنهاد مدل" : "مفروضات دستی";
    let cols;
    if (view === "cum") {
      cols = cum.map((c, k) => ({ label: CUM_LBL[(k + 1) * 3], sub: tag(c), d: c, act: c.actual }));
    } else if (["3", "6", "9", "12"].includes(view)) {
      const n = +view / 3;
      cols = quarters.slice(0, n).map((q, k) => ({ label: Q_NAMES[k], sub: srcLabel(q), d: q, act: q.actual }));
      if (n > 1) cols.push({ label: "جمع " + CUM_LBL[+view], sub: tag(cum[n - 1]), d: cum[n - 1], total: true });
    } else {
      cols = quarters.map((q, k) => ({ label: Q_NAMES[k], sub: srcLabel(q), d: q, act: q.actual }));
      cols.push({ label: `سال ${fyTxt} (برآورد)`, sub: tag(Y), d: Y, total: true });
    }
    const base = cols[cols.length - 1].d;                 // ستون «٪ از درآمد» = آخرین ستون (کل دوره)
    const mk = (kind, label, key, sign) => {
      const cells = cols.map(c => {
        const v = fmt(sign * c.d[key]);
        return `<td class="${c.act && kind !== "eps" ? "act" : ""}">${c.total ? `<b>${v}</b>` : v}</td>`;
      }).join("");
      const p = kind === "eps" ? "" : pct(base.rev ? sign * base[key] / base.rev * 100 : NaN);
      return `<tr class="${kind === "line" ? "" : kind === "eps" ? "eps-row" : kind}"><td class="lbl">${label}</td>${cells}<td class="muted">${p}</td></tr>`;
    };
    const isRows = [
      mk("line", "درآمدهای عملیاتی", "rev", 1),
      mk("line", "بهای تمام‌شده درآمدهای عملیاتی", "cogs", -1),
      mk("total", "سود (زیان) ناخالص", "gp", 1),
      mk("line", "هزینه‌های فروش، اداری و عمومی", "sga", -1),
      mk("line", "سایر درآمدها و هزینه‌های عملیاتی", "otherOp", 1),
      mk("total", "سود (زیان) عملیاتی", "op", 1),
      mk("line", "هزینه‌های مالی", "fin", -1),
      mk("line", "سایر درآمدها و هزینه‌های غیرعملیاتی", "nonOp", 1),
      mk("total", "سود (زیان) قبل از مالیات", "pbt", 1),
      mk("line", "هزینه مالیات بر درآمد", "tax", -1),
      mk("grand", "سود (زیان) خالص", "ni", 1),
      mk("eps", "سود پایه هر سهم (ریال)", "eps", 1),
    ].join("");
    const isHead = cols.map(c => `<th>${c.label}<br><span style="font-weight:400">${c.sub}</span></th>`).join("");
    const viewSeg = [["q", "فصلی"], ["cum", "تجمعی"], ["3", "۳ ماهه"], ["6", "۶ ماهه"], ["9", "۹ ماهه"], ["12", "۱۲ ماهه"]]
      .map(([v, l]) => `<button type="button" data-a="isv:${v}" aria-pressed="${view === v}">${l}</button>`).join("");
    const isTitle = view === "q" ? `صورت سود و زیان سال ${fyTxt} به تفکیک فصل`
      : view === "cum" ? `صورت سود و زیان تجمعی سال ${fyTxt} (۳، ۶، ۹ و ۱۲ ماهه)`
      : `صورت سود و زیان ${CUM_LBL[+view]} سال ${fyTxt}`;

    // بازنگری‌ها
    const snapRows = st.snaps.map((s, k) => {
      const v = val(s.eps, k > 0 ? st.snaps[k - 1].eps : NaN);
      return `<tr><td><b>${esc(s.label)}</b></td><td class="muted">${esc(s.date)}</td><td>${v.eps}</td><td>${v.chg}</td><td>${v.pe}</td><td>${v.target}</td><td>${v.upside}</td>
        <td><button type="button" class="icon-btn" aria-label="حذف این برآورد" data-a="delSnap:${s.id}">${ICON_X}</button></td></tr>`;
    }).join("");

    rerender(root, `
      <div class="pane-head" style="margin-bottom:0">
        <div>
          <div class="eyebrow">مدل غلتان فصلی · ارزش‌گذاری به روش P/E آتی</div>
          <h1>پیش‌بینی فصلی سود و زیان و سود هر سهم</h1>
          <div class="sub">فصل‌های گزارش‌شده با داده‌ی واقعی، فصل‌های گزارش‌نشده با پیش‌بینی یادگیری ماشین یا مفروضات دستی هر فصل · مبالغ به میلیون ریال</div>
        </div>
        <div class="fields">
          <label class="field">نام شرکت<input class="inp" data-k="company" value="${esc(st.company)}" style="width:190px"></label>
          <label class="field">نماد<input class="inp" data-k="ticker" value="${esc(st.ticker)}" style="width:110px;font-weight:700"></label>
          <label class="field">سال مالی<input class="inp" data-k="fy" inputmode="numeric" value="${esc(st.fy)}" style="width:90px"></label>
          <label class="field">تعداد سهام (میلیون)<input class="inp num" inputmode="decimal" data-k="shares" value="${esc(st.sc.shares)}" style="width:120px"></label>
        </div>
      </div>

      ${codalPanel()}

      ${mlPanelQ()}

      <div class="panel">
        <div class="row-between">
          <div><h2>آخرین گزارش منتشرشده</h2>
          <div class="sub">با انتشار هر گزارش میان‌دوره‌ای، مرحله را جلو ببرید، داده واقعی فصل را وارد و مفروضات را برای فصل بعد به‌روز کنید</div></div>
          <div class="seg" role="group" aria-label="آخرین گزارش">${stagesHtml}</div>
        </div>
        <div class="qcards">${qCards}</div>
      </div>

      <div class="kpis">${kpis}</div>

      ${actualsHtml}

      <div class="panel">
        <div class="row-between">
          <div><h2>مفروضات فصل‌های گزارش‌نشده</h2><div class="sub">${assumpNote}</div></div>
          ${stage < 4 ? modeSeg : ""}
        </div>
        ${assumpBody}
      </div>

      <div class="panel">
        <div class="row-between">
          <div><h2>${isTitle}</h2>
          <div class="sub">${esc(st.company)} (${esc(st.ticker)}) · ستون‌های رنگی واقعی‌اند · تجمعی = جمع فصل‌ها مثل گزارش‌های ۳، ۶، ۹ و ۱۲ ماهه‌ی کدال · میلیون ریال</div></div>
          <div class="seg" role="group" aria-label="نمای صورت سود و زیان">${viewSeg}</div>
        </div>
        <div class="tbl-wrap"><table class="tbl">
          <thead><tr><th>شرح</th>${isHead}<th>٪ از درآمد</th></tr></thead>
          <tbody>${isRows}</tbody>
        </table></div>
      </div>

      <div class="panel">
        <div class="row-between" style="align-items:flex-end">
          <div><h2>ارزش‌گذاری P/E آتی و روند بازنگری برآورد</h2>
          <div class="sub">قیمت هدف = سود هر سهم برآوردی سال × P/E هدف · بعد از هر گزارش، برآورد را ثبت کنید تا روند بازنگری‌ها دیده شود</div></div>
          <div class="fields">
            <label class="field">قیمت بازار (ریال)<input class="inp num" inputmode="decimal" data-k="price" value="${esc(st.price)}" style="width:150px"></label>
            <label class="field">P/E هدف<input class="inp num" inputmode="decimal" data-k="targetPE" value="${esc(st.targetPE)}" style="width:100px"></label>
            <button type="button" class="btn ghost" data-a="saveSnap">ثبت برآورد «${STAGES[stage]}»</button>
          </div>
        </div>
        <div class="tbl-wrap"><table class="tbl">
          <thead><tr><th>مرحله برآورد</th><th>تاریخ ثبت</th><th>سود هر سهم سال (ریال)</th><th>تغییر نسبت به قبلی</th><th>P/E در قیمت بازار</th><th>قیمت هدف (ریال)</th><th>پتانسیل بازدهی</th><th></th></tr></thead>
          <tbody>
            <tr class="current"><td>برآورد جاری (${STAGES[stage]})</td><td class="muted">—</td><td>${cur.eps}</td><td>${cur.chg}</td><td>${cur.pe}</td><td>${cur.target}</td><td>${cur.upside}</td><td></td></tr>
            ${snapRows || `<tr><td colspan="8" class="muted">هنوز برآوردی ثبت نشده است.</td></tr>`}
          </tbody>
        </table></div>
      </div>`);
  }

  root.addEventListener("change", e => {
    const k = e.target.dataset.k;
    if (!k) return;
    const v = e.target.value;
    const [type, a, b] = k.split(":");
    if (type === "codalFy") { if (sym) sync(sym, { autoFetch: false, fy: +v }); return; }
    // محصولات و مفروضات ← فصلی که در زبانه‌ی مفروضات انتخاب شده
    if (type === "prod") { const p = st.qa[st.qaSel].products.find(x => x.id === +a); if (p) p[b] = v; }
    else if (type === "sc") st.qa[st.qaSel].sc[a] = v;
    else if (type === "shares") st.sc.shares = v;
    else if (type === "act") st.actuals[+a][b] = v;
    else st[type] = v;
    commit();
  });

  root.addEventListener("click", e => {
    const btn = e.target.closest("[data-a]");
    if (!btn) return;
    const [act, arg] = btn.dataset.a.split(":");
    if (act === "codalRefresh") { if (sym) fetchCodal(sym); return; }
    const cur = st.qa[st.qaSel];
    if (act === "mode") {
      // ۱. پیش‌بینی یادگیری ماشین به‌عنوان مفروضات | ۲. ورود دستی مفروضات هر فصل
      st.mode = arg;
      if (arg === "ml" && mlq && mlqFor === sym && mlq.quarters.length) st.mlQ = { fy: mlq.fy, quarters: clone(mlq.quarters) };
    }
    else if (act === "mlToManual") {
      // ارقام پیش‌بینی مدل ← مفروضات دستی همان فصل‌ها (برای ویرایش)
      for (let i = st.stage; i < 4; i++) {
        const q = mlQuarter(i);
        if (q) st.qa[i] = assumpFrom(q, "فروش فصلی (پیشنهاد مدل)");
      }
      st.mode = "manual";
    }
    else if (act === "qsel") st.qaSel = +arg;
    else if (act === "copyNext") { for (let i = st.qaSel + 1; i < 4; i++) st.qa[i] = clone(cur); }
    else if (act === "isv") st.isView = arg;
    else if (act === "stage") st.stage = +arg;
    else if (act === "addProd") cur.products.push({ id: st.nextId++, name: "محصول جدید", unit: "تن", qty: "0", price: "0", mat: "0" });
    else if (act === "delProd") cur.products = cur.products.filter(p => p.id !== +arg);
    else if (act === "delSnap") st.snaps = st.snaps.filter(s => s.id !== +arg);
    else if (act === "saveSnap") {
      let d = "";
      try { d = new Date().toLocaleDateString("fa-IR"); } catch (err) {}
      st.snaps.push({ id: st.nextId++, label: STAGES[st.stage] + (st.stage < 4 ? (st.mode === "ml" ? " · پیشنهاد مدل" : " · مفروضات دستی") : ""), date: d, eps: compute().Y.eps });
    }
    commit();
  });

  // دریافت سابقه‌ی ۵ ساله برای آموزش مدل‌ها
  root.addEventListener("click", async e => {
    if (!e.target.closest("[data-ml-history]") || !sym) return;
    try { await ML.startHistory(sym); mlqJob = { state: "running", fetched: 0 }; render(); loadMLQ(sym); }
    catch (err) { Bourse.toast(err.message, "err"); }
  });

  // نماد آغازین مثل بخش عملکرد ماهانه: ?symbol= یا آخرین انتخاب؛ وگرنه مدل نمونه
  let startSym = new URLSearchParams(location.search).get("symbol");
  if (!startSym) { try { startSym = localStorage.getItem("bourse-monthly-symbol"); } catch (e) {} }
  if (startSym) setSymbol(startSym); else render();
})();

/* ===================== ۳. یادداشت ===================== */
(function notes() {
  const root = document.getElementById("pane-notes");
  const KEY = "notes-v1";
  let notes = load(KEY, []);
  let filter = "";

  function render() {
    const q = filter.trim();
    const list = notes.filter(n => !q || [n.title, n.symbol, n.body].some(x => (x || "").includes(q)));
    const cards = list.length
      ? list.map(n => `
        <article class="note-card">
          <div class="t">
            <h3>${esc(n.title || "بدون عنوان")}</h3>
            ${n.symbol ? `<span class="chip">${esc(n.symbol)}</span>` : ""}
            <button type="button" class="icon-btn" aria-label="حذف یادداشت" data-del="${n.id}">${ICON_TRASH}</button>
          </div>
          ${n.body ? `<div class="body">${esc(n.body)}</div>` : ""}
          <div class="meta">${esc(n.date)}</div>
        </article>`).join("")
      : `<div class="empty-state">${notes.length ? "یادداشتی با این جستجو پیدا نشد." : "هنوز یادداشتی ننوشته‌اید. اولین یادداشت را از فرم کنار بنویسید."}</div>`;

    const listEl = root.querySelector(".note-list");
    if (listEl) { listEl.innerHTML = cards; root.querySelector(".count").textContent = nf0.format(notes.length) + " یادداشت"; return; }

    root.innerHTML = `
      <div class="pane-head">
        <div>
          <div class="eyebrow">دفترچه‌ی تحلیل</div>
          <h1>یادداشت‌ها</h1>
          <div class="sub">برداشت‌ها، دلایل خرید و فروش و نکته‌های گزارش‌ها را برای هر نماد ثبت کنید · <span class="count">${nf0.format(notes.length)} یادداشت</span></div>
        </div>
        <label class="field">جستجو در یادداشت‌ها<input class="inp" id="note-filter" placeholder="عنوان، نماد یا متن…" style="width:240px"></label>
      </div>
      <div class="notes-grid">
        <form class="panel note-form" id="note-form">
          <h2>یادداشت تازه</h2>
          <label class="field">عنوان<input class="inp" name="title" required placeholder="مثلاً: نکات گزارش ۶ ماهه"></label>
          <label class="field">نماد (اختیاری)<input class="inp" name="symbol" placeholder="مثلاً: فولاد"></label>
          <label class="field">متن<textarea class="inp" name="body" placeholder="یادداشت خود را بنویسید…"></textarea></label>
          <button type="submit" class="btn">ذخیره‌ی یادداشت</button>
        </form>
        <div class="note-list">${cards}</div>
      </div>`;

    root.querySelector("#note-form").addEventListener("submit", e => {
      e.preventDefault();
      const f = e.target;
      let d = "";
      try { d = new Date().toLocaleString("fa-IR", { dateStyle: "medium", timeStyle: "short" }); } catch (err) {}
      notes.unshift({ id: Date.now(), title: f.title.value.trim(), symbol: f.symbol.value.trim(), body: f.body.value.trim(), date: d });
      save(KEY, notes);
      f.reset();
      render();
    });
    root.querySelector("#note-filter").addEventListener("input", e => { filter = e.target.value; render(); });
  }

  root.addEventListener("click", e => {
    const btn = e.target.closest("[data-del]");
    if (!btn) return;
    if (!confirm("این یادداشت حذف شود؟")) return;
    notes = notes.filter(n => n.id !== +btn.dataset.del);
    save(KEY, notes);
    render();
  });

  render();
})();
