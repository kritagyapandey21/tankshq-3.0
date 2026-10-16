// Landing page behaviour: configured links, winners carousel, hero candles, assistant.
(function () {
    const cfg = window.TANIX_CONFIG || {};

    // Links from config.js
    document.querySelectorAll('[data-link]').forEach(el => { el.href = cfg[el.dataset.link] || '#'; });

    // Winners: podium cards (list comes from the admin page, or config.js as a fallback)
    TanixPerformers.load().then(data => {
        const winners = TanixPerformers.render(document.getElementById('winCards'), data.performers);
        const month = document.getElementById('winMonth');
        if (month) month.textContent = data.month;
        if (winners[0]) {
            document.getElementById('topName').textContent = winners[0].handle;
            document.getElementById('topRoi').textContent = '+' + Number(winners[0].roi).toFixed(1) + '% ROI';
        }
    });

})();
