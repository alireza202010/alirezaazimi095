/**
 * تنظیمات اتوماسیون خبر سفرمی.
 *
 * همه مقادیر حساس (کلید Gemini، توکن CMS، ایمیل) فقط در
 * Project Settings > Script properties ذخیره می‌شوند، نه داخل کد.
 *
 * Script properties:
 *   GEMINI_API_KEY            (الزامی) کلید Google AI Studio
 *   NOTIFY_EMAIL              (الزامی) ایمیل دریافت لینک پیش‌نویس‌ها
 *   GEMINI_MODEL              (اختیاری) اگر خالی باشد جدیدترین مدل flash در دسترس خودکار انتخاب می‌شود
 *   MAX_GEMINI_CALLS_PER_DAY  (اختیاری) سقف فراخوانی روزانه Gemini، پیش‌فرض 40
 *   MAX_DRAFTS_PER_RUN        (اختیاری) سقف پیش‌نویس در هر اجرا، پیش‌فرض 3
 *   MAX_ITEM_AGE_HOURS        (اختیاری) خبرهای قدیمی‌تر از این کنار گذاشته می‌شوند، پیش‌فرض 36
 *   MIN_KEYWORD_SCORE         (اختیاری) حداقل امتیاز کلیدواژه برای ارسال به Gemini، پیش‌فرض 5
 *   MAX_GEMINI_CALLS_PER_RUN  (اختیاری) سقف فراخوانی Gemini در هر اجرا، پیش‌فرض 6
 *   FETCH_FULL_ARTICLE        (اختیاری) true/false، خواندن متن کامل صفحه خبر، پیش‌فرض true
 *   RSS_FEEDS                 (اختیاری) هر خط یک آدرس RSS؛ اگر خالی باشد از شیت Sources خوانده می‌شود
 *   CMS_WEBHOOK_URL           (اختیاری) اگر تیم فنی سفرمی endpoint ثبت پیش‌نویس بسازد
 *   CMS_WEBHOOK_TOKEN         (اختیاری) توکن اختصاصی همان endpoint (نه رمز اصلی پنل)
 *   SPREADSHEET_ID, DRAFTS_FOLDER_ID  (خودکار) توسط setup() ساخته می‌شوند
 */

