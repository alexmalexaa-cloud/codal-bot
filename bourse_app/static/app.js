const overlay = document.getElementById("overlay");

/* ---------- ابزارهای مشترک همه‌ی صفحه‌ها (زیر نام Bourse تا با home.js تداخل نکند) ---------- */
window.Bourse = (function () {
  const FA_D = "۰۱۲۳۴۵۶۷۸۹", AR_D = "٠١٢٣٤٥٦٧٨٩";
  const ICONS = {
    star: '<svg class="icon" viewBox="0 0 24 24"><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/></svg>',
    bag: '<svg class="icon" viewBox="0 0 24 24"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/></svg>',
    trash: '<svg class="icon" viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>',
  };

  // عدد فارسی با هزارگان «,» و اعشار «/»
  function faNum(n, d = 0) {
    if (n === null || n === undefined || !isFinite(n)) return "—";
    const s = Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
    return s.replace(/[0-9]/g, x => FA_D[x]).replace(".", "/");
  }
  const faDigits = s => String(s ?? "").replace(/[0-9]/g, d => FA_D[d]);
  // ورودی کاربر (ارقام فارسی/عربی، هزارگان) ← عدد
  function parseNum(s) {
    const t = String(s ?? "").replace(/[۰-۹]/g, d => FA_D.indexOf(d)).replace(/[٠-٩]/g, d => AR_D.indexOf(d))
      .replace(/[,٬\s]/g, "").replace(/[٫/]/g, ".");
    const n = parseFloat(t);
    return isFinite(n) ? n : null;
  }
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // تاریخ شمسی امروز به شکل 1405/07/15
  function todayJ() {
    try {
      const p = new Intl.DateTimeFormat("en-US-u-ca-persian-nu-latn", { year: "numeric", month: "2-digit", day: "2-digit" })
        .formatToParts(new Date());
      const g = t => p.find(x => x.type === t).value;
      return `${g("year")}/${g("month")}/${g("day")}`;
    } catch (e) { return ""; }
  }

  // درخواست به سرور؛ خطای سرور با پیام فارسی‌اش پرتاب می‌شود
  async function api(url, method = "GET", data) {
    const res = await fetch(url, {
      method,
      headers: data ? { "Content-Type": "application/json" } : {},
      body: data ? JSON.stringify(data) : undefined,
    });
    const out = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(out.error || "خطا در ارتباط با برنامه");
    // هر بخش وضعیت کارش را می‌پرسد؛ اگر کار منتظر کد امنیتی است، پنجره‌ی کد همان لحظه باز شود
    if (out && out.job && out.job.state === "captcha" && window.Bourse && window.Bourse.checkCaptcha) window.Bourse.checkCaptcha();
    return out;
  }

  let toastTimer = null;
  function toast(msg, kind = "") {
    const el = document.getElementById("toast");
    el.textContent = faDigits(msg);
    el.className = "toast " + kind;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 2800);
  }

  // واچ‌لیست: افزودن/حذف و خبر دادن به صفحه‌ها
  async function setWatch(symbol, on) {
    if (on) await api("/api/watchlist", "POST", { symbol });
    else await api("/api/watchlist/" + encodeURIComponent(symbol), "DELETE");
    toast(on ? `${symbol} به واچ‌لیست اضافه شد` : `${symbol} از واچ‌لیست حذف شد`, "ok");
    document.dispatchEvent(new CustomEvent("bourse:changed"));
  }

  async function addTrade(t) {
    await api("/api/portfolio/trades", "POST", t);
    toast(`${t.side === "sell" ? "فروش" : "خرید"} ${t.symbol} در پرتفوی ${t.portfolio_name ? "«" + t.portfolio_name + "» " : ""}ثبت شد`, "ok");
    document.dispatchEvent(new CustomEvent("bourse:changed"));
  }

  /* کادر انتخاب نماد با پیشنهاد (برای فرم‌های واچ‌لیست و پرتفوی) */
  function picker(inputEl, onPick) {
    const wrap = document.createElement("div");
    wrap.className = "picker";
    inputEl.parentNode.insertBefore(wrap, inputEl);
    wrap.appendChild(inputEl);
    const list = document.createElement("ul");
    list.className = "picker-list";
    list.hidden = true;
    wrap.appendChild(list);
    let t = null, idx = -1, items = [];

    const close = () => { list.hidden = true; idx = -1; };
    const choose = s => { inputEl.value = s.symbol; close(); onPick && onPick(s); };
    const paint = () => [...list.children].forEach((li, i) => li.classList.toggle("is-focused", i === idx));

    inputEl.setAttribute("autocomplete", "off");
    let seq = 0;
    inputEl.addEventListener("input", () => {
      clearTimeout(t);
      const q = inputEl.value.trim();
      const mine = ++seq;                          // پاسخ دیرتر رسیده‌ی تایپ قبلی نادیده گرفته می‌شود
      if (!q) { close(); return; }
      t = setTimeout(async () => {
        const res = await api("/api/search?q=" + encodeURIComponent(q)).catch(() => []);
        if (mine !== seq) return;
        items = res;
        list.innerHTML = items.length
          ? items.map(s => `<li><b>${esc(s.symbol)}</b><span>${esc(s.name)}</span></li>`).join("")
          : '<li class="empty">نمادی پیدا نشد</li>';
        [...list.querySelectorAll("li:not(.empty)")].forEach((li, i) =>
          li.addEventListener("mousedown", e => { e.preventDefault(); choose(items[i]); }));
        idx = -1;
        list.hidden = false;
      }, 200);
    });
    inputEl.addEventListener("keydown", e => {
      if (list.hidden || !items.length) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        idx = (idx + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        paint();
      } else if (e.key === "Enter" && idx >= 0) {
        e.preventDefault();
        choose(items[idx]);
      } else if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    });
    inputEl.addEventListener("blur", () => setTimeout(close, 100));
  }

  /* ---------- قیمت‌های TSETMC ---------- */
  // اگر آخرین دریافت قدیمی‌تر از maxAge ثانیه باشد، قیمت‌ها دوباره گرفته می‌شوند
  async function ensurePrices(maxAge = 300) {
    return api("/api/prices/refresh?max_age=" + maxAge, "POST");
  }

  const signedPct = (n, d = 2) => n === null || n === undefined || !isFinite(n) ? "—"
    : (n > 0 ? "+" : n < 0 ? "-" : "") + faNum(Math.abs(n), d) + "٪";

  // قیمت پایانی + درصد تغییر روز
  function priceCell(p) {
    if (!p || !p.close) return '<span class="muted">—</span>';
    const cls = p.change > 0 ? "pos" : p.change < 0 ? "neg" : "muted";
    return `<span class="px">${faNum(p.close)}</span> <span class="px-chg ${cls}">${signedPct(p.change)}</span>`;
  }

  /* نوار وضعیت قیمت‌ها با دکمه‌ی به‌روزرسانی؛ el = ظرف، m = وضعیت بازار از سرور */
  function priceBar(el, m) {
    const ago = m && m.updated_at ? new Date(m.updated_at) : null;
    const when = ago ? faDigits(ago.toTimeString().slice(0, 5)) : "";
    const idx = m && m.idx ? ` — شاخص کل ${faNum(m.idx)} <span class="${m.idx_change >= 0 ? "pos" : "neg"}" dir="ltr">${signedPct(m.idx_change / (m.idx - m.idx_change) * 100)}</span>` : "";
    el.innerHTML = m && m.updated_at
      ? `<span class="pb-dot ${m.state === "باز" ? "open" : ""}"></span>
         <span>قیمت‌های TSETMC — روز معاملاتی ${faDigits(m.date || "")}${m.state ? " — بازار " + esc(m.state) : ""}${idx}</span>
         <span class="muted">دریافت ${when}</span>`
      : `<span class="pb-dot"></span><span>قیمت‌ها هنوز از TSETMC دریافت نشده است</span>`;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pb-btn";
    btn.innerHTML = '<svg class="icon" viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/></svg>به‌روزرسانی قیمت';
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.classList.add("spin");
      try {
        await ensurePrices(0);
        toast("قیمت‌ها به‌روز شد", "ok");
        document.dispatchEvent(new CustomEvent("bourse:changed"));
      } catch (e) { toast(e.message, "err"); }
      btn.disabled = false;
      btn.classList.remove("spin");
    });
    el.appendChild(btn);
  }

  /* بارگذاری صفحه با قیمت‌های ذخیره‌شده، سپس در پس‌زمینه دریافت قیمت تازه و بارگذاری دوباره */
  function withFreshPrices(load) {
    load();
    ensurePrices(300)
      .then(st => { if (st && st.age !== null && st.age < 10) load(); })
      .catch(e => toast(e.message, "err"));
  }

  // کار پس‌زمینه‌ی سرور هنوز تمام نشده؟ (در جریان، در صف، یا منتظر کد امنیتی کاربر)
  const jobActive = j => !!j && ["running", "queued", "captcha"].includes(j.state);

  /* وضعیت کار دریافت از کدال برای همه‌ی بخش‌ها (رتبه‌بندی‌ها، عملکرد ماهانه، برآورد سود، سابقه‌ی مدل):
     منتظر کد امنیتی ← دکمه‌ی «وارد کردن کد امنیتی» که پنجره‌ی کپچا را باز می‌کند */
  function jobLine(job) {
    if (!job) return "";
    const n = job.fetched ? `<b>${faNum(job.fetched)}</b> گزارش دریافت شد` : "";
    if (job.state === "captcha") {
      return `<span class="job-line cap"><span class="cap-dot"></span>
        <span>دریافت متوقف است: کدال کد امنیتی خواسته${n ? " — " + n : ""}</span>
        <button type="button" class="pill-btn dark" data-captcha-open>وارد کردن کد امنیتی</button></span>`;
    }
    if (job.state === "queued") {        // کار تازه در صف، یا نوبت بعدیِ کار تکه‌تکه (با شمار گزارش‌های تا این‌جا)
      return `<span class="job-line"><span class="spinner sm"></span>${n ? n + " — " : ""}${faDigits(esc(job.message || "در صف دریافت از کدال"))}</span>`;
    }
    if (job.state === "running") {
      return `<span class="job-line"><span class="spinner sm"></span>${n || "دریافت از کدال…"}${job.message ? " — " + faDigits(esc(job.message)) : ""}</span>`;
    }
    return "";
  }

  // منبع داده: دیتابیس سیستم + آخرین رجوع به کدال (db = {checked, note} از سرور)
  function dbNote(db) {
    if (!db) return "";
    let when = "هنوز از کدال گرفته نشده";
    if (db.checked) {
      try {
        when = "آخرین بررسی کدال: " + new Date(db.checked).toLocaleString("fa-IR-u-ca-persian",
          { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" });
      } catch (e) { when = "آخرین بررسی کدال: " + faDigits(db.checked.replace("T", " ").slice(0, 16)); }
    }
    return `<span class="db-note" title="${esc(db.note || "")}"><svg class="icon" viewBox="0 0 24 24"><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></svg>
      از دیتابیس سیستم · ${when}</span>`;
  }

  return { faNum, faDigits, parseNum, esc, todayJ, api, toast, setWatch, addTrade, picker, ICONS,
           ensurePrices, signedPct, priceCell, priceBar, withFreshPrices, jobActive, jobLine, dbNote };
})();

