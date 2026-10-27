// رله Bot API تلگرام روی Cloudflare Workers، برای سرورهایی که به api.telegram.org دسترسی ندارند.
// بعد از deploy، آدرس worker را در TELEGRAM_API_BASE بگذارید.
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/bot")) return new Response("ok");
    const target = "https://api.telegram.org" + url.pathname + url.search;
    return fetch(new Request(target, request));
  },
};
