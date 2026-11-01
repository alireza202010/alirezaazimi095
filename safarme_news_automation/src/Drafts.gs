/**
 * ساخت پیش‌نویس.
 *
 * چون مجله سفرمی وردپرس نیست، معادل «پیش‌نویس وردپرس» اینجا دو لایه است:
 *  1) همیشه: یک Google Doc راست‌چین در پوشه پیش‌نویس‌ها + یک ردیف در شیت Queue با وضعیت pending.
 *  2) اختیاری: اگر تیم فنی سفرمی یک endpoint برای ثبت پیش‌نویس بسازد (CMS_WEBHOOK_URL)،
 *     همان محتوا با status=draft به پنل سفرمی هم ارسال می‌شود. هیچ‌وقت publish نمی‌شود.
 *
 * رمز اصلی پنل سفرمی هرگز در اسکریپت ذخیره نمی‌شود.
 */

var NEWS_TYPE_FA = {
  confirmed: 'خبر تاییدشده', announcement: 'اطلاعیه رسمی', report: 'گزارش رسانه',
  rumor: 'شایعه/تاییدنشده', satire: 'طنز', opinion: 'نظر', promotional: 'تبلیغاتی'
};

function escapeHtml_(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** HTML تمیز برای کپی در ویرایشگر پنل سفرمی. */
function buildArticleHtml_(a, item) {
  var h = [];
  h.push('<h1>' + escapeHtml_(a.title_fa) + '</h1>');
  h.push('<p><strong>' + escapeHtml_(a.lead_fa) + '</strong></p>');
  a.body_fa.forEach(function (p) { h.push('<p>' + escapeHtml_(p) + '</p>'); });
  if (a.traveler_note_fa) {
    h.push('<h2>این خبر برای مسافران چه معنایی دارد؟</h2>');
    h.push('<p>' + escapeHtml_(a.traveler_note_fa) + '</p>');
  }
  h.push('<p>منبع: <a href="' + escapeHtml_(item.link) + '" rel="nofollow noopener" target="_blank">' +
    escapeHtml_(item.feedTitle || item.link) + '</a></p>');
  return h.join('\n');
}

function createDraftDoc_(cfg, a, item) {
  var title = '[پیش‌نویس] ' + a.title_fa;
  var doc = DocumentApp.create(title);
  var body = doc.getBody();
  function para(text, heading, bold) {
    var p = body.appendParagraph(text || '');
    if (heading) p.setHeading(heading);
    p.setLeftToRight(false);
    p.setAlignment(DocumentApp.HorizontalAlignment.RIGHT);
    if (bold) p.editAsText().setBold(true);
    return p;
  }
  function bullet(text) {
    var li = body.appendListItem(text);
    li.setLeftToRight(false);
    li.setAlignment(DocumentApp.HorizontalAlignment.RIGHT);
    return li;
  }

  // بلوک ویراستار (قبل از انتشار حذف شود)
  para('بلوک ویراستار، قبل از انتشار حذف شود', DocumentApp.ParagraphHeading.HEADING3);
  para('وضعیت: پیش‌نویس، منتشر نشده');
  para('نوع خبر: ' + (NEWS_TYPE_FA[a.news_type] || a.news_type) + ' | دسته: ' + a.category +
    ' | اطمینان مدل: ' + Math.round(a.confidence * 100) + '٪');
  para('عنوان سئو: ' + a.seo_title_fa);
  para('توضیح متا: ' + a.meta_description_fa);
  para('نامک (slug): ' + a.slug_en);
  para('برچسب‌ها: ' + a.tags_fa.join('، '));
  para('منبع اصلی: ' + (item.feedTitle || '') + ' | ' + item.link);
  para('تاریخ انتشار منبع: ' + (item.published ? item.published.toISOString() : 'نامعلوم'));
  if (a.verify_fa.length) {
    para('موارد نیازمند بررسی', DocumentApp.ParagraphHeading.HEADING3);
    a.verify_fa.forEach(bullet);
  }
  body.appendHorizontalRule();

  // متن خبر
  para(a.title_fa, DocumentApp.ParagraphHeading.HEADING1);
  para(a.lead_fa, null, true);
  a.body_fa.forEach(function (p) { para(p); });
  if (a.traveler_note_fa) {
    para('این خبر برای مسافران چه معنایی دارد؟', DocumentApp.ParagraphHeading.HEADING2);
    para(a.traveler_note_fa);
  }
  var src = para('منبع: ' + (item.feedTitle || item.link));
  src.editAsText().setLinkUrl(item.link);

  // حذف پاراگراف خالی پیش‌فرض اول سند
  var first = body.getChild(0);
  if (first && first.getType() === DocumentApp.ElementType.PARAGRAPH && !first.asParagraph().getText()) {
    try { body.removeChild(first); } catch (e) { /* سند حداقل یک پاراگراف لازم دارد */ }
  }
  doc.saveAndClose();

  var file = DriveApp.getFileById(doc.getId());
  file.moveTo(DriveApp.getFolderById(cfg.draftsFolderId));
  return { id: doc.getId(), url: doc.getUrl() };
}

/**
 * ارسال اختیاری به پنل سفرمی. قرارداد پیشنهادی endpoint در README آمده است.
 * @return {string} نتیجه برای ستون cms_result
 */
function pushToCms_(cfg, a, item, html) {
  if (!cfg.cmsWebhookUrl) return 'disabled';
  var payload = {
    status: 'draft',
    title: a.title_fa,
    lead: a.lead_fa,
    content_html: html,
    seo_title: a.seo_title_fa,
    meta_description: a.meta_description_fa,
    slug: a.slug_en,
    tags: a.tags_fa,
    category: a.category,
    source_url: item.link,
    source_name: item.feedTitle || '',
    source_published_at: item.published ? item.published.toISOString() : null,
    external_id: Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, item.key || item.link))
  };
  try {
    var res = UrlFetchApp.fetch(cfg.cmsWebhookUrl, {
      method: 'post',
      contentType: 'application/json',
      headers: { 'Authorization': 'Bearer ' + cfg.cmsWebhookToken },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
    var code = res.getResponseCode();
    if (code >= 200 && code < 300) {
      var body = {};
      try { body = JSON.parse(res.getContentText()); } catch (e) { /* پاسخ غیر JSON */ }
      return 'ok' + (body.edit_url ? ' ' + body.edit_url : '');
    }
    return 'error HTTP ' + code;
  } catch (e) {
    return 'error ' + (e && e.message || e);
  }
}