/* ---------- کد امنیتی (کپچا) کدال: هر وقت کدال کد خواست، پنجره‌ی ورود کد روی هر صفحه‌ای باز می‌شود ----------
   کاربر کد تصویر را خودش وارد می‌کند؛ برنامه آن را مستقیم به کدال می‌فرستد و کار متوقف‌شده ادامه پیدا می‌کند. */
(function captchaWatcher() {
  const el = document.createElement("div");
  el.className = "captcha-modal";
  el.hidden = true;
  el.innerHTML = `
    <div class="captcha-box" role="dialog" aria-modal="true" aria-labelledby="cap-title">
      <h2 id="cap-title">کد امنیتی کدال</h2>
      <p>کدال برای ادامه‌ی دریافت <b id="cap-jobs"></b> کد امنیتی خواسته است. دریافت همین‌جا منتظر است و بعد از کد درست
        از همان گزارش ادامه پیدا می‌کند.</p>
      <div class="cap-row">
        <img id="cap-img" alt="کد امنیتی">
        <button type="button" class="pill-btn" id="cap-refresh">تصویر جدید</button>
      </div>
      <input id="cap-code" maxlength="10" autocomplete="off" dir="ltr" aria-label="کد امنیتی" placeholder="کد تصویر">
      <div class="cap-err" id="cap-err" role="alert"></div>
      <div class="cap-acts">
        <button type="button" class="btn ghost" id="cap-later">کوچک کردن</button>
        <button type="button" class="btn" id="cap-ok">تأیید و ادامه</button>
      </div>
      <small>کد مستقیم به کدال فرستاده می‌شود. تا وارد کردن کد، درخواست تازه‌ای برای گزارش‌ها فرستاده نمی‌شود.</small>
    </div>`;
  document.body.appendChild(el);

  // نوار ثابت پایین صفحه: کپچای کوچک‌شده (همیشه دیده می‌شود) یا محدودیت جستجوی کدال با شمارش معکوس
  const bar = document.createElement("div");
  bar.className = "codal-bar";
  bar.hidden = true;
  document.body.appendChild(bar);

  const $ = id => el.querySelector("#" + id);
  const img = $("cap-img"), code = $("cap-code"), err = $("cap-err"), ok = $("cap-ok");
  let open = false, minimized = false, since = null, blink = null, notified = false, last = null, tick = null;
  const title0 = document.title;

  async function loadImage() {
    img.removeAttribute("src");
    try { img.src = (await Bourse.api("/api/captcha/image")).image; }
    catch (e) { err.textContent = e.message + " — «تصویر جدید» را بزنید."; }
  }

  function notifyUser() {
    if (!notified && "Notification" in window) {           // اعلان مرورگر، حتی وقتی زبانه‌ی دیگری باز است
      notified = true;
      const send = () => {
        try {
          const n = new Notification("بورس‌یار — کد امنیتی کدال", { body: "دریافت گزارش‌ها منتظر کد امنیتی است.", tag: "codal-captcha", requireInteraction: true });
          n.onclick = () => { window.focus(); show(last && last.jobs); n.close(); };
        } catch (e) {}
      };
      if (Notification.permission === "granted") send();
      else if (Notification.permission !== "denied") Notification.requestPermission().then(p => p === "granted" && send());
    }
    clearInterval(blink);                                   // عنوان زبانه چشمک می‌زند
    let on = false;
    blink = setInterval(() => { document.title = (on = !on) ? "(!) کد امنیتی کدال" : title0; }, 1000);
  }

  function show(jobs) {
    minimized = false;
    if (!open) {
      open = true;
      el.hidden = false;
      err.textContent = "";
      code.value = "";
      loadImage();
      notifyUser();
    }
    $("cap-jobs").textContent = jobs && jobs.length ? jobs.map(j => j.name).join("، ") : "گزارش‌ها";
    setTimeout(() => code.focus(), 30);
    renderBar();
  }

  function hide(done) {
    open = false;
    el.hidden = true;
    if (done) {
      minimized = false;
      notified = false;
      clearInterval(blink);
      document.title = title0;
    }
    renderBar();
  }

  function renderBar() {
    const r = last || {};
    const th = r.throttle || {};
    if (r.pending && !open) {
      bar.hidden = false;
      bar.className = "codal-bar cap";
      bar.innerHTML = `<span class="cap-dot"></span><span>دریافت از کدال منتظر کد امنیتی است</span>
        <button type="button" class="pill-btn dark" data-captcha-open>وارد کردن کد امنیتی</button>`;
    } else if (th.active) {
      bar.hidden = false;
      bar.className = "codal-bar wait";
      const m = Math.floor(th.seconds / 60), s = th.seconds % 60;
      bar.innerHTML = `<span class="spinner sm"></span><span>${Bourse.esc(th.reason || "جستجوی کدال موقتاً محدود است")} — این محدودیت از طرف کدال
        و برای این IP است و با کد امنیتی رفع نمی‌شود. ادامه‌ی خودکار تا <b>${Bourse.faDigits(m + ":" + String(s).padStart(2, "0"))}</b> دیگر</span>`;
    } else {
      bar.hidden = true;
    }
  }

  async function verify() {
    const v = code.value.trim();
    if (!v) { err.textContent = "کد امنیتی را وارد کنید."; code.focus(); return; }
    ok.disabled = true;
    ok.textContent = "در حال بررسی…";
    err.textContent = "";
    try {
      const r = await Bourse.api("/api/captcha/verify", "POST", { code: v });
      if (r.ok) {
        hide(true);
        Bourse.toast(r.resumed ? "کد تأیید شد؛ دریافت از همان‌جا ادامه پیدا کرد" : "کد تأیید شد", "ok");
        document.dispatchEvent(new CustomEvent("bourse:captcha-solved"));
        setTimeout(check, 300);
      } else {
        err.textContent = r.error;
        loadImage();
        code.value = "";
        code.focus();
      }
    } catch (e) { err.textContent = e.message; }
    ok.disabled = false;
    ok.textContent = "تأیید و ادامه";
  }

  $("cap-refresh").addEventListener("click", loadImage);
  ok.addEventListener("click", verify);
  code.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); verify(); }
    e.stopPropagation();                                    // کلید «/» و Esc صفحه را تحریک نکند
  });
  // «کوچک کردن»: پنجره بسته می‌شود ولی نوار پایین صفحه می‌ماند؛ کپچای تازه دوباره پنجره را باز می‌کند
  $("cap-later").addEventListener("click", () => { minimized = true; hide(false); });

  let busy = false;
  async function check(force) {
    if (busy) return;
    busy = true;
    let r;
    try { r = await Bourse.api("/api/captcha"); } catch (e) { busy = false; return; }
    busy = false;
    last = r;
    if (r.pending) {
      const fresh = String(r.since) !== String(since);      // کپچای تازه ← پنجره حتی بعد از «کوچک کردن» باز می‌شود
      since = r.since;
      if (force || fresh || (!open && !minimized)) show(r.jobs);
      else if (open) $("cap-jobs").textContent = r.jobs.length ? r.jobs.map(j => j.name).join("، ") : "گزارش‌ها";
    } else {
      since = null;
      if (open || minimized) hide(true);
      else if (force) Bourse.toast("کدال فعلاً کد امنیتی نخواسته است", "ok");
    }
    renderBar();
    // شمارش معکوس محدودیت جستجو بدون درخواست اضافه
    clearInterval(tick);
    if (r.throttle && r.throttle.active) {
      tick = setInterval(() => {
        if (!last || !last.throttle || last.throttle.seconds <= 0) { clearInterval(tick); return; }
        last.throttle.seconds -= 1;
        renderBar();
      }, 1000);
    }
  }
  Bourse.checkCaptcha = check;
  setInterval(check, 1500);                                 // هر ۱٫۵ ثانیه (محلی و سبک)
  check();
  // دکمه‌ی «وارد کردن کد امنیتی» در هر بخش و نوار پایین
  document.addEventListener("click", e => {
    if (e.target.closest("[data-captcha-open]")) check(true);
  });
})();

