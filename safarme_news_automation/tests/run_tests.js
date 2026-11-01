/* eslint-disable no-console */
// تست آفلاین: فایل‌های .gs در یک sandbox با سرویس‌های شبیه‌سازی‌شده Apps Script اجرا می‌شوند.
// اجرا: node safarme_news_automation/tests/run_tests.js
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
const crypto = require('crypto');

const SRC = path.join(__dirname, '..', 'src');
const FIX = path.join(__dirname, 'fixtures');

function makeSandbox(opts) {
  opts = opts || {};
  const props = Object.assign({}, opts.props || {});
  const sheets = {};
  const docs = [];
  const mails = [];
  const fetches = [];
  const triggers = [];

  function makeSheet(name) {
    const rows = [];
    const sh = {
      name, rows,
      getName: () => name,
      getLastRow: () => rows.length,
      appendRow: (r) => { rows.push(r.slice()); },
      setFrozenRows: () => {},
      getRange: (r, c, nr, nc) => ({
        getValues: () => {
          const out = [];
          for (let i = 0; i < (nr || 1); i++) {
            const row = rows[r - 1 + i] || [];
            const o = [];
            for (let j = 0; j < (nc || 1); j++) o.push(row[c - 1 + j] === undefined ? '' : row[c - 1 + j]);
            out.push(o);
          }
          return out;
        },
        setValues: (vals) => {
          vals.forEach((v, i) => {
            const idx = r - 1 + i;
            while (rows.length <= idx) rows.push([]);
            v.forEach((x, j) => { rows[idx][c - 1 + j] = x; });
          });
        },
        clearContent: () => {
          for (let i = 0; i < nr; i++) rows[r - 1 + i] = [];
          while (rows.length && rows[rows.length - 1].every((x) => x === '' || x === undefined)) rows.pop();
        }
      })
    };
    return sh;
  }
  const ss = {
    getId: () => 'SS1', getUrl: () => 'https://docs.google.com/spreadsheets/d/SS1',
    getSheetByName: (n) => sheets[n] || null,
    insertSheet: (n) => (sheets[n] = makeSheet(n)),
    getSheets: () => Object.values(sheets),
    deleteSheet: (s) => { delete sheets[s.getName()]; }
  };

  function para(text) {
    const p = { text, setHeading: () => p, setLeftToRight: () => p, setAlignment: () => p,
      editAsText: () => ({ setBold: () => {}, setLinkUrl: () => {} }), getType: () => 'PARAGRAPH',
      asParagraph: () => ({ getText: () => text }) };
    return p;
  }

  const fetchHandler = opts.fetch || (() => ({ code: 404, body: '' }));

  const sb = {
    console,
    Logger: { log: (m) => { if (opts.verbose) console.log('  [Logger]', m); } },
    PropertiesService: {
      getScriptProperties: () => ({
        getProperties: () => Object.assign({}, props),
        getProperty: (k) => (k in props ? props[k] : null),
        setProperty: (k, v) => { props[k] = String(v); },
        deleteProperty: (k) => { delete props[k]; }
      })
    },
    UrlFetchApp: {
      fetch: (url, o) => {
        fetches.push({ url, o });
        const r = fetchHandler(url, o || {});
        if (r.throw) throw new Error(r.throw);
        return { getResponseCode: () => r.code, getContentText: () => r.body };
      }
    },
    SpreadsheetApp: { openById: () => ss, create: () => ss },
    DocumentApp: {
      ParagraphHeading: { HEADING1: 'H1', HEADING2: 'H2', HEADING3: 'H3' },
      HorizontalAlignment: { RIGHT: 'R' },
      ElementType: { PARAGRAPH: 'PARAGRAPH' },
      create: (title) => {
        const id = 'DOC' + (docs.length + 1);
        const content = [para('')];
        const d = { id, title, content };
        docs.push(d);
        return {
          getId: () => id, getUrl: () => 'https://docs.google.com/document/d/' + id,
          saveAndClose: () => {},
          getBody: () => ({
            appendParagraph: (t) => { const p = para(t); content.push(p); return p; },
            appendListItem: (t) => { const p = para(t); content.push(p); return p; },
            appendHorizontalRule: () => {},
            getChild: (i) => content[i],
            removeChild: (c) => { content.splice(content.indexOf(c), 1); }
          })
        };
      }
    },
    DriveApp: {
      getFileById: () => ({ moveTo: () => {} }),
      getFolderById: () => ({}),
      createFolder: () => ({ getId: () => 'FOLDER1' })
    },
    MailApp: { sendEmail: (m) => mails.push(m), getRemainingDailyQuota: () => 100 },
    LockService: { getScriptLock: () => ({ tryLock: () => true, releaseLock: () => {} }) },
    ScriptApp: {
      getProjectTriggers: () => triggers.slice(),
      deleteTrigger: (t) => triggers.splice(triggers.indexOf(t), 1),
      newTrigger: (fn) => ({ timeBased: () => ({ everyHours: (h) => ({ create: () => triggers.push({ fn, h, getHandlerFunction: () => fn }) }) }) })
    },
    Utilities: {
      formatDate: (d, tz, fmt) => {
        const s = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
        return fmt === 'yyyyMMdd' ? s.replace(/-/g, '') : s;
      },
      computeDigest: (_alg, s) => Array.from(crypto.createHash('sha256').update(String(s)).digest()),
      base64EncodeWebSafe: (bytes) => Buffer.from(bytes).toString('base64url'),
      DigestAlgorithm: { SHA_256: 'SHA_256' },
      sleep: () => {}
    }
  };
  vm.createContext(sb);
  fs.readdirSync(SRC).filter((f) => f.endsWith('.gs')).sort().forEach((f) => {
    vm.runInContext(fs.readFileSync(path.join(SRC, f), 'utf8'), sb, { filename: f });
  });
  sb.__state = { props, sheets, docs, mails, fetches, triggers, ss };
  return sb;
}

