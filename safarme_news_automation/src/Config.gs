/**
 * تنظیمات اتوماسیون خبر سفرمی.
 *
 * همه مقادیر حساس (کلید Gemini، توکن CMS، ایمیل) فقط در
 * Project Settings > Script properties ذخیره می‌شوند، نه داخل کد.
 *
 * Script properties:
 *   GEMINI_API_KEY            (الزامی) کلید Google AI Studio
 *   NOTIFY_EMAIL              (الزامی) ایمیل دریافت لینک پیش‌نویس‌ها
 *   GEMINI_MODEL              (اختیاری) پیش‌فرض: gemini-2.5-flash
 *   MAX_GEMINI_CALLS_PER_DAY  (اختیاری) سقف فراخوانی روزانه Gemini، پیش‌فرض 40
 *   MAX_DRAFTS_PER_RUN        (اختیاری) سقف پیش‌نویس در هر اجرا، پیش‌فرض 3
 *   MAX_ITEM_AGE_HOURS        (اختیاری) خبرهای قدیمی‌تر از این کنار گذاشته می‌شوند، پیش‌فرض 36
 *   MIN_KEYWORD_SCORE         (اختیاری) حداقل امتیاز کلیدواژه برای ارسال به Gemini، پیش‌فرض 2
 *   FETCH_FULL_ARTICLE        (اختیاری) true/false، خواندن متن کامل صفحه خبر، پیش‌فرض true
 *   RSS_FEEDS                 (اختیاری) هر خط یک آدرس RSS؛ اگر خالی باشد از شیت Sources خوانده می‌شود
 *   CMS_WEBHOOK_URL           (اختیاری) اگر تیم فنی سفرمی endpoint ثبت پیش‌نویس بسازد
 *   CMS_WEBHOOK_TOKEN         (اختیاری) توکن اختصاصی همان endpoint (نه رمز اصلی پنل)
 *   SPREADSHEET_ID, DRAFTS_FOLDER_ID  (خودکار) توسط setup() ساخته می‌شوند
 */

var DEFAULTS = {
  GEMINI_MODEL: 'gemini-2.5-flash',
  MAX_GEMINI_CALLS_PER_DAY: 40,
  MAX_DRAFTS_PER_RUN: 3,
  MAX_ITEM_AGE_HOURS: 36,
  MIN_KEYWORD_SCORE: 2,
  FETCH_FULL_ARTICLE: true,
  MAX_RUNTIME_MS: 4.5 * 60 * 1000,
  SEEN_RETENTION_DAYS: 45,
  ARTICLE_CHAR_LIMIT: 9000
};

/**
 * منابع پیش‌فرض. این لیست هنگام setup() در شیت Sources نوشته می‌شود و از آن به بعد
 * از همان شیت قابل ویرایش است (ستون enabled را FALSE کنید تا منبع غیرفعال شود).
 * قبل از فعال‌سازی تریگر حتما testFeeds() را اجرا کنید.
 */
var DEFAULT_SOURCES = [
  // name, url, type (primary = منبع دست‌اول/رسمی، trade = رسانه تخصصی صنعت)
  ['Schengen Visa Info – News', 'https://www.schengenvisainfo.com/news/feed/', 'trade'],
  ['Simple Flying', 'https://simpleflying.com/feed/', 'trade'],
  ['Skift', 'https://skift.com/feed/', 'trade'],
  ['AeroTime', 'https://www.aerotime.aero/feed', 'trade'],
  ['TravelDailyNews International', 'https://www.traveldailynews.com/feed/', 'trade'],
  ['Travel Daily Media', 'https://www.traveldailymedia.com/feed/', 'trade'],
  ['TTG Asia', 'https://www.ttgasia.com/feed/', 'trade'],
  ['eTurboNews', 'https://eturbonews.com/feed/', 'trade']
];

/**
 * کلیدواژه‌های مرتبط با مخاطب سفرمی (مسافر ایرانی: پرواز، قطار، هتل، تور، ویزا).
 * وزن بالاتر = ارتباط بیشتر.
 */