// ---------- جستجوی نماد (پنجره‌ی بازشونده) ----------
const modal = document.getElementById("search-modal");
const input = document.getElementById("search-input");
const results = document.getElementById("search-results");
let timer = null, focusIdx = -1;

// نتیجه‌ی جستجو: در صفحه‌ی خانه ← گزارش همان نماد در زبانه‌ی فعلی (عملکرد ماهانه/برآورد سود)؛ جاهای دیگر ← صفحه‌ی نماد
function symHref(sym) {
  const tab = location.hash.slice(1) || "monthly";
  return location.pathname === "/" && tab !== "notes"
    ? `/?symbol=${encodeURIComponent(sym)}#${tab}`
    : `/symbol/${encodeURIComponent(sym)}`;
}

function openSearch(open) {
  modal.hidden = !open;
  if (open) {
    closeCodal();
    input.value = "";
    results.innerHTML = "";
    showTopGrowth();
    setTimeout(() => input.focus(), 0);
  }
}

/* کادر خالی: برترین نمادها بر اساس رشد سود خالص (آخرین گزارش کدال) */
async function showTopGrowth() {
  const { esc, faNum } = Bourse;
  const r = await Bourse.api("/api/screener?top=6").catch(() => null);
  if (input.value.trim() || modal.hidden) return;    // در این فاصله کاربر تایپ کرده یا پنجره بسته شده
  focusIdx = -1;
  const ML = { 3: "۳ ماهه", 6: "۶ ماهه", 9: "۹ ماهه", 12: "سالانه" };
  const pct = v => v === null || v === undefined ? "—" : (v > 0 ? "+" : v < 0 ? "-" : "") + faNum(Math.abs(v), Math.abs(v) >= 100 ? 0 : 1) + "٪";
  const rows = r && r.rows || [];
  results.innerHTML = `
    <li class="top-head"><span>برترین رشد سود خالص</span><small>بر اساس آخرین گزارش کدال · ${faNum(r ? r.meta.ranked : 0)} شرکت</small></li>
    ${rows.length ? rows.map(x => `
      <li class="sr top-row">
        <a class="sr-main" href="${symHref(x.symbol)}">
          <span class="rank ${x.rank <= 3 ? "top" : ""}">${faNum(x.rank)}</span>
          <span class="sym">${esc(x.symbol)}</span><span class="nm">${esc(x.name)}</span>
        </a>
        <span class="gr-chip ${x.g_cum >= 0 ? "pos" : "neg"}" title="رشد ${ML[x.months]} نسبت به مدت مشابه" dir="ltr">${pct(x.g_cum)}</span>
        <span class="sr-score" title="امتیاز ترکیبی">${faNum(x.score, 0)}</span>
      </li>`).join("")
      : `<li class="empty">هنوز گزارشی بررسی نشده است.</li>`}
    <li class="top-foot"><a href="/screener">${rows.length ? "رتبه‌بندی کامل و روش محاسبه" : "رفتن به رتبه‌بندی و بررسی گزارش‌های کدال"} ←</a></li>`;
}
document.getElementById("search-btn").addEventListener("click", () => openSearch(true));