function rssFixture(now) {
  const h = (n) => new Date(now.getTime() - n * 3600000).toUTCString();
  return fs.readFileSync(path.join(FIX, 'sample_rss.xml'), 'utf8')
    .replace('{{D1}}', h(2)).replace('{{D2}}', h(3)).replace('{{D3}}', h(100))
    .replace('{{D4}}', h(1)).replace('{{D5}}', h(4)).replace('{{D6}}', h(5));
}

function geminiReply(obj) {
  return JSON.stringify({ candidates: [{ content: { parts: [{ text: JSON.stringify(obj) }] } }] });
}

const GOOD_ARTICLE = {
  relevant: true, news_type: 'announcement', category: 'visa',
  title_fa: 'گرجستان شرایط جدید ورود گردشگران ایرانی را اعلام کرد',
  lead_fa: 'به گزارش منبع، وزارت خارجه گرجستان قانون تازه‌ای برای ورود اعلام کرد — از اول دسامبر.',
  body_fa: ['پاراگراف اول.', 'پاراگراف دوم.', 'پاراگراف سوم.'],
  traveler_note_fa: '', seo_title_fa: 'شرایط جدید ورود ایرانیان به گرجستان',
  meta_description_fa: 'توضیح متا', slug_en: 'Georgia New Entry Rules for Iranians!',
  tags_fa: ['گرجستان', 'ویزا'], verify_fa: ['تاریخ اجرای قانون'], confidence: 0.9
};

