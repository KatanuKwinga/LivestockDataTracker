/* Grassland at dusk, drawn on a <canvas> behind the sign-in pages.
   Everything is drawn with code (no image or video files), so it loads
   instantly. Visitors who ask their device for reduced motion get one still
   frame instead of the animation. */
(function () {
  const canvas = document.getElementById("meadow");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let W = 0, H = 0, horizon = 0, blades = [], trees = [], hills = [], motes = [];

  function rand(a, b) { return a + Math.random() * (b - a); }

  // Build the scene once for the current window size: hills, trees, grass.
  function build() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    horizon = H * 0.62;

    hills = [
      { y: horizon - 18, amp: 22, color: "rgba(98,108,72,0.55)", seed: rand(0, 99) },
      { y: horizon + 6, amp: 14, color: "rgba(54,64,42,0.9)", seed: rand(0, 99) },
    ];

    // Flat-topped acacia trees: a forked trunk under a wide, layered canopy.
    trees = [];
    for (const [fx, scale] of [[0.06, 1.0], [0.27, 0.62], [0.47, 0.42], [0.63, 0.5], [0.95, 0.85]]) {
      const w = Math.min(W, 1400) * 0.2 * scale, h = w * 0.62;
      const blobs = [];
      for (let i = 0; i < 70; i++) {
        const a = rand(-1, 1), layer = rand(0, 1);
        blobs.push({ x: a * w * 0.5 * (1 - layer * 0.25), y: -layer * h * 0.16 + rand(-h * 0.03, h * 0.03),
                     rx: rand(w * 0.04, w * 0.1), ry: rand(h * 0.025, h * 0.06) });
      }
      trees.push({ x: fx * W, base: horizon + 10 + scale * 6, w, h, blobs, phase: rand(0, 6), shade: scale });
    }

    // Grass in three depths: far blades short and pale, near ones tall and dark.
    blades = [];
    const layers = [
      { n: 0.55, y0: horizon + 8, y1: horizon + 40, h: [10, 22], w: 1.4, c: [92, 104, 64], flex: 0.6 },
      { n: 0.75, y0: horizon + 30, y1: H * 0.86, h: [28, 60], w: 2.2, c: [62, 74, 44], flex: 0.8 },
      { n: 0.6, y0: H * 0.82, y1: H + 20, h: [60, 130], w: 3.2, c: [36, 46, 27], flex: 1.0 },
    ];
    for (const L of layers) {
      for (let i = 0, count = Math.round(W * L.n); i < count; i++) {
        const tone = rand(-14, 14), light = Math.random() < 0.08 ? 28 : 0;
        blades.push({
          x: rand(-20, W + 20), y: rand(L.y0, L.y1), h: rand(L.h[0], L.h[1]), w: L.w * rand(0.7, 1.3),
          lean: rand(-0.25, 0.25), flex: L.flex * rand(0.8, 1.2), phase: rand(0, 6),
          color: `rgb(${L.c[0] + tone + light},${L.c[1] + tone + light},${L.c[2] + tone * 0.6 + light * 0.6})`,
        });
      }
    }
    blades.sort((a, b) => a.y - b.y);   // draw from the back to the front

    motes = Array.from({ length: 36 }, () => ({ x: rand(0, W), y: rand(horizon - 120, horizon + 40), r: rand(0.6, 1.6), s: rand(4, 12), p: rand(0, 6) }));
  }

  // Wind: two slow waves rolling across the field, plus occasional gusts.
  function wind(x, t) {
    const gust = (Math.sin(t * 0.21) + 1) * 0.5 * 0.9;
    return Math.sin(x * 0.0042 + t * 1.05) * 0.55 + Math.sin(x * 0.013 - t * 0.63) * 0.25 + gust;
  }

  function draw(t) {
    const sky = ctx.createLinearGradient(0, 0, 0, horizon + 20);
    sky.addColorStop(0, "#1c2218"); sky.addColorStop(0.45, "#36402c"); sky.addColorStop(0.82, "#8a875e"); sky.addColorStop(1, "#bfae7c");
    ctx.fillStyle = sky; ctx.fillRect(0, 0, W, H);
    const sun = ctx.createRadialGradient(W * 0.72, horizon - 10, 4, W * 0.72, horizon - 10, W * 0.45);
    sun.addColorStop(0, "rgba(242,224,170,0.55)"); sun.addColorStop(0.25, "rgba(220,198,140,0.22)"); sun.addColorStop(1, "rgba(220,198,140,0)");
    ctx.fillStyle = sun; ctx.fillRect(0, 0, W, H);

    for (const hl of hills) {
      ctx.beginPath(); ctx.moveTo(0, H);
      for (let x = 0; x <= W + 10; x += 10) {
        ctx.lineTo(x, hl.y - Math.sin(x * 0.0021 + hl.seed) * hl.amp - Math.sin(x * 0.0057 + hl.seed * 2) * hl.amp * 0.45);
      }
      ctx.lineTo(W, H); ctx.closePath(); ctx.fillStyle = hl.color; ctx.fill();
    }

    for (const tr of trees) {
      const sway = Math.sin(t * 0.55 + tr.phase) * tr.w * 0.012 + wind(tr.x, t) * tr.w * 0.008;
      const top = tr.base - tr.h * 0.62;
      ctx.strokeStyle = ctx.fillStyle = `rgba(30,37,24,${0.55 + tr.shade * 0.35})`;
      ctx.lineCap = "round"; ctx.lineWidth = Math.max(1.5, tr.w * 0.028);
      ctx.beginPath(); ctx.moveTo(tr.x, tr.base);
      ctx.quadraticCurveTo(tr.x - tr.w * 0.02, tr.base - tr.h * 0.3, tr.x - tr.w * 0.14 + sway * 0.7, top + tr.h * 0.02);
      ctx.moveTo(tr.x, tr.base - tr.h * 0.28);
      ctx.quadraticCurveTo(tr.x + tr.w * 0.06, tr.base - tr.h * 0.45, tr.x + tr.w * 0.18 + sway * 0.7, top + tr.h * 0.03);
      ctx.stroke();
      for (const b of tr.blobs) {
        ctx.beginPath(); ctx.ellipse(tr.x + b.x + sway, top + b.y, b.rx, b.ry, 0, 0, Math.PI * 2); ctx.fill();
      }
    }

    const haze = ctx.createLinearGradient(0, horizon - 60, 0, horizon + 60);
    haze.addColorStop(0, "rgba(200,186,140,0)"); haze.addColorStop(0.5, "rgba(200,186,140,0.12)"); haze.addColorStop(1, "rgba(200,186,140,0)");
    ctx.fillStyle = haze; ctx.fillRect(0, horizon - 60, W, 120);

    for (const b of blades) {
      const bend = (wind(b.x, t) * 0.32 + Math.sin(t * 2.1 + b.phase) * 0.05 + b.lean) * b.h * b.flex;
      const tipX = b.x + bend, tipY = b.y - b.h + Math.abs(bend) * 0.25;
      const cx = b.x + bend * 0.35, cy = b.y - b.h * 0.55;
      ctx.beginPath();
      ctx.moveTo(b.x - b.w, b.y);
      ctx.quadraticCurveTo(cx - b.w * 0.4, cy, tipX, tipY);
      ctx.quadraticCurveTo(cx + b.w * 0.4, cy, b.x + b.w, b.y);
      ctx.closePath(); ctx.fillStyle = b.color; ctx.fill();
    }

    ctx.fillStyle = "rgba(240,224,180,0.35)";
    for (const m of motes) {
      const x = (m.x + t * m.s) % (W + 20) - 10, y = m.y + Math.sin(t * 0.8 + m.p) * 6;
      ctx.beginPath(); ctx.arc(x, y, m.r, 0, Math.PI * 2); ctx.fill();
    }
  }

  const start = performance.now();
  function frame(now) {
    if (!document.hidden) draw((now - start) / 1000);   // pause while the tab is hidden
    requestAnimationFrame(frame);
  }

  build();
  draw(4);
  if (!reduceMotion) requestAnimationFrame(frame);
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { build(); draw((performance.now() - start) / 1000); }, 150);
  });
})();