// ---------- فعال‌کردن آیتم «عملکرد ماهانه» / «برآورد سود» در نوار ----------
window.syncRail = function () {
  const onHome = location.pathname === "/";
  const tab = (location.hash.slice(1) || "monthly");
  document.querySelectorAll("[data-home-tab]").forEach(a =>
    a.classList.toggle("is-active", onHome && a.dataset.homeTab === tab));
};
window.addEventListener("hashchange", window.syncRail);
window.syncRail();

modal.addEventListener("click", e => { if (e.target === modal) openSearch(false); });

function renderResults(items) {
  const { esc, faNum, ICONS } = Bourse;
  results.innerHTML = "";
  focusIdx = -1;
  if (!items.length) {
    results.innerHTML = '<li class="empty">نمادی پیدا نشد</li>';
    return;
  }
  items.forEach(s => {
    const li = document.createElement("li");
    li.className = "sr";
    li.innerHTML = `
      <a class="sr-main" href="${symHref(s.symbol)}">
        <span class="sym">${esc(s.symbol)}</span><span class="nm">${esc(s.name)}</span>
      </a>
      ${s.growth ? `<a class="gr-chip ${s.growth.g_cum >= 0 ? "pos" : "neg"}" href="/screener?q=${encodeURIComponent(s.symbol)}"
          title="رتبه‌ی رشد سود: ${faNum(s.growth.rank)} از ${faNum(s.growth.of)} · امتیاز ${faNum(s.growth.score, 0)}">رتبه ${faNum(s.growth.rank)}</a>` : ""}
      ${s.price && s.price.close ? `<span class="sr-price">${Bourse.priceCell(s.price)}</span>` : ""}
      ${s.qty ? `<span class="sr-held">${faNum(s.qty)} سهم</span>` : ""}
      <button type="button" class="sr-act star ${s.watch ? "on" : ""}" aria-pressed="${s.watch}"
        title="${s.watch ? "حذف از واچ‌لیست" : "افزودن به واچ‌لیست"}">${ICONS.star}</button>
      <button type="button" class="sr-act buy" title="ثبت خرید در پرتفوی">${ICONS.bag}</button>`;

    const star = li.querySelector(".star");
    star.addEventListener("click", async () => {
      const on = !s.watch;
      try {
        await Bourse.setWatch(s.symbol, on);
        s.watch = on;
        star.classList.toggle("on", on);
        star.setAttribute("aria-pressed", String(on));
        star.title = on ? "حذف از واچ‌لیست" : "افزودن به واچ‌لیست";
      } catch (err) { Bourse.toast(err.message, "err"); }
    });
    li.querySelector(".buy").addEventListener("click", () => toggleBuyForm(li, s));
    results.appendChild(li);
  });
}