const MODEL_LIST = [
  { name: 'models/gemini-2.5-flash', supportedGenerationMethods: ['generateContent'] },
  { name: 'models/gemini-3.0-flash', supportedGenerationMethods: ['generateContent', 'countTokens'] },
  { name: 'models/gemini-3.0-flash-lite', supportedGenerationMethods: ['generateContent'] },
  { name: 'models/gemini-3.5-flash-preview-09-2026', supportedGenerationMethods: ['generateContent'] },
  { name: 'models/gemini-3.0-flash-image', supportedGenerationMethods: ['generateContent'] },
  { name: 'models/gemini-3.0-pro', supportedGenerationMethods: ['generateContent'] },
  { name: 'models/text-embedding-004', supportedGenerationMethods: ['embedContent'] }
];

const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

// ---------- واحد ----------
test('parseFeed_ RSS: CDATA، entity، دسته‌ها و تاریخ', () => {
  const sb = makeSandbox();
  const now = new Date();
  const items = sb.parseFeed_(rssFixture(now), 'https://feed.example/rss');
  assert.strictEqual(items.length, 6);
  assert.strictEqual(items[0].title, 'Georgia announces new entry rules for Iranian tourists & visitors');
  assert.ok(items[0].published.getTime() > 0);
  assert.ok(items[0].categories.includes('Visa'));
  assert.ok(items[0].summary.includes('Ministry of Foreign Affairs'));
});

test('parseFeed_ Atom', () => {
  const sb = makeSandbox();
  const xml = fs.readFileSync(path.join(FIX, 'sample_atom.xml'), 'utf8');
  const items = sb.parseFeed_(xml, 'https://x/atom');
  assert.strictEqual(items.length, 2);
  assert.strictEqual(items[0].link, 'https://news.example/flydubai-mashhad');
  assert.ok(items[0].categories.includes('Airlines'));
});

test('looksLikeFeed_ صفحه HTML را رد می‌کند', () => {
  const sb = makeSandbox();
  assert.strictEqual(sb.looksLikeFeed_('<!doctype html><html><body>home</body></html>'), false);
  assert.strictEqual(sb.looksLikeFeed_('<?xml version="1.0"?><rss version="2.0">'), true);
});

test('normalizeUrl_ پارامترهای ردیابی و www را حذف می‌کند', () => {
  const sb = makeSandbox();
  assert.strictEqual(sb.normalizeUrl_('http://www.Site.com/a/b/?utm_source=x&id=5&fbclid=1#top'), 'https://site.com/a/b/?id=5');
  assert.strictEqual(sb.normalizeUrl_('https://site.com/a/?utm_source=rss'), 'https://site.com/a');
});

test('keywordScore_ مرز کلمه را رعایت می‌کند (ees داخل fees شمرده نشود)', () => {
  const sb = makeSandbox();
  assert.strictEqual(sb.keywordScore_({ title: 'Bank fees rise', summary: '' }).score, 0);
  assert.ok(sb.keywordScore_({ title: 'EU delays EES launch', summary: '' }).score >= 4);
});

test('titleSimilarity_ خبر مشابه از دو منبع را تشخیص می‌دهد', () => {
  const sb = makeSandbox();
  assert.ok(sb.titleSimilarity_('Georgia announces new entry rules for Iranian tourists',
    'Iranian tourists: Georgia announces new entry rules') >= 0.6);
  assert.ok(sb.titleSimilarity_('Georgia entry rules', 'Dubai airport expansion') < 0.2);
});

test('sanitizeArticle_ خط تیره بلند و slug را اصلاح می‌کند', () => {
  const sb = makeSandbox();
  const a = sb.sanitizeArticle_(GOOD_ARTICLE);
  assert.ok(!a.lead_fa.includes('—'));
  assert.strictEqual(a.slug_en, 'georgia-new-entry-rules-for-iranians');
  assert.strictEqual(sb.acceptArticle_(a), '');
  assert.ok(sb.acceptArticle_(Object.assign({}, a, { news_type: 'satire' })));
  assert.ok(sb.acceptArticle_(Object.assign({}, a, { confidence: 0.3 })));
});

