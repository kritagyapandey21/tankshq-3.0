// Stake tracker: step-by-step stake recommendations. Session is saved in this browser only.
(function () {
    'use strict';

    const BASE_PCT = 0.005;   // first stake: 0.5% of balance
    const CAP_PCT = 0.5;      // a stake never exceeds 50% of the balance
    const WARN_PCT = 0.25;    // warn when a stake is this share of the balance

    const $ = id => document.getElementById(id);
    const round2 = v => Math.round((Number(v) + Number.EPSILON) * 100) / 100;
    const fmt = v => (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    const storeKey = 'tanix_stake_tracker_' + ((function () { try { return sessionStorage.getItem('aurox_trader_id') || ''; } catch (e) { return ''; } })().toUpperCase());
    const load = () => { try { return JSON.parse(localStorage.getItem(storeKey)); } catch (e) { return null; } };
    const save = () => { try { state ? localStorage.setItem(storeKey, JSON.stringify(state)) : localStorage.removeItem(storeKey); } catch (e) { /* storage unavailable */ } };

    // state: { start, count, trades: [{ stake, amount, result }] }
    let state = null;
    let pendingResult = '';

    const balanceAfter = n => state.trades.slice(0, n).reduce((b, t) => round2(b + (t.result === 'Win' ? t.amount : -t.amount)), state.start);
    const balance = () => balanceAfter(state.trades.length);

    // Next recommended stake: double after a loss, otherwise 0.5% of the current balance (never below 0.5% of the start).
    function nextStake() {
        const bal = balance();
        const base = round2(state.start * BASE_PCT);
        const last = state.trades[state.trades.length - 1];
        let stake = last && last.result === 'Loss'
            ? round2(last.stake * 2)
            : round2(Math.max(base, bal * BASE_PCT));
        return Math.min(stake, round2(Math.max(0, bal * CAP_PCT)));
    }

    function render() {
        $('session').hidden = !state;
        if (!state) return;

        const trades = state.trades, bal = balance(), pl = round2(bal - state.start);
        const wins = trades.filter(t => t.result === 'Win').length;
        const done = trades.length >= state.count || bal <= 0;

        $('stBalance').textContent = fmt(bal);
        const plEl = $('stPL');
        plEl.textContent = (pl > 0 ? '+' : '') + fmt(pl);
        plEl.className = pl > 0 ? 'pos' : pl < 0 ? 'neg' : '';
        $('stWL').textContent = wins + ' / ' + (trades.length - wins);
        $('stProgress').textContent = trades.length + ' / ' + state.count;
        $('barFill').style.width = Math.min(100, trades.length / state.count * 100) + '%';

        // next trade card
        const stake = done ? 0 : nextStake();
        $('nextCard').hidden = false;
        $('nextEyebrow').textContent = done ? (bal <= 0 ? 'Balance used up' : 'Session complete') : 'Trade ' + (trades.length + 1);
        $('recoValue').textContent = fmt(stake);
        const last = trades[trades.length - 1];
        $('recoNote').textContent = done ? 'Start a new session when you are ready.'
            : !last ? 'First stake: 0.5% of your starting balance.'
            : last.result === 'Loss' ? 'Last trade was a loss, so the stake is doubled.'
            : 'Last trade was a win, so the stake is back to 0.5% of your balance.';
        const warn = $('riskWarn');
        const risky = !done && bal > 0 && stake / bal >= WARN_PCT;
        warn.hidden = !risky;
        if (risky) warn.textContent = 'This stake is ' + Math.round(stake / bal * 100) + '% of your balance. Another loss would put your account at serious risk. Consider stopping for the day.';

        const amt = $('entryAmount');
        amt.disabled = done;
        amt.placeholder = stake ? stake.toFixed(2) : '0.00';
        document.querySelectorAll('.mt-seg button').forEach(b => { b.disabled = done; b.setAttribute('aria-pressed', String(b.dataset.result === pendingResult)); });
        updateLogBtn();

        // log table
        const body = $('logBody');
        body.textContent = '';
        trades.forEach((t, i) => {
            const tr = document.createElement('tr');
            tr.className = t.result === 'Win' ? 'win' : 'loss';
            [i + 1, fmt(t.stake), (t.result === 'Win' ? '+' : '-') + fmt(t.amount).replace('-', ''), t.result, fmt(balanceAfter(i + 1))]
                .forEach(v => { const td = document.createElement('td'); td.textContent = v; tr.appendChild(td); });
            body.appendChild(tr);
        });
        $('logEmpty').hidden = trades.length > 0;
        $('undoBtn').disabled = trades.length === 0;
    }

    function updateLogBtn() {
        const v = parseFloat($('entryAmount').value);
        $('logBtn').disabled = !(state && !$('entryAmount').disabled && v > 0 && pendingResult);
    }

    function logTrade() {
        const amount = round2(parseFloat($('entryAmount').value));
        if (!(amount > 0) || !pendingResult) return;
        state.trades.push({ stake: nextStake(), amount, result: pendingResult });
        pendingResult = '';
        $('entryAmount').value = '';
        save();
        render();
        $('entryAmount').focus();
    }

    function startSession(e) {
        e.preventDefault();
        const total = parseFloat($('totalAmount').value), count = Math.floor(parseFloat($('numTrades').value));
        const err = $('setupError');
        if (!(total > 0) || !(count >= 1) || count > 200) {
            err.textContent = 'Enter a total amount above 0 and between 1 and 200 trades.';
            err.hidden = false;
            return;
        }
        err.hidden = true;
        state = { start: round2(total), count, trades: [] };
        pendingResult = '';
        save();
        render();
        $('entryAmount').focus();
    }

    function reset() {
        if (state && state.trades.length && !confirm('Reset this session? Your logged trades will be cleared.')) return;
        state = null;
        pendingResult = '';
        $('totalAmount').value = '';
        $('numTrades').value = '';
        save();
        render();
    }

    document.addEventListener('DOMContentLoaded', () => {
        $('setupForm').addEventListener('submit', startSession);
        $('logBtn').addEventListener('click', logTrade);
        $('entryAmount').addEventListener('input', updateLogBtn);
        $('entryAmount').addEventListener('keydown', e => { if (e.key === 'Enter' && !$('logBtn').disabled) logTrade(); });
        document.querySelectorAll('.mt-seg button').forEach(b => b.addEventListener('click', () => { pendingResult = b.dataset.result; render(); }));
        $('undoBtn').addEventListener('click', () => { if (state && state.trades.length) { state.trades.pop(); pendingResult = ''; save(); render(); } });
        $('resetBtn').addEventListener('click', reset);

        const saved = load();
        if (saved && saved.start > 0 && Array.isArray(saved.trades)) {
            state = saved;
            $('totalAmount').value = saved.start;
            $('numTrades').value = saved.count;
        }
        render();
        document.addEventListener('aurox:ready', () => document.body.classList.remove('gated'));
    });
})();