/* فرم کوتاه خرید زیر نتیجه‌ی جستجو؛ پرتفوی (مشتری) پیش‌فرض = آخرین پرتفوی باز شده */
const LAST_PF_KEY = "bourse-last-portfolio";
async function toggleBuyForm(li, s) {
  const open = li.nextElementSibling?.classList.contains("sr-buy");
  results.querySelectorAll(".sr-buy").forEach(f => f.remove());
  results.querySelectorAll(".buy.on").forEach(b => b.classList.remove("on"));
  if (open) return;
  const pfs = await Bourse.api("/api/portfolios?brief=1").catch(() => []);
  if (!pfs.length) { Bourse.toast("پرتفوی‌ها خوانده نشد", "err"); return; }
  let last = null;
  try { last = parseInt(localStorage.getItem(LAST_PF_KEY), 10); } catch (e) {}
  if (!pfs.some(p => p.id === last)) last = pfs[0].id;
  li.querySelector(".buy").classList.add("on");
  const f = document.createElement("li");
  f.className = "sr-buy";
  f.innerHTML = `
    <form>
      <label class="pf-pick">پرتفوی مشتری<select name="pf">${pfs.map(p =>
        `<option value="${p.id}" ${p.id === last ? "selected" : ""}>${Bourse.esc(p.name)}</option>`).join("")}</select></label>
      <label>تعداد سهم<input name="qty" inputmode="decimal" required></label>
      <label>قیمت هر سهم (ریال)<input name="price" inputmode="decimal"
        ${s.price && s.price.close ? `placeholder="پایانی ${Bourse.faNum(s.price.close)}"` : "required"}></label>
      <label>تاریخ<input name="date" value="${Bourse.faDigits(Bourse.todayJ())}"></label>
      <button type="submit">ثبت خرید ${Bourse.esc(s.symbol)}</button>
    </form>`;
  li.after(f);
  const form = f.querySelector("form");
  form.qty.focus();
  form.addEventListener("keydown", e => { if (e.key === "Escape") { e.stopPropagation(); toggleBuyForm(li, s); input.focus(); } });
  form.addEventListener("submit", async e => {
    e.preventDefault();
    // قیمت خالی ← قیمت پایانی امروز
    const qty = Bourse.parseNum(form.qty.value),
      price = Bourse.parseNum(form.price.value) || (s.price && s.price.close);
    if (!qty || !price) { Bourse.toast("تعداد و قیمت را وارد کنید", "err"); return; }
    const pid = parseInt(form.pf.value, 10);
    const pfName = pfs.find(p => p.id === pid)?.name;
    try {
      await Bourse.addTrade({ portfolio_id: pid, portfolio_name: pfName, symbol: s.symbol, side: "buy", qty, price, date: form.date.value });
      try { localStorage.setItem(LAST_PF_KEY, String(pid)); } catch (e) {}
      s.qty = (s.qty || 0) + qty;
      f.remove();
      li.querySelector(".buy").classList.remove("on");
      let held = li.querySelector(".sr-held");
      if (!held) {
        held = document.createElement("span");
        held.className = "sr-held";
        li.querySelector(".star").before(held);
      }
      held.textContent = Bourse.faNum(s.qty) + " سهم";
    } catch (err) { Bourse.toast(err.message, "err"); }
  });
}