var DEFAULTS = {
  GEMINI_MODEL: '',
  MAX_GEMINI_CALLS_PER_RUN: 6,
  MAX_GEMINI_CALLS_PER_DAY: 40,
  MAX_DRAFTS_PER_RUN: 3,
  MAX_ITEM_AGE_HOURS: 36,
  MIN_KEYWORD_SCORE: 5,
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
 * کلیدواژه‌های ارتباط در سه گروه. وزن بالاتر = ارتباط بیشتر. عنوان وزن دو برابر دارد.
 *
 * دروازه ورود به Gemini: خبر باید یا به یک مقصد/بازار مرتبط اشاره کند (GEO ≥ 2)
 * یا درباره مقررات سفر باشد (REG ≥ 3). کلمات عمومی مثل airline یا hotel به‌تنهایی کافی نیستند؛
 * وگرنه افتتاح هتل در فیجی یا صف امنیتی فرودگاه‌های آمریکا هم وارد می‌شود.
 */
var GEO_KEYWORDS = {
  // ایران
  'iran': 4, 'iranian': 4, 'iranians': 4, 'tehran': 4, 'imam khomeini': 4, 'mashhad': 4, 'kish': 3,
  'qeshm': 3, 'shiraz': 3, 'isfahan': 3, 'tabriz': 3, 'mahan air': 4, 'iran air': 4, 'persian gulf': 3,
  // مقاصد پرتقاضای مسافر ایرانی
  'turkey': 2, 'türkiye': 2, 'turkiye': 2, 'istanbul': 2, 'antalya': 2, 'izmir': 2,
  'dubai': 2, 'uae': 2, 'united arab emirates': 2, 'abu dhabi': 2, 'sharjah': 2,
  'georgia': 2, 'tbilisi': 2, 'batumi': 2, 'armenia': 2, 'yerevan': 2,
  'iraq': 2, 'baghdad': 2, 'karbala': 3, 'najaf': 3, 'arbaeen': 3,
  'oman': 2, 'muscat': 2, 'qatar': 2, 'doha': 2, 'saudi': 2, 'jeddah': 2, 'hajj': 3, 'umrah': 3,
  'thailand': 2, 'bangkok': 2, 'phuket': 2, 'pattaya': 2, 'malaysia': 2, 'kuala lumpur': 2,
  'azerbaijan': 2, 'baku': 2, 'russia': 2, 'moscow': 2, 'serbia': 2, 'belgrade': 2,
  'sri lanka': 2, 'maldives': 2, 'bali': 2, 'indonesia': 1, 'vietnam': 1, 'china': 1,
  'india': 1, 'kazakhstan': 1, 'uzbekistan': 2, 'tajikistan': 2, 'belarus': 1, 'cyprus': 1,
  'schengen': 3, 'european union': 1, 'canada': 1, 'australia': 1, 'middle east': 2, 'gulf': 1,
  // ایرلاین‌هایی که به ایران یا هاب‌های ترانزیت ایرانیان پرواز دارند
  'turkish airlines': 2, 'pegasus': 2, 'flydubai': 3, 'air arabia': 3, 'qatar airways': 2,
  'emirates airline': 2, 'aeroflot': 2, 'azal': 2, 'salam air': 3, 'iraqi airways': 3
};

var REG_KEYWORDS = {
  'visa': 3, 'visas': 3, 'visa-free': 3, 'e-visa': 3, 'evisa': 3, 'etias': 3,
  'entry/exit system': 3, 'ees': 3, 'passport': 2, 'entry requirement': 3, 'entry requirements': 3,
  'entry rules': 3, 'travel ban': 3, 'travel advisory': 2, 'airspace': 3, 'border': 1,
  'tourist tax': 2, 'residence permit': 2, 'visa on arrival': 3, 'transit': 2
};

var TOPIC_KEYWORDS = {
  'airline': 1, 'airlines': 1, 'airport': 1, 'flight': 1, 'flights': 1, 'new route': 2,
  'direct flight': 2, 'direct flights': 2, 'resume': 1, 'resumes': 1, 'suspend': 1, 'suspends': 1,
  'baggage': 1, 'airfare': 1, 'iata': 1, 'icao': 1, 'railway': 1, 'train': 1, 'hotel': 1,
  'tourism': 1, 'tourist': 1, 'tourists': 1, 'travellers': 1, 'travelers': 1, 'un tourism': 2,
  'unwto': 2, 'wttc': 1, 'cruise': 1
};

/** هر خبری که این عبارت‌ها را داشته باشد بدون فراخوانی Gemini کنار گذاشته می‌شود. */
var BLOCK_PATTERNS = [
  /\bsatir(e|ical)\b/i, /\bapril fool/i, /\bparody\b/i, /\bhoroscope\b/i, /\bquiz\b/i,
  /\bsponsored\b/i, /\bpartner content\b/i, /\badvertorial\b/i, /\bpodcast\b/i, /\bwebinar\b/i,
  /\bcredit card\b/i, /\bpoints guy\b/i, /\bgiveaway\b/i, /\bdeal(s)? of the (day|week)\b/i,
  /\bopinion\b/i, /\bop-ed\b/i, /\bcrossword\b/i, /\bjob(s)? (fair|opening)\b/i,
  // مطالب همیشه‌سبز و فهرستی (خبر نیستند)
  /^\s*\d+\s+(of the )?(best|top|airlines|airports|airplanes|aircraft|hotels|ways|things|reasons|places|destinations|cities|countries|us |u\.s\.)/i,
  /^\s*(here'?s|here’s) (why|how|what)\b/i, /^\s*(why|how) (the |a |an )?[^?]{0,80}(became|was built|changed|works)\b/i,
  /\bexplained\b/i, /\bthrowback\b/i, /\bon this day\b/i
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
    maxGeminiCallsPerRun: num('MAX_GEMINI_CALLS_PER_RUN'),
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
