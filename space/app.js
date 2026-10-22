// Olmo 3 concept coverage site (design.md rows W1-W7). Data comes from space/data/, written by s09_space.py.
const CLASS_LABEL = {
  over: "over: more coverage in Dolma web",
  under: "under: less coverage in Dolma web",
  middle: "middle",
  rare_in_pile_present_in_dolma: "rare in Pile web, present in Dolma web",
  rare_in_dolma_present_in_pile: "rare in Dolma web, present in Pile web",
  too_rare_to_compare: "too rare to compare",
};
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const cache = {};
async function load(path) {
  if (!cache[path]) cache[path] = fetch(path).then((r) => { if (!r.ok) throw new Error(path); return r.json(); });
  return cache[path];
}
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (x, d = 3) => (x === null || x === undefined ? "–" : Number(x).toFixed(d));
const pct = (x) => (100 * x).toFixed(1) + "%";
const layoutBase = () => ({
  paper_bgcolor: css("--bg"), plot_bgcolor: css("--bg"), font: { color: css("--fg") },
  margin: { l: 60, r: 20, t: 20, b: 50 }, legend: { orientation: "h", y: -0.18 },
  xaxis: { gridcolor: css("--line"), zerolinecolor: css("--line") },
  yaxis: { gridcolor: css("--line"), zerolinecolor: css("--line") },
});
const drawn = {};

async function drawOverview() {
  const d = await load("data/overview.json");
  const traces = ["middle", "under", "over"].map((cls) => {
    const idx = d.cls.map((c, i) => (c === cls ? i : -1)).filter((i) => i >= 0);
    return {
      type: "scattergl", mode: "markers", name: CLASS_LABEL[cls],
      x: idx.map((i) => d.x[i]), y: idx.map((i) => d.y[i]), customdata: idx.map((i) => d.id[i]),
      marker: { size: 3, color: css("--" + cls), opacity: cls === "middle" ? 0.35 : 0.6 },
      hovertemplate: "concept %{customdata}<br>fires in %{x:.2%} of docs (mean)<br>log ratio %{y:.3f}<extra></extra>",
    };
  });
  const s = d.sampled.map((v, i) => (v ? i : -1)).filter((i) => i >= 0);
  const wrap = (t, n = 60, max = 200) => {  // W8: short, wrapped hover text
    if (!t) return "no name";
    t = t.length > max ? t.slice(0, max).replace(/\s+\S*$/, "") + " …" : t;
    const out = []; let line = "";
    for (const w of t.split(" ")) { if ((line + " " + w).length > n && line) { out.push(line); line = w; } else line = line ? line + " " + w : w; }
    out.push(line);
    return out.map((x) => x.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")).join("<br>");  // Plotly decodes these three
  };
  traces.push({
    type: "scattergl", mode: "markers", name: "named (hover or click)",
    x: s.map((i) => d.x[i]), y: s.map((i) => d.y[i]), customdata: s.map((i) => d.id[i]),
    text: s.map((i) => wrap((d.names[String(d.id[i])] || {}).dolma)),
    marker: { size: 8, color: "rgba(0,0,0,0)", line: { width: 1.5, color: css("--fg") } },
    hovertemplate: "<b>concept %{customdata}</b> · log ratio %{y:.3f}<br>%{text}<extra></extra>",
  });
  const L = layoutBase();
  L.xaxis = { ...L.xaxis, type: "log", title: "share of docs where the concept fires (mean of Dolma web and Pile web)" };
  L.yaxis = { ...L.yaxis, title: "log coverage ratio, Dolma web / Pile web" };
  L.shapes = [d.low, d.high].map((y) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: y, y1: y,
    line: { dash: "dash", width: 1, color: css("--muted") } }));
  await Plotly.newPlot("overview-plot", traces, L, { responsive: true, displaylogo: false });
  document.getElementById("overview-plot").on("plotly_click", (e) => {  // W8: description panel
    const p = e.points[0], id = p.customdata, i = d.id.indexOf(id), n = d.names[String(id)];
    const head = `<b>Concept ${id}</b> <span class="badge ${d.cls[i]}">${d.cls[i]}</span> · log ratio ${fmt(d.y[i])} · fires in ${pct(d.x[i])} of docs (mean of both corpora)`;
    document.getElementById("overview-detail").innerHTML = n
      ? `${head}<p><span class="k">Name from Dolma web examples:</span> ${esc(n.dolma || "–")}</p>
         <p><span class="k">Name from Pile web examples:</span> ${esc(n.pile || "–")}</p><a href="#c=${id}">open the concept page →</a>`
      : `${head}<p class="note">No description: names were written only for the 240 sampled concepts (80 per class, row F3). This concept is not one of them.</p>`;
  });

  const order = ["over", "under", "middle", "rare_in_pile_present_in_dolma", "rare_in_dolma_present_in_pile", "too_rare_to_compare"];
  const B = layoutBase();
  B.margin.l = 260;
  B.xaxis = { ...B.xaxis, title: "concepts" };
  B.yaxis = { ...B.yaxis, autorange: "reversed" };
  await Plotly.newPlot("class-bars", [{
    type: "bar", orientation: "h", y: order.map((c) => CLASS_LABEL[c]), x: order.map((c) => d.class_counts[c] || 0),
    text: order.map((c) => (d.class_counts[c] || 0).toLocaleString()), textposition: "auto",
    marker: { color: order.map((c) => css("--" + c) || css("--middle")) }, hovertemplate: "%{x}<extra></extra>",
  }], B, { responsive: true, displaylogo: false });
}