test('extractArticleText_ پاراگراف‌های اصلی را برمی‌دارد', () => {
  const sb = makeSandbox();
  const html = '<html><nav><p>Menu menu menu menu menu menu menu menu menu</p></nav><article><p>The ministry confirmed that the new rule applies from December 1 to all visitors.</p><p>Read more: something unrelated here that is long enough</p></article></html>';
  const t = sb.extractArticleText_(html, 5000);
  assert.ok(t.includes('December 1'));
  assert.ok(!t.includes('Read more'));
});

// ---------- یکپارچه ----------
function pipelineSandbox(extra) {
  extra = extra || {};
  const now = new Date();
  let geminiCalls = 0;
  const modelsUsed = [];
  const sb = makeSandbox({
    props: Object.assign({ GEMINI_API_KEY: 'k', NOTIFY_EMAIL: 'me@example.com', RSS_FEEDS: 'https://feed.example/rss\nhttps://home.example/' }, extra.props || {}),
    fetch: (url, o) => {
      if (url === 'https://feed.example/rss') return { code: 200, body: rssFixture(now) };
      if (url === 'https://home.example/') return { code: 200, body: '<!doctype html><html></html>' };
      if (url.startsWith('https://generativelanguage.googleapis.com/v1beta/models?')) {
        return { code: 200, body: JSON.stringify(extra.models || { models: MODEL_LIST }) };
      }
      if (url.startsWith('https://generativelanguage.googleapis.com/')) {
        geminiCalls++;
        modelsUsed.push(url.split('/models/')[1].split(':')[0]);
        assert.strictEqual(o.headers['x-goog-api-key'], 'k');
        if (extra.gemini) return extra.gemini(geminiCalls, JSON.parse(o.payload));
        return { code: 200, body: geminiReply(GOOD_ARTICLE) };
      }
      if (url === 'https://cms.example/drafts') return { code: 201, body: '{"edit_url":"https://safarme.ir/admin/news/1/edit"}' };
      return { code: 200, body: '<article><p>Full article text with enough length to pass the filter for sure.</p></article>' };
    }
  });
  sb.setup();
  return { sb, now, calls: () => geminiCalls, modelsUsed };
}

test('dryRun: فقط خبرهای تازه، مرتبط، غیرطنز انتخاب می‌شوند و Gemini صدا زده نمی‌شود', () => {
  const { sb, calls } = pipelineSandbox();
  const r = sb.dryRun();
  const titles = r.candidates.map((c) => c.title);
  assert.strictEqual(calls(), 0);
  assert.ok(titles.some((t) => t.startsWith('Georgia announces')));
  assert.ok(titles.some((t) => t.startsWith('Turkish Airlines')));
  assert.ok(!titles.some((t) => /satire/i.test(t)), 'طنز باید حذف شود');
  assert.ok(!titles.some((t) => /Old news/i.test(t)), 'قدیمی باید حذف شود');
  assert.ok(!titles.some((t) => /pizza/i.test(t)), 'نامرتبط باید حذف شود');
  assert.ok(!titles.some((t) => /Iranian visitors: Georgia/i.test(t)), 'تکراری باید حذف شود');
  assert.strictEqual(sb.__state.sheets.Seen.rows.length, 1, 'dryRun نباید سابقه بنویسد');
});

