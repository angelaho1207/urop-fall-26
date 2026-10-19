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
  traces.push({
    type: "scattergl", mode: "markers", name: "sampled (click to open)",
    x: s.map((i) => d.x[i]), y: s.map((i) => d.y[i]), customdata: s.map((i) => d.id[i]),
    marker: { size: 8, color: "rgba(0,0,0,0)", line: { width: 1.5, color: css("--fg") } },
    hovertemplate: "concept %{customdata} (sampled)<br>log ratio %{y:.3f}<extra></extra>",
  });
  const L = layoutBase();
  L.xaxis = { ...L.xaxis, type: "log", title: "share of docs where the concept fires (mean of Dolma web and Pile web)" };
  L.yaxis = { ...L.yaxis, title: "log coverage ratio, Dolma web / Pile web" };
  L.shapes = [d.low, d.high].map((y) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: y, y1: y,
    line: { dash: "dash", width: 1, color: css("--muted") } }));
  await Plotly.newPlot("overview-plot", traces, L, { responsive: true, displaylogo: false });
  document.getElementById("overview-plot").on("plotly_click", (e) => {
    const p = e.points[0];
    if (p.curveNumber === 3) location.hash = "c=" + p.customdata;
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
  }
  if (tab === "concepts") await drawTable();
}
document.getElementById("class-filter").onchange = drawTable;
window.addEventListener("hashchange", route);
route();
