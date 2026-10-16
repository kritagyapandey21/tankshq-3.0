// Shared effects: falling money background and the TANIX assistant chatbot.
(function () {
    const isLogin = document.body.dataset.page === 'login';
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ---- Falling money ----
    let rain = document.getElementById('moneyRain');
    if (!rain) {
        rain = document.createElement('canvas');
        rain.id = 'moneyRain';
        rain.setAttribute('aria-hidden', 'true');
        (document.getElementById('loginScreen') || document.body).prepend(rain);
    }
    const rctx = rain.getContext('2d');
    const symbols = ['$', '$', '$', '\u20B9', '\u20AC', '$'];
    let drops = [];
    function sizeRain() {
        rain.width = window.innerWidth;
        rain.height = window.innerHeight;
        const count = window.innerWidth < 700 ? 14 : 30;
        drops = Array.from({ length: count }, () => ({
            x: Math.random() * rain.width, y: Math.random() * rain.height,
            size: Math.random() * 16 + 14, v: Math.random() * 1.2 + 0.6,
            sway: Math.random() * Math.PI * 2, s: symbols[Math.floor(Math.random() * symbols.length)],
            a: Math.random() * 0.3 + 0.12,
        })).map(d => (d.font = '700 ' + d.size + 'px Manrope, sans-serif', d));
    }
    function rainFrame() {
        if (document.hidden) { requestAnimationFrame(rainFrame); return; }
        rctx.clearRect(0, 0, rain.width, rain.height);
        drops.forEach(d => {
            rctx.font = d.font;
            rctx.fillStyle = 'rgba(212,175,55,' + d.a + ')';
            rctx.fillText(d.s, d.x + Math.sin(d.sway) * 10, d.y);
            if (!reduceMotion) { d.y += d.v; d.sway += 0.02; }
            if (d.y > rain.height + 30) { d.y = -30; d.x = Math.random() * rain.width; }
        });
        requestAnimationFrame(rainFrame);
    }
    sizeRain();
    rainFrame();
    window.addEventListener('resize', sizeRain);

    // ---- Assistant (landing and login only) ----
    if (isLogin || document.getElementById('bot')) {
        if (!document.getElementById('bot')) {
            const wrap = document.createElement('div');
            wrap.innerHTML =
                '<button class="bot-fab" id="botFab" type="button" aria-label="Open TANIX assistant" aria-expanded="false"><i class="fa-solid fa-robot"></i></button>' +
                '<div class="glass bot" id="bot" role="dialog" aria-label="TANIX AI Assistant">' +
                '<div class="bot-head"><span><i class="fa-solid fa-robot"></i> TANIX AI Assistant</span><button type="button" id="botClose" aria-label="Close assistant"><i class="fa-solid fa-xmark"></i></button></div>' +
                '<div class="bot-log" id="botLog"><div class="msg">Hello! I\'m the TANIX AI assistant. Ask me about access, the money guide or the Telegram channel.</div></div>' +
                '<form class="bot-form" id="botForm"><input id="botInput" type="text" placeholder="Ask a question..." autocomplete="off" aria-label="Your question"><button type="submit" aria-label="Send"><i class="fa-solid fa-paper-plane"></i></button></form></div>';
            while (wrap.firstChild) document.body.appendChild(wrap.firstChild);
        }
        const bot = document.getElementById('bot'), fab = document.getElementById('botFab');
        function toggleBot(open) {
            bot.classList.toggle('open', open);
            fab.setAttribute('aria-expanded', String(open));
            if (open) document.getElementById('botInput').focus();
        }
        fab.addEventListener('click', () => toggleBot(!bot.classList.contains('open')));
        document.getElementById('botClose').addEventListener('click', () => toggleBot(false));
        const ask = document.getElementById('askBot');
        if (ask) ask.addEventListener('click', () => toggleBot(true));
        function addMsg(text, me) {
            const log = document.getElementById('botLog');
            const m = document.createElement('div');
            m.className = 'msg' + (me ? ' me' : '');
            m.textContent = text;
            log.appendChild(m);
            log.scrollTop = log.scrollHeight;
        }
        document.getElementById('botForm').addEventListener('submit', e => {
            e.preventDefault();
            const input = document.getElementById('botInput');
            const q = input.value.trim();
            if (!q) return;
            addMsg(q, true);
            input.value = '';
            const t = q.toLowerCase();
            let reply = 'TANIX AI 3.0 combines RSI, EMA and MACD on live candles to give BUY / SELL signals. Join our Telegram channel for updates!';
            if (/access|register|login|log in|sign|trader id|id/.test(t)) {
                reply = isLogin
                    ? "Enter your verified Trader ID, pick your time zone and press INITIALIZE ACCESS. You'll land in your member hub."
                    : "Press 'Get Private Access', then log in with your verified Trader ID. You'll land in your member hub.";
            } else if (/zone|time/.test(t)) {
                reply = 'Choose your time zone on the login form. Signal times are shown in that zone.';
            } else if (/guide|money|risk|pdf/.test(t)) {
                reply = 'The Money Management Guide is in your member hub after login \u2014 it includes a position size calculator.';
            } else if (/telegram|channel/.test(t)) {
                reply = 'Your member hub has a Join Telegram card that opens our channel.';
            }
            setTimeout(() => addMsg(reply, false), 400);
        });

    }
})();
