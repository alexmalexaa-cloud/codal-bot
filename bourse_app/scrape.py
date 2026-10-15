"""
جمع‌آوری داده از کدال و ذخیره در data/bourse.db

  python scrape.py symbols                    لیست همه‌ی نمادها
  python scrape.py prices                     آخرین قیمت همه‌ی نمادها از TSETMC
  python scrape.py screen --limit 150         رتبه‌بندی رشد سود: صورت‌های مالی کل بازار
  python scrape.py mrank --month 1405-06      رتبه‌بندی تغییر درآمد: گزارش‌های ماهانه‌ی همان ماه (کل بازار)
  python scrape.py history فولاد --years 5     سابقه‌ی ۵ ساله برای آموزش مدل‌های پیش‌بینی
  python scrape.py cache                      وضعیت حافظه‌ی پاسخ‌های کدال (data/cache.db)

همه‌ی پاسخ‌های کدال در data/cache.db ذخیره می‌شوند: صفحه‌ی گزارش برای همیشه، جستجوها با مهلت؛
پس اجرای دوباره درخواست تازه‌ای نمی‌فرستد مگر برای اطلاعیه‌های جدید.
  python scrape.py letters فولاد               اطلاعیه‌های نماد (فقط عنوان و لینک)
  python scrape.py monthly فولاد --limit 24    گزارش‌های فعالیت ماهانه
  python scrape.py financial فولاد --limit 12  صورت سود و زیان (غیرتلفیقی؛ --consolidated برای تلفیقی)
  python scrape.py all فولاد                   ماهانه + صورت‌های مالی
  python scrape.py show فولاد                  خلاصه‌ی داده‌های ذخیره‌شده

گزارش‌هایی که قبلاً خوانده شده‌اند دوباره دانلود نمی‌شوند (مگر با --force).
"""
import argparse
import base64
import os
import sys

import tsetmc
from codal import client, collect, db, financial, mrank, screener, search
from codal.report import UnsupportedReport
from codal.text import key, norm


def log(*a):
    print(*a, flush=True)


def cmd_symbols(con, args):
    rows = search.companies()
    db.save_symbols(con, rows)
    log(f"{len(rows)} نماد ذخیره شد.")


def cmd_prices(con, args):
    st = tsetmc.refresh(con)
    log(f"قیمت {st['count']} نماد از TSETMC ذخیره شد — "
        f"آخرین معامله‌ی بازار: {st['date']} ساعت {st['time']} (بازار {st['state']})")


def ask_captcha():
    """
    کدال کد امنیتی خواسته: تصویر در data/captcha.jpg ذخیره و باز می‌شود، کاربر کد را در خط فرمان وارد می‌کند.
    خروجی True اگر کد درست بود. ورودی خالی = انصراف.
    """
    path = os.path.join(client.DATA_DIR, "captcha.jpg")
    log("\nکدال کد امنیتی (کپچا) خواسته است.")
    for _ in range(5):
        try:
            uri = client.captcha_image()
        except RuntimeError as e:
            log(e)
            return False
        with open(path, "wb") as f:
            f.write(base64.b64decode(uri.split(",", 1)[1]))
        log(f"تصویر کد: {path}")
        try:
            os.startfile(path)          # ویندوز: باز کردن تصویر با برنامه‌ی پیش‌فرض
        except (AttributeError, OSError):
            pass
        code = input("کد تصویر را وارد کنید (Enter خالی = انصراف): ").strip()
        if not code:
            return False
        if client.captcha_verify(code):
            log("کد تأیید شد؛ ادامه…")
            return True
        log("کد درست نبود؛ تصویر جدید…")
    return False


