# طلاسنج — بات تلگرامی قیمت لحظه‌ای طلای آنلاین

هر چند دقیقه یک‌بار قیمت خرید و فروش هر گرم طلای ۱۸ عیار را از پلتفرم‌های آنلاین طلا
(میلی‌گلد، گلدیکا، طلاین، ملّی‌گلد، طلاسی، هاشین‌گلد، دیجی‌کالا، وال‌گلد، تکنوگلد، اسنپ سرمایه، همراه‌گلد)
می‌گیرد و یک پیام مقایسه‌ای در کانال تلگرام منتشر می‌کند. نمونه پیام:

```
🟡 قیمت لحظه‌ای طلای آنلاین
🗓 سه‌شنبه ۵ آبان ۱۴۰۵ — ساعت ۱۴:۳۰
💰 هر گرم طلای ۱۸ عیار — تومان

۱. پلتفرم ب
   🛒 خرید: ۷٬۲۵۰٬۰۰۰
   💵 فروش: ۷٬۱۵۰٬۰۰۰
   ↔️ اختلاف: ۱.۳۸٪
۲. پلتفرم الف
   🛒 خرید: ۷٬۳۰۰٬۰۰۰ 🔺۴.۲۹٪
   ...
✅ ارزان‌ترین خرید: پلتفرم ب (۷٬۲۵۰٬۰۰۰)
✅ بهترین فروش: پلتفرم الف (۷٬۲۰۰٬۰۰۰)
⚠️ در دسترس نبود: پلتفرم ج
```

## ساختار

| فایل | کار |
|---|---|
| `platforms.json` | لیست پلتفرم‌ها و روش استخراج قیمت هر کدام (بدون نیاز به تغییر کد) |
| `goldbot/scrapers.py` | سه روش استخراج: `json` (API مستقیم)، `html` (regex)، `browser` (رندر با Playwright) |
| `goldbot/discover.py` | ابزار پیدا کردن API قیمت هر سایت |
| `goldbot/formatter.py` | ساخت متن پیام (تاریخ شمسی، مرتب‌سازی، درصد تغییر، ارزان‌ترین/بهترین) |
| `goldbot/store.py` | تاریخچه قیمت در SQLite (برای 🔺🔻 و جلوگیری از پست تکراری) |
| `goldbot/telegram.py` | کلاینت Bot API |
| `goldbot/main.py` | زمان‌بندی، انتشار و پاسخ به `/price` در چت خصوصی |

## راه‌اندازی قدم‌به‌قدم

1. **ساخت بات:** در تلگرام به `@BotFather` پیام بدهید، `/newbot` بزنید و توکن را بگیرید.
2. **کانال:** یک کانال بسازید و بات را **ادمین** کانال کنید (با دسترسی ارسال و ویرایش پیام).
3. **نصب:**
   ```bash
   cd gold_bot
   pip install -r requirements.txt
   python -m playwright install --with-deps chromium
   cp .env.example .env    # BOT_TOKEN و CHANNEL_ID را پر کنید
   ```
4. **تست پلتفرم‌ها (بدون تلگرام):** `python -m goldbot check`
5. **یک پست آزمایشی:** `set -a; . ./.env; set +a; python -m goldbot once`
6. **اجرای دائمی:** `python -m goldbot run`

## ⚠️ مهم: تنظیم دقیق هر پلتفرم

آدرس‌های `platforms.json` (`verified: false`) **روی سایت واقعی تست نشده‌اند**؛ چون این سایت‌ها
از محیطی که این کد در آن نوشته شد در دسترس نبودند. حالت پیش‌فرض همه `browser` است که صفحه را رندر
می‌کند و عدد بعد از کلمات «خرید/فروش» را برمی‌دارد — برای بسیاری از سایت‌ها کار می‌کند اما شکننده است.
برای دقت و سرعت بیشتر، برای هر سایت API قیمتش را پیدا کنید:

```bash
python -m goldbot.discover https://milli.gold/
```

خروجی، درخواست‌های JSON حاوی عدد شبیه قیمت را با مسیرشان نشان می‌دهد، مثلاً:

```
https://api.example.ir/v1/price/gold18
    path=data.buy_price  value=72500000
```

سپس در `platforms.json`:

```json
{ "key": "milligold", "name": "میلی‌گلد", "url": "https://milli.gold/",
  "method": "json", "api_url": "https://api.example.ir/v1/price/gold18",
  "buy_path": "data.buy_price", "sell_path": "data.sell_price",
  "unit": "rial", "verified": true }
```