test('runNow: پیش‌نویس، صف، ایمیل و سقف هر اجرا', () => {
  const { sb, calls } = pipelineSandbox({ props: { MAX_DRAFTS_PER_RUN: '1' } });
  const r = sb.runNow();
  assert.strictEqual(r.stats.drafts, 1);
  assert.strictEqual(calls(), 1);
  const st = sb.__state;
  assert.strictEqual(st.docs.length, 1);
  assert.ok(st.docs[0].title.startsWith('[پیش‌نویس]'));
  assert.strictEqual(st.mails.length, 1);
  assert.ok(st.mails[0].subject.includes('گرجستان'));
  assert.ok(st.mails[0].htmlBody.includes('https://docs.google.com/document/d/DOC1'));
  const q = st.sheets.Queue.rows;
  assert.strictEqual(q.length, 2);
  assert.strictEqual(q[1][1], 'pending');
  assert.strictEqual(q[1][11], 'disabled');
  assert.ok(q[1][13].includes('<h1>'));
  // اجرای دوم: خبر قبلی تکراری است، خبر بعدی پردازش می‌شود
  const r2 = sb.runNow();
  assert.strictEqual(r2.stats.drafts, 1);
  assert.strictEqual(st.docs.length, 2);
  // اجرای سوم: هر دو خبر پیش‌نویس شده‌اند؛ چیزی برای پردازش نمانده
  const r3 = sb.runNow();
  assert.strictEqual(r3.stats.drafts, 0);
  assert.strictEqual(r3.stats.candidates, 0);
  const keys = st.sheets.Seen.rows.slice(1).map((x) => x[0]);
  assert.strictEqual(new Set(keys).size, keys.length, 'سابقه نباید کلید تکراری داشته باشد');
});

test('منبع HTML (صفحه اصلی) به‌عنوان خطای منبع ثبت می‌شود', () => {
  const { sb } = pipelineSandbox();
  const r = sb.runNow();
  assert.strictEqual(r.stats.sourceErrors, 1);
  assert.ok(sb.__state.sheets.Log.rows.some((x) => String(x[2]).includes('RSS/Atom نیست')));
});

test('سقف روزانه Gemini رعایت می‌شود', () => {
  const { sb, calls } = pipelineSandbox({ props: { MAX_GEMINI_CALLS_PER_DAY: '1', MAX_DRAFTS_PER_RUN: '5' } });
  sb.runNow();
  assert.strictEqual(calls(), 1);
  sb.runNow();
  assert.strictEqual(calls(), 1, 'بعد از پر شدن سقف نباید فراخوانی دیگری انجام شود');
});

test('رد مدل (شایعه طنز/نامرتبط) پیش‌نویس نمی‌سازد ولی در سابقه ثبت می‌شود', () => {
  const { sb } = pipelineSandbox({
    props: { MAX_DRAFTS_PER_RUN: '5' },
    gemini: () => ({ code: 200, body: geminiReply(Object.assign({}, GOOD_ARTICLE, { relevant: false, reject_reason: 'بی‌ربط' })) })
  });
  const r = sb.runNow();
  assert.strictEqual(r.stats.drafts, 0);
  assert.ok(r.stats.modelRejected >= 2);
  assert.ok(sb.__state.sheets.Seen.rows.some((x) => String(x[3]).includes('مدل: نامرتبط')));
});

test('خطای 429 اجرا را متوقف می‌کند و خبر برای ساعت بعد باقی می‌ماند', () => {
  const { sb } = pipelineSandbox({ gemini: () => ({ code: 429, body: '{}' }) });
  const r = sb.runNow();
  assert.strictEqual(r.stats.drafts, 0);
  assert.strictEqual(r.stats.geminiCalls, 1);
  assert.ok(!sb.__state.sheets.Seen.rows.some((x) => x[3] === 'draft'));
  assert.ok(!sb.__state.sheets.Seen.rows.some((x) => String(x[1]).startsWith('Georgia announces')));
});

test('ارسال اختیاری به پنل سفرمی با status=draft', () => {
  const { sb } = pipelineSandbox({ props: { MAX_DRAFTS_PER_RUN: '1', CMS_WEBHOOK_URL: 'https://cms.example/drafts', CMS_WEBHOOK_TOKEN: 'tok' } });
  sb.runNow();
  const call = sb.__state.fetches.find((f) => f.url === 'https://cms.example/drafts');
  assert.ok(call);
  const body = JSON.parse(call.o.payload);
  assert.strictEqual(body.status, 'draft');
  assert.strictEqual(call.o.headers.Authorization, 'Bearer tok');
  assert.ok(sb.__state.sheets.Queue.rows[1][11].startsWith('ok https://safarme.ir/admin'));
});

