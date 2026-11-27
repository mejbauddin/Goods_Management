/* ==========================================================================
   GoodsHub — chart engine
   Dependency-free SVG charts: area, donut, bars, sparkline, heatmap.
   Data is declared in the page with:
     <script type="application/json" data-chart="area" data-target="#id">…</script>
   ========================================================================== */
(function () {
  "use strict";

  const SVGNS = "http://www.w3.org/2000/svg";
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const palette = [
    "#6366f1", "#22d3ee", "#a855f7", "#10b981",
    "#f59e0b", "#ef4444", "#14b8a6", "#ec4899",
  ];

  const fmt = (n) => {
    const v = Number(n) || 0;
    if (Math.abs(v) >= 1000) return v.toLocaleString();
    return Number.isInteger(v) ? String(v) : v.toFixed(2);
  };

  const el = (tag, attrs = {}) => {
    const node = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    return node;
  };

  const easeOut = (t) => 1 - Math.pow(1 - t, 3);

  /** Run an animation frame loop from 0 to 1. */
  function animate(duration, onFrame) {
    if (reduceMotion) {
      onFrame(1);
      return;
    }
    const start = performance.now();
    function step(now) {
      const t = Math.min(1, (now - start) / duration);
      onFrame(easeOut(t), t);
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  /* ---------------- area chart ---------------- */
  function areaChart(host, cfg) {
    const values = (cfg.values || []).map((n) => Number(n) || 0);
    const labels = cfg.labels || values.map((_, i) => String(i + 1));

    host.innerHTML = "";
    if (!values.length) {
      host.innerHTML = '<div class="chart-empty">No records in this period.</div>';
      return;
    }

    const W = 1000, H = 300;
    const padL = 52, padR = 20, padT = 26, padB = 36;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const max = Math.max(...values, 1);
    const niceMax = max <= 4 ? 4 : Math.ceil(max / 4) * 4;
    const n = values.length;
    const x = (i) => (n === 1 ? padL + plotW / 2 : padL + (i * plotW) / (n - 1));
    const y = (v) => H - padB - (v / niceMax) * plotH;

    const svg = el("svg", {
      viewBox: `0 0 ${W} ${H}`,
      role: "img",
      "aria-label": cfg.aria || "Trend chart",
    });

    // gradient
    const gid = "areaGrad" + Math.random().toString(36).slice(2, 8);
    const defs = el("defs");
    const grad = el("linearGradient", { id: gid, x1: "0", y1: "0", x2: "0", y2: "1" });
    grad.appendChild(el("stop", { offset: "0%", "stop-color": "#6366f1", "stop-opacity": ".32" }));
    grad.appendChild(el("stop", { offset: "55%", "stop-color": "#22d3ee", "stop-opacity": ".16" }));
    grad.appendChild(el("stop", { offset: "100%", "stop-color": "#22d3ee", "stop-opacity": "0" }));
    defs.appendChild(grad);
    svg.appendChild(defs);

    // horizontal grid + y labels
    const axis = el("g", { class: "axis" });
    for (let i = 0; i <= 4; i++) {
      const value = (niceMax / 4) * i;
      const gy = y(value);
      axis.appendChild(el("line", {
        class: "gridline", x1: padL, x2: W - padR, y1: gy, y2: gy,
      }));
      const label = el("text", { x: padL - 10, y: gy + 4, "text-anchor": "end" });
      label.textContent = fmt(Math.round(value * 10) / 10);
      axis.appendChild(label);
    }
    svg.appendChild(axis);

    // optional average line (matches the legend swatch)
    if (cfg.average) {
      const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
      const avgY = y(mean);
      svg.appendChild(el("line", {
        class: "avg-line",
        x1: padL, x2: W - padR, y1: avgY, y2: avgY,
        stroke: "#22d3ee", "stroke-width": 1.4, "stroke-dasharray": "7 6", opacity: .6,
      }));
      const tag = el("text", {
        class: "avg-label", x: W - padR, y: Math.max(avgY - 7, padT + 9), "text-anchor": "end",
      });
      tag.textContent = "avg " + fmt(Math.round(mean * 10) / 10);
      svg.appendChild(tag);
    }

    // x labels
    const xAxis = el("g", { class: "axis" });
    const stride = n > 10 ? Math.ceil(n / 8) : 1;
    labels.forEach((label, i) => {
      if (i % stride !== 0 && i !== n - 1) return;
      const t = el("text", { x: x(i), y: H - padB + 22, "text-anchor": "middle" });
      t.textContent = label;
      xAxis.appendChild(t);
    });
    svg.appendChild(xAxis);

    // smooth path (control points clamped to the plot so a flat run
    // never sags below the baseline)
    const clampY = (v) => Math.max(padT, Math.min(H - padB, v));
    const pts = values.map((v, i) => [x(i), y(v)]);
    let d = `M ${pts[0][0]} ${pts[0][1]}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[i + 2] || p2;
      const c1x = p1[0] + (p2[0] - p0[0]) / 6;
      const c1y = clampY(p1[1] + (p2[1] - p0[1]) / 6);
      const c2x = p2[0] - (p3[0] - p1[0]) / 6;
      const c2y = clampY(p2[1] - (p3[1] - p1[1]) / 6);
      d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2[0]} ${p2[1]}`;
    }

    const areaGroup = el("g");
    const areaPath = el("path", {
      d: d + ` L ${pts[pts.length - 1][0]} ${H - padB} L ${pts[0][0]} ${H - padB} Z`,
      fill: `url(#${gid})`,
    });
    areaGroup.appendChild(areaPath);
    areaGroup.style.clipPath = "inset(0 100% 0 0)";
    svg.appendChild(areaGroup);

    // guide at last point
    const lastX = pts[pts.length - 1][0];
    svg.appendChild(el("line", {
      x1: lastX, x2: lastX, y1: padT, y2: H - padB,
      stroke: "#6366f1", "stroke-width": 1, "stroke-dasharray": "4 5", opacity: .45,
    }));

    const line = el("path", { class: "line-main", d: d });
    svg.appendChild(line);

    const dots = el("g");
    pts.forEach(([px, py], i) => {
      const dot = el("circle", { class: "dot-main", cx: px, cy: py, r: 0 });
      dot.dataset.i = i;
      dots.appendChild(dot);
    });
    svg.appendChild(dots);

    // live halo on last point
    const halo = el("circle", {
      cx: lastX, cy: pts[pts.length - 1][1], r: 4, fill: "#22d3ee", opacity: .9,
    });
    svg.appendChild(halo);

    host.appendChild(svg);

    // tooltip
    const tip = document.createElement("div");
    tip.className = "tooltip";
    tip.innerHTML = '<div class="tt-k"></div><div class="tt-v"></div>';
    host.appendChild(tip);
    const tipK = tip.querySelector(".tt-k");
    const tipV = tip.querySelector(".tt-v");

    const hit = el("rect", {
      x: padL, y: padT, width: plotW, height: plotH, fill: "transparent", style: "cursor:crosshair",
    });
    svg.appendChild(hit);

    let active = -1;
    function show(i) {
      if (i < 0 || i >= n) return;
      active = i;
      tipK.textContent = labels[i];
      tipV.textContent = fmt(values[i]) + (cfg.unit ? " " + cfg.unit : "");
      const rect = host.getBoundingClientRect();
      const scale = rect.width / W;
      tip.style.left = (pts[i][0] * scale) + "px";
      tip.style.top = (pts[i][1] * (rect.height / H)) + "px";
      tip.classList.add("on");
      Array.from(dots.children).forEach((dot, idx) => {
        dot.setAttribute("r", idx === i ? 4.2 : 2.6);
        dot.style.opacity = idx === i ? 1 : .55;
      });
    }
    function hide() {
      active = -1;
      tip.classList.remove("on");
      Array.from(dots.children).forEach((dot) => {
        dot.setAttribute("r", 2.6);
        dot.style.opacity = 1;
      });
    }

    hit.addEventListener("mousemove", (event) => {
      const box = svg.getBoundingClientRect();
      const localX = ((event.clientX - box.left) / box.width) * W;
      let nearest = 0;
      let dist = Infinity;
      pts.forEach(([px], i) => {
        const diff = Math.abs(px - localX);
        if (diff < dist) { dist = diff; nearest = i; }
      });
      show(nearest);
    });
    hit.addEventListener("mouseleave", hide);

    // entrance animation
    const total = line.getTotalLength();
    line.style.strokeDasharray = String(total);
    line.style.strokeDashoffset = String(total);
    animate(1300, (p) => {
      line.style.strokeDashoffset = String(total * (1 - p));
      areaGroup.style.clipPath = `inset(0 ${100 - p * 100}% 0 0)`;
      Array.from(dots.children).forEach((dot, i) => {
        const local = Math.min(1, Math.max(0, p * 1.35 - i / (n * 1.35)));
        dot.setAttribute("r", 2.6 * local);
      });
    });
  }

  /* ---------------- donut ---------------- */
  function donutChart(host, cfg) {
    const segments = (cfg.segments || []).filter((s) => Number(s.value) > 0);
    const total = segments.reduce((sum, s) => sum + Number(s.value), 0);

    host.innerHTML = "";
    if (!total) {
      host.innerHTML = '<div class="chart-empty">Nothing to display yet.</div>';
      return;
    }

    const cells = cfg.cells || 2;
    const W = 260, H = 260;
    const R = 82, SW = 17;
    const C = 2 * Math.PI * R;
    const cx = W / 2, cy = H / 2;

    const wrap = document.createElement("div");
    wrap.style.display = "grid";
    wrap.style.gridTemplateColumns = cells > 1 ? "minmax(150px, 1fr) minmax(160px, 1fr)" : "1fr";
    wrap.style.alignItems = "center";
    wrap.style.gap = "12px";

    const svg = el("svg", {
      viewBox: `0 0 ${W} ${H}`,
      role: "img",
      "aria-label": cfg.aria || "Distribution",
      style: "max-width:240px;margin:0 auto",
    });

    const track = el("circle", {
      cx, cy, r: R, fill: "none", "stroke-width": SW,
      stroke: "rgba(120,130,160,.16)",
    });
    svg.appendChild(track);

    const arcs = el("g", { transform: `rotate(-90 ${cx} ${cy})` });
    let offset = 0;
    const arcNodes = [];

    segments.forEach((seg, i) => {
      const frac = Number(seg.value) / total;
      const color = seg.color || palette[i % palette.length];
      const arc = el("circle", {
        cx, cy, r: R, fill: "none",
        stroke: color, "stroke-width": SW,
        "stroke-dasharray": `0 ${C}`,
        "stroke-dashoffset": String(-offset * C),
        "stroke-linecap": "butt",
        style: "transition:stroke-width .2s,opacity .2s",
      });
      arc.dataset.frac = String(frac);
      arc.dataset.color = color;
      arcs.appendChild(arc);
      arcNodes.push(arc);
      offset += frac;
    });

    // gaps between segments
    const gapGroup = el("g", { transform: `rotate(-90 ${cx} ${cy})` });
    let pos = 0;
    segments.forEach((seg) => {
      const frac = Number(seg.value) / total;
      if (frac > 0.012) {
        const angle = pos * 360;
        const gap = el("line", {
          x1: cx, y1: cy - R - SW / 2 + 2, x2: cx, y2: cy - R + SW / 2 - 2,
          transform: `rotate(${angle} ${cx} ${cy})`,
          stroke: "var(--card-solid)", "stroke-width": 3,
        });
        gapGroup.appendChild(gap);
      }
      pos += frac;
    });

    svg.appendChild(arcs);
    svg.appendChild(gapGroup);

    const centerValue = el("text", {
      x: cx, y: cy + 4, "text-anchor": "middle",
      fill: "var(--ink)", "font-size": 30, "font-weight": 800,
    });
    centerValue.textContent = fmt(cfg.centerValue != null ? cfg.centerValue : total);
    const centerLabel = el("text", {
      x: cx, y: cy + 26, "text-anchor": "middle",
      fill: "var(--muted)", "font-size": 10.5, "letter-spacing": "2",
    });
    centerLabel.textContent = (cfg.centerLabel || "TOTAL").toUpperCase();
    svg.appendChild(centerValue);
    svg.appendChild(centerLabel);

    const svgBox = document.createElement("div");
    svgBox.appendChild(svg);

    const legend = document.createElement("ul");
    legend.className = "donut-legend";
    segments.forEach((seg, i) => {
      const pct = total ? (Number(seg.value) * 100 / total).toFixed(1).replace(".0", "") : "0";
      const li = document.createElement("li");
      li.innerHTML =
        `<span class="sw" style="background:${seg.color || palette[i % palette.length]}"></span>` +
        `<span>${seg.label}</span>` +
        `<span class="p">${pct}%</span>` +
        `<span class="n">${fmt(seg.value)}</span>`;
      li.addEventListener("mouseenter", () => {
        arcNodes.forEach((a, idx) => {
          a.style.opacity = idx === i ? "1" : ".35";
          a.style.strokeWidth = idx === i ? SW + 4 : SW;
        });
        centerValue.textContent = fmt(seg.value);
        centerLabel.textContent = String(seg.label).toUpperCase().slice(0, 14);
      });
      li.addEventListener("mouseleave", () => {
        arcNodes.forEach((a) => {
          a.style.opacity = "1";
          a.style.strokeWidth = SW;
        });
        centerValue.textContent = fmt(cfg.centerValue != null ? cfg.centerValue : total);
        centerLabel.textContent = (cfg.centerLabel || "TOTAL").toUpperCase();
      });
      legend.appendChild(li);
    });

    wrap.appendChild(svgBox);
    wrap.appendChild(legend);
    host.appendChild(wrap);

    animate(1100, (p) => {
      arcNodes.forEach((arc, i) => {
        const local = Math.max(0, Math.min(1, p * 1.45 - i * 0.12));
        const len = Number(arc.dataset.frac) * C * local;
        arc.setAttribute("stroke-dasharray", `${len} ${C}`);
      });
      gapGroup.style.opacity = String(p);
    });
  }

  /* ---------------- horizontal bars ---------------- */
  function barChart(host, cfg) {
    const rows = cfg.rows || [];
    host.innerHTML = "";

    if (!rows.length) {
      host.innerHTML = '<div class="chart-empty">No data yet.</div>';
      return;
    }

    const max = Math.max(...rows.map((r) => Number(r.value) || 0), 1);
    const list = document.createElement("ul");
    list.className = "bars stagger";

    rows.forEach((row, i) => {
      const li = document.createElement("li");
      li.className = "bar-row";
      li.style.setProperty("--i", String(i));
      const share = cfg.total ? (Number(row.value) * 100 / cfg.total) : null;
      li.innerHTML =
        `<div class="bar-meta"><span>${row.label}</span>` +
        `<span class="v">${fmt(row.value)}${share != null ? " · " + share.toFixed(1).replace(".0", "") + "%" : ""}</span></div>` +
        `<div class="bar-track"><div class="bar-fill ${row.tone || ""}"></div></div>`;
      list.appendChild(li);
      const fill = li.querySelector(".bar-fill");
      const target = (Number(row.value) || 0) / max * 100;
      requestAnimationFrame(() => {
        setTimeout(() => { fill.style.width = target + "%"; }, reduceMotion ? 0 : 60);
      });
    });

    host.appendChild(list);
  }

  /* ---------------- sparkline ---------------- */
  function sparkline(host, cfg) {
    const values = (cfg.values || []).map((n) => Number(n) || 0);
    host.innerHTML = "";
    if (values.length < 2) return;

    const W = 120, H = 40;
    const max = Math.max(...values, 1);
    const pts = values.map((v, i) => [
      (i * W) / (values.length - 1),
      H - 4 - (v / max) * (H - 8),
    ]);

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", "aria-hidden": "true" });

    let d = `M ${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length; i++) {
      const mid = (pts[i - 1][0] + pts[i][0]) / 2;
      d += ` C ${mid} ${pts[i - 1][1]}, ${mid} ${pts[i][1]}, ${pts[i][0]} ${pts[i][1]}`;
    }

    svg.appendChild(el("path", {
      d, fill: "none", stroke: cfg.color || "#6366f1",
      "stroke-width": 1.8, "stroke-linecap": "round", opacity: ".85",
      "vector-effect": "non-scaling-stroke",
    }));
    const gid = "sp" + Math.random().toString(36).slice(2, 7);
    const defs = el("defs");
    const g = el("linearGradient", { id: gid, x1: "0", y1: "0", x2: "0", y2: "1" });
    g.appendChild(el("stop", { offset: "0%", "stop-color": cfg.color || "#6366f1", "stop-opacity": ".28" }));
    g.appendChild(el("stop", { offset: "100%", "stop-color": cfg.color || "#6366f1", "stop-opacity": "0" }));
    defs.appendChild(g);
    svg.insertBefore(defs, svg.firstChild);
    svg.appendChild(el("path", {
      d: d + ` L ${pts[pts.length - 1][0]} ${H} L 0 ${H} Z`,
      fill: `url(#${gid})`,
    }));

    host.appendChild(svg);

    const line = svg.querySelector("path");
    const total = line.getTotalLength();
    line.style.strokeDasharray = String(total);
    line.style.strokeDashoffset = String(total);
    animate(1100, (p) => { line.style.strokeDashoffset = String(total * (1 - p)); });
  }

  /* ---------------- dispatcher ---------------- */
  function renderAll(root = document) {
    root.querySelectorAll('script[type="application/json"][data-chart]').forEach((node) => {
      const target = document.querySelector(node.dataset.target);
      if (!target || target.dataset.chartDone === "1") return;

      let cfg;
      try {
        cfg = JSON.parse(node.textContent);
      } catch (error) {
        console.warn("chart data invalid", node.dataset.target, error);
        return;
      }

      target.dataset.chartDone = "1";
      const type = node.dataset.chart;
      if (type === "area") areaChart(target, cfg);
      else if (type === "donut") donutChart(target, cfg);
      else if (type === "bars") barChart(target, cfg);
      else if (type === "spark") sparkline(target, cfg);
    });
  }

  window.GHCharts = { renderAll, areaChart, donutChart, barChart, sparkline };
  document.addEventListener("DOMContentLoaded", () => renderAll());
})();
