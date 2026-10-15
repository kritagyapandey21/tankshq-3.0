// Landing page behaviour: configured links, winners carousel, hero candles, assistant.
(function () {
    const cfg = window.TANIX_CONFIG || {};

    // Links from config.js
    document.querySelectorAll('[data-link]').forEach(el => { el.href = cfg[el.dataset.link] || '#'; });

    // Winners: giveaway-style podium cards (2nd, 1st, 3rd)
    const winners = [...(cfg.performers || [])].sort((a, b) => b.roi - a.roi).slice(0, 3);
    const wrap = document.getElementById('winCards');
    const places = ['1st', '2nd', '3rd'];
    [1, 0, 2].forEach(i => {
        const w = winners[i];
        if (!w) return;
        const c = document.createElement('div');
        c.className = 'glass win-card p' + (i + 1);
        const parts = [];
        if (i === 0) parts.push(['span', 'crown', '\u265B']);
        parts.push(['div', 'medal', '']);
        parts.push(['div', 'place', places[i] + ' place']);
        parts.push(['div', 'nm', w.handle]);
        parts.push(['div', 'st', w.strategy || '']);
        parts.push(['div', 'rr', '+' + Number(w.roi).toFixed(1) + '%']);
        parts.forEach(([tag, cls, text]) => { const e = document.createElement(tag); e.className = cls; e.textContent = text; c.appendChild(e); });
        // avatar photo: config `photo` if given, otherwise a generated portrait; falls back to the initial
        const medal = c.querySelector('.medal');
        const initial = w.handle.replace('@', '').charAt(0).toUpperCase();
        medal.textContent = initial;
        const img = new Image();
        img.alt = w.handle;
        img.src = w.photo || 'https://api.dicebear.com/7.x/avataaars/svg?backgroundColor=1c1c1c&seed=' + encodeURIComponent(w.handle);
        img.onload = () => { medal.textContent = ''; medal.classList.add('has-photo'); medal.appendChild(img); };
        const small = document.createElement('small');
        small.textContent = 'ROI';
        c.querySelector('.rr').appendChild(small);
        wrap.appendChild(c);
    });
    if (winners[0]) {
        document.getElementById('topName').textContent = winners[0].handle;
        document.getElementById('topRoi').textContent = '+' + Number(winners[0].roi).toFixed(1) + '% ROI';
    }

})();