test('installHourlyTrigger فقط یک تریگر ساعتی می‌سازد', () => {
  const sb = makeSandbox();
  sb.installHourlyTrigger();
  sb.installHourlyTrigger();
  assert.strictEqual(sb.__state.triggers.length, 1);
  assert.strictEqual(sb.__state.triggers[0].h, 1);
  assert.strictEqual(sb.__state.triggers[0].fn, 'hourlyJob');
});

test('بدون کلید Gemini اجرا با پیام روشن متوقف می‌شود', () => {
  const sb = makeSandbox({ props: { NOTIFY_EMAIL: 'me@example.com' } });
  sb.setup();
  assert.throws(() => sb.runNow(), /GEMINI_API_KEY/);
});

test('pickFlashModel_ جدیدترین flash پایدار را انتخاب می‌کند', () => {
  const sb = makeSandbox();
  assert.strictEqual(sb.pickFlashModel_(MODEL_LIST), 'gemini-3.0-flash');
  assert.deepStrictEqual(Array.from(sb.rankFlashModels_(MODEL_LIST)).slice(0, 3), ['gemini-3.0-flash', 'gemini-2.5-flash', 'gemini-3.0-flash-lite']);
  assert.strictEqual(sb.pickFlashModel_([{ name: 'models/gemini-3.5-flash-preview-09-2026', supportedGenerationMethods: ['generateContent'] }]), 'gemini-3.5-flash-preview-09-2026');
  assert.strictEqual(sb.pickFlashModel_([]), '');
});

test('مدل از کار افتاده (404) با مدل تازه جایگزین می‌شود', () => {
  const { sb, modelsUsed } = pipelineSandbox({
    props: { MAX_DRAFTS_PER_RUN: '1', GEMINI_MODEL_RESOLVED: 'gemini-2.5-flash', GEMINI_MODEL_RESOLVED_AT: String(Date.now()) },
    gemini: (n) => (n === 1 ? { code: 404, body: '{"error":{"code":404,"message":"no longer available"}}' } : { code: 200, body: geminiReply(GOOD_ARTICLE) })
  });
  const r = sb.runNow();
  assert.deepStrictEqual(modelsUsed, ['gemini-2.5-flash', 'gemini-3.0-flash']);
  assert.strictEqual(r.stats.drafts, 1);
  assert.strictEqual(sb.__state.props.GEMINI_MODEL_RESOLVED, 'gemini-3.0-flash');
});

test('GEMINI_MODEL دستی بر انتخاب خودکار مقدم است', () => {
  const { sb, modelsUsed } = pipelineSandbox({ props: { MAX_DRAFTS_PER_RUN: '1', GEMINI_MODEL: 'gemini-x-flash' } });
  sb.runNow();
  assert.deepStrictEqual(modelsUsed, ['gemini-x-flash']);
});

test('سقف فراخوانی Gemini در هر اجرا', () => {
  const { sb, calls } = pipelineSandbox({
    props: { MAX_DRAFTS_PER_RUN: '5', MAX_GEMINI_CALLS_PER_RUN: '1' },
    gemini: () => ({ code: 200, body: geminiReply(Object.assign({}, GOOD_ARTICLE, { relevant: false })) })
  });
  sb.runNow();
  assert.strictEqual(calls(), 1);
});

