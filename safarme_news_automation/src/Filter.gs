/**
 * قوانین محتوا قبل از هر فراخوانی Gemini:
 * تکراری، قدیمی، نامرتبط، طنز/تبلیغاتی => کنار گذاشته می‌شود.
 */

/** کلید یکتا برای تشخیص تکرار: لینک نرمال‌شده. */
function normalizeUrl_(url) {
  var u = String(url || '').trim();
  u = u.replace(/#.*$/, '');
  // حذف پارامترهای ردیابی
  u = u.replace(/([?&])(utm_[^=&]+|fbclid|gclid|mc_cid|mc_eid|ref|cmpid|ito)=[^&]*/gi, '$1')
    .replace(/[?&]+$/, '').replace(/\?&+/, '?').replace(/&&+/g, '&');
  u = u.replace(/^http:\/\//i, 'https://').replace(/^https:\/\/www\./i, 'https://');
  u = u.replace(/\/+$/, '');
  return u.toLowerCase();
}

/** کلید دوم برای تشخیص یک خبر واحد که چند رسانه با عنوان مشابه منتشر کرده‌اند. */
function titleKey_(title) {
  var stop = { the: 1, a: 1, an: 1, of: 1, to: 1, in: 1, on: 1, for: 1, and: 1, with: 1, at: 1, by: 1,
    from: 1, is: 1, are: 1, as: 1, its: 1, new: 1, after: 1, will: 1 };
  var words = String(title || '').toLowerCase()
    .replace(/[^a-z0-9À-ɏ؀-ۿ\s]/g, ' ')
    .split(/\s+/)
    .filter(function (w) { return w && !stop[w] && w.length > 2; });
  var uniq = [];
  words.forEach(function (w) { if (uniq.indexOf(w) < 0) uniq.push(w); });
  return uniq.sort().slice(0, 8).join(' ');
}

/** شباهت Jaccard دو عنوان؛ بالای ۰.۶ یعنی احتمالا یک خبرند. */
function titleSimilarity_(a, b) {
  var A = titleKey_(a).split(' ').filter(String);
  var B = titleKey_(b).split(' ').filter(String);
  if (!A.length || !B.length) return 0;
  var inter = A.filter(function (w) { return B.indexOf(w) >= 0; }).length;
  return inter / (A.length + B.length - inter);
}

function isBlocked_(item) {
  var text = [item.title, item.summary, (item.categories || []).join(' '), item.link].join(' ');
  for (var i = 0; i < BLOCK_PATTERNS.length; i++) {
    if (BLOCK_PATTERNS[i].test(text)) return String(BLOCK_PATTERNS[i]);
  }
  return '';
}

/**
 * امتیاز ارتباط بر اساس سه گروه کلیدواژه؛ عنوان وزن دو برابر دارد.
 * @return {{score:number, geo:number, reg:number, topic:number, hits:Array<string>, gated:boolean}}
 */
function keywordScore_(item) {
  var title = ' ' + String(item.title || '').toLowerCase() + ' ';
  var body = ' ' + [item.summary, (item.categories || []).join(' ')].join(' ').toLowerCase().slice(0, 3000) + ' ';
  var hits = [];
  function scoreGroup(group) {
    var total = 0;
    Object.keys(group).forEach(function (kw) {
      var re = new RegExp('(^|[^a-z0-9\u00c0-\u024f])' + kw.replace(/[.*+?^${}()|[\]\\\/]/g, '\\$&') + '(?=$|[^a-z0-9\u00c0-\u024f])', 'i');
      if (re.test(title)) { total += group[kw] * 2; hits.push(kw); }
      else if (re.test(body)) { total += group[kw]; hits.push(kw); }
    });
    return total;
  }
  var geo = scoreGroup(GEO_KEYWORDS);
  var reg = scoreGroup(REG_KEYWORDS);
  var topic = Math.min(scoreGroup(TOPIC_KEYWORDS), 6); // کلمات عمومی نباید امتیاز را باد کنند
  return { score: geo + reg + topic, geo: geo, reg: reg, topic: topic, hits: hits, gated: geo >= 2 || reg >= 3 };
}

function isFresh_(item, maxAgeHours, now) {
  if (!item.published) return false; // خبر بدون تاریخ قابل اعتماد نیست
  var age = (now.getTime() - item.published.getTime()) / 3600000;
  return age <= maxAgeHours && age > -6; // تاریخ آینده (بیش از ۶ ساعت) مشکوک است
}

/**
 * لیست خبرها را فیلتر و رتبه‌بندی می‌کند.
 * @param items خروجی parseFeed_
 * @param seen  {urls:Object, titles:Array<string>} سابقه پردازش‌شده‌ها
 * @return {{candidates:Array, rejected:Array}}
 */
function selectCandidates_(items, seen, cfg, now) {
  var candidates = [], rejected = [];
  var batchTitles = [];
  items.forEach(function (item) {
    var key = normalizeUrl_(item.link);
    item.key = key;
    var reason = '';
    if (seen.urls[key]) reason = 'تکراری (قبلا بررسی شده)';
    else if (!isFresh_(item, cfg.maxItemAgeHours, now)) reason = 'قدیمی یا بدون تاریخ';
    else {
      var blocked = isBlocked_(item);
      if (blocked) reason = 'طنز/تبلیغاتی/نامرتبط: ' + blocked;
    }
    if (!reason) {
      var allTitles = seen.titles.concat(batchTitles);
      for (var i = 0; i < allTitles.length; i++) {
        if (titleSimilarity_(item.title, allTitles[i]) >= 0.6) { reason = 'تکراری (خبر مشابه از منبع دیگر)'; break; }
      }
    }
    if (!reason) {
      var ks = keywordScore_(item);
      item.keywordScore = ks.score;
      item.keywordHits = ks.hits;
      item.keywordGeo = ks.geo;
      item.keywordReg = ks.reg;
      if (!ks.gated) reason = 'نامرتبط (بدون مقصد یا مقررات مرتبط)';
      else if (ks.score < cfg.minKeywordScore) reason = 'نامرتبط (امتیاز کلیدواژه ' + ks.score + ')';
    }
    if (reason) {
      item.rejectReason = reason;
      rejected.push(item);
    } else {
      batchTitles.push(item.title);
      candidates.push(item);
    }
  });
  candidates.sort(function (a, b) {
    return (b.keywordScore - a.keywordScore) || (b.published - a.published);
  });
  return { candidates: candidates, rejected: rejected };
}
