/**
 * ترجمه و بازنویسی خبر با Gemini API و کنترل سقف مصرف روزانه.
 * یک فراخوانی برای هر خبر: هم داوری نهایی (مرتبط/شایعه/طنز) و هم ترجمه.
 */

var GEMINI_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/';

var GEMINI_SCHEMA = {
  type: 'OBJECT',
  properties: {
    relevant: { type: 'BOOLEAN', description: 'آیا برای مسافر ایرانی/مخاطب سفرمی مفید و خبر واقعی است' },
    reject_reason: { type: 'STRING', description: 'اگر relevant=false، دلیل کوتاه' },
    news_type: { type: 'STRING', enum: ['confirmed', 'announcement', 'report', 'rumor', 'satire', 'opinion', 'promotional'] },
    category: { type: 'STRING', enum: ['visa', 'flight', 'airport', 'hotel', 'tour', 'train', 'destination', 'regulation', 'industry', 'other'] },
    title_fa: { type: 'STRING' },
    lead_fa: { type: 'STRING', description: 'لید خبری یک یا دو جمله' },
    body_fa: { type: 'ARRAY', items: { type: 'STRING' }, description: 'پاراگراف‌های متن خبر' },
    traveler_note_fa: { type: 'STRING', description: 'این خبر برای مسافر ایرانی چه معنایی دارد، فقط اگر از متن منبع قابل استنتاج است وگرنه خالی' },
    seo_title_fa: { type: 'STRING' },
    meta_description_fa: { type: 'STRING' },
    slug_en: { type: 'STRING' },
    tags_fa: { type: 'ARRAY', items: { type: 'STRING' } },
    verify_fa: { type: 'ARRAY', items: { type: 'STRING' }, description: 'ادعاهایی که ویراستار باید قبل از انتشار بررسی کند' },
    confidence: { type: 'NUMBER', description: '0 تا 1، اطمینان از صحت ترجمه و ارتباط' }
  },
  required: ['relevant', 'news_type', 'category', 'title_fa', 'lead_fa', 'body_fa', 'slug_en', 'verify_fa', 'confidence']
};

function buildPrompt_(item, articleText) {
  return [
    'تو دبیر خبر مجله گردشگری سفرمی (safarme.ir) هستی؛ آژانس آنلاین بلیت هواپیما، قطار، هتل و تور برای مسافران ایرانی.',
    'وظیفه: خبر انگلیسی زیر را بررسی کن و اگر مناسب است به فارسی روان، دقیق و خبری ترجمه کن.',
    '',
    'قوانین داوری:',
    '- اگر خبر طنز، تبلیغاتی، مقاله نظر، فهرست تخفیف یا بی‌ربط به سفر و گردشگری است: relevant=false.',
    '- اگر خبر برای مسافر ایرانی یا صنعت گردشگری منطقه هیچ کاربردی ندارد (مثلا خبر داخلی یک فرودگاه کوچک آمریکا): relevant=false.',
    '- خبرهای ویزا، پرواز، فرودگاه، مقررات ورود، مقاصد پرتقاضای ایرانیان (ترکیه، امارات، گرجستان، ارمنستان، عراق، عمان، تایلند، مالزی، شنگن و...) و آمار رسمی گردشگری اولویت دارند.',
    '- اگر منبع می‌گوید «گزارش‌ها»، «احتمالا»، «منابع ناشناس» یا تایید رسمی ندارد: news_type=rumor و در متن فارسی با «به گزارش ...» و «هنوز به‌طور رسمی تایید نشده» بنویس. شایعه را هرگز خبر قطعی ننویس.',
    '',
    'قوانین ترجمه:',
    '- فقط ترجمه و بازآرایی خبری. هیچ واقعیت، عدد، تاریخ، قیمت یا نقل‌قولی اضافه نکن که در متن منبع نیست.',
    '- اعداد، تاریخ‌ها، نام شرکت‌ها و مقام‌ها را دقیق نگه دار. نام‌های خاص را به شکل رایج فارسی بنویس (مثلا «ترکیش ایرلاینز»، «فرودگاه استانبول»).',
    '- تاریخ میلادی را نگه دار؛ تبدیل به شمسی نکن.',
    '- منبع را در لید یا پاراگراف اول ذکر کن: «به گزارش ' + (item.feedTitle || 'منبع') + '».',
    '- لحن خبری و بی‌طرف. جمله‌های کوتاه و متنوع. بدون خط تیره بلند (—)، بدون عبارت‌های کلیشه‌ای مثل «در دنیای امروز»، بدون جمع‌بندی اغراق‌آمیز.',
    '- body_fa بین ۳ تا ۸ پاراگراف؛ هر پاراگراف یک ایده.',
    '- traveler_note_fa فقط وقتی پر شود که پیامد عملی برای مسافر مستقیما از متن منبع درمی‌آید.',
    '- seo_title_fa کمتر از ۶۰ کاراکتر، meta_description_fa کمتر از ۱۶۰ کاراکتر، slug_en انگلیسی با خط تیره.',
    '- verify_fa: هر ادعایی که ویراستار باید با منبع رسمی چک کند (مثلا تاریخ اجرای قانون یا قیمت).',
    '',
    'خبر:',
    'منبع: ' + (item.feedTitle || '') + ' (' + item.link + ')',
    'تاریخ انتشار: ' + (item.published ? item.published.toISOString() : 'نامعلوم'),
    'عنوان: ' + item.title,
    'دسته‌های منبع: ' + (item.categories || []).join(', '),
    'خلاصه RSS: ' + (item.summary || '').slice(0, 1500),
    '',
    'متن کامل (ممکن است ناقص باشد):',
    (articleText || '(در دسترس نیست؛ فقط از خلاصه استفاده کن و این را در verify_fa بنویس)')
  ].join('\n');
}

