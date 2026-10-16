/* Shared member-area footer (hub + guide). Links come from config.js. */
(function () {
    var cfg = window.TANIX_CONFIG || {};
    var el = document.querySelector('footer.site-footer[data-site-footer]');
    if (!el) return;
    var ICON = {
        telegram: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.5 4.3L2.9 11.5c-.8.3-.8 1.3 0 1.6l4.6 1.5 1.8 5.6c.2.6 1 .8 1.4.3l2.6-2.6 4.8 3.5c.6.4 1.3.1 1.5-.6l3.2-15.3c.2-.9-.7-1.6-1.3-1.2zM9.4 14.2l9-6.3-7.2 7.6-.3 3.1-1.5-4.4z" fill="currentColor"/></svg>',
        youtube: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 8.2a3 3 0 0 0-2.1-2.1C18 5.6 12 5.6 12 5.6s-6 0-7.9.5A3 3 0 0 0 2 8.2C1.5 10 1.5 12 1.5 12s0 2 .5 3.8a3 3 0 0 0 2.1 2.1c1.9.5 7.9.5 7.9.5s6 0 7.9-.5a3 3 0 0 0 2.1-2.1c.5-1.8.5-3.8.5-3.8s0-2-.5-3.8zM10 15V9l5.2 3z" fill="currentColor"/></svg>',
        instagram: '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.3" cy="6.7" r="1" fill="currentColor" stroke="none"/></svg>'
    };
    function social(key, url, label) {
        return '<a href="' + (url || '#') + '" target="_blank" rel="noopener noreferrer" aria-label="' + label + '">' + ICON[key] + '</a>';
    }
    el.innerHTML =
        '<div class="container sf-wrap">' +
          '<div class="sf-top">' +
            '<div class="sf-brand">' +
              '<img src="assets/tanishq-logo.webp" alt="" width="44" height="44">' +
              '<div><b>LEARN WITH <span>TANISHQ</span></b><small>Your gateway to intelligent markets</small></div>' +
            '</div>' +
            '<nav class="sf-links" aria-label="Footer">' +
              '<a href="./">Home</a><a href="hub">Member hub</a><a href="tanix">Signal terminal</a><a href="guide">Money guide</a>' +
            '</nav>' +
            '<div class="sf-social">' +
              social('telegram', cfg.telegramUrl, 'Telegram') + social('youtube', cfg.youtubeUrl, 'YouTube') + social('instagram', cfg.instagramUrl, 'Instagram') +
            '</div>' +
          '</div>' +
          '<p class="risk">Trading involves substantial risk and can result in the loss of your invested capital. Signals are informational, not financial advice. Past results do not guarantee future performance.</p>' +
          '<div class="sf-bottom"><span>\u00a9 2026 Learn With Tanishq. All rights reserved.</span><span>Secure session</span></div>' +
        '</div>';
})();