def cmd_cache(con, args):
    """وضعیت حافظه‌ی پاسخ‌های کدال؛ --clear-search جستجوهای ذخیره‌شده را پاک می‌کند (گزارش‌ها می‌مانند)"""
    if args.clear_search:
        log(f"{client.cache_clear('search')} پاسخ جستجو پاک شد.")
    names = {"report": "صفحه‌ی گزارش", "search": "جستجوی اطلاعیه", "companies": "لیست شرکت‌ها"}
    for k, s in client.cache_stats().items():
        log(f"  {names.get(k, k):<16} {s['count']:>6} مورد   {s['stored_bytes'] / 1e6:6.1f} MB "
            f"(اصل {s['raw_bytes'] / 1e6:.1f} MB)")
    log(f"فایل: {client.CACHE_PATH}")


def cmd_history(con, args):
    """سابقه‌ی چندساله (گزارش ماهانه و صورت مالی) برای آموزش مدل‌های پیش‌بینی"""
    for kind in ("monthly", "financial"):
        log(f"{'گزارش‌های ماهانه' if kind == 'monthly' else 'صورت‌های مالی'} {args.symbol} — {args.years} سال:")
        try:
            n = collect.collect(con, args.symbol, kind, lambda fetched, skipped, last: log(f"  ✓ {last}"),
                                years=args.years)
            log(f"{n} گزارش تازه.")
        except UnsupportedReport as e:
            log(f"  – پشتیبانی نمی‌شود: {e}")


