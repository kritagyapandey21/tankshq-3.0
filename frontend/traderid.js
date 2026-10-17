/* Adds a mask / unmask (eye) toggle to every trader ID display: elements marked [data-tid].
   Hides the whole ID with dots. It starts hidden; the eye button reveals it. State is shared across pages for the browser session. */
(function () {
    var KEY = 'aurox_tid_masked';
    function getId() { try { return (sessionStorage.getItem('aurox_trader_id') || '').toUpperCase(); } catch (e) { return ''; } }
    function isMasked() { try { return sessionStorage.getItem(KEY) !== '0'; } catch (e) { return true; } }   // hidden unless the user chose to show it
    function setMasked(v) { try { sessionStorage.setItem(KEY, v ? '1' : '0'); } catch (e) {} }
    var EYE = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/><line class="slash" x1="3" y1="21" x2="21" y2="3"/></svg>';
    var views = [];

    function text(masked, id) {
        if (!id) return '--';
        return masked ? '\u2022'.repeat(id.length) : id;
    }
    function render(v) {
        var id = getId(), masked = isMasked(), t = text(masked, id);
        if (v.el.textContent !== t) v.el.textContent = t;
        v.btn.setAttribute('aria-pressed', masked);
        v.btn.setAttribute('aria-label', masked ? 'Unmask trader ID' : 'Mask trader ID');
        v.btn.classList.toggle('is-masked', masked);
    }
    function setup(el) {
        var row = el.parentNode;
        if (!row.classList || !row.classList.contains('tid-row')) {
            row = document.createElement('span');
            row.className = 'tid-row';
            el.parentNode.insertBefore(row, el);
            row.appendChild(el);
        }
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'tid-eye';
        btn.title = 'Show / hide Trader ID';
        btn.innerHTML = EYE;
        row.appendChild(btn);
        var v = { el: el, btn: btn };
        views.push(v);
        btn.addEventListener('click', function () { setMasked(!isMasked()); views.forEach(render); });
        // other scripts may rewrite the ID text; re-apply the mask when they do
        new MutationObserver(function () { render(v); }).observe(el, { childList: true, characterData: true, subtree: true });
        render(v);
    }
    function init() { document.querySelectorAll('[data-tid]').forEach(setup); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