- `unit`: اگر سایت ریال می‌دهد `rial` بگذارید (تقسیم بر ۱۰ می‌شود).
- اگر API بدون مرورگر جواب نداد (توکن/کوکی می‌خواهد)، `method: "browser"` با
  `capture_url_contains` (بخشی از آدرس آن درخواست) و همان `buy_path`/`sell_path` بگذارید.
- برای صفحات HTML ساده: `method: "html"` با `buy_regex`/`sell_regex` (گروه اول = قیمت).
- «خرید» یعنی قیمتی که **کاربر** می‌خرد (معمولاً بالاتر)، «فروش» قیمتی که کاربر می‌فروشد.
- یک پلتفرم را با `"enabled": false` خاموش کنید.

## تنظیمات (متغیر محیطی)

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `BOT_TOKEN` | — | توکن BotFather |
| `CHANNEL_ID` | — | `@channel` یا آیدی عددی `-100…` |
| `INTERVAL_MINUTES` | `10` | فاصله پست‌ها |
| `EDIT_LAST_MESSAGE` | `0` | `1` = به‌جای پست جدید، همان پیام قبلی ویرایش شود (کانال «لحظه‌ای») |
| `ONLY_ON_CHANGE` | `1` | اگر هیچ قیمتی عوض نشده، پست نکن |
| `QUIET_HOURS` | — | مثلاً `0-8` (به وقت تهران) |
| `CHANNEL_TITLE` / `CHANNEL_HANDLE` | | عنوان و امضای پیام |
| `TELEGRAM_API_BASE` | `https://api.telegram.org` | آدرس رله (پایین را ببینید) |
| `TELEGRAM_PROXY` | — | پروکسی HTTP/SOCKS برای تلگرام (برای socks: `pip install httpx[socks]`) |
| `SCRAPE_PROXY` | — | پروکسی برای سایت‌های طلا |
| `MIN_PRICE` / `MAX_PRICE` | `1e6` / `2e8` | بازه معقول قیمت گرم (تومان)؛ اعداد خارج از آن رد می‌شوند |
| `CHROMIUM_PATH` | — | مسیر Chromium اگر نمی‌خواهید از نسخه Playwright استفاده کنید |

## کجا اجرا کنیم؟ (مشکل فیلترینگ دوطرفه)

- بسیاری از سایت‌های طلای ایرانی **IP خارجی را مسدود می‌کنند** ← سرور باید در ایران باشد.
- **تلگرام در ایران فیلتر است** ← سرور ایران به `api.telegram.org` دسترسی ندارد.

راه‌حل پیشنهادی: سرور ایران (مثلاً لیارا) + رله رایگان Cloudflare Worker برای تلگرام:

1. در Cloudflare یک Worker بسازید و محتوای `cloudflare/telegram-relay.js` را در آن بگذارید.
2. `TELEGRAM_API_BASE=https://<نام-worker>.<حساب>.workers.dev` قرار دهید.

(در صورت فیلتر بودن دامنه workers.dev، یک دامنه شخصی به Worker وصل کنید یا از `TELEGRAM_PROXY` استفاده کنید.)
برعکس، اگر سرور خارج است، `SCRAPE_PROXY` را روی یک پروکسی با IP ایران تنظیم کنید.

### استقرار روی لیارا
```bash
cd gold_bot
liara create --app goldbot --platform docker
liara disk create --app goldbot --name data --size 1
liara env set --app goldbot BOT_TOKEN=... CHANNEL_ID=@... TELEGRAM_API_BASE=https://...
liara deploy
```

### Docker معمولی
```bash
docker build -t goldbot .
docker run -d --restart=always --env-file .env -v $PWD/data:/app/data goldbot
```

## تست‌ها
```bash
pytest -q
```
تست `tests/test_browser.py` یک سایت محلی (SPA با API) را با Playwright واقعی رندر می‌کند و هر سه روش
استخراج را بررسی می‌کند؛ اگر Playwright نصب نباشد رد می‌شود.

## نکات حقوقی
پیش از انتشار عمومی، قوانین استفاده هر سایت را بررسی کنید، فاصله درخواست‌ها را معقول نگه دارید
(پیش‌فرض ۱۰ دقیقه) و منبع قیمت‌ها را ذکر کنید.
