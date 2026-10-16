/* Service worker: shows the daily "time to trade" notification, even when the site is closed. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));

self.addEventListener('push', event => {
    let data = {};
    try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data ? event.data.text() : '' }; }
    const title = data.title || 'Time to trade';
    event.waitUntil(self.registration.showNotification(title, {
        body: data.body || 'A new trading day is open. Follow your plan.',
        icon: 'assets/tanishq-logo.webp',
        badge: 'assets/tanishq-logo.webp',
        tag: 'daily-trade-reminder',
        data: { url: data.url || '/hub' },
    }));
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    const target = new URL((event.notification.data && event.notification.data.url) || '/hub', self.location.origin).href;
    event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
        for (const client of list) {
            if (client.url.startsWith(self.location.origin) && 'focus' in client) { client.navigate(target); return client.focus(); }
        }
        return self.clients.openWindow(target);
    }));
});
