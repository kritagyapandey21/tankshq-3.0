// Best performers: loads the list an admin saved (falls back to config.js) and draws the podium cards.
// Used by the landing page, the member hub and the admin preview.
(function () {
    'use strict';
    const cfg = window.TANIX_CONFIG || {};
    const apiBase = () => (typeof API_BASE_URL !== 'undefined' ? API_BASE_URL : (window.API_BASE_URL || ''));

    // Uploaded photos are served by the backend; everything else (assets/..., https://...) is used as-is.
    function photoUrl(photo) {
        if (!photo) return '';
        return photo.startsWith('/uploads/') ? apiBase() + photo : photo;
    }

    async function load() {
        try {
            const ctl = new AbortController();
            const timer = setTimeout(() => ctl.abort(), 4000);
            const res = await fetch(apiBase() + '/performers', { signal: ctl.signal });
            clearTimeout(timer);
            if (res.ok) {
                const data = await res.json();
                if (data.configured && Array.isArray(data.performers) && data.performers.length) {
                    return { month: data.month || cfg.performersMonth || 'Last Month', performers: data.performers };
                }
            }
        } catch (e) { /* offline or backend down: use the built-in list */ }
        return { month: cfg.performersMonth || 'Last Month', performers: cfg.performers || [] };
    }

    // Podium order on screen: 2nd, 1st, 3rd.
    function render(container, list) {
        const winners = [...(list || [])].sort((a, b) => b.roi - a.roi).slice(0, 3);
        const places = ['1st', '2nd', '3rd'];
        container.textContent = '';
        [1, 0, 2].forEach(i => {
            const w = winners[i];
            if (!w) return;
            const card = document.createElement('div');
            card.className = 'glass win-card p' + (i + 1);
            const parts = [];
            if (i === 0) parts.push(['span', 'crown', '♛']);
            parts.push(['div', 'medal', ''], ['div', 'place', places[i] + ' place'], ['div', 'nm', w.handle],
                       ['div', 'rr', '+' + Number(w.roi).toFixed(1) + '%']);
            parts.forEach(([tag, cls, text]) => { const e = document.createElement(tag); e.className = cls; e.textContent = text; card.appendChild(e); });
            const medal = card.querySelector('.medal');
            medal.textContent = String(w.handle).replace('@', '').charAt(0).toUpperCase();
            const src = photoUrl(w.photo);
            if (src) {
                const img = new Image();
                img.alt = w.handle;
                img.decoding = 'async';
                img.onload = () => { medal.textContent = ''; medal.classList.add('has-photo'); medal.appendChild(img); };
                img.src = src;
            }
            const small = document.createElement('small');
            small.textContent = 'ROI';
            card.querySelector('.rr').appendChild(small);
            container.appendChild(card);
        });
        return winners;
    }

    window.TanixPerformers = { load, render, photoUrl };
})();