async function drawNoise() {
  const d = await load("data/noise.json");
  document.getElementById("noise-stats").textContent =
    `Spearman between halves: ${d.spearman}. Same class in both halves: ${pct(d.same_class_share)} of comparable concepts.`;
  const traces = ["middle", "under", "over"].map((cls) => {
    const idx = d.cls.map((c, i) => (c === cls ? i : -1)).filter((i) => i >= 0);
    return {
      type: "scattergl", mode: "markers", name: CLASS_LABEL[cls] + " (full-sample class)",
      x: idx.map((i) => d.h1[i]), y: idx.map((i) => d.h2[i]), customdata: idx.map((i) => d.id[i]),
      marker: { size: 3, color: css("--" + cls), opacity: cls === "middle" ? 0.3 : 0.6 },
      hovertemplate: "concept %{customdata}<br>half 1 %{x:.3f}<br>half 2 %{y:.3f}<extra></extra>",
    };
  });
  const L = layoutBase();
  L.xaxis = { ...L.xaxis, title: "log ratio, half 1" };
  L.yaxis = { ...L.yaxis, title: "log ratio, half 2", scaleanchor: "x" };
  L.shapes = [{ type: "line", x0: -6, y0: -6, x1: 6, y1: 6, line: { dash: "dot", width: 1, color: css("--muted") } }];
  await Plotly.newPlot("noise-plot", traces, L, { responsive: true, displaylogo: false });
}

const TYPE_LABEL = {
  partial_char: "partial character", whitespace: "whitespace / newline", digits: "digits", prose_punct: "prose punctuation",
  symbols: "code / math symbols", non_latin: "non-Latin letters", word_start_cap: "capitalized word start",
  word_start_lower: "lowercase word start", word_piece: "word piece", mixed: "code identifiers (mixed)",
};
async function drawPatterns() {
  const d = await load("data/patterns.json");
  const types = Object.keys(TYPE_LABEL);
  const traces = ["over", "middle", "under"].map((cls) => ({
    type: "bar", name: CLASS_LABEL[cls], y: types.map((t) => TYPE_LABEL[t]), orientation: "h",
    x: types.map((t) => d.share[cls][t][0]),
    error_x: { type: "data", symmetric: false, array: types.map((t) => d.share[cls][t][2] - d.share[cls][t][0]),
               arrayminus: types.map((t) => d.share[cls][t][0] - d.share[cls][t][1]), color: css("--muted") },
    marker: { color: css("--" + cls) }, hovertemplate: "%{x:.1%}<extra>" + cls + "</extra>",
  }));
  const L = layoutBase();
  L.barmode = "group"; L.margin.l = 190;
  L.xaxis = { ...L.xaxis, title: "share of concepts in the class", tickformat: ".0%" };
  L.yaxis = { ...L.yaxis, autorange: "reversed" };
  await Plotly.newPlot("patterns-plot", traces, L, { responsive: true, displaylogo: false });
  document.getElementById("patterns-examples").innerHTML = d.examples.map((e) => `<div class="card" style="margin:10px 0">
    <div class="k"><span class="badge ${e.cls}">${e.cls}</span> mostly ${TYPE_LABEL[e.type]}: ${(100 * e.diff).toFixed(1)} points more common than in middle</div>
    ${e.concepts.map((c) => `<p><a href="#c=${c.id}">concept ${c.id}</a>: ${esc(c.name)}</p>`).join("") || "<p class='note'>no named example</p>"}</div>`).join("");
}

