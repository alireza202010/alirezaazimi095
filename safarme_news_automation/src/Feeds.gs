/**
 * دریافت و پارس RSS 2.0 و Atom. پارسر عمدا بدون XmlService نوشته شده تا
 * فیدهای کمی خراب (که در خبرگزاری‌ها رایج است) هم خوانده شوند و منطق آن خارج از گوگل قابل تست باشد.
 */

var FEED_FETCH_OPTIONS = {
  muteHttpExceptions: true,
  followRedirects: true,
  headers: {
    'User-Agent': 'Mozilla/5.0 (compatible; SafarmeNewsBot/1.0; +https://safarme.ir)',
    'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5'
  }
};

/** @return {{ok:boolean, status:number, items:Array, error:string, isFeed:boolean}} */
function fetchFeed_(url) {
  var res;
  try {
    res = UrlFetchApp.fetch(url, FEED_FETCH_OPTIONS);
  } catch (e) {
    return { ok: false, status: 0, items: [], isFeed: false, error: String(e && e.message || e) };
  }
  var status = res.getResponseCode();
  var body = res.getContentText();
  if (status < 200 || status >= 300) {
    return { ok: false, status: status, items: [], isFeed: false, error: 'HTTP ' + status };
  }
  if (!looksLikeFeed_(body)) {
    // قانون منبع: صفحه اصلی سایت خوراک خبری نیست.
    return { ok: false, status: status, items: [], isFeed: false, error: 'پاسخ RSS/Atom نیست (احتمالا صفحه HTML است)' };
  }
  var items = parseFeed_(body, url);
  return { ok: true, status: status, items: items, isFeed: true, error: '' };
}

function looksLikeFeed_(text) {
  var head = String(text || '').slice(0, 2000).toLowerCase();
  return /<rss[\s>]|<feed[\s>]|<rdf:rdf[\s>]/.test(head);
}

function parseFeed_(xml, feedUrl) {
  xml = String(xml || '');
  var isAtom = /<feed[\s>]/i.test(xml.slice(0, 2000)) && !/<rss[\s>]/i.test(xml.slice(0, 2000));
  var blocks = matchAll_(xml, isAtom ? /<entry[\s>][\s\S]*?<\/entry>/gi : /<item[\s>][\s\S]*?<\/item>/gi);
  var feedTitle = decodeEntities_(stripCdata_(firstTag_(xml.replace(/<(item|entry)[\s>][\s\S]*$/i, ''), 'title')));
  var out = [];
  blocks.forEach(function (b) {
    var title = cleanText_(firstTag_(b, 'title'));
    var link = isAtom ? atomLink_(b) : cleanText_(firstTag_(b, 'link'));
    if (!link) link = cleanText_(firstTag_(b, 'guid'));
    var guid = cleanText_(firstTag_(b, isAtom ? 'id' : 'guid')) || link;
    var dateStr = cleanText_(firstTag_(b, 'pubDate') || firstTag_(b, 'published') ||
      firstTag_(b, 'updated') || firstTag_(b, 'dc:date'));
    var summaryRaw = firstTag_(b, 'content:encoded') || firstTag_(b, 'content') ||
      firstTag_(b, 'description') || firstTag_(b, 'summary');
    var categories = matchAll_(b, /<category\b[^>]*\/>|<category\b[^>]*>[\s\S]*?<\/category>/gi)
      .map(function (c) {
        var m = /term="([^"]*)"/i.exec(c);
        return cleanText_(m ? m[1] : c.replace(/<\/?category[^>]*>/gi, ''));
      }).filter(String);
    if (!title || !/^https?:\/\//i.test(link)) return;
    out.push({
      title: title,
      link: link.trim(),
      guid: guid,
      published: parseDate_(dateStr),
      summary: htmlToText_(stripCdata_(summaryRaw)).slice(0, 4000),
      categories: categories,
      feedTitle: feedTitle,
      feedUrl: feedUrl
    });
  });
  return out;
}