let searchSeq = 0;
input.addEventListener("input", () => {
  clearTimeout(timer);
  const q = input.value.trim();
  const seq = ++searchSeq;                         // پاسخ دیرتر رسیده‌ی جستجوی قبلی، نتیجه‌ی تازه را جایگزین نکند
  if (!q) { showTopGrowth(); return; }
  timer = setTimeout(async () => {
    const items = await Bourse.api("/api/search?q=" + encodeURIComponent(q)).catch(() => []);
    if (seq === searchSeq) renderResults(items);
  }, 150);
});

input.addEventListener("keydown", e => {
  const links = [...results.querySelectorAll("a.sr-main")];
  if (e.key === "Escape") { openSearch(false); return; }
  if (!links.length) return;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    focusIdx = (focusIdx + (e.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
    links.forEach((a, i) => a.classList.toggle("is-focused", i === focusIdx));
  } else if (e.key === "Enter") {
    e.preventDefault();
    (links[focusIdx] || links[0]).click();
  }
});

// کلید / باز کردن جستجو، Esc بستن همه
document.addEventListener("keydown", e => {
  const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName);
  if (e.key === "/" && !typing) { e.preventDefault(); openSearch(true); }
  if (e.key === "Escape") { openSearch(false); closeCodal(); openAI(false); }
});

