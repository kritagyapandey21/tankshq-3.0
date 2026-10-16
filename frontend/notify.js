// After login: a popup that offers the daily trading reminder (browser notifications).
(function () {
    'use strict';
    const popup = document.getElementById('notifPopup');
    if (!popup) return;
    const card = popup.querySelector('.notif-card');
    const msgEl = document.getElementById('notifMessage');
    const titleEl = document.getElementById('notifTitle');
    const subEl = popup.querySelector('.notif-sub');
    const helpEl = document.getElementById('notifHelp');
    const onBtn = document.getElementById('notifOn');
    const laterBtn = document.getElementById('notifLater');

    const DISMISS_KEY = 'tanix_notif_popup_seen';       // per login: cleared when the tab's session ends
    const supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
    let registration = null;

    const api = (path, options) => authenticatedFetch(`${API_BASE_URL}${path}`, options);
    const postJSON = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const seen = () => { try { return sessionStorage.getItem(DISMISS_KEY) === '1'; } catch (e) { return false; } };
    const markSeen = () => { try { sessionStorage.setItem(DISMISS_KEY, '1'); } catch (e) { /* ignore */ } };

    function urlBase64ToUint8Array(b64) {
        const pad = '='.repeat((4 - (b64.length % 4)) % 4);
        const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
        return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
    }

    function open() {
        popup.hidden = false;
        document.body.style.overflow = 'hidden';
        onBtn.focus();
    }
    function close() {
        popup.hidden = true;
        document.body.style.overflow = '';
        markSeen();
    }

    // Browsers never let a page re-ask once a site is blocked, so explain how to unblock it.
    function blockedHelp() {
        const ua = navigator.userAgent;
        const where = /Firefox/i.test(ua)
            ? 'Click the <b>lock icon</b> in the address bar, open <b>Permissions</b>, find <b>Receive Notifications</b> and remove the block.'
            : (/Safari/i.test(ua) && !/Chrome|Chromium|Edg/i.test(ua))
                ? 'Open <b>Safari &gt; Settings &gt; Websites &gt; Notifications</b>, find this site and choose <b>Allow</b>.'
                : 'Click the <b>lock / settings icon</b> at the left of the address bar, open <b>Site settings</b>, and set <b>Notifications</b> to <b>Allow</b>.';
        return 'Notifications are blocked for this site. ' + where + ' Once you allow it, the Turn on button comes back.';
    }
    function showBlocked() {
        helpEl.innerHTML = blockedHelp();
        helpEl.hidden = false;
        onBtn.hidden = true;
        laterBtn.textContent = 'Close';
    }

    async function finish() {
        titleEl.textContent = "You're all set";
        subEl.textContent = 'Your daily trading reminder is on. See you tomorrow, Trader.';
        card.classList.add('is-done');
        markSeen();
        setTimeout(close, 1800);
    }

    async function turnOn() {
        onBtn.disabled = true;
        try {
            const permission = await Notification.requestPermission();
            if (permission === 'denied') return showBlocked();
            if (permission !== 'granted') return;                     // dismissed the browser prompt: leave the popup open
            const keyRes = await api('/push/public-key');
            const { publicKey } = await keyRes.json();
            const sub = (await registration.pushManager.getSubscription()) || await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(publicKey),
            });
            const res = await postJSON('/push/subscribe', sub.toJSON());
            if (!res.ok) throw new Error('subscribe failed');
            await finish();
        } catch (e) {
            helpEl.textContent = 'Could not turn on notifications. Please try again.';
            helpEl.hidden = false;
        } finally {
            onBtn.disabled = false;
        }
    }

    async function init() {
        if (seen()) return;
        let message = '';
        try {
            const res = await api('/notifications/today');
            if (res.ok) message = (await res.json()).body || '';
        } catch (e) { return; }                                         // offline: skip the popup
        if (!message) return;

        if (!supported) return;                                         // nothing to offer on this browser
        try { registration = await navigator.serviceWorker.register('sw.js'); } catch (e) { return; }

        const sub = await registration.pushManager.getSubscription();
        if (sub && Notification.permission === 'granted') {
            postJSON('/push/subscribe', sub.toJSON()).catch(() => {});  // keep the server's copy tied to this trader
            return;                                                     // already on: no popup
        }

        msgEl.textContent = message;
        if (Notification.permission === 'denied') showBlocked();
        open();

        onBtn.addEventListener('click', turnOn);
        laterBtn.addEventListener('click', close);
        popup.addEventListener('click', e => { if (e.target === popup) close(); });
        document.addEventListener('keydown', e => { if (e.key === 'Escape' && !popup.hidden) close(); });
        if (navigator.permissions && navigator.permissions.query) {
            navigator.permissions.query({ name: 'notifications' }).then(p => {
                p.onchange = () => { if (Notification.permission === 'granted' && !popup.hidden) { helpEl.hidden = true; onBtn.hidden = false; laterBtn.textContent = 'Not now'; } };
            }).catch(() => {});
        }
    }

    document.addEventListener('aurox:ready', init);
})();