test('فیلتر ارتباط روی عنوان‌های واقعی dryRun اول', () => {
  const sb = makeSandbox();
  const cfg = { maxItemAgeHours: 36, minKeywordScore: 5 };
  const now = new Date();
  const mk = (title, summary) => ({ title, summary: summary || '', link: 'https://x/' + encodeURIComponent(title), published: now, categories: [] });
  const items = [
    mk('10 Airlines Offering Stopover Packages For A Fraction Of The Cost Of A Separate Trip', 'Qatar Airways, Turkish Airlines, Emirates, Malaysia'),
    mk('Lufthansa Crew Member Dies Of Electrocution In Hotel Swimming Pool During Layover', 'India airport'),
    mk('Three killed in midair helicopter collision at Oregon airport', 'flight'),
    mk('5 US Airports With The Longest Security Lines In 2026', 'baggage travel'),
    mk('Here’s Why Dassault Scrapped The Falcon 5X Before It Ever Entered Service', 'flights'),
    mk('Marriott to launch JW Marriott in Fiji by 2027', 'China hotel tourism'),
    mk('Passenger rights group sues DOT over rule shifting flight delay costs to travelers', 'airline hotel'),
    mk('Capella Dubai to open at Dubai Peninsula in 2030', 'hotel tourism'),
    mk('Turkey extends visa-free travel to new countries', 'tourists'),
    mk('flydubai resumes flights to Mashhad', 'airline')
  ];
  const sel = sb.selectCandidates_(items, { urls: {}, titles: [] }, cfg, now);
  const picked = Array.from(sel.candidates, (c) => c.title);
  assert.deepStrictEqual(picked.sort(), [
    'Capella Dubai to open at Dubai Peninsula in 2030',
    'Turkey extends visa-free travel to new countries',
    'flydubai resumes flights to Mashhad'
  ].sort());
});

test('503 پایدار: تلاش مجدد و بعد مدل جایگزین، با یک واحد مصرف روزانه', () => {
  const { sb, modelsUsed } = pipelineSandbox({
    props: { MAX_DRAFTS_PER_RUN: '1' },
    gemini: (n) => (n <= 3 ? { code: 503, body: '{"error":{"code":503,"status":"UNAVAILABLE"}}' } : { code: 200, body: geminiReply(GOOD_ARTICLE) })
  });
  const r = sb.runNow();
  assert.deepStrictEqual(modelsUsed, ['gemini-3.0-flash', 'gemini-3.0-flash', 'gemini-3.0-flash', 'gemini-2.5-flash']);
  assert.strictEqual(r.stats.drafts, 1);
  assert.strictEqual(sb.geminiCallsToday_(new Date()), 1);
});

test('503 گذرا: تلاش دوم موفق می‌شود', () => {
  const { sb, modelsUsed } = pipelineSandbox({
    props: { MAX_DRAFTS_PER_RUN: '1' },
    gemini: (n) => (n === 1 ? { code: 503, body: '{}' } : { code: 200, body: geminiReply(GOOD_ARTICLE) })
  });
  assert.strictEqual(sb.runNow().stats.drafts, 1);
  assert.deepStrictEqual(modelsUsed, ['gemini-3.0-flash', 'gemini-3.0-flash']);
});

test('کش قدیمی بدون فهرست جایگزین تازه‌سازی می‌شود', () => {
  const { sb, modelsUsed } = pipelineSandbox({
    props: { MAX_DRAFTS_PER_RUN: '1', GEMINI_MODEL_RESOLVED: 'gemini-3.0-flash', GEMINI_MODEL_RESOLVED_AT: String(Date.now()) },
    gemini: (n) => (n <= 3 ? { code: 503, body: '{}' } : { code: 200, body: geminiReply(GOOD_ARTICLE) })
  });
  assert.strictEqual(sb.runNow().stats.drafts, 1);
  assert.strictEqual(modelsUsed[3], 'gemini-2.5-flash');
});

let failed = 0;
for (const t of tests) {
  try { t.fn(); console.log('✓', t.name); } catch (e) { failed++; console.log('✗', t.name, '\n   ', e.stack.split('\n').slice(0, 3).join('\n    ')); }
}
console.log(`\n${tests.length - failed}/${tests.length} passed`);
process.exit(failed ? 1 : 0);