def cmd_screen(con, args):
    """بررسی صورت‌های مالی کل بازار برای رتبه‌بندی رشد سود (مثل دکمه‌ی صفحه‌ی رتبه‌بندی، ولی بزرگ‌تر)"""
    def progress(fetched, skipped, last):
        log(f"  {fetched} دریافت، {skipped} رد — {last}")
    st = screener.scan(con, progress, budget=args.limit, feed_pages=max(5, args.limit // 15))
    rows = [r for r in screener.ranking(con) if r["rank"]]
    log(f"{st['fetched']} گزارش دریافت شد. {len(rows)} شرکت رتبه‌بندی شد. ده رتبه‌ی اول:")
    for r in rows[:10]:
        g = r["g_cum"]
        log(f"  {r['rank']:>3}. {r['symbol']:<10} {r['months']:>2} ماهه  رشد {g:+.0f}٪  امتیاز {r['score']:.0f}")


def cmd_mrank(con, args):
    """رتبه‌بندی تغییر درآمد ماهانه‌ی یک ماه: گزارش‌های همان ماه و ماه قبلِ همان نمادها، فقط آنچه در دیتابیس نیست"""
    def progress(fetched, skipped, last):
        log(f"  {fetched} دریافت، {skipped} رد — {last}")
    ym = mrank.parse_month(args.month) if args.month else mrank.default_month()
    if not ym:
        log("ماه را به شکل 1405-06 وارد کنید.")
        return
    st = mrank.scan(con, progress, budget=args.limit, month=mrank.month_key(ym))
    db.mark_checked(con, "mrank", mrank.month_key(ym))
    rows = [r for r in mrank.ranking(con, ym) if r["g_mom"] is not None]
    rows.sort(key=lambda r: -r["g_mom"])
    log(f"{st['fetched']} گزارش دریافت شد ({mrank.month_key(ym)}). ده تغییر بیشتر نسبت به ماه قبل:")
    for r in rows[:10]:
        log(f"  {r['symbol']:<10} {r['period_end']}  {r['g_mom']:+.0f}٪")


def cmd_letters(con, args):
    n = 0
    for x in search.iter_letters(args.symbol, max_pages=args.pages):
        db.save_letter(con, x)
        n += 1
        log(f"  {x['published'][:10]}  {x['letter_code']:<6} {x['title']}")
    con.commit()
    log(f"{n} اطلاعیه ذخیره شد.")


def _collect(con, args, letter_type, kind, fetch, save, accept=None):
    """
    اطلاعیه‌های یک نوع را می‌گردد و گزارش‌های جدید را تا سقف --limit می‌خواند.
    accept: تابعی که اطلاعیه را قبل از دانلود رد یا قبول می‌کند (None یعنی همه)
    """
    done = errors = 0
    for x in search.iter_letters(args.symbol, letter_type, max_pages=args.pages):
        db.save_letter(con, x)
        if accept and not accept(x):
            continue
        if not args.force and db.is_done(con, x["tracing_no"], kind):
            continue
        if done >= args.limit:
            break
        done += 1
        try:
            rep = fetch(x["url"])
            db.forget(con, x["tracing_no"], kind)     # بعد از دریافت موفق (کپچا وسط کار چیزی را پاک نکند)
            save(con, x, rep)
            log(f"  ✓ {x['title']}")
        except UnsupportedReport as e:
            db.save_skip(con, x, kind, e)
            log(f"  – رد شد: {x['title']}  ({e})")
        except client.RateLimited:
            raise
        except Exception as e:   # خطای شبکه و…: ثبت نمی‌شود تا دفعه‌ی بعد دوباره امتحان شود
            errors += 1
            log(f"  ✗ خطا: {x['title']}  ({e})")
            if errors >= 5:
                log("خطاهای پشت سر هم زیاد شد؛ کار متوقف شد.")
                break
    con.commit()
    log(f"{done} گزارش بررسی شد.")


def cmd_monthly(con, args):
    log(f"گزارش‌های فعالیت ماهانه‌ی {args.symbol} (سال مالی قبل کامل + سال جاری تا آخرین گزارش):")
    n = collect.collect_monthly(con, args.symbol, lambda fetched, skipped, last: log(f"  ✓ {last}"),
                                max_reports=args.limit)
    cov = collect.monthly_coverage(con, args.symbol)
    if cov:
        log(f"{n} گزارش تازه. سال قبل {cov['prev_have']} از ۱۲ ماه؛ سال جاری {cov['cur_have']} از {cov['cur_upto']} ماه"
            + (f"؛ جاافتاده: {', '.join('%d/%02d' % m for m in cov['missing'])}" if cov["missing"] else " — کامل."))


def cmd_financial(con, args):
    cons = args.consolidated
    log(f"صورت‌های مالی {args.symbol} ({'تلفیقی' if cons else 'غیرتلفیقی'}):")
    # صورت تلفیقی فقط در اطلاعیه‌هایی است که عنوانشان «تلفیقی» دارد؛
    # صورت شرکت اصلی در همه‌ی اطلاعیه‌ها (تلفیقی یا نه) هست
    _collect(con, args, search.LETTER_FINANCIAL, "financial_cons" if cons else "financial",
             lambda url: financial.fetch(url, cons), db.save_financial,
             accept=(lambda x: "تلفیقی" in key(x["title"])) if cons else None)


def cmd_all(con, args):
    cmd_monthly(con, args)
    cmd_financial(con, args)


def _b(v):
    """میلیون ریال ← میلیارد تومان"""
    return "—" if v is None else f"{v / 10_000:,.0f}"


def cmd_show(con, args):
    s = args.symbol
    log(f"\nفروش ماهانه‌ی {s} (میلیارد تومان، آخرین نسخه‌ی هر ماه):")
    for r in con.execute("SELECT * FROM monthly_latest WHERE symbol=? ORDER BY period_end", (s,)):
        n = con.execute("SELECT COUNT(*) FROM monthly_items WHERE report_id=?", (r["id"],)).fetchone()[0]
        log(f"  {r['period_end']}  سال {r['fiscal_year']} ماه {r['fiscal_month']:>2}  "
            f"فروش {_b(r['total']):>10}   {n} محصول{'  (اصلاحیه)' if r['is_correction'] else ''}")
    log(f"\nصورت سود و زیان {s} (میلیارد تومان، تجمعی از ابتدای سال):")
    for r in con.execute("SELECT * FROM fin_latest WHERE symbol=? ORDER BY period_end, months", (s,)):
        log(f"  {r['period_end']}  {r['months']:>2} ماهه{' تلفیقی' if r['consolidated'] else ''}  "
            f"درآمد {_b(r['rev']):>9}  سود عملیاتی {_b(r['op_profit']):>8}  "
            f"سود خالص {_b(r['net']):>8}  EPS {r['eps'] if r['eps'] is not None else '—'}")
    sk = con.execute("SELECT COUNT(*) FROM skipped WHERE symbol=?", (s,)).fetchone()[0]
    if sk:
        log(f"\n{sk} گزارش رد شده (قالب قدیمی/ناشناخته). جزئیات در جدول skipped.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="جمع‌آوری داده از کدال")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("symbols")
    sub.add_parser("prices")
    sp = sub.add_parser("screen", help="رتبه‌بندی رشد سود: بررسی صورت‌های مالی کل بازار")
    sp.add_argument("--limit", type=int, default=150, help="حداکثر گزارش برای دانلود")
    sp = sub.add_parser("mrank", help="رتبه‌بندی تغییر درآمد: گزارش‌های ماهانه‌ی یک ماه از کل بازار + ماه قبلِ همان نمادها")
    sp.add_argument("--month", help="ماه گزارش، مثلاً 1405-06 (پیش‌فرض: ماه گذشته)")
    sp.add_argument("--limit", type=int, default=80, help="حداکثر گزارش برای دانلود")
    sp = sub.add_parser("cache", help="وضعیت حافظه‌ی پاسخ‌های کدال")
    sp.add_argument("--clear-search", action="store_true", help="پاک کردن جستجوهای ذخیره‌شده")
    sp = sub.add_parser("history", help="سابقه‌ی چندساله برای آموزش مدل‌های پیش‌بینی")
    sp.add_argument("symbol")
    sp.add_argument("--years", type=int, default=5)
    for name in ("letters", "monthly", "financial", "all", "show"):
        sp = sub.add_parser(name)
        sp.add_argument("symbol")
        sp.add_argument("--pages", type=int, default=20, help="حداکثر صفحه‌های جستجو (هر صفحه ۲۰ اطلاعیه)")
        sp.add_argument("--limit", type=int, default=24, help="حداکثر گزارش جدید برای دانلود")
        sp.add_argument("--force", action="store_true", help="خواندن دوباره‌ی گزارش‌های قبلی")
        sp.add_argument("--consolidated", action="store_true", help="صورت‌های مالی تلفیقی")
    p.add_argument("--delay", type=float, default=client.DELAY, help="فاصله‌ی بین درخواست‌ها (ثانیه)")
    args = p.parse_args()
    if hasattr(args, "symbol"):
        args.symbol = norm(args.symbol)
    client.DELAY = args.delay

    con = db.connect()
    # کپچا ← همان لحظه کد از ترمینال گرفته می‌شود و همان گزارش ادامه پیدا می‌کند (بدون شروع دوباره‌ی دستور)
    client.CAPTCHA_WAIT = ask_captcha
    try:
        # اگر کد وارد نشد: دستور متوقف می‌شود؛ اجرای بعدی از همین‌جا ادامه می‌دهد (گزارش‌های گرفته‌شده در حافظه‌اند)
        try:
            globals()["cmd_" + args.cmd](con, args)
        except client.Captcha:
            log("کد وارد نشد؛ دستور متوقف شد. اجرای بعدی از همین‌جا ادامه می‌دهد.")
    except tsetmc.PriceError as e:
        log(f"\n{e}")
    except client.RateLimited as e:
        log(f"\n{e}\nداده‌های ذخیره‌شده تا این لحظه محفوظ است؛ اجرای بعدی از همین‌جا ادامه می‌دهد.")
    except KeyboardInterrupt:
        log("\nمتوقف شد. داده‌های ذخیره‌شده تا این لحظه محفوظ است.")
    finally:
        con.close()
        client.cache_checkpoint()          # فایل -wal حافظه‌ی پاسخ‌ها در cache.db ادغام شود


if __name__ == "__main__":
    main()
