/**
 * اتوماسیون خبر گردشگری سفرمی
 * RSS → فیلتر → ترجمه با Gemini → پیش‌نویس (Google Doc + صف + اختیاری پنل سفرمی) → ایمیل
 *
 * ترتیب اجرا (از منوی Run در ویرایشگر Apps Script):
 *   1) setup()                ساخت شیت و پوشه پیش‌نویس
 *   2) testFeeds()            بررسی اینکه همه منابع واقعا RSS هستند
 *   3) testEmail()            ایمیل آزمایشی
 *   4) testGemini()           یک فراخوانی آزمایشی Gemini
 *   5) dryRun()               نمایش خبرهای انتخاب‌شده بدون مصرف Gemini
 *   6) runNow()               یک اجرای واقعی دستی
 *   7) installHourlyTrigger() فعال‌سازی اجرای ساعتی
 */

function setup() {
  var props = getProps_();
  var cfg = getConfig_();
  var ss;
  if (cfg.spreadsheetId) {
    ss = SpreadsheetApp.openById(cfg.spreadsheetId);
  } else {
    ss = SpreadsheetApp.create('سفرمی | صف خبر گردشگری');
    props.setProperty('SPREADSHEET_ID', ss.getId());
  }
  ensureSheets_(ss);
  seedSources_(ss);
  if (!cfg.draftsFolderId) {
    var folder = DriveApp.createFolder('سفرمی | پیش‌نویس‌های خبر');
    props.setProperty('DRAFTS_FOLDER_ID', folder.getId());
  }
  var missing = [];
  if (!cfg.geminiApiKey) missing.push('GEMINI_API_KEY');
  if (!cfg.notifyEmail) missing.push('NOTIFY_EMAIL');
  log_(ss, 'INFO', 'setup انجام شد. شیت: ' + ss.getUrl() +
    (missing.length ? ' | هنوز این Script properties را وارد کنید: ' + missing.join('، ') : ''));
  return ss.getUrl();
}

/** خواندن همه منابع و ثبت نتیجه در ستون last_status شیت Sources. */
function testFeeds() {
  var cfg = getConfig_();
  var ss = openSpreadsheet_(cfg);
  var now = new Date();
  var report = loadSources_(ss, cfg).map(function (src) {
    var r = fetchFeed_(src.url);
    var fresh = r.items.filter(function (it) { return isFresh_(it, cfg.maxItemAgeHours, now); }).length;
    var undated = r.items.filter(function (it) { return !it.published; });
    var newest = r.items.reduce(function (m, it) { return it.published && (!m || it.published > m) ? it.published : m; }, null);
    var status = r.ok ? 'OK' : 'FAIL: ' + r.error;
    updateSourceStatus_(ss, src, status, r.items.length, now);
    return (r.ok ? '✅ ' : '❌ ') + src.name + ' | ' + status + ' | آیتم: ' + r.items.length + ' | تازه: ' + fresh +
      ' | جدیدترین: ' + (newest ? Utilities.formatDate(newest, 'Asia/Tehran', 'yyyy-MM-dd HH:mm') : '-') +
      (undated.length ? ' | بدون تاریخ: ' + undated.length + ' (نمونه تاریخ خام: "' + (undated[0].rawDate || '') + '")' : '') +
      (r.items[0] ? ' | نمونه: ' + r.items[0].title : '');
  });
  log_(ss, 'INFO', 'testFeeds\n' + report.join('\n'));
  return report;
}

function testEmail() {
  var cfg = getConfig_();
  MailApp.sendEmail({
    to: cfg.notifyEmail,
    subject: '[سفرمی] ایمیل آزمایشی اتوماسیون خبر',
    htmlBody: '<div dir="rtl" style="font-family:Tahoma">اتصال ایمیل درست کار می‌کند. سهمیه باقی‌مانده امروز: ' +
      MailApp.getRemainingDailyQuota() + '</div>'
  });
  Logger.log('ایمیل آزمایشی به ' + cfg.notifyEmail + ' ارسال شد');
}

function testGemini() {
  var cfg = getConfig_();
  var item = {
    title: 'Test: Turkish Airlines adds a daily Tehran–Istanbul flight from December',
    link: 'https://example.com/test', feedTitle: 'Test Source', published: new Date(),
    summary: 'This is a connectivity test. Turkish Airlines said it will add one more daily flight between Tehran and Istanbul starting December 1.',
    categories: ['Airlines']
  };
  var r = callGemini_(cfg, buildPrompt_(item, ''), new Date());
  Logger.log(r.ok ? JSON.stringify(r.data, null, 2) : 'خطا: ' + r.error);
  Logger.log('فراخوانی‌های امروز: ' + geminiCallsToday_(new Date()) + ' از ' + cfg.maxGeminiCallsPerDay);
  return r;
}

/** بدون Gemini و بدون ساخت پیش‌نویس؛ فقط نشان می‌دهد چه خبرهایی انتخاب می‌شوند. */
function dryRun() {
  return runPipeline_({ dryRun: true });
}

function runNow() {
  return runPipeline_({ dryRun: false });
}

/** تابعی که تریگر ساعتی صدا می‌زند. */
function hourlyJob() {
  return runPipeline_({ dryRun: false });
}

function installHourlyTrigger() {
  removeTriggers();
  ScriptApp.newTrigger('hourlyJob').timeBased().everyHours(1).create();
  Logger.log('تریگر ساعتی hourlyJob فعال شد');
}

function removeTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'hourlyJob') ScriptApp.deleteTrigger(t);
  });
}

function runPipeline_(opts) {
  var started = Date.now();
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) {
    Logger.log('اجرای قبلی هنوز تمام نشده؛ این نوبت رد شد');
    return null;
  }
  var cfg = getConfig_();
  var ss = null;
  var stats = { sources: 0, sourceErrors: 0, items: 0, candidates: 0, geminiCalls: 0, drafts: 0, modelRejected: 0, errors: 0 };
  try {
    requireConfig_(cfg);
    ss = openSpreadsheet_(cfg);
    var now = new Date();
    var seen = loadSeen_(ss);
    var sources = loadSources_(ss, cfg);
    var all = [];

    sources.forEach(function (src) {
      if (Date.now() - started > DEFAULTS.MAX_RUNTIME_MS / 3) return;
      stats.sources++;
      var r = fetchFeed_(src.url);
      updateSourceStatus_(ss, src, r.ok ? 'OK' : 'FAIL: ' + r.error, r.items.length, now);
      if (!r.ok) { stats.sourceErrors++; log_(ss, 'WARN', 'منبع ' + src.name + ': ' + r.error); return; }
      r.items.forEach(function (it) { if (!it.feedTitle || it.feedTitle.length > 60) it.feedTitle = src.name; });
      all = all.concat(r.items);
    });
    stats.items = all.length;

    var sel = selectCandidates_(all, seen, cfg, now);
    stats.candidates = sel.candidates.length;

    var seenRows = [];
    sel.rejected.forEach(function (it) {
      if (it.rejectReason.indexOf('قبلا بررسی') < 0 && !seen.urls[it.key]) {
        seen.urls[it.key] = true;
        seenRows.push([it.key, it.title, now, it.rejectReason]);
      }
    });

    if (opts.dryRun) {
      // در dryRun چیزی به سابقه اضافه نمی‌شود
      var lines = sel.candidates.slice(0, 20).map(function (c) {
        return '[' + c.keywordScore + '] ' + c.title + ' | ' + c.feedTitle + ' | ' + c.keywordHits.join(',');
      });
      log_(ss, 'INFO', 'dryRun: ' + sel.candidates.length + ' نامزد از ' + all.length + ' آیتم\n' + lines.join('\n'));
      return { stats: stats, candidates: sel.candidates, rejected: sel.rejected };
    }

    var ssUrl = ss.getUrl();
    for (var i = 0; i < sel.candidates.length && stats.drafts < cfg.maxDraftsPerRun; i++) {
      if (Date.now() - started > DEFAULTS.MAX_RUNTIME_MS) { log_(ss, 'WARN', 'زمان اجرا به سقف رسید'); break; }
      if (!hasGeminiQuota_(cfg, now)) { log_(ss, 'WARN', 'سقف روزانه Gemini (' + cfg.maxGeminiCallsPerDay + ') پر شد'); break; }
      var item = sel.candidates[i];
      var text = cfg.fetchFullArticle ? fetchArticleText_(item.link, DEFAULTS.ARTICLE_CHAR_LIMIT) : '';
      var g = callGemini_(cfg, buildPrompt_(item, text), now);
      stats.geminiCalls++;
      if (!g.ok) {
        stats.errors++;
        log_(ss, 'ERROR', item.title + ' | ' + g.error);
        if (g.quotaExceeded) break;
        continue; // سابقه ثبت نمی‌شود تا ساعت بعد دوباره تلاش شود
      }
      var a = g.data;
      var reject = acceptArticle_(a);
      if (reject) {
        stats.modelRejected++;
        seenRows.push([item.key, item.title, now, reject]);
        continue;
      }
      var doc = createDraftDoc_(cfg, a, item);
      var html = buildArticleHtml_(a, item);
      var cms = pushToCms_(cfg, a, item, html);
      appendQueue_(ss, [now, 'pending', a.title_fa, doc.url, item.feedTitle, item.link, item.published,
        a.news_type, a.category, item.keywordScore, a.confidence, cms, a.slug_en, html]);
      seenRows.push([item.key, item.title, now, 'draft']);
      sendDraftEmail_(cfg, a, item, doc, cms, ssUrl);
      stats.drafts++;
    }

    appendSeen_(ss, seenRows);
    pruneSeen_(ss, now);
    log_(ss, 'INFO', 'اجرا تمام شد ' + JSON.stringify(stats) + ' | ' + Math.round((Date.now() - started) / 1000) + 's');
    return { stats: stats };
  } catch (e) {
    var msg = 'خطای اجرا: ' + (e && e.stack || e);
    log_(ss, 'ERROR', msg);
    notifyErrorThrottled_(cfg, msg);
    throw e;
  } finally {
    lock.releaseLock();
  }
}

/** حداکثر یک ایمیل خطا در هر ۶ ساعت. */
function notifyErrorThrottled_(cfg, msg) {
  var props = getProps_();
  var last = Number(props.getProperty('LAST_ERROR_EMAIL') || 0);
  if (Date.now() - last < 6 * 3600000) return;
  props.setProperty('LAST_ERROR_EMAIL', String(Date.now()));
  try { sendErrorEmail_(cfg, msg); } catch (e) { Logger.log('ارسال ایمیل خطا ناموفق: ' + e); }
}
