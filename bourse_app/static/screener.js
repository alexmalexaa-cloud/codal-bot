/* ===================== رتبه‌بندی رشد سود خالص ===================== */
(function () {
  const { faNum, faDigits, esc, api, toast, ICONS } = Bourse;
  const $ = id => document.getElementById(id);
  let data = null, months = 0, sortKey = "score", sortDir = -1, pollTimer = null;
  let watched = new Set();

  const bn = v => v === null || v === undefined ? "—" : (v < 0 ? "(" + faNum(-v / 10000, 0) + ")" : faNum(v / 10000, 0));
  const pctTxt = v => v === null || v === undefined || !isFinite(v) ? "—"
    : (v > 0 ? "+" : v < 0 ? "-" : "") + faNum(Math.abs(v), Math.abs(v) >= 100 ? 0 : 1) + "٪";
  const pctCell = v => `<span class="g ${v > 0 ? "pos" : v < 0 ? "neg" : "muted"}" dir="ltr">${pctTxt(v)}</span>`;
  const MONTH_LBL = { 3: "۳ ماهه", 6: "۶ ماهه", 9: "۹ ماهه", 12: "سالانه" };

  // ---------- بررسی گزارش‌های جدید کدال ----------
  function renderScanBar() {
    const el = $("scan-bar"), m = data.meta, job = data.job;
    const running = Bourse.jobActive(job);
    el.innerHTML = `
      <span class="pb-dot ${running ? "open" : ""}"></span>
      <span><b>${faNum(m.ranked)}</b> شرکت رتبه‌بندی‌شده
        ${m.count > m.ranked ? `<span class="muted">(${faNum(m.count - m.ranked)} بدون رتبه)</span>` : ""}
        ${m.latest ? ` — آخرین گزارش بررسی‌شده: ${faDigits(m.latest.slice(0, 16))}` : ""}</span>
      ${running
        ? `<span class="scan-acts">${Bourse.jobLine(job)}</span>`
        : `${job && job.state === "error" ? `<span class="neg">${faDigits(esc(job.message))}</span>` : ""}
           <span class="scan-acts">
             <select id="scan-budget" aria-label="تعداد گزارش">
               <option value="20">۲۰ گزارش (~۱ دقیقه)</option>
               <option value="40" selected>۴۰ گزارش (~۲ دقیقه)</option>
               <option value="80">۸۰ گزارش (~۴ دقیقه)</option>
             </select>
             <button type="button" class="pb-btn" id="scan-btn">بررسی گزارش‌های جدید کدال</button>
           </span>`}
      <span class="scan-db">${Bourse.dbNote(data.db)}</span>`;
    $("scan-btn")?.addEventListener("click", () => startScan(false));
  }

  // اول دیتابیس، بعد کدال: auto = بررسی خودکار هنگام باز شدن صفحه (اگر خوراک کدال مدتی بررسی نشده، فقط گزارش‌های تازه)
  async function startScan(auto) {
    const budget = auto ? 20 : $("scan-budget").value;
    try {
      const r = await api(`/api/screener/scan?budget=${budget}${auto ? "&auto=1" : ""}`, "POST");
      if (r.fresh) { if (!auto) toast(r.message, "ok"); return; }
      load();
    } catch (e) { toast(e.message, "err"); }
  }
  let autoScanned = false;

  // ---------- جدول ----------
  const COLS = [
    ["rank", "رتبه"], ["symbol", "نماد"], ["period_end", "آخرین گزارش"], ["net", "سود خالص دوره"],
    ["g_cum", "۱. رشد نسبت به مدت مشابه"], ["g_q_yoy", "۲. فصل آخر / فصل مشابه"], ["g_q_qoq", "۲. فصل آخر / فصل قبل"],
    ["realization", "۳. تحقق سود سال قبل"], ["score", "امتیاز"],
  ];

  function rowsToShow() {
    const q = $("f-q").value.trim();
    const showAll = $("f-all").checked;
    let rows = data.rows.filter(r =>
      (showAll || r.rank) && (!months || r.months === months) &&
      (!q || r.symbol.includes(q) || (r.name || "").includes(q)));
    const val = r => r[sortKey];
    rows = [...rows].sort((a, b) => {
      const va = val(a), vb = val(b);
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      return (va > vb ? 1 : va < vb ? -1 : 0) * sortDir;
    });
    return rows;
  }

  function renderTable() {
    const rows = rowsToShow();
    const box = $("scr-table");
    if (!data.rows.length) {
      box.innerHTML = `<div class="empty-state">هنوز گزارشی بررسی نشده است.<br>
        <span class="sub">دکمه‌ی «بررسی گزارش‌های جدید کدال» را بزنید؛ آخرین صورت‌های مالی منتشرشده‌ی شرکت‌ها خوانده و رتبه‌بندی می‌شوند.
        با هر بار اجرا شرکت‌های بیشتری اضافه می‌شوند.</span></div>`;
      return;
    }
    const head = COLS.map(([k, l]) =>
      `<th class="sortable ${sortKey === k ? "on" : ""}" data-sort="${k}">${l}${sortKey === k ? (sortDir < 0 ? " ▾" : " ▴") : ""}</th>`).join("");
    const body = rows.map(r => {
      const pace = r.months / 12 * 100;                     // سهم زمانی
      const realW = Math.max(0, Math.min(r.realization ?? 0, 150)) / 150 * 100;
      const realBar = r.realization === null || r.realization === undefined ? '<span class="muted">—</span>' : `
        <div class="real">
          <span class="real-val ${r.realization >= pace ? "pos" : ""}">${faNum(r.realization, 0)}٪</span>
          <span class="real-track"><span style="width:${realW}%"></span><i style="right:${pace / 150 * 100}%" title="سهم زمانی ${faNum(pace, 0)}٪"></i></span>
        </div>`;
      const score = r.score === null || r.score === undefined ? '<span class="muted">—</span>' : `
        <div class="score"><b>${faNum(r.score, 0)}</b><span class="score-track"><span style="width:${r.score}%"></span></span>
        ${r.params < 3 ? `<small title="پارامترهای موجود">${faNum(r.params)} از ۳</small>` : ""}</div>`;
      const why = !r.rank ? (r.stale ? "گزارش قدیمی" : !r.has_comparatives ? "ستون مقایسه‌ای ندارد" : "رشد قابل محاسبه نیست") : "";
      return `<tr class="${r.rank ? "" : "unranked"}">
        <td>${r.rank ? `<span class="rank ${r.rank <= 3 ? "top" : ""}">${faNum(r.rank)}</span>` : `<small class="muted">${why}</small>`}</td>
        <td><a class="sym-link" href="/symbol/${encodeURIComponent(r.symbol)}">${esc(r.symbol)}</a><small class="co">${esc(r.name)}</small></td>
        <td><span class="chip ${r.audited ? "green" : ""}">${MONTH_LBL[r.months]}</span><small class="co">منتهی به ${faDigits(r.period_end)}</small></td>
        <td><b>${bn(r.net)}</b><small class="co">سال قبل ${bn(r.net_ly)}</small></td>
        <td>${pctCell(r.g_cum)}</td>
        <td>${pctCell(r.g_q_yoy)}${r.q !== null && r.q !== undefined ? `<small class="co">فصل ${bn(r.q)} / ${bn(r.q_ly)}</small>` : '<small class="co">گزارش قبلی لازم است</small>'}</td>
        <td>${pctCell(r.g_q_qoq)}${r.q_prev !== null && r.q_prev !== undefined ? `<small class="co">فصل قبل ${bn(r.q_prev)}</small>` : ""}</td>
        <td>${realBar}</td>
        <td>${score}</td>
        <td class="row-acts">
          <a class="mini-btn" href="/?symbol=${encodeURIComponent(r.symbol)}#estimate" title="برآورد سود این نماد">تحلیل</a>
          <button type="button" class="sr-act star ${watched.has(r.symbol) ? "on" : ""}" data-watch="${esc(r.symbol)}"
            title="${watched.has(r.symbol) ? "حذف از واچ‌لیست" : "افزودن به واچ‌لیست"}">${ICONS.star}</button>
        </td>
      </tr>`;
    }).join("");
    box.innerHTML = `
      <div class="tbl-wrap"><table class="tbl scr">
        <thead><tr>${head}<th></th></tr></thead>
        <tbody>${body || `<tr><td colspan="10" class="muted">نتیجه‌ای با این فیلتر نیست.</td></tr>`}</tbody>
      </table></div>
      <div class="source">${faNum(rows.length)} ردیف — برای مرتب‌سازی روی عنوان ستون بزنید</div>`;
    box.querySelectorAll("[data-sort]").forEach(th => th.addEventListener("click", () => {
      const k = th.dataset.sort;
      if (sortKey === k) sortDir = -sortDir;
      else { sortKey = k; sortDir = k === "symbol" || k === "rank" ? 1 : -1; }
      renderTable();
    }));
    box.querySelectorAll("[data-watch]").forEach(b => b.addEventListener("click", async () => {
      try { await Bourse.setWatch(b.dataset.watch, !watched.has(b.dataset.watch)); } catch (e) { toast(e.message, "err"); }
    }));
  }

  // ---------- فیلترها ----------
  $("f-q").addEventListener("input", () => data && renderTable());
  $("f-all").addEventListener("change", () => data && renderTable());
  $("f-months").querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    months = +b.dataset.m;
    $("f-months").querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    data && renderTable();
  }));

  async function load() {
    clearTimeout(pollTimer);
    try {
      const [d, wl] = await Promise.all([api("/api/screener"), api("/api/watchlist")]);
      data = d;
      watched = new Set(wl.items.map(w => w.symbol));
    } catch (e) { toast(e.message, "err"); return; }
    renderScanBar();
    renderTable();
    if (Bourse.jobActive(data.job)) pollTimer = setTimeout(load, 3000);
    else if (!autoScanned) { autoScanned = true; startScan(true); }
  }

  // جستجو از پنجره‌ی جستجو: /screener?q=فولاد
  const q0 = new URLSearchParams(location.search).get("q");
  if (q0) { $("f-q").value = q0; $("f-all").checked = true; }
  document.addEventListener("bourse:changed", load);
  load();
})();
