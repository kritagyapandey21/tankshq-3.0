
// ── Config ─────────────────────────────────────────────────────────
const _isLocal = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
const API_BASE_URL = (_isLocal ? 'http://localhost:8000' : null)
    || window.API_BASE_URL
    || 'http://localhost:8000';
const SESSION_TOKEN_KEY = 'aurox_session_token';
const SESSION_HEARTBEAT_INTERVAL = 30_000;
let sessionHeartbeatInterval = null;
function authenticatedFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = sessionStorage.getItem(SESSION_TOKEN_KEY);
    if (token) headers.set('Authorization', `Bearer ${token}`);
    return fetch(url, { ...options, headers });
}
const TIME_SYNC_INTERVAL      = 5000;
const COUNTDOWN_TICK          = 100;
const STATS_REFRESH_INTERVAL  = 60000;
const RING_CIRCUMFERENCE      = 364;   // 2π × r=58 for confidence ring
const CRING_CIRCUMFERENCE     = 289;   // 2π × r=46 for countdown ring

// ── State ───────────────────────────────────────────────────────────
const state = {
    serverTimeOffset:  0,
    currentSignal:     null,
    activePairs:       [],
    correlations:      { nodes: [], links: [] },
    signalHistory:     JSON.parse(localStorage.getItem('auroxSignalHistory') || '[]'),
    countdownInterval: null,
    timeSyncInterval:  null,
    statsInterval:     null,
    displayInterval:   null,   // FIX: was never stored/cleaned
    neuralStatusInterval: null,
    loginClockInterval: null,
    timezone:          'Asia/Kolkata',
    timezoneExplicit:  false,
    timezoneCatalog:   [],
};

// ── DOM refs ────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const signalBtn       = $('signalBtn');
const refreshTimeBtn  = $('refreshTimeBtn');
const signalDisplay   = $('signalDisplay');
const errorDisplay    = $('errorDisplay');
const serverTimeEl    = $('serverTime');
const statusDot       = $('statusDot');
const statusText      = $('statusText');
const infoText        = $('infoText');
const btnLoader       = $('btnLoader');

// ── Particle canvas ─────────────────────────────────────────────────
(function initCanvas() {
    const canvas = $('bgCanvas');
    const ctx    = canvas.getContext('2d');
    let W, H, particles;

    const isMobile = window.matchMedia('(max-width: 650px)').matches;
    const PARTICLE_COUNT = isMobile ? 24 : 70;
    const MAX_DIST = 140;
    const SPEED    = 0.25;
    let frame = 0;

    function resize() {
        W = canvas.width  = window.innerWidth;
        H = canvas.height = window.innerHeight;
    }

    function makeParticle() {
        return {
            x:  Math.random() * W,
            y:  Math.random() * H,
            vx: (Math.random() - 0.5) * SPEED,
            vy: (Math.random() - 0.5) * SPEED,
            r:  Math.random() * 1.5 + 0.5,
        };
    }

    function init() {
        resize();
        particles = Array.from({ length: PARTICLE_COUNT }, makeParticle);
    }

    function draw() {
        frame += 1;
        if (document.hidden || (isMobile && frame % 2)) {
            requestAnimationFrame(draw);
            return;
        }
        ctx.clearRect(0, 0, W, H);

        // Update positions
        for (const p of particles) {
            p.x += p.vx;
            p.y += p.vy;
            if (p.x < 0) p.x = W;
            if (p.x > W) p.x = 0;
            if (p.y < 0) p.y = H;
            if (p.y > H) p.y = 0;
        }

        // Draw connections
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < MAX_DIST) {
                    const alpha = (1 - dist / MAX_DIST) * 0.18;
                    ctx.strokeStyle = `rgba(0,229,255,${alpha})`;
                    ctx.lineWidth = 0.6;
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.stroke();
                }
            }
        }

        // Draw dots
        for (const p of particles) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(0,229,255,0.5)';
            ctx.fill();
        }

        requestAnimationFrame(draw);
    }

    window.addEventListener('resize', resize);
    init();
    draw();
}());

// ── Time helpers ────────────────────────────────────────────────────
function getServerNow() {
    return new Date(Date.now() + state.serverTimeOffset);
}

function formatInTimezone(timestamp, includeDate = false) {
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return '--:--:--';
    return new Intl.DateTimeFormat(undefined, {
        timeZone: state.timezone,
        dateStyle: includeDate ? 'medium' : undefined,
        timeStyle: 'medium',
    }).format(date);
}

function formatTime(date) {
    return [date.getHours(), date.getMinutes(), date.getSeconds()]
        .map(n => String(n).padStart(2, '0')).join(':');
}

function updateLoginClock() {
    const clock = $('loginClock');
    if (clock) clock.textContent = formatInTimezone(new Date());
}

function updateDisplayTime() {
    serverTimeEl.textContent = formatInTimezone(getServerNow());
    updateSignalAvailability();
}

function updateSignalAvailability() {
    const notice = $('newSignalNotice');
    const button = $('newTradeButton');
    if (!notice || !button || !state.currentSignal) return;
    const expiry = new Date(state.currentSignal.expiry_timestamp || state.currentSignal.expiry_time);
    const available = getServerNow().getTime() >= expiry.getTime();
    notice.classList.toggle('visible', available);
    button.classList.toggle('new-signal-ready', available);
    button.textContent = available ? '↻ GET NEW SIGNAL' : '＋ NEW TRADE';
}

// ── Price formatting (dynamic precision) ───────────────────────────
function formatPrice(price) {
    if (price >= 1000) return price.toFixed(2);
    if (price >= 1)    return price.toFixed(4);
    if (price >= 0.01) return price.toFixed(6);
    return price.toFixed(8);
}

