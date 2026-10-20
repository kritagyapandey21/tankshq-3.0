// Admin page: edit the best performers shown on the website.
(function () {
    'use strict';
    const $ = id => document.getElementById(id);
    const KEY_STORE = 'tanix_admin_key';
    const MAX_ROWS = 3;

    const loginCard = $('loginCard'), editor = $('editor'), lockBtn = $('lockBtn');
    const rowsEl = $('rows'), preview = $('preview'), saveBtn = $('saveBtn'), saveStatus = $('saveStatus');
    let adminKey = '';
    let rows = [];        // [{ handle, roi, photo }]

    const getKey = () => { try { return sessionStorage.getItem(KEY_STORE) || ''; } catch (e) { return ''; } };
    const setKey = k => { try { k ? sessionStorage.setItem(KEY_STORE, k) : sessionStorage.removeItem(KEY_STORE); } catch (e) { /* ignore */ } };

    async function api(path, options = {}) {
        const res = await fetch(window.API_BASE_URL + path, {
            ...options,
            headers: { 'X-Admin-Key': adminKey, ...(options.headers || {}) },
        });
        let body = {};
        try { body = await res.json(); } catch (e) { /* no body */ }
        return { ok: res.ok, status: res.status, body };
    }

    function status(msg, kind) {
        saveStatus.textContent = msg || '';
        saveStatus.className = 'ad-status' + (kind ? ' ' + kind : '');
    }

    // ---------------------------------------------------------------- rows
    function render() {
        rowsEl.textContent = '';
        rows.forEach((row, i) => {
            const el = document.createElement('div');
            el.className = 'ad-row';
            el.innerHTML = `
                <div class="ad-photo">
                    <div class="ad-avatar"></div>
                    <div class="ad-photo-actions">
                        <button type="button" class="ad-link" data-act="upload">${row.photo ? 'Change photo' : 'Add photo'}</button>
                        <button type="button" class="ad-link" data-act="clear" ${row.photo ? '' : 'hidden'}>Remove</button>
                    </div>
                    <input type="file" accept="image/jpeg,image/png,image/webp" hidden>
                </div>
                <div class="ad-field"><label>Name / handle</label><input type="text" data-f="handle" maxlength="31" placeholder="@RohanTrades" autocomplete="off"></div>
                <div class="ad-field"><label>ROI (%)</label><input type="number" data-f="roi" min="0" max="100000" step="0.1" inputmode="decimal" placeholder="288.1"></div>
                ${rows.length > 1 ? '<button type="button" class="ad-remove" data-act="remove">Remove this performer</button>' : ''}`;
            const avatar = el.querySelector('.ad-avatar');
            const src = TanixPerformers.photoUrl(row.photo);
            if (src) { const img = new Image(); img.alt = ''; img.src = src; avatar.appendChild(img); }
            else avatar.textContent = (row.handle || '?').replace('@', '').charAt(0).toUpperCase() || '?';

            const handle = el.querySelector('[data-f="handle"]'), roi = el.querySelector('[data-f="roi"]');
            handle.value = row.handle; roi.value = row.roi;
            handle.addEventListener('input', () => { row.handle = handle.value; if (!row.photo) avatar.textContent = (row.handle.replace('@', '').charAt(0) || '?').toUpperCase(); refreshPreview(); });
            roi.addEventListener('input', () => { row.roi = roi.value; refreshPreview(); });

            const file = el.querySelector('input[type="file"]');
            el.querySelector('[data-act="upload"]').addEventListener('click', () => file.click());
            el.querySelector('[data-act="clear"]').addEventListener('click', () => { row.photo = ''; render(); refreshPreview(); });
            const rm = el.querySelector('[data-act="remove"]');
            if (rm) rm.addEventListener('click', () => { rows.splice(i, 1); render(); refreshPreview(); });
            file.addEventListener('change', async () => {
                const f = file.files[0];
                if (!f) return;
                if (f.size > 2 * 1024 * 1024) return status('That photo is over 2 MB. Please choose a smaller one.', 'err');
                status('Uploading photo...');
                const form = new FormData(); form.append('file', f);
                const r = await api('/admin/performers/photo', { method: 'POST', body: form });
                if (!r.ok) return status(r.body.detail || 'Upload failed.', 'err');
                row.photo = r.body.photo; status(''); render(); refreshPreview();
            });
            rowsEl.appendChild(el);
        });
        if (rows.length < MAX_ROWS) {
            const add = document.createElement('button');
            add.type = 'button'; add.className = 'btn btn-ghost'; add.textContent = '+ Add performer';
            add.addEventListener('click', () => { rows.push({ handle: '', roi: '', photo: '' }); render(); });
            rowsEl.appendChild(add);
        }
    }

    function validRows() {
        return rows.filter(r => String(r.handle).trim() && r.roi !== '' && Number.isFinite(Number(r.roi)))
                   .map(r => ({ handle: String(r.handle).trim(), roi: Number(r.roi), photo: r.photo || '' }));
    }
    function refreshPreview() {
        $('monthPreview').textContent = $('month').value.trim() || 'Last Month';
        TanixPerformers.render(preview, validRows().map(r => ({ ...r, handle: '@' + r.handle.replace(/^@/, '') })));
    }

    // ---------------------------------------------------------------- load / save
    function load(data) {
        $('month').value = data.month || (window.TANIX_CONFIG || {}).performersMonth || 'Last Month';
        const list = data.configured ? data.performers : ((window.TANIX_CONFIG || {}).performers || []);
        rows = list.slice(0, MAX_ROWS).map(p => ({ handle: p.handle, roi: p.roi, photo: p.photo || '' }));
        if (!rows.length) rows = [{ handle: '', roi: '', photo: '' }];
        $('updatedAt').textContent = data.updated_at
            ? 'Last updated ' + new Date(data.updated_at).toLocaleString()
            : 'Not edited yet: the website is showing the built-in sample winners until you save.';
        render(); refreshPreview();
    }

    async function save() {
        const items = validRows();
        if (!items.length) return status('Add at least one performer with a name and ROI.', 'err');
        if (rows.some(r => (String(r.handle).trim() || r.roi !== '') && !validRows().some(v => v.handle === String(r.handle).trim()))) {
            return status('Each performer needs both a name and an ROI.', 'err');
        }
        saveBtn.disabled = true; status('Saving...');
        const r = await api('/admin/performers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ month: $('month').value.trim() || 'Last Month', performers: items }),
        });
        saveBtn.disabled = false;
        if (!r.ok) {
            const d = r.body.detail;
            return status(typeof d === 'string' ? d : 'Could not save. Please check the fields.', 'err');
        }
        load(r.body);
        status('Saved. The website is updated.', 'ok');
    }

    // ---------------------------------------------------------------- tabs
    function openTab(name) {
        document.querySelectorAll('.ad-tab').forEach(t => {
            const on = t.dataset.tab === name;
            t.classList.toggle('is-active', on); t.setAttribute('aria-selected', String(on));
        });
        $('tab-performers').hidden = name !== 'performers';
        $('tab-telegram').hidden = name !== 'telegram';
        $('tab-usage').hidden = name !== 'usage';
        if (name === 'telegram') loadTelegram();
        if (name === 'usage') loadUsage();
    }
    document.querySelectorAll('.ad-tab').forEach(t => t.addEventListener('click', () => openTab(t.dataset.tab)));

    // ---------------------------------------------------------------- telegram access list
    let tgTraders = [];
    const tgStatus = (msg, kind) => { $('tgStatus').textContent = msg || ''; $('tgStatus').className = 'ad-status' + (kind ? ' ' + kind : ''); };

    function renderTelegram() {
        const q = $('tgSearch').value.trim().toUpperCase();
        const list = tgTraders.filter(t => !q || t.trader_id.includes(q));
        const body = $('tgBody');
        body.textContent = '';
        list.forEach(t => {
            const tr = document.createElement('tr');
            const id = document.createElement('td'); id.textContent = t.trader_id;
            const when = document.createElement('td'); when.textContent = new Date(t.joined_at).toLocaleString();
            const act = document.createElement('td');
            const btn = document.createElement('button');
            btn.type = 'button'; btn.className = 'ad-tg-remove'; btn.textContent = 'Remove';
            btn.addEventListener('click', () => removeTelegram(t.trader_id, btn));
            act.appendChild(btn);
            tr.append(id, when, act);
            body.appendChild(tr);
        });
        $('tgCount').textContent = String(tgTraders.length);
        $('tgEmpty').hidden = list.length > 0;
        $('tgEmpty').textContent = tgTraders.length ? 'No Trader ID matches your search.' : 'No traders on the list yet.';
    }

    async function loadTelegram(keepStatus) {
        if (keepStatus !== true) tgStatus('');
        const r = await api('/admin/telegram-joins');
        if (!r.ok) return tgStatus(r.status === 403 ? 'Admin key rejected. Lock and sign in again.' : 'Could not load the list.', 'err');
        tgTraders = r.body.traders || [];
        renderTelegram();
    }

    async function removeTelegram(traderId, btn) {
        if (!confirm('Remove ' + traderId + ' from the list?\n\nThe "Join Telegram" card will show again for this trader on their next visit.')) return;
        btn.disabled = true;
        const r = await api('/admin/telegram-joins/remove', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trader_id: traderId }),
        });
        btn.disabled = false;
        if (!r.ok && r.status !== 404) return tgStatus(typeof r.body.detail === 'string' ? r.body.detail : 'Could not remove.', 'err');
        tgStatus(traderId + ' removed. Their Join Telegram card will show again.', 'ok');
        loadTelegram(true);
    }
    $('tgSearch').addEventListener('input', renderTelegram);
    $('tgRefresh').addEventListener('click', () => loadTelegram());

    // ---------------------------------------------------------------- TANIX 3.0 usage (one record per trader per day)
    const usStatus = (msg, kind) => { $('usStatus').textContent = msg || ''; $('usStatus').className = 'ad-status' + (kind ? ' ' + kind : ''); };

    function indiaDate(daysAgo) {                       // days are counted in India time, like the server does
        return new Date(Date.now() + 5.5 * 3600 * 1000 - daysAgo * 86400000).toISOString().slice(0, 10);
    }

    function renderUsage(data) {
        const days = data.days || [];
        const body = $('usBody');
        body.textContent = '';
        days.forEach(d => {
            const tr = document.createElement('tr');
            const date = document.createElement('td');
            date.textContent = new Date(d.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
            const count = document.createElement('td'); count.textContent = String(d.count);
            const ids = document.createElement('td');
            ids.textContent = d.traders.map(t => t.trader_id).join(', ');
            ids.className = 'us-ids';
            tr.append(date, count, ids);
            body.appendChild(tr);
        });
        const byDate = Object.fromEntries(days.map(d => [d.date, d.count]));
        const today = byDate[indiaDate(0)] || 0;
        $('usToday').textContent = String(today); $('usageToday').textContent = String(today);
        $('usYesterday').textContent = String(byDate[indiaDate(1)] || 0);
        $('usWeek').textContent = String([0, 1, 2, 3, 4, 5, 6].reduce((s, n) => s + (byDate[indiaDate(n)] || 0), 0));
        $('usBest').textContent = String(days.reduce((m, d) => Math.max(m, d.count), 0));
        $('usEmpty').hidden = days.length > 0;
    }

    async function loadUsage() {
        usStatus('');
        const r = await api('/admin/terminal-usage?days=' + encodeURIComponent($('usRange').value));
        if (!r.ok) return usStatus(r.status === 403 ? 'Admin key rejected. Lock and sign in again.' : 'Could not load the usage list.', 'err');
        renderUsage(r.body);
    }
    $('usRefresh').addEventListener('click', loadUsage);
    $('usRange').addEventListener('change', loadUsage);

    // ---------------------------------------------------------------- sign in
    function show(unlocked) {
        loginCard.hidden = unlocked; editor.hidden = !unlocked; lockBtn.hidden = !unlocked;
    }
    async function unlock(key, quiet) {
        adminKey = key;
        const err = $('loginError');
        let r;
        try { r = await api('/admin/performers'); } catch (e) { if (!quiet) { err.textContent = 'Cannot reach the server.'; err.hidden = false; } return; }
        if (r.status === 403) { setKey(''); adminKey = ''; if (!quiet) { err.textContent = 'Wrong admin key (or the server has no ADMIN_KEY set).'; err.hidden = false; } return; }
        if (!r.ok) { if (!quiet) { err.textContent = 'Something went wrong. Try again.'; err.hidden = false; } return; }
        setKey(key); err.hidden = true;
        show(true); load(r.body); loadTelegram(); loadUsage();
    }

    $('loginForm').addEventListener('submit', e => { e.preventDefault(); unlock($('adminKey').value.trim(), false); });
    lockBtn.addEventListener('click', () => { setKey(''); adminKey = ''; $('adminKey').value = ''; show(false); });
    saveBtn.addEventListener('click', save);
    $('month').addEventListener('input', refreshPreview);

    const saved = getKey();
    if (saved) unlock(saved, true);
})();
