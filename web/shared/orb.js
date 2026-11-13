// <sonara-orb mode="idle|listening|thinking|speaking|success|error|card"> — Sonara's companion.
// One solid circular body, white eyes up and to the right. Listening: turns lavender and the
// circle morphs into a speech wave. Thinking: shrinks into the middle of three pulsing dots.
// Theme per mode with CSS --orb-idle / --orb-listening / … Optional: orb.level = 0..1 (mic loudness) drives the wave; otherwise a synthetic speech rhythm.
(() => {
  const N = 96, HALF = N / 2;                    // outline points: top edge L→R, then bottom edge R→L
  const ORANGE = "#F2994A", LAVENDER = "#A97BF0";
  const GREEN = "#78C83F", RED = "#E5484D";
  const PAL = { card: "#ECDDF8", idle: ORANGE, speaking: ORANGE, thinking: ORANGE, success: GREEN, error: RED, listening: LAVENDER };
  const OPEN = { card: 1, idle: 1, speaking: 1, thinking: 1, success: 1, error: 0.45, listening: 1 };

  // Body: a plain circle. u = 0..1 left→right.
  const circle = (u, top) => {
    const a = top ? Math.PI - u * Math.PI : Math.PI + u * Math.PI;
    return [Math.cos(a) * 72, -Math.sin(a) * 72];
  };
  // Card: rounded rectangle, half-size w × h, corner r (viewBox units, set by the page with --orb-box-*)
  const box = (u, top, w, h, r) => {
    const x = (u - 0.5) * 2 * w, e = Math.abs(x) - (w - r);
    const y = e > 0 ? h - r + Math.sqrt(Math.max(0, r * r - e * e)) : h;
    return [x, top ? -y : y];
  };
  const wave = (u, top, t, amp) => {               // speech-wave ribbon
    const x = (u - 0.5) * 2, env = Math.pow(1 - x * x, 1.6), k = t * 5;
    const h = Math.abs(Math.sin(x * 8 + k) * 0.7 + Math.sin(x * 15 - k * 1.2) * 0.3);
    const hw = 4 + env * (8 + 40 * amp * h);
    return [x * 112, top ? -hw : hw];
  };
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const rgb = c => `rgb(${c.map(Math.round).join(",")})`;
  const ease = (cur, target, k) => cur + (target - cur) * k;
  const f1 = n => n.toFixed(1);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  const EYES = [[8, -22], [34, -26]];             // up-right, slanted pills

  class SonaraOrb extends HTMLElement {
    static observedAttributes = ["mode"];
    constructor() {
      super();
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = `<style>:host{display:block;cursor:pointer;-webkit-tap-highlight-color:transparent}
        svg{width:100%;height:100%;display:block;overflow:visible}</style>
        <svg viewBox="-130 -115 260 230" aria-hidden="true">
          <g class="all">
            <path class="body"/>
            <g class="face" fill="#fff" stroke="#fff" stroke-linecap="round">
              <rect class="eye"/><rect class="eye"/>
              <path class="happy" fill="none" stroke-width="8"/>
              <ellipse class="mouth"/>
            </g>
          </g>
          <circle class="dot"/><circle class="dot"/>
        </svg>`;
      const q = s => root.querySelector(s);
      this.el = { all: q(".all"), body: q(".body"), face: q(".face"), eyes: root.querySelectorAll(".eye"),
                  happy: q(".happy"), mouth: q(".mouth"), dots: root.querySelectorAll(".dot") };
      this.mode = "idle"; this.level = null;
      this.s = { wave: 0, think: 0, look: [0, 0], lookT: [0, 0], blink: 0, squish: 0, happy: 0, open: 1,
                 talk: 0, think: 0, box: 0, boxSize: [125, 22, 3], amp: 0, col: null };
      this.nextBlink = 0; this.t0 = performance.now();
    }
    attributeChangedCallback(_, __, v) { this.mode = PAL[v] ? v : "idle"; }
    connectedCallback() {
      this.onMove = e => this.lookAt(e.clientX, e.clientY);
      this.onFocus = e => { const r = e.target.getBoundingClientRect?.(); if (r) this.lookAt(r.x + r.width / 2, r.y + r.height / 2); };
      addEventListener("pointermove", this.onMove, { passive: true });
      addEventListener("focusin", this.onFocus);
      this.addEventListener("pointerdown", () => { this.s.squish = 1; });
      this.raf = requestAnimationFrame(t => this.frame(t));
    }
    disconnectedCallback() {
      cancelAnimationFrame(this.raf);
      removeEventListener("pointermove", this.onMove); removeEventListener("focusin", this.onFocus);
    }
    // Body colour: the page can theme each mode with --orb-<mode> (6-digit hex), else the built-in palette
    colour(m) { const v = getComputedStyle(this).getPropertyValue("--orb-" + m).trim(); return /^#[0-9a-f]{6}$/i.test(v) ? v : PAL[m]; }
    // Glance toward a screen point (pointer, a focused button, a new card)
    lookAt(x, y) {
      const r = this.getBoundingClientRect(), dx = x - (r.x + r.width / 2), dy = y - (r.y + r.height / 2);
      const m = Math.hypot(dx, dy) || 1, k = Math.min(1, m / 400);
      this.s.lookT = [dx / m * k, dy / m * k]; this.lastLook = performance.now();
    }
    lookAtEl(el) { const r = el.getBoundingClientRect(); this.lookAt(r.x + r.width / 2, r.y + r.height / 2); }

    frame(now) {
      this.raf = requestAnimationFrame(t => this.frame(t));
      if (document.hidden) return;
      const s = this.s, calm = reduce.matches ? 0.25 : 1, t = (now - this.t0) / 1000 * calm;
      s.wave = ease(s.wave, this.mode === "listening" ? 1 : 0, 0.09);
      s.happy = ease(s.happy, this.mode === "success" ? 1 : 0, 0.15);
      s.open = ease(s.open, OPEN[this.mode], 0.15);
      s.box = ease(s.box, this.mode === "card" ? 1 : 0, 0.12);
      s.think = ease(s.think, this.mode === "thinking" ? 1 : 0, 0.12);
      s.talk = ease(s.talk, this.mode === "speaking" ? 1 : 0, 0.15);
      s.squish = ease(s.squish, 0, 0.12);
      if (this.colMode !== this.mode) {
        this.colMode = this.mode; this.target = hex(this.colour(this.mode));
        if (this.mode === "card") { const cs = getComputedStyle(this), n = (k, d) => parseFloat(cs.getPropertyValue("--orb-box-" + k)) || d;
          s.boxSize = [n("w", 125), n("h", 22), n("r", 3)]; }
      }
      const target = this.target;
      s.col ??= target;
      s.col = s.col.map((v, j) => ease(v, target[j], 0.08));
      if (now - (this.lastLook || 0) > 2500 && now > (this.nextGlance || 0)) {   // idle: look around on its own
        const a = Math.random() * Math.PI * 2, r = Math.random() < 0.3 ? 0 : 0.4 + Math.random() * 0.6;
        s.lookT = [Math.cos(a) * r, Math.sin(a) * r * 0.8];
        this.nextGlance = now + 700 + Math.random() * 1800;
      }
      s.look = s.look.map((v, i) => ease(v, s.lookT[i], 0.16));   // quick, saccade-like
      if (now > this.nextBlink) { s.blink = 1; this.nextBlink = now + 2500 + Math.random() * 3500; }
      s.blink = ease(s.blink, 0, 0.25);
      const synth = 0.45 + 0.35 * Math.sin(t * 7.3) * Math.sin(t * 2.1) + 0.2 * Math.sin(t * 13.7);
      s.amp = ease(s.amp, this.level ?? Math.max(0.15, synth), 0.2);
      this.draw(t, calm);
    }

    draw(t, calm) {
      const { s, el } = this, breathe = 1 + Math.sin(t * 1.4) * 0.015;
      const sx = (1 + s.squish * 0.12) * breathe, sy = (1 - s.squish * 0.12) / breathe;
      const w = s.wave * s.wave * (3 - 2 * s.wave);

      // body: circle ↔ wave
      const pts = [];
      for (let i = 0; i < N; i++) {
        const top = i < HALF, u = top ? i / (HALF - 1) : 1 - (i - HALF) / (HALF - 1);
        const [cx, cy] = circle(u, top), [wx, wy] = wave(u, top, t, s.amp);
        const [bx, by] = box(u, top, ...s.boxSize), b = s.box * s.box * (3 - 2 * s.box);
        const px = cx + (wx - cx) * w, py = cy + (wy - cy) * w;
        pts.push([(px + (bx - px) * b) * (b > 0.99 ? 1 : sx), (py + (by - py) * b) * (b > 0.99 ? 1 : sy)]);
      }
      let d = "";
      for (let i = 0; i <= N; i++) {                          // quadratic smoothing through midpoints
        const p = pts[i % N], q = pts[(i + 1) % N], mx = (p[0] + q[0]) / 2, my = (p[1] + q[1]) / 2;
        d += i ? `Q${f1(p[0])} ${f1(p[1])} ${f1(mx)} ${f1(my)}` : `M${f1(mx)} ${f1(my)}`;
      }
      const fill = rgb(s.col);
      el.body.setAttribute("d", d + "Z"); el.body.setAttribute("fill", fill);

      // thinking: body shrinks into the middle dot, two dots slide out, all three pulse in a wave
      const th = s.think, pf = i => 1 + 0.22 * Math.sin(t * 6 - i * 1.1) * calm;   // 0.78..1.22, staggered
      el.all.setAttribute("transform", `scale(${(1 - th * (1 - 0.22 * pf(1))).toFixed(3)})`);   // body = middle dot
      el.dots.forEach((c, i) => {
        const n = i ? 2 : 0, p = pf(n);
        c.setAttribute("cx", f1((i ? 44 : -44) * th)); c.setAttribute("cy", 0);
        c.setAttribute("r", f1(16 * th * p)); c.setAttribute("fill", fill);
        c.setAttribute("opacity", (th * (0.55 + 0.45 * (p - 0.78) / 0.44)).toFixed(2));
      });

      // face: white slanted pill eyes up-right; fades out as the body becomes a wave
      el.face.setAttribute("opacity", Math.max(0, 1 - w * 1.6 - s.think * 1.6 - s.box * 2.5).toFixed(2));
      const ox = s.look[0] * 12, oy = s.look[1] * 9;
      const h = Math.max(3, 26 * s.open * (1 - s.blink * 0.9));
      const happy = s.happy > 0.5;
      el.eyes.forEach((e, i) => {
        const [ex, ey] = EYES[i], x = ex + ox, y = ey + oy;
        e.setAttribute("x", f1(x - 6)); e.setAttribute("y", f1(y - h / 2));
        e.setAttribute("width", 12); e.setAttribute("height", f1(h)); e.setAttribute("rx", 6);
        e.setAttribute("transform", `rotate(-18 ${f1(x)} ${f1(y)})`);
        e.setAttribute("opacity", happy ? 0 : 1);
      });
      el.happy.setAttribute("d", EYES.map(([ex, ey]) => { const x = ex + ox, y = ey + oy;
        return `M${f1(x - 10)} ${f1(y + 5)}Q${f1(x)} ${f1(y - 11)} ${f1(x + 10)} ${f1(y + 5)}`; }).join(""));
      el.happy.setAttribute("opacity", happy ? 1 : 0);
      const m = s.talk * (0.3 + 0.7 * Math.abs(Math.sin(t * 8)));
      el.mouth.setAttribute("cx", f1(22 + ox)); el.mouth.setAttribute("cy", f1(4 + oy));
      el.mouth.setAttribute("rx", f1(7 * s.talk)); el.mouth.setAttribute("ry", f1(6 * m));
    }
  }
  customElements.define("sonara-orb", SonaraOrb);
})();