// ── Status indicator ────────────────────────────────────────────────
function setStatus(cls, text) {
    statusDot.className = `status-dot ${cls}`;
    statusText.textContent = text;
}

// ── Server time sync ────────────────────────────────────────────────
async function syncServerTime() {
    try {
        const res  = await authenticatedFetch(`${API_BASE_URL}/server-time`);
        if (!res.ok) throw new Error('sync failed');
        const data = await res.json();
        const serverMs = data.unix_timestamp * 1000;
        state.serverTimeOffset = serverMs - Date.now();
        setStatus('active', 'ONLINE');
        signalBtn.disabled = false;
        infoText.textContent = 'Neural link established. Ready to scan.';
        return data;
    } catch {
        setStatus('error', 'OFFLINE');
        signalBtn.disabled = true;
        infoText.textContent = 'Connection lost. Retrying...';
        return null;
    }
}

// ── Confidence ring ─────────────────────────────────────────────────
function setConfidenceRing(pct, direction) {
    const ring   = $('confidenceRing');
    const offset = RING_CIRCUMFERENCE * (1 - pct / 100);
    ring.style.strokeDashoffset = offset;

    // Color by direction
    const color = direction === 'BUY' ? '#00ff88' : direction === 'SELL' ? '#ff2d6b' : '#00e5ff';
    ring.style.stroke = color;
    ring.style.filter = `drop-shadow(0 0 6px ${color})`;
}

// ── Countdown ring ──────────────────────────────────────────────────
function setCountdownRing(remainingMs, totalMs) {
    const ring  = $('countdownRing');
    const ratio = Math.max(0, Math.min(1, remainingMs / totalMs));
    ring.style.strokeDashoffset = CRING_CIRCUMFERENCE * (1 - ratio);
}

// ── Display signal ──────────────────────────────────────────────────
function displaySignal(signal) {
    addSignalToHistory(signal);
    showSignalToast(signal);
    renderNeuralPairs.selectedPair = signal.pair;
    setNeuralSignalState(signal.direction);
    $('marketSignalPair').textContent = signal.pair;
    $('marketSignalDirection').textContent = signal.direction;
    $('marketSignalDirection').className = `direction-badge ${signal.direction.toLowerCase()}`;
    $('marketSignalDirectionBelow').textContent = signal.direction;
    $('marketSignalDirectionBelow').className = signal.direction === 'BUY' ? 'positive' : 'negative';
    $('marketSignalDirectionCell').className = `signal-direction-cell ${signal.direction.toLowerCase()}`;
    $('marketSignalEntry').textContent = formatInTimezone(signal.entry_timestamp);
    $('marketSignalExpiry').textContent = formatInTimezone(signal.expiry_timestamp);
    $('driverSignal').textContent = `${signal.direction} · ${signal.pair}`;
    setIndicator('driverRsiScore', 'driverRsiPercent', signal.indicator_scores.rsi);
    setIndicator('driverEmaScore', 'driverEmaPercent', signal.indicator_scores.ema);
    setIndicator('driverMacdScore', 'driverMacdPercent', signal.indicator_scores.macd);
    $('demoMarketView').style.display = 'none';
    $('marketSignalView').style.display = 'block';
    $('signalPair').textContent       = signal.pair;
    $('currentPrice').textContent     = formatPrice(signal.current_price);
    $('generatedAt').textContent      = formatInTimezone(signal.generated_timestamp);
    $('entryTime').textContent        = formatInTimezone(signal.entry_timestamp);
    $('expiryTime').textContent       = formatInTimezone(signal.expiry_timestamp);

    // Confidence is now a float from the API
    const pct = Math.round(signal.confidence);
    $('signalConfidence').textContent = `${pct}%`;

    // Direction badge
    const dirEl = $('signalDirection');
    dirEl.textContent = signal.direction;
    dirEl.className   = `direction-badge ${signal.direction.toLowerCase()}`;
    $('signalDirectionBelow').textContent = signal.direction;
    $('signalDirectionBelow').className = signal.direction === 'BUY' ? 'positive' : 'negative';
    $('signalEntryBelow').textContent = formatInTimezone(signal.entry_timestamp);
    $('signalExpiryBelow').textContent = formatInTimezone(signal.expiry_timestamp);

    // Confidence ring
    setConfidenceRing(signal.confidence, signal.direction);

    // Indicator bars (stagger via CSS delay is handled by the fill elements)
    const scores = signal.indicator_scores;
    setIndicator('rsiScore',  'rsiPercent',  scores.rsi);
    setIndicator('emaScore',  'emaPercent',  scores.ema);
    setIndicator('macdScore', 'macdPercent', scores.macd);

    signalDisplay.style.display = 'none';
    $('terminalDashboard').style.display = 'block';
    errorDisplay.style.display  = 'none';
    requestAnimationFrame(() => drawSignalChart(signal.chart_candles || [], 'marketSignalChart'));
}

function showSignalToast(signal) {
    const toast = $('signalToast');
    const text = $('signalToastText');
    if (!toast || !text) return;
    text.textContent = `${signal.pair} · ${signal.direction} · ${Math.round(signal.confidence)}% confidence`;
    toast.classList.remove('show');
    requestAnimationFrame(() => toast.classList.add('show'));
    clearTimeout(showSignalToast.timeout);
    showSignalToast.timeout = setTimeout(() => toast.classList.remove('show'), 4200);
}