var RELEVANCE_KEYWORDS = {
  // بسیار مرتبط با مسافر ایرانی
  'iran': 4, 'iranian': 4, 'tehran': 4, 'imam khomeini': 4, 'mashhad': 4, 'kish': 3, 'qeshm': 3,
  'shiraz': 3, 'isfahan': 3, 'tabriz': 3, 'mahan air': 4, 'iran air': 4,
  // مقاصد پرتقاضا
  'turkey': 2, 'türkiye': 2, 'istanbul': 2, 'antalya': 2, 'dubai': 2, 'uae': 2, 'abu dhabi': 2,
  'georgia': 2, 'tbilisi': 2, 'batumi': 2, 'armenia': 2, 'yerevan': 2, 'iraq': 2, 'karbala': 3,
  'najaf': 3, 'oman': 2, 'muscat': 2, 'qatar': 2, 'doha': 2, 'thailand': 2, 'phuket': 2,
  'malaysia': 2, 'kuala lumpur': 2, 'russia': 1, 'moscow': 1, 'saudi': 2, 'hajj': 3, 'umrah': 3,
  'azerbaijan': 2, 'baku': 2, 'china': 1, 'india': 1, 'sri lanka': 2, 'maldives': 2, 'bali': 2,
  'schengen': 3, 'europe': 1, 'cyprus': 1, 'serbia': 2, 'belarus': 1, 'kazakhstan': 1,
  // مقررات سفر
  'visa': 3, 'visa-free': 3, 'e-visa': 3, 'etias': 3, 'entry/exit system': 3, 'ees': 2,
  'passport': 2, 'entry requirement': 3, 'border': 1, 'travel ban': 3, 'travel advisory': 2,
  'airspace': 3, 'customs': 1, 'tourist tax': 2, 'residence permit': 1,
  // حمل‌ونقل و اقامت
  'airline': 2, 'airport': 2, 'flight': 2, 'flights': 2, 'route': 1, 'new route': 3,
  'direct flight': 3, 'baggage': 2, 'fare': 1, 'airfare': 2, 'cancel': 1, 'suspend': 2,
  'resume': 2, 'iata': 2, 'icao': 2, 'turkish airlines': 3, 'pegasus': 2, 'flydubai': 3,
  'emirates': 2, 'qatar airways': 2, 'air arabia': 3, 'aeroflot': 2, 'train': 1, 'railway': 1,
  'hotel': 1, 'cruise': 1, 'tourism': 2, 'tourist': 2, 'tourists': 2, 'travel': 1,
  'un tourism': 3, 'unwto': 3, 'wttc': 2
};

/** هر خبری که این عبارت‌ها را داشته باشد بدون فراخوانی Gemini کنار گذاشته می‌شود. */
var BLOCK_PATTERNS = [
  /\bsatir(e|ical)\b/i, /\bapril fool/i, /\bparody\b/i, /\bhoroscope\b/i, /\bquiz\b/i,
  /\bsponsored\b/i, /\bpartner content\b/i, /\badvertorial\b/i, /\bpodcast\b/i, /\bwebinar\b/i,
  /\bcredit card\b/i, /\bpoints guy\b/i, /\bgiveaway\b/i, /\bdeal(s)? of the (day|week)\b/i,
  /\bopinion\b/i, /\bop-ed\b/i, /\bcrossword\b/i, /\bjob(s)? (fair|opening)\b/i
];

function getProps_() {
  return PropertiesService.getScriptProperties();
}

function getConfig_() {
  var p = getProps_().getProperties();
  function num(key) {
    var v = p[key];
    return v !== undefined && v !== '' && !isNaN(Number(v)) ? Number(v) : DEFAULTS[key];
  }
  return {
    geminiApiKey: p.GEMINI_API_KEY || '',
    geminiModel: p.GEMINI_MODEL || DEFAULTS.GEMINI_MODEL,
    notifyEmail: p.NOTIFY_EMAIL || '',
    maxGeminiCallsPerDay: num('MAX_GEMINI_CALLS_PER_DAY'),
    maxDraftsPerRun: num('MAX_DRAFTS_PER_RUN'),
    maxItemAgeHours: num('MAX_ITEM_AGE_HOURS'),
    minKeywordScore: num('MIN_KEYWORD_SCORE'),
    fetchFullArticle: p.FETCH_FULL_ARTICLE ? String(p.FETCH_FULL_ARTICLE).toLowerCase() !== 'false' : DEFAULTS.FETCH_FULL_ARTICLE,
    rssFeeds: (p.RSS_FEEDS || '').split(/\s*[\n,]\s*/).filter(function (s) { return /^https?:\/\//.test(s); }),
    cmsWebhookUrl: p.CMS_WEBHOOK_URL || '',
    cmsWebhookToken: p.CMS_WEBHOOK_TOKEN || '',
    spreadsheetId: p.SPREADSHEET_ID || '',
    draftsFolderId: p.DRAFTS_FOLDER_ID || ''
  };
}

function requireConfig_(cfg) {
  var missing = [];
  if (!cfg.geminiApiKey) missing.push('GEMINI_API_KEY');
  if (!cfg.notifyEmail) missing.push('NOTIFY_EMAIL');
  if (!cfg.spreadsheetId) missing.push('SPREADSHEET_ID (اول setup() را اجرا کنید)');
  if (!cfg.draftsFolderId) missing.push('DRAFTS_FOLDER_ID (اول setup() را اجرا کنید)');
  if (missing.length) throw new Error('Script properties ناقص است: ' + missing.join('، '));
}
