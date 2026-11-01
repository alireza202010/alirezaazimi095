/** ایمیل اطلاع‌رسانی: برای هر پیش‌نویس یک ایمیل جدا. */

function sendDraftEmail_(cfg, a, item, doc, cmsResult, spreadsheetUrl) {
  var typeFa = NEWS_TYPE_FA[a.news_type] || a.news_type;
  var subject = '[سفرمی | پیش‌نویس خبر] ' + a.title_fa;
  var cmsLine = /^ok/.test(cmsResult)
    ? '<p>در پنل سفرمی هم به‌صورت پیش‌نویس ثبت شد. ' + escapeHtml_(cmsResult.replace(/^ok\s*/, '')) + '</p>'
    : '';
  var warn = a.news_type === 'rumor'
    ? '<p style="color:#b45309"><strong>هشدار:</strong> منبع این خبر را تاییدنشده گزارش کرده است.</p>' : '';
  var verify = a.verify_fa.length
    ? '<p><strong>قبل از انتشار بررسی کنید:</strong></p><ul>' +
      a.verify_fa.map(function (v) { return '<li>' + escapeHtml_(v) + '</li>'; }).join('') + '</ul>'
    : '';
  var html = [
    '<div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;line-height:1.9;font-size:14px">',
    '<h2 style="margin:0 0 8px">' + escapeHtml_(a.title_fa) + '</h2>',
    '<p>' + escapeHtml_(a.lead_fa) + '</p>',
    warn,
    '<p>نوع: ' + escapeHtml_(typeFa) + ' | دسته: ' + escapeHtml_(a.category) +
      ' | اطمینان مدل: ' + Math.round(a.confidence * 100) + '٪</p>',
    '<p><a href="' + escapeHtml_(doc.url) + '">باز کردن پیش‌نویس (Google Doc)</a></p>',
    '<p>منبع اصلی: <a href="' + escapeHtml_(item.link) + '">' + escapeHtml_(item.feedTitle || item.link) + '</a></p>',
    cmsLine,
    verify,
    '<p><a href="' + escapeHtml_(spreadsheetUrl) + '">صف پیش‌نویس‌ها (شیت Queue)</a></p>',
    '<p style="color:#6b7280;font-size:12px">انتشار نهایی با شماست. این ایمیل را اتوماسیون خبر سفرمی (Google Apps Script) ارسال کرده است.</p>',
    '</div>'
  ].join('');
  MailApp.sendEmail({ to: cfg.notifyEmail, subject: subject, htmlBody: html, name: 'اتوماسیون خبر سفرمی' });
}

function sendErrorEmail_(cfg, message) {
  if (!cfg.notifyEmail) return;
  MailApp.sendEmail({
    to: cfg.notifyEmail,
    subject: '[سفرمی | خطای اتوماسیون خبر]',
    htmlBody: '<div dir="rtl" style="font-family:Tahoma,Arial,sans-serif">' + escapeHtml_(message) + '</div>',
    name: 'اتوماسیون خبر سفرمی'
  });
}