function setNeuralSignalState(direction) {
    const panel = document.querySelector('.neural-engine-panel');
    if (!panel) return;
    panel.classList.toggle('signal-buy', direction === 'BUY');
    panel.classList.toggle('signal-sell', direction === 'SELL');
    renderNeuralPairs.selectedDirection = direction;
    updateNeuralPairSelection();
}

function updateNeuralPairSelection() {
    const selected = String(renderNeuralPairs.selectedPair || '')
        .replace(/[_/-]/g, '').toUpperCase();
    document.querySelectorAll('.neural-live-pair').forEach(pair => {
        const isSelected = pair.dataset.pair === selected;
        pair.classList.toggle('selected-buy', isSelected && renderNeuralPairs.selectedDirection === 'BUY');
        pair.classList.toggle('selected-sell', isSelected && renderNeuralPairs.selectedDirection === 'SELL');
    });
}

function renderNeuralPairs(nodes) {
    const orbit = $('neuralOrbit');
    if (!orbit) return;
    const pairKey = nodes.map(node => node.id).join('|');
    if (renderNeuralPairs.lastKey === pairKey) {
        updateNeuralPairSelection();
        return;
    }
    renderNeuralPairs.lastKey = pairKey;
    orbit.textContent = '';
    if (!nodes.length) return;

    const tracks = [0, 1, 2].map(trackIndex => {
        const track = document.createElement('div');
        track.className = `neural-orbit-track orbit-track-${trackIndex}`;
        orbit.appendChild(track);
        return track;
    });
    nodes.forEach((node, index) => {
        const trackIndex = index % tracks.length;
        const trackNodes = nodes.filter((_, nodeIndex) => nodeIndex % tracks.length === trackIndex);
        const trackPosition = trackNodes.indexOf(node);
        const angle = (trackPosition / trackNodes.length) * Math.PI * 2 - Math.PI / 2;
        const pair = document.createElement('span');
        pair.className = 'neural-live-pair';
        pair.dataset.pair = String(node.id).replace(/[_/-]/g, '').toUpperCase();
        pair.style.left = `${50 + Math.cos(angle) * 40}%`;
        pair.style.top = `${50 + Math.sin(angle) * 40}%`;
        pair.textContent = String(node.label || node.id)
            .replace('_otc', '')
            .replace(/([A-Z]{3})([A-Z]{3})/, '$1/$2');
        tracks[trackIndex].appendChild(pair);
    });
    updateNeuralPairSelection();
}

function drawSignalChart(candles, canvasId = 'signalChart') {
    const canvas = $(canvasId);
    if (!canvas || !candles.length) return;
    const bounds = canvas.getBoundingClientRect();
    if (bounds.width < 2 || bounds.height < 2) return;
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.floor(bounds.width * ratio));
    const height = Math.max(1, Math.floor(bounds.height * ratio));
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const prices = candles.map(candle => Number(candle.close));
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || max * 0.001 || 1;
    const padding = 16;
    const xStep = (bounds.width - padding * 2) / Math.max(1, prices.length - 1);
    const y = price => bounds.height - padding - ((price - min) / range) * (bounds.height - padding * 2);
    context.clearRect(0, 0, bounds.width, bounds.height);
    context.strokeStyle = 'rgba(112, 194, 207, .14)';
    context.lineWidth = 1;
    for (let index = 1; index < 4; index += 1) {
        const lineY = padding + ((bounds.height - padding * 2) / 4) * index;
        context.beginPath(); context.moveTo(0, lineY); context.lineTo(bounds.width, lineY); context.stroke();
    }
    context.beginPath();
    prices.forEach((price, index) => {
        const x = padding + xStep * index;
        if (index === 0) context.moveTo(x, y(price)); else context.lineTo(x, y(price));
    });
    context.strokeStyle = '#6be2ed';
    context.lineWidth = 2;
    context.shadowColor = '#6be2ed';
    context.shadowBlur = 8;
    context.stroke();
    context.shadowBlur = 0;
    const lastX = padding + xStep * (prices.length - 1);
    context.fillStyle = '#ffffff';
    context.beginPath(); context.arc(lastX, y(prices[prices.length - 1]), 3, 0, Math.PI * 2); context.fill();
}

function addSignalToHistory(signal) {
    state.signalHistory = [
        {
            pair: signal.pair,
            direction: signal.direction,
            confidence: signal.confidence,
            generatedAt: signal.generated_at,
            generatedTimestamp: signal.generated_timestamp,
            dataSource: signal.data_source,
        },
        ...state.signalHistory.filter(item =>
            !(item.pair === signal.pair && item.generatedAt === signal.generated_at)
        ),
    ].slice(0, 8);
    localStorage.setItem('auroxSignalHistory', JSON.stringify(state.signalHistory));
    renderSignalHistory();
}

function renderSignalHistory() {
    const historyEl = $('signalHistory');
    if (!historyEl) return;
    historyEl.textContent = '';
    if (!state.signalHistory.length) {
        const empty = document.createElement('div');
        empty.className = 'summary-row history-empty';
        empty.textContent = 'No signals generated yet';
        historyEl.appendChild(empty);
        return;
    }
    state.signalHistory.forEach(item => {
        const row = document.createElement('div');
        row.className = 'summary-row';
        const date = document.createElement('span');
        date.textContent = item.generatedTimestamp ? formatInTimezone(item.generatedTimestamp) : (item.generatedAt || '--:--:--');
        const signal = document.createElement('b');
        signal.textContent = `${item.pair} ${item.direction}`;
        const confidence = document.createElement('em');
        confidence.className = item.direction === 'BUY' ? 'positive' : 'negative';
        confidence.textContent = `${Math.round(item.confidence)}%`;
        row.append(date, signal, confidence);
        historyEl.appendChild(row);
    });
}

