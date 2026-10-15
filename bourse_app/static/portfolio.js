/* ===================== پرتفوی‌ها (هر مشتری یک پرتفوی) =====================
   /portfolio?p=all        نمای کلی همه‌ی مشتری‌ها
   /portfolio?p=3          پرتفوی یک مشتری
   /portfolio?symbol=فولاد  فرم خرید در آخرین پرتفوی باز شده
*/
(function () {
  const { faNum, faDigits, parseNum, esc, api, toast, todayJ, addTrade, setWatch, picker, ICONS } = Bourse;
  const $ = id => document.getElementById(id);
  const form = $("pf-form"), sideSeg = $("pf-side"), submit = $("pf-submit"), totalEl = $("pf-total");

  let view = null;                       // "all" یا شناسه‌ی پرتفوی
  let overview = null;                   // پاسخ /api/portfolios
  let data = { positions: [], trades: [] }, watched = new Set(), side = "buy";

  const COLORS = ["#2F6BFF", "#1FAF55", "#F8CF4A", "#16181D", "#E5484D", "#8B5CF6", "#06B6D4", "#A3A8B4"];
  const money = v => faNum(v, 0);
  const paren = v => v < 0 ? "(" + money(-v) + ")" : money(v);
  const tone = v => v > 0 ? "up" : v < 0 ? "down" : "";
  const pl = v => v ? `<span class="${v >= 0 ? "pos" : "neg"}">${paren(v)}</span>` : '<span class="muted">۰</span>';
  const plPct = (v, base) => v === null || v === undefined ? '<span class="muted">—</span>'
    : `${pl(v)}<small class="pct ${v >= 0 ? "pos" : "neg"}">${Bourse.signedPct(base ? v / base * 100 : 0, 1)}</small>`;
  const kpi = (lbl, v, note, cls = "") =>
    `<div class="kpi"><span class="lbl">${lbl}</span><span class="val ${cls}">${v}</span><span class="note">${note}</span></div>`;

  // آخرین پرتفوی باز شده (برای خرید سریع از جستجو و لینک‌های «خرید»)
  const LAST_KEY = "bourse-last-portfolio";
  const getLast = () => { try { return parseInt(localStorage.getItem(LAST_KEY), 10) || null; } catch (e) { return null; } };
  const setLast = id => { try { localStorage.setItem(LAST_KEY, String(id)); } catch (e) {} };

  // ==================== مسیر ====================
  function setView(v, push = true) {
    view = v;
    if (push) history.replaceState(null, "", "?p=" + v);
    if (v !== "all") setLast(v);
    load();
  }

  function currentPf() {
    return overview && overview.portfolios.find(p => p.id === view);
  }

  // ==================== تب‌ها و سربرگ ====================
  function renderTabs() {
    const pfs = overview.portfolios;
    const tab = (v, label, extra = "") =>
      `<button type="button" class="pf-tab ${view === v ? "on" : ""}" data-view="${v}">${label}${extra}</button>`;
    $("pf-tabs").innerHTML =
      tab("all", "همه‌ی مشتری‌ها", ` <span class="cnt">${faNum(pfs.length)}</span>`) +
      pfs.map(p => {
        const u = p.summary.unrealized;
        const dot = u === null ? "" : `<i class="${u >= 0 ? "pos" : "neg"}"></i>`;
        return tab(p.id, esc(p.name), dot);
      }).join("") +
      `<button type="button" class="pf-tab add" id="pf-new">+ مشتری جدید</button>`;
    $("pf-tabs").querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () =>
      setView(b.dataset.view === "all" ? "all" : parseInt(b.dataset.view, 10))));
    $("pf-new").addEventListener("click", () => openDialog());
    $("pf-tabs").querySelector(".pf-tab.on")?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function renderHead() {
    const acts = $("pf-head-acts");
    if (view === "all") {
      $("pf-eyebrow").textContent = "مدیریت پرتفوی مشتریان";
      $("pf-title").textContent = "همه‌ی مشتری‌ها";
      $("pf-sub").textContent = "جمع دارایی‌های تحت مدیریت با قیمت پایانی امروز؛ مبالغ به ریال";
      acts.innerHTML = "";
      return;
    }
    const pf = currentPf();
    $("pf-eyebrow").textContent = "پرتفوی مشتری";
    $("pf-title").textContent = pf.name;
    $("pf-sub").textContent = pf.note || "قیمت‌ها به ریال؛ بهای تمام‌شده به روش میانگین موزون (با کارمزد)";
    acts.innerHTML = `
      <button type="button" class="btn ghost" id="pf-edit">ویرایش نام و یادداشت</button>
      <button type="button" class="btn danger" id="pf-del">حذف پرتفوی</button>`;
    $("pf-edit").addEventListener("click", () => openDialog(pf));
    $("pf-del").addEventListener("click", () => deletePf(pf));
  }

  // ==================== مشتری جدید / ویرایش / حذف ====================
  const dlg = $("pf-dialog"), dlgForm = $("pf-dialog-form");
  let editing = null;

  function openDialog(pf = null) {
    editing = pf;
    $("pf-dialog-title").textContent = pf ? "ویرایش پرتفوی" : "مشتری جدید";
    $("pf-dialog-ok").textContent = pf ? "ذخیره" : "ساخت پرتفوی";
    dlgForm.name.value = pf ? pf.name : "";
    dlgForm.note.value = pf ? (pf.note || "") : "";
    dlg.showModal();
    dlgForm.name.focus();
  }
  $("pf-dialog-cancel").addEventListener("click", () => dlg.close());
  dlg.addEventListener("keydown", e => { if (e.key === "Escape") e.stopPropagation(); });
  dlgForm.addEventListener("submit", async e => {
    e.preventDefault();
    const body = { name: dlgForm.name.value.trim(), note: dlgForm.note.value.trim() };
    if (!body.name) { toast("نام مشتری را وارد کنید", "err"); return; }
    try {
      if (editing) {
        await api("/api/portfolios/" + editing.id, "PUT", body);
        toast("پرتفوی ویرایش شد", "ok");
        dlg.close();
        load();
      } else {
        const r = await api("/api/portfolios", "POST", body);
        toast(`پرتفوی «${body.name}» ساخته شد`, "ok");
        dlg.close();
        setView(r.id);
      }
    } catch (err) { toast(err.message, "err"); }
  });

  async function deletePf(pf) {
    const n = pf.trade_count;
    if (!confirm(`پرتفوی «${pf.name}»${n ? ` همراه ${faNum(n)} معامله` : ""} برای همیشه حذف شود؟`)) return;
    try {
      await api("/api/portfolios/" + pf.id, "DELETE");
      toast(`پرتفوی «${pf.name}» حذف شد`, "ok");
      setView("all");
    } catch (e) { toast(e.message, "err"); }
  }

  // ==================== نمای کلی ====================
  function renderAll() {
    const { totals: T, portfolios: pfs, exposure } = overview;
    const hasPrice = T.value !== null;
    $("all-kpis").innerHTML = [
      kpi("ارزش کل تحت مدیریت", hasPrice ? money(T.value) : "—",
        T.missing_prices ? `ریال — قیمت ${faNum(T.missing_prices)} موجودی پیدا نشد` : "ریال — با قیمت پایانی امروز"),
      kpi("سود و زیان باز", hasPrice ? paren(T.unrealized) : "—",
        hasPrice ? `<span dir="ltr">${Bourse.signedPct(T.priced_cost ? T.unrealized / T.priced_cost * 100 : 0)}</span> نسبت به بهای تمام‌شده` : "بعد از دریافت قیمت", tone(T.unrealized)),
      kpi("تغییر امروز", hasPrice ? paren(T.day_change) : "—", "ریال — همه‌ی مشتری‌ها", tone(T.day_change)),
      kpi("سود و زیان محقق‌شده", paren(T.realized || 0), "ریال — از فروش‌ها، پس از کارمزد", tone(T.realized)),
      kpi("تعداد مشتری‌ها", faNum(T.clients), `${faNum(pfs.filter(p => p.summary.symbols).length)} پرتفوی دارای موجودی`),
    ].join("");

    // جدول مشتری‌ها (بزرگ‌ترین اول)
    const weight = p => p.summary.value ?? p.summary.cost;
    const total = pfs.reduce((s, p) => s + (weight(p) || 0), 0);
    const rows = [...pfs].sort((a, b) => (weight(b) || 0) - (weight(a) || 0));
    $("all-clients").innerHTML = `
      <div class="box-head">
        <div><h2>مشتری‌ها</h2><div class="sub">برای دیدن جزئیات و ثبت معامله روی نام مشتری بزنید</div></div>
        <div class="legend"><span>مبالغ: ریال</span></div>
      </div>
      <div class="tbl-wrap"><table class="tbl clients">
        <thead><tr><th>مشتری</th><th>نمادها</th><th>بهای تمام‌شده</th><th>ارزش روز</th><th>سود و زیان باز</th>
          <th>تغییر امروز</th><th>سود محقق‌شده</th><th>سهم از کل</th><th></th></tr></thead>
        <tbody>${rows.map((p, i) => {
          const s = p.summary, share = total ? (weight(p) || 0) / total * 100 : 0, c = COLORS[i % COLORS.length];
          return `<tr class="click" data-open="${p.id}">
            <td><span class="sym-cell"><i style="background:${c}"></i><b class="client">${esc(p.name)}</b></span>
              <small class="co">${esc(p.note) || `${faNum(p.trade_count)} معامله`}</small></td>
            <td>${s.symbols ? faNum(s.symbols) : '<span class="muted">—</span>'}</td>
            <td>${s.cost ? money(s.cost) : '<span class="muted">۰</span>'}</td>
            <td>${s.value !== null ? `<b>${money(s.value)}</b>` : '<span class="muted">—</span>'}</td>
            <td>${plPct(s.unrealized, s.priced_cost)}</td>
            <td>${s.day_change !== null ? pl(s.day_change) : '<span class="muted">—</span>'}</td>
            <td>${pl(s.realized)}</td>
            <td><span class="share"><span class="share-track"><span style="width:${share}%;background:${c}"></span></span>${faNum(share, 1)}٪</span></td>
            <td><button type="button" class="mini-btn" data-open="${p.id}">مشاهده</button></td>
          </tr>`;
        }).join("")}</tbody>
      </table></div>`;
    $("all-clients").querySelectorAll("tr[data-open]").forEach(tr =>
      tr.addEventListener("click", () => setView(parseInt(tr.dataset.open, 10))));

    // جمع هر نماد در همه‌ی پرتفوی‌ها
    const ex = $("all-exposure");
    if (!exposure.length) {
      ex.innerHTML = `<h2>نمادها در همه‌ی پرتفوی‌ها</h2><div class="empty-state">هنوز در هیچ پرتفویی سهمی نیست.<br>
        <span class="sub">یک مشتری را باز کنید و معامله ثبت کنید، یا با کلید <kbd>/</kbd> نماد را جستجو کنید.</span></div>`;
      return;
    }
    const exTotal = exposure.reduce((s, e) => s + (e.value ?? e.cost), 0);
    ex.innerHTML = `
      <div class="box-head">
        <div><h2>نمادها در همه‌ی پرتفوی‌ها</h2><div class="sub">تمرکز دارایی‌های تحت مدیریت روی هر نماد و مشتری‌های دارنده</div></div>
      </div>
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>نماد</th><th>قیمت پایانی و تغییر روز</th><th>تعداد کل</th><th>بهای تمام‌شده</th><th>ارزش روز</th>
          <th>سود و زیان باز</th><th>سهم از کل</th><th>مشتری‌های دارنده</th></tr></thead>
        <tbody>${exposure.map(e => {
          const share = exTotal ? (e.value ?? e.cost) / exTotal * 100 : 0;
          const un = e.value !== null ? e.value - e.cost : null;
          return `<tr>
            <td><a class="sym-link" href="/symbol/${encodeURIComponent(e.symbol)}">${esc(e.symbol)}</a><small class="co">${esc(e.name)}</small></td>
            <td>${Bourse.priceCell(e.price)}</td>
            <td>${faNum(e.qty)}</td>
            <td>${money(e.cost)}</td>
            <td>${e.value !== null ? `<b>${money(e.value)}</b>` : '<span class="muted">—</span>'}</td>
            <td>${plPct(un, e.cost)}</td>
            <td><span class="share"><span class="share-track"><span style="width:${share}%;background:var(--primary)"></span></span>${faNum(share, 1)}٪</span></td>
            <td class="holders">${e.holders.map(h =>
              `<button type="button" class="holder" data-open="${h.id}" title="${faNum(h.qty)} سهم">${esc(h.name)} <span>${faNum(h.qty)}</span></button>`).join("")}</td>
          </tr>`;
        }).join("")}</tbody>
      </table></div>`;
    ex.querySelectorAll(".holder").forEach(b => b.addEventListener("click", () => setView(parseInt(b.dataset.open, 10))));
  }

  // ==================== یک پرتفوی: فرم ====================
  function setSide(s) {
    side = s;
    sideSeg.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.side === s)));
    submit.textContent = s === "buy" ? "ثبت خرید" : "ثبت فروش";
    submit.classList.toggle("sell", s === "sell");
    updateTotal();
  }
  sideSeg.querySelectorAll("button").forEach(b => b.addEventListener("click", () => setSide(b.dataset.side)));

  // بعد از انتخاب نماد، قیمت پایانی امروز پیشنهاد می‌شود (اگر کادر قیمت خالی بماند، همین ثبت می‌شود)
  let suggested = null;
  const priceVal = () => parseNum(form.price.value) || suggested;
  async function suggestPrice(symbol) {
    form.price.placeholder = "";
    suggested = null;
    if (!symbol) return;
    const r = await api("/api/price/" + encodeURIComponent(symbol)).catch(() => null);
    if (r && r.price && r.price.close) {
      suggested = r.price.close;
      form.price.placeholder = "پایانی " + faNum(suggested);
    }
    updateTotal();
  }

  function updateTotal() {
    const q = parseNum(form.qty.value), p = priceVal(), f = parseNum(form.fee.value) || 0;
    const held = data.positions.find(x => x.symbol === form.symbol.value.trim());
    let html = "";
    if (q && p) {
      const total = side === "buy" ? q * p + f : q * p - f;
      html = `${side === "buy" ? "مبلغ پرداختی" : "مبلغ دریافتی"}: <b>${money(total)}</b> ریال`;
    }
    if (side === "sell" && held) html += `${html ? " — " : ""}موجودی این مشتری: <b>${faNum(held.qty)}</b> سهم`;
    totalEl.innerHTML = html;
  }
  form.addEventListener("input", updateTotal);
  picker(form.symbol, s => { updateTotal(); suggestPrice(s.symbol); form.qty.focus(); });
  form.symbol.addEventListener("change", () => suggestPrice(form.symbol.value.trim()));

  form.addEventListener("submit", async e => {
    e.preventDefault();
    const pf = currentPf();
    if (!pf) return;
    const t = {
      portfolio_id: pf.id, portfolio_name: pf.name,
      symbol: form.symbol.value.trim(), side,
      qty: parseNum(form.qty.value), price: priceVal(),
      fee: parseNum(form.fee.value) || 0, date: form.date.value.trim(), note: form.note.value.trim(),
    };
    if (!t.symbol || !t.qty || !t.price) { toast("نماد، تعداد و قیمت را وارد کنید", "err"); return; }
    try {
      await addTrade(t);
      ["symbol", "qty", "price", "fee", "note"].forEach(n => { form[n].value = ""; });
      suggestPrice("");
    } catch (err) { toast(err.message, "err"); }
  });

  function prefill(symbol, s = "buy") {
    form.symbol.value = symbol;
    suggestPrice(symbol);
    setSide(s);
    form.scrollIntoView({ behavior: "smooth", block: "center" });
    form.qty.focus();
  }

  // ==================== یک پرتفوی: نمایش ====================
  function renderOne() {
    const s = data.summary, open = data.positions.filter(p => p.qty > 0);
    const hasPrice = s.value !== null;
    $("pf-form-sub").textContent = `معامله‌ی جدید برای «${data.portfolio.name}» — تاریخ شمسی`;
    $("pf-kpis").innerHTML = [
      kpi("ارزش روز پرتفوی", hasPrice ? money(s.value) : "—",
        s.missing_prices ? `ریال — قیمت ${faNum(s.missing_prices)} نماد پیدا نشد` : "ریال — با قیمت پایانی امروز"),
      kpi("سود و زیان باز", hasPrice ? paren(s.unrealized) : "—",
        hasPrice ? `<span dir="ltr">${Bourse.signedPct(s.priced_cost ? s.unrealized / s.priced_cost * 100 : 0)}</span> نسبت به بهای تمام‌شده` : "بعد از دریافت قیمت", tone(s.unrealized)),
      kpi("تغییر امروز", hasPrice ? paren(s.day_change) : "—", "ریال — پایانی امروز نسبت به دیروز", tone(s.day_change)),
      kpi("بهای تمام‌شده", money(s.cost), `ریال — ${faNum(open.length)} نماد با کارمزد خرید`),
      kpi("سود و زیان محقق‌شده", paren(s.realized), `ریال — از فروش‌ها؛ ${faNum(data.trades.length)} معامله`, tone(s.realized)),
    ].join("");
    renderPositions();
    renderTrades();
    updateTotal();
  }

  function renderPositions() {
    const box = $("pf-positions");
    const open = data.positions.filter(p => p.qty > 0);
    const closed = data.positions.filter(p => p.qty <= 0);
    if (!data.positions.length) {
      box.innerHTML = `<h2>دارایی‌ها</h2><div class="empty-state">هنوز معامله‌ای برای «${esc(data.portfolio.name)}» ثبت نشده است.<br>
        <span class="sub">از فرم بالا، یا با کلید <kbd>/</kbd> و دکمه‌ی خرید کنار نتیجه‌ی جستجو.</span></div>`;
      return;
    }
    // وزن هر نماد: با ارزش روز اگر قیمت همه موجود است، وگرنه با بهای تمام‌شده
    const byValue = open.length && open.every(p => p.market_value !== null);
    const weight = p => byValue ? p.market_value : p.cost;
    const total = open.reduce((s, p) => s + weight(p), 0);
    const shares = open.map((p, i) => ({ ...p, share: total ? weight(p) / total * 100 : 0, color: COLORS[i % COLORS.length] }));
    const bar = shares.map(p => `<span style="width:${p.share}%;background:${p.color}" title="${esc(p.symbol)}"></span>`).join("");
    const row = (p, isOpen) => `<tr class="${isOpen ? "" : "closed"}">
      <td><span class="sym-cell">${isOpen ? `<i style="background:${p.color}"></i>` : ""}
        <a class="sym-link" href="/symbol/${encodeURIComponent(p.symbol)}">${esc(p.symbol)}</a></span>
        <small class="co">${esc(p.name)}</small></td>
      <td>${isOpen ? faNum(p.qty) : '<span class="muted">فروخته شد</span>'}</td>
      <td>${isOpen ? money(p.avg) : "—"}</td>
      <td>${Bourse.priceCell(p.price)}</td>
      <td>${isOpen ? money(p.cost) : "—"}</td>
      <td>${isOpen && p.market_value !== null ? `<b>${money(p.market_value)}</b>` : '<span class="muted">—</span>'}</td>
      <td>${isOpen ? plPct(p.unrealized, p.cost) : "—"}</td>
      <td>${isOpen ? `<span class="share"><span class="share-track"><span style="width:${p.share}%;background:${p.color}"></span></span>${faNum(p.share, 1)}٪</span>` : "—"}</td>
      <td>${pl(p.realized)}</td>
      <td class="row-acts">
        <button type="button" class="mini-btn" data-buy="${esc(p.symbol)}">خرید</button>
        ${isOpen ? `<button type="button" class="mini-btn sell" data-sell="${esc(p.symbol)}">فروش</button>` : ""}
        <button type="button" class="sr-act star ${watched.has(p.symbol) ? "on" : ""}" data-watch="${esc(p.symbol)}"
          title="${watched.has(p.symbol) ? "حذف از واچ‌لیست" : "افزودن به واچ‌لیست"}">${ICONS.star}</button>
      </td>
    </tr>`;
    box.innerHTML = `
      <div class="box-head">
        <div><h2>دارایی‌ها</h2><div class="sub">ترکیب پرتفوی بر اساس ${byValue ? "ارزش روز" : "بهای تمام‌شده"}</div></div>
        <div class="legend"><span>مبالغ: ریال</span></div>
      </div>
      ${open.length ? `<div class="mix-bar">${bar}</div>` : ""}
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>نماد</th><th>تعداد</th><th>میانگین خرید</th><th>قیمت پایانی و تغییر روز</th><th>بهای تمام‌شده</th>
          <th>ارزش روز</th><th>سود و زیان باز</th><th>سهم از پرتفوی</th><th>سود محقق‌شده</th><th></th></tr></thead>
        <tbody>${shares.map(p => row(p, true)).join("")}${closed.map(p => row(p, false)).join("")}</tbody>
      </table></div>`;

    box.querySelectorAll("[data-buy]").forEach(b => b.addEventListener("click", () => prefill(b.dataset.buy, "buy")));
    box.querySelectorAll("[data-sell]").forEach(b => b.addEventListener("click", () => prefill(b.dataset.sell, "sell")));
    box.querySelectorAll("[data-watch]").forEach(b => b.addEventListener("click", async () => {
      try { await setWatch(b.dataset.watch, !watched.has(b.dataset.watch)); } catch (e) { toast(e.message, "err"); }
    }));
  }

  function renderTrades() {
    const box = $("pf-trades");
    if (!data.trades.length) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `
      <div class="box-head"><div><h2>تاریخچه‌ی معاملات</h2><div class="sub">جدیدترین اول</div></div></div>
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>تاریخ</th><th>نماد</th><th>نوع</th><th>تعداد</th><th>قیمت</th><th>کارمزد</th><th>مبلغ</th><th>یادداشت</th><th></th></tr></thead>
        <tbody>${data.trades.map(t => {
          const amt = t.side === "buy" ? t.qty * t.price + t.fee : t.qty * t.price - t.fee;
          return `<tr>
            <td class="muted">${t.date ? faDigits(t.date) : "—"}</td>
            <td><a class="sym-link" href="/symbol/${encodeURIComponent(t.symbol)}">${esc(t.symbol)}</a></td>
            <td><span class="chip ${t.side === "buy" ? "green" : "red"}">${t.side === "buy" ? "خرید" : "فروش"}</span></td>
            <td>${faNum(t.qty)}</td><td>${money(t.price)}</td><td class="muted">${money(t.fee)}</td>
            <td>${money(amt)}</td><td class="muted note-cell">${esc(t.note) || ""}</td>
            <td><button type="button" class="icon-btn" data-del="${t.id}" title="حذف معامله">${ICONS.trash}</button></td>
          </tr>`;
        }).join("")}</tbody>
      </table></div>`;
    box.querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", async () => {
      if (!confirm("این معامله حذف شود؟")) return;
      try {
        await api("/api/portfolio/trades/" + b.dataset.del, "DELETE");
        toast("معامله حذف شد", "ok");
        load();
      } catch (e) { toast(e.message, "err"); }
    }));
  }

  // ==================== بارگذاری ====================
  async function load() {
    try {
      const [ov, wl] = await Promise.all([api("/api/portfolios"), api("/api/watchlist")]);
      overview = ov;
      watched = new Set(wl.items.map(w => w.symbol));
      // نمای پیش‌فرض: با چند مشتری نمای کلی، با یک پرتفوی همان پرتفوی؛
      // اگر برای خرید آمده (?symbol=) و پرتفوی قبلی معلوم نیست، اولین پرتفوی
      const first = ov.portfolios[0].id;
      if (view === null) view = wantForm || ov.portfolios.length === 1 ? first : "all";
      if (view !== "all" && !currentPf()) view = wantForm ? first : "all";
      if (view !== "all") {
        setLast(view);
        data = await api("/api/portfolio?p=" + view);
      }
    } catch (e) { toast(e.message, "err"); return; }

    Bourse.priceBar($("price-bar"), overview.market);
    renderTabs();
    renderHead();
    $("view-all").hidden = view !== "all";
    $("view-one").hidden = view === "all";
    if (view === "all") renderAll(); else renderOne();
  }

  // ورودی آدرس
  form.date.value = faDigits(todayJ());
  const qs = new URLSearchParams(location.search);
  const p = qs.get("p");
  const wantForm = !!qs.get("symbol");             // «خرید» از واچ‌لیست یا صفحه‌ی نماد
  if (p === "all") view = "all";
  else if (p && parseInt(p, 10)) view = parseInt(p, 10);
  else if (wantForm) view = getLast();
  setSide(qs.get("side") === "sell" ? "sell" : "buy");
  if (qs.get("symbol")) {
    form.symbol.value = qs.get("symbol");
    suggestPrice(form.symbol.value);
    setTimeout(() => form.qty.focus(), 300);
  }

  document.addEventListener("bourse:changed", load);
  Bourse.withFreshPrices(load);
})();