async function drawTopics() {
  let d;
  try { d = await load("data/topics.json"); } catch { return; }
  document.getElementById("topics-stats").textContent =
    `Agreement between the two codings: ${pct(d.agreement)} (Cohen's kappa ${d.kappa}).`;
  const traces = ["over", "middle", "under"].map((cls) => ({
    type: "bar", name: CLASS_LABEL[cls], orientation: "h", y: d.categories, x: d.categories.map((c) => d.share[cls][c][0]),
    error_x: { type: "data", symmetric: false, array: d.categories.map((c) => d.share[cls][c][2] - d.share[cls][c][0]),
               arrayminus: d.categories.map((c) => d.share[cls][c][0] - d.share[cls][c][1]), color: css("--muted") },
    marker: { color: css("--" + cls) }, hovertemplate: "%{x:.0%}<extra>" + cls + "</extra>",
  }));
  const L = layoutBase();
  L.barmode = "group"; L.margin.l = 330;
  L.xaxis = { ...L.xaxis, title: "share of the class's 80 named concepts", tickformat: ".0%" };
  L.yaxis = { ...L.yaxis, autorange: "reversed" };
  await Plotly.newPlot("topics-plot", traces, L, { responsive: true, displaylogo: false });
}

let sortKey = "log_ratio", sortDir = -1;
const COLUMNS = [
  ["id", "concept"], ["cls", "class"], ["log_ratio", "log ratio"], ["share_dolma", "fires in Dolma web"],
  ["share_pile", "fires in Pile web"], ["name_pile", "name from Pile"], ["name_dolma", "name from Dolma"],
  ["quiz_pile", "quiz, Pile name"], ["quiz_dolma", "quiz, Dolma name"],
];
async function drawTable() {
  const rows = await load("data/sample.json");
  const filter = document.getElementById("class-filter").value;
  const head = document.querySelector("#concept-table thead");
  head.innerHTML = "<tr>" + COLUMNS.map(([k, label]) =>
    `<th data-k="${k}">${label}${k === sortKey ? (sortDir > 0 ? " ▲" : " ▼") : ""}</th>`).join("") + "</tr>";
  head.querySelectorAll("th").forEach((th) => th.onclick = () => {
    sortDir = th.dataset.k === sortKey ? -sortDir : -1; sortKey = th.dataset.k; drawTable();
  });
  const shown = rows.filter((r) => !filter || r.cls === filter).slice().sort((a, b) => {
    const x = a[sortKey], y = b[sortKey];
    if (x === null) return 1; if (y === null) return -1;
    return (x > y ? 1 : x < y ? -1 : 0) * sortDir;
  });
  document.querySelector("#concept-table tbody").innerHTML = shown.map((r) => `<tr data-id="${r.id}">
    <td>${r.id}</td><td><span class="badge ${r.cls}">${r.cls}</span></td><td>${fmt(r.log_ratio)}</td>
    <td>${pct(r.share_dolma)}</td><td>${pct(r.share_pile)}</td>
    <td>${r.name_pile ? esc(r.name_pile) : "<span class='note'>pending</span>"}</td>
    <td>${r.name_dolma ? esc(r.name_dolma) : "<span class='note'>pending</span>"}</td>
    <td>${fmt(r.quiz_pile, 2)}</td><td>${fmt(r.quiz_dolma, 2)}</td></tr>`).join("");
  document.querySelectorAll("#concept-table tbody tr").forEach((tr) => tr.onclick = () => location.hash = "c=" + tr.dataset.id);
}