function atomLink_(block) {
  var links = matchAll_(block, /<link\b[^>]*>/gi);
  var best = '';
  links.forEach(function (l) {
    var href = (/href="([^"]+)"/i.exec(l) || [])[1];
    var rel = (/rel="([^"]+)"/i.exec(l) || [])[1] || 'alternate';
    if (href && rel === 'alternate' && !best) best = href;
  });
  if (!best && links.length) best = (/href="([^"]+)"/i.exec(links[0]) || [])[1] || '';
  return decodeEntities_(best);
}

function firstTag_(xml, tag) {
  var esc = tag.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  var re = new RegExp('<' + esc + '(?:\\s[^>]*)?>([\\s\\S]*?)<\\/' + esc + '>', 'i');
  var m = re.exec(xml);
  return m ? m[1] : '';
}

function matchAll_(text, re) {
  var out = [], m;
  re.lastIndex = 0;
  while ((m = re.exec(text)) !== null) {
    out.push(m[0]);
    if (m[0] === '') re.lastIndex++;
  }
  return out;
}

function stripCdata_(s) {
  return String(s || '').replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1');
}

function cleanText_(s) {
  return decodeEntities_(stripCdata_(s)).replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}

function decodeEntities_(s) {
  var named = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', rsquo: '’', lsquo: '‘',
    rdquo: '”', ldquo: '“', ndash: '–', mdash: '—', hellip: '…', eacute: 'é', uuml: 'ü', ouml: 'ö' };
  return String(s || '')
    .replace(/&#x([0-9a-f]+);/gi, function (_, h) { return String.fromCodePoint(parseInt(h, 16)); })
    .replace(/&#(\d+);/g, function (_, d) { return String.fromCodePoint(Number(d)); })
    .replace(/&([a-z]+);/gi, function (m, n) { return named.hasOwnProperty(n.toLowerCase()) ? named[n.toLowerCase()] : m; });
}

function htmlToText_(html) {
  var s = String(html || '')
    .replace(/<(script|style|noscript|iframe|svg|figure|figcaption|form|nav|footer|header|aside)\b[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|h[1-6]|li|blockquote|tr)>/gi, '\n')
    .replace(/<li[^>]*>/gi, '- ')
    .replace(/<[^>]+>/g, ' ');
  return decodeEntities_(s)
    .replace(/[ \t ]+/g, ' ')
    .replace(/\n\s*\n+/g, '\n\n')
    .trim();
}

function parseDate_(s) {
  if (!s) return null;
  var d = new Date(s);
  if (!isNaN(d.getTime())) return d;
  // RFC822 با نام منطقه زمانی غیراستاندارد مثل "EST" یا "+0330" بدون فاصله
  var cleaned = String(s).replace(/\s+[A-Z]{2,5}$/, ' GMT');
  d = new Date(cleaned);
  return isNaN(d.getTime()) ? null : d;
}

/**
 * متن اصلی صفحه خبر را تا حد ممکن استخراج می‌کند. اگر نشد، خلاصه RSS استفاده می‌شود.
 */
function fetchArticleText_(url, limit) {
  try {
    var res = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true, followRedirects: true,
      headers: { 'User-Agent': FEED_FETCH_OPTIONS.headers['User-Agent'], 'Accept': 'text/html' }
    });
    if (res.getResponseCode() !== 200) return '';
    return extractArticleText_(res.getContentText(), limit);
  } catch (e) {
    return '';
  }
}

function extractArticleText_(html, limit) {
  html = String(html || '');
  var scope = firstTag_(html, 'article') || firstTag_(html, 'main') || html;
  var paras = matchAll_(scope, /<p\b[^>]*>[\s\S]*?<\/p>/gi)
    .map(function (p) { return cleanText_(p); })
    .filter(function (t) {
      return t.length > 40 && !/^(read more|also read|related|subscribe|sign up|advertisement|image:|photo:|credit:)/i.test(t);
    });
  var text = paras.join('\n\n');
  return text.slice(0, limit || DEFAULTS.ARTICLE_CHAR_LIMIT);
}