function setIndicator(barId, pctId, value) {
    const pct = Math.min(100, Math.max(0, value));
    $(barId).style.width       = `${pct}%`;
    $(pctId).textContent       = `${Math.round(pct)}%`;
}

// ── Countdown timer ─────────────────────────────────────────────────
function startCountdown(signal) {
    if (state.countdownInterval) clearInterval(state.countdownInterval);

    const target = new Date(signal.entry_timestamp);

    // Measure total time once for ring calculation
    const totalMs = Math.max(1, target.getTime() - getServerNow().getTime());

    function tick() {
        const remaining = Math.max(0, target.getTime() - getServerNow().getTime());
        const sec = Math.floor((remaining / 1000) % 60);
        const min = Math.floor(remaining / 60000);

        $('countdownTimer').textContent =
            `${String(min).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;

        setCountdownRing(remaining, totalMs);

        if (remaining <= 0) {
            clearInterval(state.countdownInterval);
            state.countdownInterval = null;
            $('countdownTimer').textContent = '00:00';
            setCountdownRing(0, 1);
        }
    }

    tick();
    state.countdownInterval = setInterval(tick, COUNTDOWN_TICK);
}

// ── Fetch signal ────────────────────────────────────────────────────
async function fetchSignal() {
    try {
        $('newSignalNotice')?.classList.remove('visible');
        $('newTradeButton')?.classList.remove('new-signal-ready');
        if ($('newTradeButton')) $('newTradeButton').textContent = 'SCANNING...';
        signalBtn.disabled = true;
        signalBtn.classList.add('loading');
        infoText.textContent = 'Scanning markets — running neural analysis...';
        errorDisplay.style.display = 'none';

        const res = await authenticatedFetch(`${API_BASE_URL}/signal`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Signal generation failed');
        }

        const data = await res.json();
        state.currentSignal = data;
        updateSignalAvailability();
        displaySignal(data);
        startCountdown(data);
        updateStats();
        infoText.textContent = `Signal acquired — ${data.pair} ${data.direction}`;
    } catch (err) {
        showError(err.message);
    } finally {
        signalBtn.disabled = false;
        signalBtn.classList.remove('loading');
    }
}

// ── Error display ───────────────────────────────────────────────────
function showError(msg) {
    $('errorMessage').textContent  = msg;
    errorDisplay.style.display     = 'block';
    signalDisplay.style.display    = 'none';
    $('terminalDashboard').style.display = 'block';
    $('marketSignalView').style.display = 'none';
    $('demoMarketView').style.display = 'block';
}

// ── Stats update ────────────────────────────────────────────────────
async function updateStats() {
    try {
        const [timeRes, statusRes, pairsRes, correlationsRes] = await Promise.all([
            authenticatedFetch(`${API_BASE_URL}/server-time`),
            authenticatedFetch(`${API_BASE_URL}/status`),
            authenticatedFetch(`${API_BASE_URL}/pairs`),
            authenticatedFetch(`${API_BASE_URL}/correlations`),
        ]);

        if (timeRes.ok) {
            const d = await timeRes.json();
            $('lastUpdate').textContent = d.server_time;
        }
        if (statusRes.ok) {
            const d = await statusRes.json();
            $('cacheStatus').textContent = d.cache_valid ? 'LIVE' : 'STALE';
        }
        if (pairsRes.ok) {
            const d = await pairsRes.json();
            const pairs = d.pairs || d.assets || [];
            state.activePairs = pairs.filter(pair => {
                const symbol = String(pair).replace(/[_/-]/g, '').toUpperCase();
                return !symbol.includes('ETH') && !symbol.includes('XAU') && !symbol.includes('GOLD');
            });
            $('pairsCount').textContent = state.activePairs.length || '--';
            renderActivePairs();
        }
        if (correlationsRes.ok) {
            state.correlations = await correlationsRes.json();
            updateCorrelationInsight();
        }
    } catch { /* silent */ }
}

function updateCorrelationInsight() {
    const links = state.correlations.links || [];
    const strongest = [...links].sort((a, b) => Math.abs(b.value) - Math.abs(a.value))[0];
    const insight = $('correlationInsight');
    const confidence = $('correlationConfidence');
    const sentiment = $('correlationSentiment');
    const risk = $('correlationRisk');
    if (!insight || !strongest) return;
    const first = String(strongest.source).replace('_otc', '').replace(/([A-Z]{3})([A-Z]{3})/, '$1/$2');
    const second = String(strongest.target).replace('_otc', '').replace(/([A-Z]{3})([A-Z]{3})/, '$1/$2');
    const direction = strongest.value >= 0 ? 'moving together' : 'moving inversely';
    insight.textContent = `${first} and ${second} are ${direction} across the latest candles.`;
    confidence.textContent = `${Math.round(Math.abs(strongest.value) * 100)}%`;
    sentiment.textContent = strongest.value >= 0 ? 'ALIGNED' : 'DIVERGING';
    risk.textContent = Math.abs(strongest.value) > 0.7 ? 'HIGH' : 'MODERATE';
}

function renderActivePairs() {
    const pairsEl = $('activePairs');
    if (!pairsEl) return;
    pairsEl.textContent = '';
    if (!state.activePairs.length) {
        pairsEl.textContent = 'Waiting for active Pocket Option pairs...';
        return;
    }
    state.activePairs.forEach(pair => {
        const item = document.createElement('span');
        item.className = 'active-pair';
        item.textContent = String(pair).replace('_otc', '').replace(/([A-Z]{3})([A-Z]{3})/, '$1/$2');
        pairsEl.appendChild(item);
    });
}

// ── Event listeners ─────────────────────────────────────────────────
function initListeners() {
    signalBtn.addEventListener('click', fetchSignal);

    refreshTimeBtn.addEventListener('click', async () => {
        const ok = await syncServerTime();
        if (ok) infoText.textContent = 'Time synchronised.';
    });


    $('retryBtn').addEventListener('click', fetchSignal);
}

function initSidebar() {
    const sidebar = $('sidebar');
    const toggle = $('sidebarToggle');
    if (!sidebar || !toggle || sidebar.dataset.ready) return;
    sidebar.dataset.ready = 'true';
    toggle.addEventListener('click', () => {
        const collapsed = sidebar.classList.toggle('collapsed');
        toggle.setAttribute('aria-expanded', String(!collapsed));
    });
    document.querySelectorAll('.nav-item[data-nav]').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.nav-item[data-nav]').forEach(navItem => navItem.classList.remove('active'));
            item.classList.add('active');
            const destination = item.dataset.nav === 'signals' ? $('signalDisplay') : $('terminalDashboard');
            destination?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });
}

function startNeuralEngine() {
    const status = $('neuralStatus');
    const index = $('neuralStatusIndex');
    const bar = document.querySelector('.neural-status-bar');
    if (!status || !index || !bar || state.neuralStatusInterval) return;

    const messages = [
        'Ingesting Pocket Option ticks & price action...',
        'Evaluating multi-timeframe volatility matrix...',
        'Calculating neural weight distribution...',
        'Synthesizing optimal trade direction signal...',
    ];
    let currentIndex = 0;
    state.neuralStatusInterval = setInterval(() => {
        currentIndex = (currentIndex + 1) % messages.length;
        status.textContent = messages[currentIndex];
        index.textContent = `${String(currentIndex + 1).padStart(2, '0')} / 04`;
        bar.classList.remove('is-changing');
        requestAnimationFrame(() => bar.classList.add('is-changing'));
    }, 2500);
}

// ── Dashboard visualization and demo interactions ───────────────────
function initDashboardVisuals() {
    if (document.body.dataset.dashboardReady) return;
    document.body.dataset.dashboardReady = 'true';
    const chartCanvas = $('marketChart');
    const chartContext = chartCanvas.getContext('2d');
    const networkCanvas = $('correlationNetwork');
    const networkContext = networkCanvas.getContext('2d');
    const chartTooltip = $('chartTooltip');
    const isMobile = window.matchMedia('(max-width: 650px)').matches;
    let lastNetworkFrame = 0;
    const chartValues = [68180, 68420, 68270, 68740, 68610, 68960, 69140, 68880, 69340, 69720, 69550, 69840, 70120, 69890, 70420, 70180, 70610, 70340, 70820, 70670, 71120, 70980, 71400, 71240];
    let networkNodes = [];
    let networkLinks = [];

    function updateNetworkPairs() {
        const nodes = state.correlations.nodes.length
            ? state.correlations.nodes
            : state.activePairs.map(id => ({ id, label: id }));
        networkNodes = nodes.map((node, index) => {
            const angle = index * 2.39996;
            const radius = 0.22 + (index % 3) * 0.08;
            return {
                id: node.id,
                label: String(node.label).replace('_otc', '').replace(/([A-Z]{3})([A-Z]{3})/, '$1/$2'),
                x: 0.5 + Math.cos(angle) * radius,
                y: 0.5 + Math.sin(angle) * radius,
                radius: 6 + (index % 3) * 1.5,
                color: index % 3 === 0 ? '#6be2ed' : index % 3 === 1 ? '#72dfbf' : '#90b9dc',
            };
        });
        renderNeuralPairs(networkNodes);
        const nodeIds = new Set(networkNodes.map(node => node.id));
        networkLinks = (state.correlations.links || []).filter(link => nodeIds.has(link.source) && nodeIds.has(link.target));
    }

    function fitCanvas(canvas, context) {
        const bounds = canvas.getBoundingClientRect();
        const pixelRatio = window.devicePixelRatio || 1;
        canvas.width = Math.max(1, Math.floor(bounds.width * pixelRatio));
        canvas.height = Math.max(1, Math.floor(bounds.height * pixelRatio));
        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
        return bounds;
    }

    function drawMarketChart() {
        const bounds = fitCanvas(chartCanvas, chartContext); const width = bounds.width; const height = bounds.height;
        chartContext.clearRect(0, 0, width, height); const plotTop = 16; const plotBottom = height - 34; const minPrice = 67500; const maxPrice = 72000;
        const priceY = price => plotBottom - ((price - minPrice) / (maxPrice - minPrice)) * (plotBottom - plotTop); const candleWidth = Math.max(5, width / 36); const step = width / (chartValues.length + 1);
        chartContext.font = '9px Chakra Petch, sans-serif'; chartContext.fillStyle = 'rgba(129, 170, 178, .8)';
        [70000, 68500, 68400, 66300].forEach(price => chartContext.fillText(price.toLocaleString(), width - 43, priceY(price)));
        chartContext.beginPath(); chartValues.forEach((price, index) => { const x = step * (index + 1); const movingAverage = chartValues.slice(Math.max(0, index - 4), index + 1).reduce((sum, value) => sum + value, 0) / Math.min(index + 1, 5); if (index === 0) chartContext.moveTo(x, priceY(movingAverage)); else chartContext.lineTo(x, priceY(movingAverage)); }); chartContext.strokeStyle = 'rgba(120, 211, 229, .75)'; chartContext.lineWidth = 1.2; chartContext.stroke();
        chartValues.forEach((price, index) => { const x = step * (index + 1); const open = price - (index % 3 === 0 ? 130 : -75); const high = Math.max(open, price) + 90; const low = Math.min(open, price) - 95; const rising = price >= open; chartContext.strokeStyle = rising ? '#65d8c0' : '#c87480'; chartContext.fillStyle = rising ? 'rgba(72, 195, 174, .8)' : 'rgba(193, 91, 105, .8)'; chartContext.lineWidth = 1; chartContext.beginPath(); chartContext.moveTo(x, priceY(high)); chartContext.lineTo(x, priceY(low)); chartContext.stroke(); const bodyTop = priceY(Math.max(open, price)); const bodyHeight = Math.max(3, Math.abs(priceY(open) - priceY(price))); chartContext.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight); const volumeHeight = 12 + (index % 5) * 5; chartContext.fillStyle = rising ? 'rgba(67, 179, 162, .48)' : 'rgba(180, 76, 91, .48)'; chartContext.fillRect(x - candleWidth / 2, height - volumeHeight - 9, candleWidth, volumeHeight); });
    }

    function drawNetwork(timestamp = 0) {
        if (document.hidden) {
            window.requestAnimationFrame(drawNetwork);
            return;
        }
        if (isMobile && timestamp - lastNetworkFrame < 33) {
            window.requestAnimationFrame(drawNetwork);
            return;
        }
        lastNetworkFrame = timestamp;
        updateNetworkPairs();
        const bounds = fitCanvas(networkCanvas, networkContext); const width = bounds.width; const height = bounds.height; const drift = Math.sin(timestamp / 1700) * 2; networkContext.clearRect(0, 0, width, height);
        const points = networkNodes.map(node => ({ ...node, px: node.x * width + drift, py: node.y * height + Math.cos(timestamp / 1900 + node.x * 4) * 2 }));
        const pointById = new Map(points.map(point => [point.id, point]));
        networkLinks.forEach(link => { const start = pointById.get(link.source); const end = pointById.get(link.target); if (!start || !end) return; const strength = Math.abs(link.value); networkContext.beginPath(); networkContext.moveTo(start.px, start.py); networkContext.lineTo(end.px, end.py); networkContext.strokeStyle = link.value >= 0 ? `rgba(83, 213, 165, ${.18 + strength * .55})` : `rgba(230, 123, 135, ${.18 + strength * .55})`; networkContext.lineWidth = 0.7 + strength * 3; networkContext.stroke(); });
        points.forEach(node => { const glow = 5 + Math.sin(timestamp / 500 + node.x * 10) * 2; networkContext.beginPath(); networkContext.arc(node.px, node.py, node.radius + glow, 0, Math.PI * 2); networkContext.fillStyle = `${node.color}15`; networkContext.fill(); networkContext.beginPath(); networkContext.arc(node.px, node.py, node.radius / 2.7, 0, Math.PI * 2); networkContext.fillStyle = node.color; networkContext.shadowColor = node.color; networkContext.shadowBlur = 10; networkContext.fill(); networkContext.shadowBlur = 0; networkContext.fillStyle = 'rgba(190, 222, 226, .82)'; networkContext.font = '9px Chakra Petch, sans-serif'; networkContext.fillText(node.label, node.px + node.radius + 4, node.py + 3); });
        window.requestAnimationFrame(drawNetwork);
    }

    function resizeVisuals() { drawMarketChart(); }
    drawMarketChart(); drawNetwork(); window.addEventListener('resize', resizeVisuals);
    chartCanvas.addEventListener('mousemove', event => { const bounds = chartCanvas.getBoundingClientRect(); const index = Math.min(chartValues.length - 1, Math.max(0, Math.floor((event.clientX - bounds.left) / bounds.width * chartValues.length))); chartTooltip.textContent = `BTC/USD  ${chartValues[index].toLocaleString()}.21`; chartTooltip.style.display = 'block'; chartTooltip.style.left = `${Math.min(bounds.width - 116, Math.max(4, event.clientX - bounds.left + 10))}px`; chartTooltip.style.top = `${Math.max(4, event.clientY - bounds.top - 28)}px`; });
    chartCanvas.addEventListener('mouseleave', () => { chartTooltip.style.display = 'none'; });
    document.querySelectorAll('.dashboard-tab').forEach(tab => tab.addEventListener('click', () => { document.querySelectorAll('.dashboard-tab').forEach(item => item.classList.toggle('active', item === tab)); document.querySelectorAll('.tab-content').forEach(content => content.classList.toggle('active', content.id === tab.dataset.tab)); }));
    document.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', () => { const action = button.dataset.action; if (action === 'new-trade') { if (!signalBtn.disabled) signalBtn.click(); else infoText.textContent = 'Connect to the market feed before starting a demo scan.'; } if (action === 'new-orders') { button.textContent = 'Order window ready'; button.classList.add('positive'); } }));
    renderSignalHistory();
}

// ── Visibility: pause/resume loops ──────────────────────────────────
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        clearInterval(state.countdownInterval);
        clearInterval(state.timeSyncInterval);
        clearInterval(state.displayInterval);   // FIX: also clear display timer
        clearInterval(state.statsInterval);     // FIX: clear stats too
        clearInterval(state.neuralStatusInterval);
        state.neuralStatusInterval = null;
    } else {
        if (state.currentSignal) {
            const now = getServerNow();
            const entryTarget = new Date(state.currentSignal.entry_timestamp);
            if (entryTarget > now) startCountdown(state.currentSignal);
        }
        state.timeSyncInterval = setInterval(syncServerTime, TIME_SYNC_INTERVAL);
        state.displayInterval  = setInterval(updateDisplayTime, 1000);
        state.statsInterval    = setInterval(updateStats, STATS_REFRESH_INTERVAL); // FIX: restart
        startNeuralEngine();
        updateDisplayTime();
    }
});

// ── Cleanup ─────────────────────────────────────────────────────────
window.addEventListener('beforeunload', () => {
    clearInterval(state.countdownInterval);
    clearInterval(state.timeSyncInterval);
    clearInterval(state.displayInterval);
    clearInterval(state.statsInterval);
    clearInterval(state.neuralStatusInterval);
    clearInterval(state.loginClockInterval);
});

// ── Online / offline ─────────────────────────────────────────────────
window.addEventListener('online',  () => { if (!statusDot) return; setStatus('active', 'ONLINE');  syncServerTime(); });
window.addEventListener('offline', () => { if (!statusDot) return; setStatus('error',  'OFFLINE'); signalBtn.disabled = true; });

// ── Login ─────────────────────────────────────────────────────────────
async function initLogin() {
    const loginScreen = document.getElementById('loginScreen');
    const loginBtn    = document.getElementById('loginBtn');
    const loginForm   = document.getElementById('loginForm');
    const loginInput  = document.getElementById('traderIdInput');
    const loginError  = document.getElementById('loginError');
    const timezoneTrigger = document.getElementById('timezoneTrigger');
    const timezoneMenu = document.getElementById('timezoneMenu');
    const timezoneSearch = document.getElementById('timezoneSearch');
    const timezoneOptions = document.getElementById('timezoneOptions');

    function renderTimezones(query = '') {
        const normalized = query.trim().toLowerCase();
        timezoneOptions.textContent = '';
        state.timezoneCatalog.filter(item => !normalized || item.search.includes(normalized)).slice(0, 80).forEach(item => {
            const option = document.createElement('button');
            option.type = 'button'; option.className = 'timezone-option'; option.setAttribute('role', 'option');
            option.innerHTML = `<strong>${item.country || item.city}</strong><small>${item.id} · ${item.offset} · ${item.abbreviation}</small>`;
            option.addEventListener('click', () => selectTimezone(item));
            timezoneOptions.appendChild(option);
        });
        if (!timezoneOptions.children.length) timezoneOptions.textContent = 'No matching time zones';
    }

    function selectTimezone(item, persist = true) {
        state.timezone = item.id;
        if (persist) state.timezoneExplicit = true;
        timezoneTrigger.textContent = `${item.country || item.city} · ${item.id} · ${item.offset}`;
        timezoneMenu.hidden = true; timezoneTrigger.setAttribute('aria-expanded', 'false');
        updateLoginClock();
    }

    async function loadTimezones() {
        try {
            const response = await fetch(`${API_BASE_URL}/timezones`);
            state.timezoneCatalog = await response.json();
        } catch { state.timezoneCatalog = []; }
        const selected = state.timezoneCatalog.find(item => item.id === state.timezone);
        if (selected) selectTimezone(selected, false);
    }

    timezoneTrigger.addEventListener('click', () => {
        timezoneMenu.hidden = !timezoneMenu.hidden;
        timezoneTrigger.setAttribute('aria-expanded', String(!timezoneMenu.hidden));
        if (!timezoneMenu.hidden) { timezoneSearch.value = ''; renderTimezones(); timezoneSearch.focus(); }
    });
    timezoneSearch.addEventListener('input', () => renderTimezones(timezoneSearch.value));

    function showLoginError(msg) {
        loginError.textContent = msg;
        loginError.style.display = 'block';
        loginBtn.disabled = false;
        loginBtn.classList.remove('loading');
        document.getElementById('loginBtnText').textContent = 'INITIALIZE ACCESS';
    }

    async function doLogin() {
        const id = loginInput.value.trim();
        if (!id) {
            loginError.textContent = 'Enter your trader ID.';
            loginError.style.display = 'block';
            loginInput.setAttribute('aria-invalid', 'true');
            loginInput.focus();
            return;
        }

        loginError.style.display = 'none';
        loginInput.removeAttribute('aria-invalid');
        loginBtn.disabled = true;
        loginBtn.classList.add('loading');
        document.getElementById('loginBtnText').textContent = 'Signing in...';

        // Verify trader ID via PocketPartners Telegram bot
        try {
            const res = await fetch(`${API_BASE_URL}/verify-trader`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ trader_id: id, ...(state.timezoneExplicit ? { timezone: state.timezone } : {}) }),
            });

            // Non-2xx → show the server's error detail
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                showLoginError(`⚠ ${err.detail || 'VERIFICATION FAILED — TRY AGAIN'}`);
                return;
            }

            const data = await res.json();
            if (!data.found) {
                showLoginError(`⚠ ${data.message || 'TRADER NOT FOUND'}`);
                return;
            }
            if (!data.session_token) {
                showLoginError('⚠ SESSION COULD NOT BE CREATED — PLEASE TRY AGAIN');
                return;
            }
            sessionStorage.setItem(SESSION_TOKEN_KEY, data.session_token);
            if (data.timezone) {
                state.timezone = data.timezone;
                localStorage.setItem(`aurox_timezone_${id.toUpperCase()}`, data.timezone);
                const saved = state.timezoneCatalog.find(item => item.id === data.timezone);
                if (saved) selectTimezone(saved, false);
            }
        } catch (err) {
            showLoginError('⚠ SERVER UNREACHABLE — CHECK YOUR CONNECTION AND TRY AGAIN');
            return;
        }

        document.getElementById('loginBtnText').textContent = 'Authenticating...';

        // Store trader ID and continue to the member hub
        sessionStorage.setItem('aurox_trader_id', id);
        loginScreen.classList.add('fade-out');
        setTimeout(() => { location.href = 'hub.html'; }, 450);
    }

    loginForm.addEventListener('submit', event => { event.preventDefault(); doLogin(); });
    document.getElementById('signUpLink')?.addEventListener('click', event => {
        event.preventDefault();
        window.open(event.currentTarget.href, '_blank', 'noopener,noreferrer');
    });

    if (new URLSearchParams(location.search).has('expired')) {
        loginError.textContent = '⚠ SESSION EXPIRED — PLEASE LOG IN AGAIN';
        loginError.style.display = 'block';
    }
    const storedTraderId = sessionStorage.getItem('aurox_trader_id');
    const storedToken = sessionStorage.getItem(SESSION_TOKEN_KEY);
    if (storedTraderId && storedToken) {
        try {
            const response = await authenticatedFetch(`${API_BASE_URL}/session/heartbeat`, { method: 'POST' });
            if (!response.ok) throw new Error('expired');
            location.replace('hub.html');
            return;
        } catch {
            clearSession();
            loginInput.focus();
        }
    } else {
        clearSession();
        loginInput.focus();
    }
    loadTimezones();
    updateLoginClock();
    state.loginClockInterval = setInterval(updateLoginClock, 1000);

}

function startSessionHeartbeat() {
    clearInterval(sessionHeartbeatInterval);
    sessionHeartbeatInterval = setInterval(async () => {
        try {
            const response = await authenticatedFetch(`${API_BASE_URL}/session/heartbeat`, { method: 'POST' });
            if (!response.ok) doLogout();
        } catch {
            // Keep the current session during brief network interruptions; the
            // server expires it if heartbeats stop for SESSION_TTL_SECONDS.
        }
    }, SESSION_HEARTBEAT_INTERVAL);
}

// ── Inactivity auto-logout (30 min) ──────────────────────────────────
const INACTIVITY_TIMEOUT = 30 * 60 * 1000;
let inactivityTimer = null;

function resetInactivityTimer() {
    clearTimeout(inactivityTimer);
    inactivityTimer = setTimeout(doLogout, INACTIVITY_TIMEOUT);
}

let activityFrame = null;
function scheduleActivityReset() {
    if (activityFrame) return;
    activityFrame = requestAnimationFrame(() => {
        activityFrame = null;
        resetInactivityTimer();
    });
}

function clearSession() {
    sessionStorage.removeItem('aurox_trader_id');
    sessionStorage.removeItem(SESSION_TOKEN_KEY);
}

function doLogout(expired = true) {
    const token = sessionStorage.getItem(SESSION_TOKEN_KEY);
    const finish = () => { location.replace(expired ? 'login.html?expired=1' : 'login.html'); };
    clearInterval(sessionHeartbeatInterval);
    clearTimeout(inactivityTimer);
    clearSession();
    if (!token) { finish(); return; }
    fetch(`${API_BASE_URL}/session/logout`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
        .catch(() => {}).finally(finish);
}

function startInactivityWatcher() {
    ['mousemove','mousedown','keydown','scroll','touchstart','click'].forEach(evt =>
        document.addEventListener(evt, scheduleActivityReset, { passive: true })
    );
    resetInactivityTimer();
}

// ── Protected pages (hub, guide, terminal) ───────────────────────────
// Verifies the stored session; sends visitors without one to the login page.
async function requireSession() {
    const traderId = sessionStorage.getItem('aurox_trader_id');
    const token = sessionStorage.getItem(SESSION_TOKEN_KEY);
    if (!traderId || !token) { location.replace('login.html'); return null; }
    try {
        const response = await authenticatedFetch(`${API_BASE_URL}/session/heartbeat`, { method: 'POST' });
        if (!response.ok) throw new Error('expired');
    } catch (error) {
        // Only an explicit rejection ends the session; a network blip keeps it.
        if (error.message === 'expired') { clearSession(); location.replace('login.html?expired=1'); return null; }
    }
    state.timezone = localStorage.getItem(`aurox_timezone_${traderId.toUpperCase()}`) || state.timezone;
    const display = document.getElementById('traderIdDisplay');
    if (display) display.textContent = traderId.toUpperCase();
    document.querySelectorAll('[data-trader-id]').forEach(el => { el.textContent = traderId.toUpperCase(); });
    startSessionHeartbeat();
    startInactivityWatcher();
    document.getElementById('logoutBtn')?.addEventListener('click', () => doLogout(false));
    return traderId;
}

async function initTerminal() {
    if (!(await requireSession())) return;
    bootApp();
}

// ── Boot (runs after login) ───────────────────────────────────────────
async function bootApp() {
    initSidebar();
    startNeuralEngine();
    initDashboardVisuals();
    initListeners();
    const connected = await syncServerTime();
    state.timeSyncInterval = setInterval(syncServerTime, TIME_SYNC_INTERVAL);
    updateDisplayTime();
    state.displayInterval = setInterval(updateDisplayTime, 1000);
    await updateStats();
    state.statsInterval = setInterval(updateStats, STATS_REFRESH_INTERVAL);
    if (connected) await fetchSignal();
}

document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.dataset.page;
    if (page === 'login') initLogin();
    else if (page === 'terminal') initTerminal();
    else if (page === 'hub' || page === 'guide') requireSession().then(id => { if (id) document.dispatchEvent(new CustomEvent('aurox:ready')); });
});
