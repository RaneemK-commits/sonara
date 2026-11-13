// <sonara-intro> — Sonara's start-up animation, usable anywhere (needs orb.js loaded first).
// The logo slides in from the left and stops in the middle, the wordmark wipes back into the
// soundmark, the five bars swell and fuse into a circle, and the circle wakes up as the orb.
//   <sonara-intro autoplay>                 plays once, ends on the orb in the middle
//   <sonara-intro autoplay land="#orb">     then flies the orb onto that element and fades away (boot screen)
//   <sonara-intro inline>                   sits in the page flow instead of covering the screen
// el.play() → Promise. Events: "reveal" (the orb starts flying to `land`: start showing the UI), "done".
// Theme with CSS: --intro-bg, --intro-size (mark height in px), --ink, --orb-idle.
(() => {
  const BARS = [10, 20, 32, 22, 12];          // soundmark bar lengths, 8 units apart (same as #i-mark)
  const T = { slide: 1100, hold: 1350, word: 1850, morph: 2950, fly: 3450, end: 4150 };   // ms
  const clamp = v => Math.max(0, Math.min(1, v));
  const seg = (t, a, b) => clamp((t - a) / (b - a));
  const lerp = (a, b, k) => a + (b - a) * k;
  const outQuart = x => 1 - Math.pow(1 - x, 4);
  const inOut = x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  const smooth = x => x * x * (3 - 2 * x);
  const hex = h => /^#[0-9a-f]{6}$/i.test(h) ? [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)) : null;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");

  class SonaraIntro extends HTMLElement {
    constructor() {
      super();
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = `<style>
          :host { position: fixed; inset: 0; z-index: 50; display: block; overflow: hidden; }
          :host([inline]) { position: relative; inset: auto; min-height: 240px; }
          .bg { position: absolute; inset: 0; background: var(--intro-bg, #FBF7F3); }
          .mark, .word, sonara-orb { position: absolute; left: 0; top: 0; transform-origin: 50% 50%; }
          .mark { overflow: visible; }
          .word { margin: 0; font: 700 64px/1 var(--intro-font, "Inter", "Segoe UI", system-ui, sans-serif);
            letter-spacing: -.02em; color: var(--ink, #161616); white-space: nowrap; transform-origin: 0 50%; }
          sonara-orb { opacity: 0; }
        </style>
        <div class="bg"></div>
        <svg class="mark" viewBox="-20 -20 40 40" aria-hidden="true">
          <defs><filter id="goo" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="0" result="b"/>
            <feColorMatrix in="b" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 24 -10" result="goo"/>
            <feComposite in="SourceGraphic" in2="goo" operator="atop"/>
          </filter>
          <clipPath id="blob">${BARS.map(() => "<rect/>").join("")}</clipPath></defs>
          <g>${BARS.map(() => "<rect/>").join("")}<circle class="glow" r="0" clip-path="url(#blob)"/></g>
        </svg>
        <p class="word" aria-hidden="true">Sonara</p>
        <sonara-orb mode="idle" aria-hidden="true"></sonara-orb>`;
      const q = s => root.querySelector(s);
      this.el = { bg: q(".bg"), mark: q(".mark"), word: q(".word"), orb: q("sonara-orb"),
                  bars: root.querySelectorAll("svg > g rect"), shape: root.querySelectorAll("clipPath rect"), glow: q(".glow"), blur: q("feGaussianBlur"), g: q("svg > g") };
    }
    connectedCallback() {
      this.setAttribute("role", "img");
      this.setAttribute("aria-label", "Sonara");
      if (this.hasAttribute("autoplay")) this.play();
    }
    disconnectedCallback() { cancelAnimationFrame(this.raf); clearTimeout(this.to); }

    measure() {
      const r = this.getBoundingClientRect(), cs = getComputedStyle(this), { el } = this;
      const H = parseFloat(cs.getPropertyValue("--intro-size")) || Math.max(48, Math.min(140, Math.min(r.width, r.height) * .16));
      el.word.style.fontSize = H * .8 + "px";
      el.mark.style.width = el.mark.style.height = H + "px";
      const w = el.word.getBoundingClientRect();
      let D = H * 1.9, land = null;                       // D: diameter of the finished orb's body
      const target = this.getAttribute("land") && document.querySelector(this.getAttribute("land"));
      if (target) {
        const b = target.getBoundingClientRect();
        land = { x: b.x + b.width / 2 - r.x, y: b.y + b.height / 2 - r.y };
        D = b.width * 144 / 260;                          // orb.js: body radius 72 in a 260-wide viewBox
      }
      el.orb.style.width = D * 260 / 144 + "px";
      el.orb.style.height = D * 230 / 144 + "px";
      this.geo = { W: r.width, SH: r.height, H, gap: H * .32, wordW: w.width, wordH: w.height, D, land,
                   ink: hex(cs.getPropertyValue("--ink").trim()) || [22, 22, 22],
                   orange: hex(cs.getPropertyValue("--orb-idle").trim()) || [242, 153, 74] };
    }

    // Draw the frame at time t (ms). Deterministic, so it can be scrubbed or recorded.
    render(t) {
      const { el, geo: g } = this;
      const { H, gap } = g, lockW = H + gap + g.wordW;

      // 1. slide in from the left and stop with the lockup centred
      const sl = outQuart(seg(t, 0, T.slide));
      const left = lerp(-lockW - H, (g.W - lockW) / 2, sl);
      // 2. the wordmark wipes back into the mark while the mark glides to the exact centre
      const wd = seg(t, T.hold, T.word), wde = inOut(wd);
      let cx = lerp(left + H / 2, g.W / 2, wde), cy = g.SH / 2;
      // 4. fly to the landing spot
      if (g.land) { const f = inOut(seg(t, T.fly, T.end)); cx = lerp(cx, g.land.x, f); cy = lerp(cy, g.land.y, f); }

      el.word.style.transform = `translate(${cx + H / 2 + gap - wde * gap}px, ${cy - g.wordH / 2}px)`;
      el.word.style.clipPath = `inset(-20% ${(wde * 100).toFixed(2)}% -20% 0)`;
      el.word.style.opacity = 1 - smooth(seg(t, T.hold + 200, T.word));

      // 3. morph, liquid: each bar swells into a circle of the orb's size and drifts to the centre
      //    (middle bar first, outer bars last); a gooey filter melts them together on the way,
      //    so the five bars pour into one round body with no hard step
      const m = seg(t, T.word - 150, T.morph);
      const talk = 1 - sl;                              // bars bounce like a level meter while sliding
      el.bars.forEach((r, i) => {
        const p = inOut(clamp((m - Math.abs(i - 2) * .08) / .84));
        const base = Math.max(2, BARS[i] * (1 + talk * .55 * Math.sin(t / 85 + i * 1.9))) + 2.6;
        const x = lerp(-16 + 8 * i, 0, p), w = lerp(2.6, 40, p * p * p), len = lerp(base, 40, p * p);   // gather first, swell last
        r.setAttribute("x", (x - w / 2).toFixed(2)); r.setAttribute("width", w.toFixed(2));
        r.setAttribute("y", (-len / 2).toFixed(2)); r.setAttribute("height", len.toFixed(2));
        r.setAttribute("rx", (Math.min(w, len) / 2).toFixed(2));
        for (const a of ["x", "y", "width", "height", "rx"]) el.shape[i].setAttribute(a, r.getAttribute(a));
      });
      const goo = 2.6 * Math.sin(Math.PI * m);         // only while melting: the logo and the final circle stay crisp
      el.blur.setAttribute("stdDeviation", goo.toFixed(2));
      if (goo > .05) el.g.setAttribute("filter", "url(#goo)"); else el.g.removeAttribute("filter");
      // colour: orange spreads out from the centre of the ink blob (it lights up), never a muddy ink/orange blend
      el.g.setAttribute("fill", `rgb(${g.ink})`);
      el.glow.setAttribute("fill", `rgb(${g.orange})`);
      el.glow.setAttribute("r", (24 * inOut(seg(m, .45, .85))).toFixed(2));
      const s = lerp(1, g.D / H, inOut(m));
      el.mark.style.transform = `translate(${cx - H / 2}px, ${cy - H / 2}px) scale(${s.toFixed(4)})`;

      // the finished circle becomes the orb, which wakes up: eyes open, a small squash
      const awake = t >= T.morph, o = el.orb;
      el.mark.style.opacity = awake ? 0 : 1;
      o.style.opacity = awake ? 1 : 0;
      o.style.transform = `translate(${cx - o.offsetWidth / 2}px, ${cy - o.offsetHeight / 2}px)`;
      if (awake && !this.woke && o.s) {
        this.woke = true;
        o.s.blink = 1; o.s.squish = .45; o.s.lookT = [.45, -.35]; o.lastLook = performance.now();
      }

      if (g.land) el.bg.style.opacity = 1 - smooth(seg(t, T.fly + 100, T.end));
      if (g.land && !this.revealed && t >= T.fly) { this.revealed = true; this.dispatchEvent(new Event("reveal")); }
    }

    async play() {
      cancelAnimationFrame(this.raf); clearTimeout(this.to);
      await customElements.whenDefined("sonara-orb");
      if (document.fonts) await document.fonts.ready;
      this.measure();
      this.woke = this.revealed = false;
      this.el.bg.style.opacity = 1;
      const quick = reduce.matches;   // reduced motion: three still steps (logo, orb, landed), no travel
      return new Promise(done => {
        const t0 = performance.now();
        const step = now => {
          const e = now - t0, t = quick ? (e < 1000 ? T.hold : e < 1800 ? T.morph : T.end) : Math.min(e, T.end);
          this.render(t);
          if (quick ? e >= 1800 : e >= T.end) { this.dispatchEvent(new Event("done")); done(); }
          else next();
        };
        // next frame on rAF, with a timer fallback: if rAF stalls (hidden or throttled tab) the
        // boot still finishes, so the patient screen is never left covered by the intro
        const next = () => {
          let fired = false;
          const go = now => { if (fired) return; fired = true; cancelAnimationFrame(this.raf); clearTimeout(this.to); step(now); };
          this.raf = requestAnimationFrame(go);
          this.to = setTimeout(() => go(performance.now()), 100);
        };
        next();
      });
    }
    // Hand the orb's gaze over to the page's own orb so the swap is seamless
    handOff(orb) {
      const mine = this.el.orb.s;
      if (orb && orb.s && mine) { orb.s.look = mine.look.slice(); orb.s.lookT = mine.lookT.slice(); orb.lastLook = this.el.orb.lastLook; }
    }
  }
  SonaraIntro.TIMELINE = T;
  customElements.define("sonara-intro", SonaraIntro);
})();
