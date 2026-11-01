/**
 * فضای ذخیره: یک Google Sheet با چهار برگه.
 *   Sources : منابع RSS (قابل ویرایش)
 *   Queue   : صف پیش‌نویس‌ها برای بررسی و انتشار دستی
 *   Seen    : سابقه لینک‌های بررسی‌شده برای جلوگیری از تکرار
 *   Log     : گزارش هر اجرا
 */

var SHEETS = {
  Sources: ['enabled', 'name', 'url', 'type', 'last_status', 'last_checked', 'last_items'],
  Queue: ['created_at', 'status', 'title_fa', 'doc_url', 'source', 'source_url', 'published_at',
    'news_type', 'category', 'keyword_score', 'confidence', 'cms_result', 'slug_en', 'html'],
  Seen: ['key', 'title', 'first_seen', 'decision'],
  Log: ['time', 'level', 'message']
};

function openSpreadsheet_(cfg) {
  return SpreadsheetApp.openById(cfg.spreadsheetId);
}

function ensureSheets_(ss) {
  Object.keys(SHEETS).forEach(function (name) {
    var sh = ss.getSheetByName(name) || ss.insertSheet(name);
    if (sh.getLastRow() === 0) {
      sh.appendRow(SHEETS[name]);
      sh.setFrozenRows(1);
    }
  });
  var first = ss.getSheets()[0];
  if (first && first.getName() === 'Sheet1' && first.getLastRow() === 0 && ss.getSheets().length > 1) {
    ss.deleteSheet(first);
  }
}

function seedSources_(ss) {
  var sh = ss.getSheetByName('Sources');
  if (sh.getLastRow() > 1) return;
  DEFAULT_SOURCES.forEach(function (s) { sh.appendRow([true, s[0], s[1], s[2], '', '', '']); });
}

/** @return {Array<{row:number,name:string,url:string,type:string}>} */
function loadSources_(ss, cfg) {
  if (cfg.rssFeeds.length) {
    return cfg.rssFeeds.map(function (u) { return { row: 0, name: u.replace(/^https?:\/\/(www\.)?/, '').split('/')[0], url: u, type: 'custom' }; });
  }
  var sh = ss.getSheetByName('Sources');
  var rows = sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues() : [];
  var out = [];
  rows.forEach(function (r, i) {
    var enabled = r[0] === true || String(r[0]).toLowerCase() === 'true';
    if (enabled && /^https?:\/\//.test(String(r[2]))) out.push({ row: i + 2, name: String(r[1]), url: String(r[2]).trim(), type: String(r[3]) });
  });
  return out;
}

function updateSourceStatus_(ss, source, status, count, now) {
  if (!source.row) return;
  ss.getSheetByName('Sources').getRange(source.row, 5, 1, 3).setValues([[status, now, count]]);
}

/** @return {{urls:Object, titles:Array<string>}} */
function loadSeen_(ss) {
  var sh = ss.getSheetByName('Seen');
  var n = sh.getLastRow() - 1;
  var urls = {}, titles = [];
  if (n > 0) {
    sh.getRange(2, 1, n, 4).getValues().forEach(function (r) {
      urls[String(r[0])] = true;
      // فقط عنوان خبرهایی که پیش‌نویس شده‌اند مبنای تشخیص «خبر مشابه» است؛
      // وگرنه یک تکراریِ ردشده می‌تواند جلوی نسخه اصلی را بگیرد.
      if (r[1] && r[3] === 'draft') titles.push(String(r[1]));
    });
  }
  return { urls: urls, titles: titles.slice(-400) };
}

function appendSeen_(ss, rows) {
  if (!rows.length) return;
  var sh = ss.getSheetByName('Seen');
  sh.getRange(sh.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
}

/** حذف سوابق قدیمی‌تر از SEEN_RETENTION_DAYS تا شیت سنگین نشود. */
function pruneSeen_(ss, now) {
  var sh = ss.getSheetByName('Seen');
  var n = sh.getLastRow() - 1;
  if (n < 2000) return;
  var cutoff = now.getTime() - DEFAULTS.SEEN_RETENTION_DAYS * 86400000;
  var values = sh.getRange(2, 1, n, 4).getValues();
  var keep = values.filter(function (r) { return new Date(r[2]).getTime() >= cutoff; });
  if (keep.length === values.length) return;
  sh.getRange(2, 1, n, 4).clearContent();
  if (keep.length) sh.getRange(2, 1, keep.length, 4).setValues(keep);
}

function appendQueue_(ss, row) {
  ss.getSheetByName('Queue').appendRow(row);
}

function log_(ss, level, message) {
  Logger.log(level + ': ' + message);
  try {
    if (ss) ss.getSheetByName('Log').appendRow([new Date(), level, String(message).slice(0, 5000)]);
  } catch (e) { /* لاگ نباید اجرای اصلی را متوقف کند */ }
}