/** شمارنده مصرف روزانه به وقت تهران. */
function quotaKey_(now) {
  return 'GEMINI_CALLS_' + Utilities.formatDate(now || new Date(), 'Asia/Tehran', 'yyyyMMdd');
}

function geminiCallsToday_(now) {
  return Number(getProps_().getProperty(quotaKey_(now)) || 0);
}

function incrementGeminiCalls_(now) {
  var props = getProps_();
  var key = quotaKey_(now);
  props.setProperty(key, String(Number(props.getProperty(key) || 0) + 1));
  // پاک‌کردن شمارنده روزهای قبل
  Object.keys(props.getProperties()).forEach(function (k) {
    if (/^GEMINI_CALLS_\d{8}$/.test(k) && k !== key) props.deleteProperty(k);
  });
}

function hasGeminiQuota_(cfg, now) {
  return geminiCallsToday_(now) < cfg.maxGeminiCallsPerDay;
}

/**
 * @return {{ok:boolean, data:Object, error:string, quotaExceeded:boolean}}
 */
function callGemini_(cfg, prompt, now) {
  if (!hasGeminiQuota_(cfg, now)) {
    return { ok: false, data: null, error: 'سقف روزانه Gemini پر شده است', quotaExceeded: true };
  }
  incrementGeminiCalls_(now);
  var url = GEMINI_ENDPOINT + encodeURIComponent(cfg.geminiModel) + ':generateContent';
  var payload = {
    contents: [{ role: 'user', parts: [{ text: prompt }] }],
    generationConfig: {
      temperature: 0.2,
      responseMimeType: 'application/json',
      responseSchema: GEMINI_SCHEMA
    }
  };
  var res;
  try {
    res = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      headers: { 'x-goog-api-key': cfg.geminiApiKey },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
  } catch (e) {
    return { ok: false, data: null, error: 'خطای شبکه Gemini: ' + (e && e.message || e), quotaExceeded: false };
  }
  var code = res.getResponseCode();
  var text = res.getContentText();
  if (code === 429) {
    return { ok: false, data: null, error: 'Gemini 429: محدودیت نرخ یا سهمیه رایگان تمام شده', quotaExceeded: true };
  }
  if (code !== 200) {
    return { ok: false, data: null, error: 'Gemini HTTP ' + code + ': ' + text.slice(0, 300), quotaExceeded: false };
  }
  return parseGeminiResponse_(text);
}

function parseGeminiResponse_(text) {
  var json;
  try { json = JSON.parse(text); } catch (e) {
    return { ok: false, data: null, error: 'پاسخ Gemini JSON معتبر نیست', quotaExceeded: false };
  }
  var cand = json.candidates && json.candidates[0];
  if (!cand || !cand.content || !cand.content.parts) {
    var block = json.promptFeedback && json.promptFeedback.blockReason;
    return { ok: false, data: null, error: 'Gemini خروجی نداد' + (block ? ' (' + block + ')' : ''), quotaExceeded: false };
  }
  var out = cand.content.parts.map(function (p) { return p.text || ''; }).join('');
  out = out.replace(/^```(?:json)?\s*/i, '').replace(/\s*```\s*$/, '');
  var data;
  try { data = JSON.parse(out); } catch (e) {
    return { ok: false, data: null, error: 'خروجی مدل JSON نیست', quotaExceeded: false };
  }
  return { ok: true, data: sanitizeArticle_(data), error: '', quotaExceeded: false };
}

/** پاکسازی خروجی مدل: حذف خط تیره بلند، اطمینان از نوع فیلدها، محدودیت طول. */
function sanitizeArticle_(d) {
  function s(v) { return String(v == null ? '' : v).replace(/\s*—\s*/g, '، ').replace(/\s+/g, ' ').trim(); }
  function arr(v) { return (Array.isArray(v) ? v : (v ? [v] : [])).map(s).filter(String); }
  var slug = String(d.slug_en || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80);
  return {
    relevant: d.relevant === true,
    reject_reason: s(d.reject_reason),
    news_type: s(d.news_type) || 'report',
    category: s(d.category) || 'other',
    title_fa: s(d.title_fa),
    lead_fa: s(d.lead_fa),
    body_fa: arr(d.body_fa),
    traveler_note_fa: s(d.traveler_note_fa),
    seo_title_fa: s(d.seo_title_fa).slice(0, 70),
    meta_description_fa: s(d.meta_description_fa).slice(0, 170),
    slug_en: slug,
    tags_fa: arr(d.tags_fa).slice(0, 8),
    verify_fa: arr(d.verify_fa),
    confidence: Math.max(0, Math.min(1, Number(d.confidence) || 0))
  };
}

/** داوری نهایی روی خروجی مدل. */
function acceptArticle_(a) {
  if (!a.relevant) return 'مدل: نامرتبط' + (a.reject_reason ? ' (' + a.reject_reason + ')' : '');
  if (['satire', 'opinion', 'promotional'].indexOf(a.news_type) >= 0) return 'مدل: ' + a.news_type;
  if (!a.title_fa || a.body_fa.length < 2) return 'مدل: متن ناقص';
  if (a.confidence < 0.5) return 'مدل: اطمینان پایین (' + a.confidence + ')';
  return '';
}