// ---------- میانبر کدال ----------
const codalBtn = document.getElementById("codal-btn");
const codalMenu = document.getElementById("codal-menu");
function closeCodal() {
  codalMenu.hidden = true;
  codalBtn.setAttribute("aria-expanded", "false");
}
codalBtn.addEventListener("click", e => {
  e.stopPropagation();
  const willOpen = codalMenu.hidden;
  codalMenu.hidden = !willOpen;
  codalBtn.setAttribute("aria-expanded", String(willOpen));
});
codalMenu.addEventListener("click", e => e.stopPropagation());
document.addEventListener("click", closeCodal);

document.getElementById("codal-symbol-form").addEventListener("submit", e => {
  e.preventDefault();
  const sym = document.getElementById("codal-symbol").value.trim();
  if (!sym) return;
  window.open("https://codal.ir/ReportList.aspx?search&Symbol=" + encodeURIComponent(sym), "_blank");
});

// ---------- دستیار AI ----------
const panel = document.getElementById("ai-panel");
const msgs = document.getElementById("ai-messages");
const aiInput = document.getElementById("ai-input");

function openAI(open) {
  panel.classList.toggle("is-open", open);
  panel.setAttribute("aria-hidden", String(!open));
  overlay.hidden = !open;
  if (open) { closeCodal(); aiInput.focus(); }
}
document.getElementById("ai-btn").addEventListener("click", () => openAI(true));
document.getElementById("ai-close").addEventListener("click", () => openAI(false));
overlay.addEventListener("click", () => openAI(false));

function addMsg(text, who) {
  const div = document.createElement("div");
  div.className = "msg " + who;
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

document.getElementById("ai-form").addEventListener("submit", async e => {
  e.preventDefault();
  const text = aiInput.value.trim();
  if (!text) return;
  addMsg(text, "user");
  aiInput.value = "";
  try {
    const res = await fetch("/api/ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    addMsg((await res.json()).reply, "bot");
  } catch {
    addMsg("خطا در ارتباط با دستیار.", "bot");
  }
});