function windowHtml(w) {
  const top = Math.max(...w.acts) || 1;
  const toks = w.pieces.map((p, i) => {
    const a = w.acts[i];
    if (!p) return "";
    if (a <= 0) return esc(p);
    return `<span class="tok" title="activation ${a}" style="background: rgba(${css("--hl")}, ${(0.15 + 0.85 * a / top).toFixed(2)})">${esc(p)}</span>`;
  }).join("");
  return `<div class="win"><span class="meta">max ${w.max} · rank group ${w.group + 1} of 10</span>${toks}</div>`;
}

async function drawConcept(id) {
  const box = document.getElementById("concept-detail");
  box.innerHTML = "<p class='note'>loading…</p>";
  let c;
  try { c = await load(`data/concepts/${id}.json`); }
  catch { box.innerHTML = `<p>Concept ${esc(String(id))} is not in the sample, so it has no page yet.</p>`; return; }
  const name = (label, n, q) => `<div class="card"><div class="k">${label}</div><div class="v">${n ? esc(n) : "<span class='note'>pending: written in the faithfulness run</span>"}</div>
    <div class="k">detection quiz on Dolma web held-out windows: ${fmt(q, 2)}</div></div>`;
  const column = (title, ws) => `<div><h2>${title}</h2>${ws.slice(0, 10).map(windowHtml).join("")}
    <details><summary>show the other ${ws.length - 10} (weaker activations)</summary>${ws.slice(10).map(windowHtml).join("")}</details></div>`;
  box.innerHTML = `<h1>Concept ${c.id} <span class="badge ${c.cls}">${c.cls}</span></h1>
    <div class="cards">
      <div class="card"><div class="k">log coverage ratio, Dolma web / Pile web</div><div class="v">${fmt(c.log_ratio)}</div></div>
      <div class="card"><div class="k">fires in Dolma web docs (train)</div><div class="v">${pct(c.share_dolma)}</div></div>
      <div class="card"><div class="k">fires in Pile web docs</div><div class="v">${pct(c.share_pile)}</div></div>
    </div>
    <p class="note" id="topic-line"></p>
    <div class="cards">${name("name written from Pile web windows", c.name_pile, c.quiz_pile)}${name("name written from Dolma web windows", c.name_dolma, c.quiz_dolma)}</div>
    <p class="note">40 windows per side, 4 from each of 10 rank groups by activation; shading is each token's activation relative to its window's maximum. Hover a token for its value.</p>
    <div class="cols">${column("Dolma web (train, T1)", c.dolma)}${column("Pile web (Pile-CC)", c.pile)}</div>`;
  try {
    const t = await load("data/topics.json");
    const cat = t.concepts[String(c.id)];
    document.getElementById("topic-line").textContent = "Topic category: " + (cat || "not assigned (the answer hit its length cap)");
  } catch {}
}

