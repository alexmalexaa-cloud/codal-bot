/* ===================== واچ‌لیست ===================== */
(function () {
  const { faNum, faDigits, esc, api, toast, setWatch, picker, ICONS } = Bourse;
  const box = document.getElementById("watch-box");
  const form = document.getElementById("watch-form");
  const inp = document.getElementById("watch-input");

  // میلیون ریال ← میلیارد تومان
  const bn = v => faNum(v / 10000, 0);
  const signed = n => n === null || n === undefined ? "—" : (n > 0 ? "+" : n < 0 ? "-" : "") + faNum(Math.abs(n), 1) + "٪";

  async function add(symbol) {
    symbol = symbol.trim();
    if (!symbol) return;
    try {
      await setWatch(symbol, true);
      inp.value = "";
    } catch (e) { toast(e.message, "err"); }
  }
  picker(inp, s => add(s.symbol));
  form.addEventListener("submit", e => { e.preventDefault(); add(inp.value); });

  async function render() {
    let rows, res;
    try { res = await api("/api/watchlist"); rows = res.items; }
    catch (e) { box.innerHTML = `<div class="warn">${esc(e.message)}</div>`; return; }
    Bourse.priceBar(document.getElementById("price-bar"), res.market);

    if (!rows.length) {
      box.innerHTML = `<div class="empty-state">
        هنوز نمادی به واچ‌لیست اضافه نکرده‌اید.<br>
        <span class="sub">از کادر بالا، یا با کلید <kbd>/</kbd> و ستاره‌ی کنار نتیجه‌ی جستجو اضافه کنید.</span></div>`;
      return;
    }
    const missing = rows.filter(r => !r.monthly).map(r => r.symbol);
    box.innerHTML = `
      <div class="box-head">
        <div><h2>نمادها</h2><div class="sub">${faNum(rows.length)} نماد</div></div>
        <div class="legend"><span>قیمت: ریال</span><span>فروش: میلیارد تومان</span></div>
      </div>
      <div class="tbl-wrap">
        <table class="tbl">
          <thead><tr>
            <th>نماد</th><th>قیمت پایانی و تغییر روز</th><th>آخرین معامله</th><th>P/E</th>
            <th>آخرین فروش ماهانه</th><th>ماه گزارش</th>
            <th>تغییر فروش نسبت به سال قبل</th><th>در پرتفوی</th><th></th>
          </tr></thead>
          <tbody>${rows.map(r => {
            const m = r.monthly, p = r.price;
            const cls = m && m.yoy !== null ? (m.yoy >= 0 ? "pos" : "neg") : "muted";
            return `<tr>
              <td><a class="sym-link" href="/symbol/${encodeURIComponent(r.symbol)}">${esc(r.symbol)}</a>
                <small class="co">${esc(r.name)}</small></td>
              <td>${Bourse.priceCell(p)}</td>
              <td class="muted">${p && p.last ? faNum(p.last) : "—"}</td>
              <td>${p && p.pe ? faNum(p.pe, 1) : '<span class="muted">—</span>'}</td>
              <td>${m ? bn(m.total) : '<span class="muted">—</span>'}</td>
              <td class="muted">${m ? faDigits(m.period_end) : "—"}</td>
              <td class="${cls}" dir="ltr" style="text-align:right">${m ? signed(m.yoy) : "—"}</td>
              <td>${r.qty ? `<span class="chip green">${faNum(r.qty)} سهم</span>` : '<span class="muted">—</span>'}</td>
              <td class="row-acts">
                <a class="mini-btn" href="/portfolio?symbol=${encodeURIComponent(r.symbol)}" title="ثبت خرید در پرتفوی">${ICONS.bag}<span>خرید</span></a>
                <button type="button" class="icon-btn" data-del="${esc(r.symbol)}" title="حذف از واچ‌لیست">${ICONS.trash}</button>
              </td>
            </tr>`;
          }).join("")}</tbody>
        </table>
      </div>
      ${missing.length ? `<div class="source">فروش ماهانه‌ی ${missing.map(s =>
        `<a href="/?symbol=${encodeURIComponent(s)}#monthly">${esc(s)}</a>`).join("، ")} هنوز در دیتابیس نیست —
        با باز کردن عملکرد ماهانه‌ی نماد، از کدال گرفته و ذخیره می‌شود.</div>` : ""}`;

    box.querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", async () => {
      try { await setWatch(b.dataset.del, false); } catch (e) { toast(e.message, "err"); }
    }));
  }

  document.addEventListener("bourse:changed", render);
  Bourse.withFreshPrices(render);
})();
