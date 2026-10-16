// Hero: animated bull vs bear fight.
// Each animal's wireframe artwork is cut into a mesh and bent every frame (rearing,
// head toss, galloping legs, breathing) so the whole body moves, then the two are
// choreographed through pace -> wind-up -> charge -> clash -> grapple -> separate.
(function () {
    const canvas = document.getElementById('heroCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const SCALE = parseFloat(canvas.dataset.scale) || 0.4;   // fighter width as a fraction of the stage
    const MSCALE = parseFloat(canvas.dataset.mscale) || 0.5; // same, on phones
    const BASE = parseFloat(canvas.dataset.base) || 0.93;    // ground line as a fraction of stage height
    const CYCLE = 6.4;          // seconds per round
    const COLS = 20, ROWS = 14; // mesh resolution
    const SW = 480;             // working width of each fighter bitmap

    const clamp01 = t => Math.max(0, Math.min(1, t));
    const lerp = (a, b, t) => a + (b - a) * t;
    const ss = (a, b, x) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); };
    const easeIn = t => t * t * t;
    const easeOut = t => 1 - Math.pow(1 - t, 3);

    // ---- Fighter: source bitmap + deformation mesh ------------------------------------------
    function makeFighter(src, dir) {
        const f = { dir, ready: false, img: new Image(), sw: SW, sh: SW * 2 / 3 };
        f.img.onload = () => {
            f.sh = Math.round(SW * f.img.naturalHeight / f.img.naturalWidth);
            f.src = document.createElement('canvas');
            f.src.width = f.sw; f.src.height = f.sh;
            f.src.getContext('2d').drawImage(f.img, 0, 0, f.sw, f.sh);
            f.mx = f.sw * 0.4; f.my = f.sh * 0.6;
            f.off = document.createElement('canvas');
            f.off.width = Math.round(f.sw * 1.8); f.off.height = Math.round(f.sh * 1.8);
            f.octx = f.off.getContext('2d');
            // which mesh cells contain any artwork (skip empty ones)
            f.active = null;
            try {
                const data = f.src.getContext('2d').getImageData(0, 0, f.sw, f.sh).data;
                f.active = [];
                for (let j = 0; j < ROWS; j++) for (let i = 0; i < COLS; i++) {
                    const x0 = Math.floor(i * f.sw / COLS), x1 = Math.ceil((i + 1) * f.sw / COLS);
                    const y0 = Math.floor(j * f.sh / ROWS), y1 = Math.ceil((j + 1) * f.sh / ROWS);
                    let hit = false;
                    for (let y = y0; y < y1 && !hit; y += 3) for (let x = x0; x < x1; x += 3) {
                        if (data[(y * f.sw + x) * 4 + 3] > 20) { hit = true; break; }
                    }
                    f.active.push(hit);
                }
            } catch (e) { f.active = null; }
            f.ready = true;
        };
        f.img.src = src;
        // animation state (smoothed)
        f.s = { rear: 0, head: 0, stride: 0.4, paw: 0, squash: 0 };
        f.legPhase = Math.random() * 6; f.pawPhase = 0; f.breath = Math.random() * 6;
        return f;
    }

    function rot(x, y, px, py, a) {
        const c = Math.cos(a), s = Math.sin(a), dx = x - px, dy = y - py;
        return [px + dx * c - dy * s, py + dx * s + dy * c];
    }

    // Bend the artwork: (u,v) in 0..1 image space -> position in the fighter bitmap
    function deform(f, u, v, time) {
        const { sw, sh, dir } = f, s = f.s;
        const fx = dir > 0 ? u : 1 - u;           // 0 = tail end, 1 = head end
        let x = u * sw, y = v * sh;

        // galloping / walking legs (lower body only)
        const legMask = ss(0.55, 0.88, v);
        if (legMask > 0) {
            const ph = f.legPhase + fx * 5.2;
            x += dir * Math.sin(ph) * s.stride * sw * 0.075 * legMask;
            y -= Math.max(0, Math.cos(ph)) * s.stride * sh * 0.09 * legMask;
            // pawing: front legs scrape and lift
            const frontMask = ss(0.6, 0.82, fx) * legMask;
            y -= Math.abs(Math.sin(f.pawPhase)) * s.paw * sh * 0.16 * frontMask;
            x -= dir * Math.abs(Math.sin(f.pawPhase)) * s.paw * sw * 0.04 * frontMask;
        }

        // squash on impact
        const gy = sh * 0.94;
        x = sw / 2 + (x - sw / 2) * (1 - 0.05 * s.squash);
        y = gy + (y - gy) * (1 + 0.05 * s.squash);

        // breathing
        y -= Math.sin(f.breath) * 0.007 * sh * (1 - v);

        // tail swish
        if (fx < 0.18 && v < 0.55) y += Math.sin(time * 7 + fx * 22) * 0.035 * sh * (0.18 - fx) / 0.18;

        // rearing: the front half rotates up around the hips
        const pivotX = (dir > 0 ? 0.3 : 0.7) * sw, pivotY = 0.86 * sh;
        const wBody = ss(0.18, 0.62, fx);
        if (wBody > 0) [x, y] = rot(x, y, pivotX, pivotY, -dir * s.rear * Math.PI / 180 * wBody);

        // head / neck toss
        const nx = (dir > 0 ? 0.68 : 0.32) * sw, ny = 0.42 * sh;
        const [px, py] = rot(nx, ny, pivotX, pivotY, -dir * s.rear * Math.PI / 180 * ss(0.18, 0.62, 0.68));
        const wHead = ss(0.62, 0.86, fx);
        if (wHead > 0) [x, y] = rot(x, y, px, py, -dir * s.head * Math.PI / 180 * wHead);

        return [x + f.mx, y + f.my];
    }

    function tri(c, img, x0, y0, x1, y1, x2, y2, u0, v0, u1, v1, u2, v2) {
        const D = u0 * (v1 - v2) + u1 * (v2 - v0) + u2 * (v0 - v1);
        if (Math.abs(D) < 1e-6) return;
        const a = (x0 * (v1 - v2) + x1 * (v2 - v0) + x2 * (v0 - v1)) / D;
        const cc = (x0 * (u2 - u1) + x1 * (u0 - u2) + x2 * (u1 - u0)) / D;
        const e = (x0 * (u1 * v2 - u2 * v1) + x1 * (u2 * v0 - u0 * v2) + x2 * (u0 * v1 - u1 * v0)) / D;
        const b = (y0 * (v1 - v2) + y1 * (v2 - v0) + y2 * (v0 - v1)) / D;
        const d = (y0 * (u2 - u1) + y1 * (u0 - u2) + y2 * (u1 - u0)) / D;
        const g = (y0 * (u1 * v2 - u2 * v1) + y1 * (u2 * v0 - u0 * v2) + y2 * (u0 * v1 - u1 * v0)) / D;
        // grow the clip a touch so neighbouring triangles overlap (no hairline seams)
        const mx = (x0 + x1 + x2) / 3, my = (y0 + y1 + y2) / 3;
        const grow = (x, y) => { const dx = x - mx, dy = y - my, l = Math.hypot(dx, dy) || 1; return [x + dx / l * 0.7, y + dy / l * 0.7]; };
        const p0 = grow(x0, y0), p1 = grow(x1, y1), p2 = grow(x2, y2);
        c.save();
        c.beginPath(); c.moveTo(p0[0], p0[1]); c.lineTo(p1[0], p1[1]); c.lineTo(p2[0], p2[1]); c.closePath(); c.clip();
        c.transform(a, b, cc, d, e, g);
        c.drawImage(img, 0, 0);
        c.restore();
    }

    function renderFighter(f, time) {
        const c = f.octx, { sw, sh } = f;
        c.clearRect(0, 0, f.off.width, f.off.height);
        const pts = [];
        for (let j = 0; j <= ROWS; j++) for (let i = 0; i <= COLS; i++) pts.push(deform(f, i / COLS, j / ROWS, time));
        const P = (i, j) => pts[j * (COLS + 1) + i];
        for (let j = 0; j < ROWS; j++) for (let i = 0; i < COLS; i++) {
            if (f.active && !f.active[j * COLS + i]) continue;
            const a = P(i, j), b = P(i + 1, j), d = P(i, j + 1), e = P(i + 1, j + 1);
            const u0 = i * sw / COLS, u1 = (i + 1) * sw / COLS, v0 = j * sh / ROWS, v1 = (j + 1) * sh / ROWS;
            tri(c, f.src, a[0], a[1], b[0], b[1], d[0], d[1], u0, v0, u1, v0, u0, v1);
            tri(c, f.src, b[0], b[1], e[0], e[1], d[0], d[1], u1, v0, u1, v1, u0, v1);
        }
    }

    const bull = makeFighter('assets/bull-wireframe-cutout.webp', 1);   // faces right
    const bear = makeFighter('assets/bear-wireframe-cutout.webp', -1);  // faces left

    // ---- Scene -------------------------------------------------------------------------------
    let W = 0, H = 0, candles = [], sparks = [], rings = [], dust = [];
    let flash = 0, shake = 0, lastT = 0, fired = {};

    function resize() {
        const r = canvas.parentElement.getBoundingClientRect();
        W = canvas.width = r.width; H = canvas.height = r.height;
        candles = Array.from({ length: Math.max(8, Math.floor(W / 62)) }, (_, i) => ({
            x: i * 62 + 30, y: Math.random() * H * 0.5 + 50, h: Math.random() * 80 + 30,
            up: Math.random() > 0.4, v: (Math.random() - 0.5) * 0.5,
        }));
    }

    function burst(x, y, power) {
        const n = Math.round(46 * power);
        for (let i = 0; i < n; i++) {
            const ang = Math.random() * Math.PI * 2, sp = (Math.random() * 9 + 2) * (0.6 + power * 0.5);
            sparks.push({ x, y, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp - 1.5, life: 1, r: Math.random() * 2.6 + 1,
                color: ['#f4d77b', '#d4af37', '#39e58c', '#e05b6b', '#ffffff'][Math.floor(Math.random() * 5)] });
        }
        rings.push({ x, y, r: 10, a: 0.9 * power }, { x, y, r: 4, a: 0.7 * power });
        flash = Math.max(flash, power); shake = Math.max(shake, 14 * power);
    }
    function puff(x, y, n) {
        for (let i = 0; i < n; i++) dust.push({ x: x + (Math.random() - 0.5) * 40, y, vx: (Math.random() - 0.5) * 2, vy: -Math.random() * 1.2, r: Math.random() * 8 + 5, a: 0.35 });
    }

    // Targets for one round; p = progress 0..1, winner = +1 bull pushes, -1 bear pushes
    function choreo(p, winner, fw) {
        const far = Math.max(W * 0.3, fw * 0.75), near = fw * 0.38;
        const bu = { rear: 0, head: -8, stride: 0.5, freq: 2.4, paw: 0, squash: 0 };
        const be = { rear: 4, head: 0, stride: 0.5, freq: 2.2, paw: 0, squash: 0 };
        let d = far, shove = 0, hop = 0, contact = false;
        if (p < 0.22) {                              // pace and glare
            d = far * (1 - 0.12 * ss(0, 0.22, p));
            bu.head = -12; be.rear = 6;
        } else if (p < 0.4) {                        // wind-up: bull paws, bear rears and roars
            const k = ss(0.22, 0.4, p);
            d = far * (0.88 + 0.08 * k);
            Object.assign(bu, { head: -22, rear: -5, stride: 0.15, freq: 2, paw: 1 });
            Object.assign(be, { rear: 32, head: 14, stride: 0.1, freq: 1.5 });
        } else if (p < 0.54) {                       // charge
            const k = easeIn((p - 0.4) / 0.14);
            d = lerp(far * 0.96, near, k);
            Object.assign(bu, { head: -26, rear: -7, stride: 1.25, freq: 11 });
            Object.assign(be, { head: 4, rear: lerp(30, 9, k), stride: 0.9, freq: 8 });
            hop = -Math.abs(Math.sin((p - 0.4) / 0.14 * Math.PI * 2.5)) * 14;
        } else if (p < 0.88) {                       // grapple
            const t = (p - 0.54) / 0.34, w = t * Math.PI * 2 * 3;
            d = near; contact = true;
            shove = winner * (28 + 26 * Math.sin(t * Math.PI * 2 * 1.3)) * ss(0, 0.2, t);
            Object.assign(bu, { rear: 12 + 16 * Math.sin(w), head: 16 * Math.sin(w + 1.1), stride: 0.4, freq: 7, squash: 0.5 + 0.5 * Math.sin(w * 2) });
            Object.assign(be, { rear: 24 + 12 * Math.sin(w + Math.PI), head: 10 * Math.sin(w + 2.6), stride: 0.35, freq: 6, squash: 0.5 + 0.5 * Math.sin(w * 2 + 1) });
        } else {                                     // break apart
            const k = easeOut((p - 0.88) / 0.12);
            d = lerp(near, far, k);
            Object.assign(bu, { head: -6, rear: 0, stride: 0.7, freq: 3 });
            Object.assign(be, { head: 0, rear: 0, stride: 0.7, freq: 3 });
        }
        return { bu, be, d, shove, hop, contact };
    }

    function drawFighter(f, cx, baseY, scale, alpha) {
        if (!f.ready) return;
        ctx.globalAlpha = alpha;
        ctx.drawImage(f.off, cx - (f.mx + f.sw / 2) * scale, baseY - (f.my + f.sh * 0.94) * scale, f.off.width * scale, f.off.height * scale);
        ctx.globalAlpha = 1;
    }

    function smoothTo(f, target, dt) {
        const k = 1 - Math.exp(-dt * 9);
        for (const key of ['rear', 'head', 'stride', 'paw', 'squash']) f.s[key] += (target[key] - f.s[key]) * k;
        f.legPhase += dt * target.freq * Math.PI * 2 * (0.5 + f.s.stride * 0.5);
        f.pawPhase += dt * 9;
        f.breath += dt * 2.6;
    }

    function frame(now) {
        const t0 = performance.now();
        const time = (now || 0) / 1000;
        const dt = Math.min(0.05, time - lastT || 0.016); lastT = time;
        const cycle = Math.floor(time / CYCLE);
        const p = (time % CYCLE) / CYCLE;
        const winner = cycle % 2 ? -1 : 1;

        ctx.clearRect(0, 0, W, H);
        ctx.save();
        if (shake > 0.3) { ctx.translate((Math.random() - 0.5) * shake, (Math.random() - 0.5) * shake); shake *= 0.9; }

        candles.forEach(c => {
            if (!reduce) c.y += c.v;
            if (c.y < 40 || c.y > H - 40 - c.h) c.v *= -1;
            ctx.strokeStyle = c.up ? 'rgba(57,229,140,.24)' : 'rgba(224,91,107,.24)';
            ctx.fillStyle = c.up ? 'rgba(57,229,140,.12)' : 'rgba(224,91,107,.12)';
            ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.moveTo(c.x, c.y - 18); ctx.lineTo(c.x, c.y + c.h + 18); ctx.stroke();
            ctx.fillRect(c.x - 8, c.y, 16, c.h);
        });

        if (bull.ready && bear.ready) {
            const fw = Math.min(W * (W < 700 ? MSCALE : SCALE), 460), scale = fw / SW;
            const baseY = H * BASE, mid = W / 2;
            const ch = reduce ? choreo(0.3, 1, fw) : choreo(p, winner, fw);
            smoothTo(bull, ch.bu, dt); smoothTo(bear, ch.be, dt);
            renderFighter(bull, time); renderFighter(bear, time);

            const bx = mid - ch.d + ch.shove, rx = mid + ch.d + ch.shove;
            const by = baseY + ch.hop;

            // events: big clash, then smaller hits as they trade blows
            const hit = (key, at, power) => { if (p >= at && !fired[cycle + key]) { fired[cycle + key] = 1; burst(mid + ch.shove, baseY - fw * 0.33, power); } };
            if (!reduce) { hit('a', 0.54, 1); hit('b', 0.63, 0.55); hit('c', 0.73, 0.7); hit('d', 0.83, 0.5); }
            if (!reduce && p > 0.4 && p < 0.54 && Math.random() < 0.5) { puff(bx, baseY, 1); }
            if (!reduce && ch.contact && Math.random() < 0.2) puff(bx, baseY, 1), puff(rx, baseY, 1);

            // ground shadows
            ctx.fillStyle = 'rgba(0,0,0,.35)';
            [bx, rx].forEach(x => { ctx.beginPath(); ctx.ellipse(x, baseY + 4, fw * 0.4, fw * 0.045, 0, 0, Math.PI * 2); ctx.fill(); });

            // motion trails during the charge
            if (p > 0.4 && p < 0.54) for (let g = 3; g >= 1; g--) { drawFighter(bull, bx - g * 22, by, scale, 0.12); drawFighter(bear, rx + g * 22, by, scale, 0.12); }
            drawFighter(bull, bx, by, scale, 0.88);
            drawFighter(bear, rx, by, scale, 0.88);
        }

        dust.forEach(d => {
            d.x += d.vx; d.y += d.vy; d.r += 0.4; d.a *= 0.95;
            ctx.fillStyle = 'rgba(212,190,120,' + d.a + ')';
            ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2); ctx.fill();
        });
        dust = dust.filter(d => d.a > 0.03);

        if (flash > 0.02) {
            const cy = H * BASE - Math.min(W * (W < 700 ? MSCALE : SCALE), 460) * 0.33;
            const gr = ctx.createRadialGradient(W / 2, cy, 0, W / 2, cy, 360);
            gr.addColorStop(0, 'rgba(255,240,190,' + (0.6 * flash) + ')');
            gr.addColorStop(1, 'rgba(212,175,55,0)');
            ctx.fillStyle = gr; ctx.fillRect(0, 0, W, H);
            flash *= 0.88;
        }
        rings.forEach(r => {
            r.r += 9; r.a *= 0.93;
            ctx.strokeStyle = 'rgba(244,215,123,' + r.a + ')'; ctx.lineWidth = 3;
            ctx.beginPath(); ctx.ellipse(r.x, r.y, r.r * 1.3, r.r * 0.8, 0, 0, Math.PI * 2); ctx.stroke();
        });
        rings = rings.filter(r => r.a > 0.04);
        sparks.forEach(s => {
            s.x += s.vx; s.y += s.vy; s.vy += 0.22; s.vx *= 0.985; s.life -= 0.022;
            ctx.globalAlpha = Math.max(0, s.life);
            ctx.fillStyle = s.color; ctx.shadowColor = s.color; ctx.shadowBlur = 8;
            ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill();
        });
        ctx.shadowBlur = 0; ctx.globalAlpha = 1;
        sparks = sparks.filter(s => s.life > 0);
        ctx.restore();

        window.__fightMs = (window.__fightMs || 0) * 0.9 + (performance.now() - t0) * 0.1;
        schedule();
    }

    // Pause the animation when the hero is scrolled out of view or the tab is hidden.
    let visible = true, rafId = 0;
    function schedule() {
        if (rafId || !visible || document.hidden) return;
        rafId = requestAnimationFrame(t => { rafId = 0; frame(t); });
    }
    if ('IntersectionObserver' in window) {
        new IntersectionObserver(entries => { visible = entries[0].isIntersecting; schedule(); }, { rootMargin: '80px' }).observe(canvas);
    }
    document.addEventListener('visibilitychange', schedule);

    resize();
    window.addEventListener('resize', resize);
    schedule();
})();