// Exp 2 "Temp visualizations" tab (exp2_rollout_gap/design.md G10, G12, G23, G24).
// Data written by exp2_rollout_gap/s05_space.py; images by exp2_rollout_gap/figures/make_rollout_figure.py.
const GEN_LABEL = { stage1: "end of stage 1 (stage1-step1413814)", main: "final model (main)" };
const GEN_COLOR = { V: "--middle", stage1: "--under", main: "--over" };
async function drawRollouts() {
  const d = await load("data/rollouts.json");
  const select = document.getElementById("rollout-gen");
  const gens = d.sets.filter((s) => s !== "V");
  if (!select.options.length) {
    select.innerHTML = gens.map((g) => `<option value="${g}">${GEN_LABEL[g] || g}</option>`).join("");
    select.onchange = drawRollouts;
  }
  const g = select.value;
  const rgba = (name, a) => { const n = parseInt(css(name).replace("#", ""), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
  const label = (s) => (s === "V" ? "Dolma V (held out)" : "rollouts, " + (GEN_LABEL[s] || s));
  // One band = lower edge, upper edge filled to it, median line. ax is "" for graph 1, "2" or "3" for graphs 2-3
  const band = (f, s, ax, legend) => [
    { x: d.band_rank, y: f.sets[s].lo, xaxis: "x" + ax, yaxis: "y" + ax, mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
    { x: d.band_rank, y: f.sets[s].hi, xaxis: "x" + ax, yaxis: "y" + ax, mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: rgba(GEN_COLOR[s], 0.2), hoverinfo: "skip", showlegend: false },
    { x: d.band_rank, y: f.sets[s].mid, xaxis: "x" + ax, yaxis: "y" + ax, mode: "lines", line: { color: css(GEN_COLOR[s]), width: 2 }, name: label(s) + ": median, 10th-90th pct", hoverinfo: "skip", showlegend: legend },
  ];
  const train = (ax, legend) => ({ x: d.train.rank, y: d.train.chi, xaxis: "x" + ax, yaxis: "y" + ax, mode: "lines", line: { color: css("--fg"), width: 2 }, name: "Dolma train (sets the order)", hoverinfo: "skip", showlegend: legend });
  const traces = (f) => [
    ...band(f, "V", "", false), train("", false),
    ...band(f, g, "2", false),
    ...band(f, "V", "3", true), train("3", true), ...band(f, g, "3", true),
    { x: d.named.map((n) => n.rank), y: d.named.map((n) => n.chi[f.key][g]), xaxis: "x3", yaxis: "y3", mode: "markers", name: "240 named concepts (rollout χ)",
      marker: { size: 7, color: css(GEN_COLOR[g]), line: { color: css("--bg"), width: 1.5 } },
      text: d.named.map((n) => `#${n.c}: ${esc(n.name)}<br>χ train ${fmt(n.train, 4)} · V ${fmt(n.chi[f.key].V, 4)} · rollouts ${fmt(n.chi[f.key][g], 4)}`),
      hovertemplate: "%{text}<extra></extra>" },
    // Graph 4 (G27): the overlay again without the named-concept dots
    ...band(f, "V", "5", false), train("5", false), ...band(f, g, "5", false),
    ...["V", g].map((s) => ({ x: d.bin_rank, y: f.sets[s].ratio, xaxis: "x4", yaxis: "y4", mode: "lines+markers",
      line: { color: css(GEN_COLOR[s]), width: 2 }, marker: { size: 8, line: { color: css("--bg"), width: 2 } },
      name: `${label(s)}: median log(χ / χ train), slope ${fmt(f.sets[s].slope, 2)}`, hovertemplate: "rank %{x}: %{y:.3f}<extra></extra>" })),
  ];
  const stats = (f) => {
    const dl = d.delta[g];
    const delta = f.key === "doc" ? (dl ? `Δ slope (rollouts − V): ${fmt(dl.delta, 3)}, 95% CI ${fmt(dl.ci95_basic[0], 3)} to ${fmt(dl.ci95_basic[1], 3)}` : "")
      : "window slopes are descriptive, with no interval";
    return `${f.label}: ${f.docs.toLocaleString()} documents per set. ${delta}${d.run === "pilot" ? " · PILOT DATA (200 rollouts), not a result" : ""}`;
  };
  // Fixed ranges over every frame, so the axes stay put while the frames play
  const all = (pick) => d.frames.flatMap((f) => d.sets.flatMap((s) => pick(f.sets[s]))).filter((v) => v !== null);
  const ratios = all((x) => x.ratio);
  const chis = all((x) => [...x.lo, ...x.hi]).concat(d.train.chi.filter((v) => v > 0));
  const chiRange = [Math.log10(Math.min(...chis)) - 0.2, Math.log10(Math.max(...chis)) + 0.2];
  const base = layoutBase();
  const xr = [0, Math.max(...d.train.rank) * 1.02];
  const top = (dom, title) => ({ ...base.xaxis, domain: dom, range: xr, title: { text: "rank by Dolma train χ", font: { size: 12 } } });
  const logy = (anchor, showTitle) => ({ ...base.yaxis, type: "log", range: chiRange, domain: [0.47, 0.93], anchor,
    title: showTitle ? "χ (relative to the average concept)" : "", showticklabels: showTitle });
  const ann = (x, text) => ({ text, x, y: 0.95, xref: "paper", yref: "paper", xanchor: "left", showarrow: false, font: { size: 15 } });
  const layout = {
    ...base, margin: { l: 70, r: 20, t: 90, b: 110 }, hovermode: "closest",
    legend: { orientation: "h", x: 0, y: 1.0, yanchor: "bottom", font: { size: 11 } },
    annotations: [ann(0, "1. Dolma"), ann(0.255, "2. Rollouts"), ann(0.51, "3. Overlay"), ann(0.765, "4. Overlay, curves only")],
    xaxis: top([0, 0.235]), xaxis2: top([0.255, 0.49]), xaxis3: top([0.51, 0.745]), xaxis5: top([0.765, 1]),
    yaxis: logy("x", true), yaxis2: logy("x2", false), yaxis3: logy("x3", false), yaxis5: logy("x5", false),
    xaxis4: { ...base.xaxis, domain: [0, 1], range: xr, anchor: "y4", title: "concept rank by Dolma train χ (1 = most common)" },
    yaxis4: { ...base.yaxis, domain: [0, 0.33], anchor: "x4", title: "median log(χ / χ train)", zeroline: true,
      range: [Math.min(...ratios) - 0.1, Math.max(...ratios, 0) + 0.1] },
    sliders: [{ active: 0, x: 0.1, len: 0.88, y: -0.07, yanchor: "top", currentvalue: { prefix: "Frame: " },
      steps: d.frames.map((f) => ({ label: f.label, method: "animate",
        args: [[f.key], { mode: "immediate", frame: { duration: 0, redraw: true }, transition: { duration: 0 } }] })) }],
    updatemenus: [{ type: "buttons", showactive: false, x: 0, y: -0.07, yanchor: "top", xanchor: "left", pad: { t: 30 },
      buttons: [{ label: "Play", method: "animate", args: [null, { frame: { duration: 1500, redraw: true }, fromcurrent: true }] }] }],
  };
  const el = document.getElementById("rollout-plot");
  // newPlot, not react: a redraw for another generator must replace the frames, not add to them
  await Plotly.newPlot(el, traces(d.frames[0]), layout, { responsive: true });
  await Plotly.addFrames(el, d.frames.map((f) => ({ name: f.key, data: traces(f) })));
  document.getElementById("rollout-stats").textContent = stats(d.frames[0]);
  el.on("plotly_animatingframe", (e) => {
    document.getElementById("rollout-stats").textContent = stats(d.frames.find((f) => f.key === e.name) || d.frames[0]);
  });
  // Static PNGs and GIFs (G23), one row per generator
  const frameName = (f) => (f.key === "doc" ? "doc" : "w" + f.key);
  document.getElementById("rollout-gallery").innerHTML = gens.map((s) => `
    <h3>${esc(label(s))}</h3>
    <p class="note">Animated GIF (5 frames, 1.5 s each): <a href="data/exp2/${d.run}_${s}_animation.gif" target="_blank">open</a></p>
    <div class="cards">${d.frames.map((f) => `<a href="data/exp2/${d.run}_${s}_${frameName(f)}.png" target="_blank"><figure style="margin:0">
      <img src="data/exp2/${d.run}_${s}_${frameName(f)}.png" alt="${esc(label(s))}, ${esc(f.label)}" style="width:100%;max-width:560px" loading="lazy">
      <figcaption class="note">${esc(f.label)}</figcaption></figure></a>`).join("")}</div>`).join("");
}

async function route() {
  const h = location.hash.replace("#", "") || "overview";
  const tab = h.startsWith("c=") ? "concept" : h;
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === "tab-" + tab));
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  if (tab === "concept") return drawConcept(h.slice(2));
  if (!drawn[tab]) {
    drawn[tab] = true;
    if (tab === "overview") await drawOverview();
    if (tab === "noise") await drawNoise();
    if (tab === "patterns") { await drawPatterns(); await drawTopics(); }
    if (tab === "temp") await drawRollouts();
  }
  if (tab === "concepts") await drawTable();
}
document.getElementById("class-filter").onchange = drawTable;
window.addEventListener("hashchange", route);
route();
