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

// G81: one-sentence concept name. Keeps the first sentence, removes parentheticals, cuts before example lists. The full name stays in a dropdown.
function shortName(text) {
  if (!text) return text;
  const ABBREVIATION = /(?:\be\.g|\bi\.e|\bvs|\betc|\bcf|\bDr|\bMr|\bMs|\bSt|\bNo|\bU\.S|\b[A-Z])$/;
  const isQuote = (ch) => ch === '"' || ch === "“" || ch === "”";
  const NEXT_SENTENCE = /^["')]?\s+(?:["“(]\S|[A-Z])/;
  let depth = 0, inQuote = false, end = text.length;
  for (let i = 0; i < text.length; i++) {  // first sentence end outside any parenthesis or double quote
    const ch = text[i];
    if (isQuote(ch) && depth === 0) inQuote = !inQuote;
    else if (!inQuote && ch === "(") depth++;
    else if (!inQuote && ch === ")") depth = Math.max(0, depth - 1);
    else if (!inQuote && depth === 0 && ".!?".includes(ch) && NEXT_SENTENCE.test(text.slice(i + 1)) && !ABBREVIATION.test(text.slice(0, i))) { end = i; break; }
  }
  let bare = "";  // the sentence without parentheticals; an unclosed one ends the sentence there
  depth = 0; inQuote = false;
  for (const ch of text.slice(0, end)) {
    if (isQuote(ch) && depth === 0) inQuote = !inQuote;
    if (!inQuote && ch === "(") depth++;
    else if (!inQuote && ch === ")") depth = Math.max(0, depth - 1);
    else if (depth === 0) bare += ch;
  }
  bare = bare.replace(/\s+([,;:])/g, "$1").replace(/\s+\.(?=\s|$)/g, ".").replace(/\s{2,}/g, " ").trim();
  const CUT = /:\s|;\s|\s[—–-]\s|,?\s(?:such as|e\.g\.|i\.e\.|including|especially)\s|,\s(?:like|mostly|chiefly|often|typically|usually|particularly|notably|mainly|primarily)\s/g;
  let short = bare, cut;
  while ((cut = CUT.exec(bare))) {  // cut before an example list, outside quotes, keeping at least 25 characters
    const head = bare.slice(0, cut.index);
    if (head.length >= 25 && (head.match(/["“”]/g) || []).length % 2 === 0) { short = head; break; }
  }
  const stray = short.search(/[a-z0-9)"'][.!?]\s+[A-Z]/);  // a stray quote can hide a sentence end from the scan above
  if (stray >= 25) short = short.slice(0, stray + 1);
  const clipped = text.length === 140 && short === bare && !/[.!?]["')]?$/.test(text);  // s05 clips hover names at 140 characters
  return short.replace(/[\s,;:.]+$/, "") + (clipped ? " …" : ".");
}

// Exp 2 rollouts tab (exp2_rollout_gap/design.md G10-G28, G61, G70-G84). Visible results are drawn on load; plots inside a dropdown are drawn
// the first time it opens (G82). Data: s05_space.py (curves), s17_space_diag.py (diagnostics), s23_space_named.py (names).
const SET_LABEL = { V: "held-out Dolma (V)", stage1: "mid-trained (stage1)", main: "pretrained (main)", sft: "post-trained (SFT)", dpo: "post-trained (DPO)", instruct: "post-trained (Instruct)" };
const GEN_LABEL = { stage1: "mid-trained (stage1-step1413814)", main: "pretrained (main)", sft: "post-trained (Olmo-3-7B-Instruct-SFT)", dpo: "post-trained (Olmo-3-7B-Instruct-DPO)", instruct: "post-trained (Olmo-3-7B-Instruct)" };
const GEN_COLOR = { V: "--middle", stage1: "--under", main: "--over", sft: "--sft", dpo: "--dpo", instruct: "--instruct" };
const NAMED_MODELS = ["stage1", "main", "sft", "dpo", "instruct"];
const PLOT_CFG = { responsive: true, displaylogo: false };
const FRAME_NAMES = "whole document, tokens 0-256, 256-512, 512-768, 768-1024";

// One name cell: one sentence, with the full text in a dropdown (G81)
function nameCell(full) {
  if (!full) return '<span class="nm">–</span>';
  const short = shortName(full);
  if (short === full) return `<span class="nm">${esc(short)}</span>`;
  return `<span class="nm">${esc(short)}<details class="name-more"><summary>Full description and examples</summary>${esc(full)}</details></span>`;
}

// Interactive curves, one chart per file (G10, G23, G27, G30-G37). One frame shows at a time, with a slider for position in the document
async function drawCurves(file, selectId, plotId, statsId) {
  const d = await load(file);
  const select = document.getElementById(selectId);
  const gens = d.sets.filter((s) => s !== "V");
  if (!select.options.length) {
    select.innerHTML = gens.map((g) => `<option value="${g}">${GEN_LABEL[g] || g}</option>`).join("");
    select.onchange = () => drawCurves(file, selectId, plotId, statsId);
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
      text: d.named.map((n) => `#${n.c}: ${hoverN(n.name)}<br>χ train ${fmt(n.train, 4)} · V ${fmt(n.chi[f.key].V, 4)} · rollouts ${fmt(n.chi[f.key][g], 4)}`),
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
  const top = (dom) => ({ ...base.xaxis, domain: dom, range: xr, title: { text: "rank by Dolma train χ", font: { size: 12 } } });
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
  const el = document.getElementById(plotId);
  // newPlot, not react: a redraw for another generator must replace the frames, not add to them
  await Plotly.newPlot(el, traces(d.frames[0]), layout, { responsive: true });
  await Plotly.addFrames(el, d.frames.map((f) => ({ name: f.key, data: traces(f) })));
  document.getElementById(statsId).textContent = stats(d.frames[0]);
  el.on("plotly_animatingframe", (e) => {
    document.getElementById(statsId).textContent = stats(d.frames.find((f) => f.key === e.name) || d.frames[0]);
  });
}

// Series of five figures per model, each model in its own dropdown (G23, G28, G82). part is "" for curves, "hist_" for histograms
async function drawSeries(file, divId, part, kindLabel) {
  const d = await load(file);
  const frameName = (f) => (f.key === "doc" ? "doc" : "w" + f.key);
  document.getElementById(divId).innerHTML = d.sets.filter((s) => s !== "V").map((s) => `
    <details class="more sub"><summary>${kindLabel}, ${esc(GEN_LABEL[s] || s)}: ${FRAME_NAMES} (${d.frames[0].docs.toLocaleString()} docs per set, whole document)</summary>
    <p class="note">Animated GIF (5 frames, 1.5 s each): <a href="data/exp2/${d.run}_${s}_${part}animation.gif" target="_blank">open</a></p>
    <div class="cards">${d.frames.map((f) => `<a href="data/exp2/${d.run}_${s}_${part}${frameName(f)}.png" target="_blank"><figure style="margin:0">
      <img src="data/exp2/${d.run}_${s}_${part}${frameName(f)}.png" alt="${esc(kindLabel)}, ${esc(GEN_LABEL[s] || s)}, ${esc(f.label)}" style="width:100%;max-width:560px" loading="lazy">
      <figcaption class="note">${esc(f.label)}, ${f.docs.toLocaleString()} docs per set</figcaption></figure></a>`).join("")}</div></details>`).join("");
}

// Visible result 1: top movers per model, extreme filtered lists (G70, G80)
async function drawKeyMoved() {
  const rows = await load("data/exp2_named_lists.json");
  const select = document.getElementById("key-moved-model");
  select.innerHTML = NAMED_MODELS.map((g) => `<option value="${g}">${esc(SET_LABEL[g])}</option>`).join("");
  select.value = "instruct";
  const top = (model, side) => rows.filter((r) => r.model === model && r.list === "extreme_filtered" && r.class === side)
    .sort((a, b) => (side === "over" ? b.r - a.r : a.r - b.r)).slice(0, 10);
  const table = (list) => tableN(["concept", "r", "name (written from Dolma text)"], list.map((r) => [r.concept, fmt(r.r, 2), nameCell(r.name)]));
  const draw = () => {
    document.getElementById("key-moved-over").innerHTML = table(top(select.value, "over"));
    document.getElementById("key-moved-under").innerHTML = table(top(select.value, "under"));
  };
  select.onchange = draw;
  draw();
}

// Visible results 2-4: excess dispersion, scatter, shuffle share, Δ slope (G40, G42, G43, G45, G58, G80)
async function drawKeyDistribution() {
  const d = await load("data/exp2_diagnostics.json");
  const shape = Object.fromEntries(d.shape_dispersion.map((r) => [r.set, r]));
  const labels = NAMED_MODELS.map((g) => SET_LABEL[g]);
  const D = layoutBase();
  D.margin.l = 170; D.margin.b = 45;
  D.xaxis = { ...D.xaxis, title: "excess dispersion: sd of r beyond noise (ln units)", rangemode: "tozero" };
  D.yaxis = { ...D.yaxis, autorange: "reversed" };
  await Plotly.newPlot("key-dispersion", [{ type: "bar", orientation: "h", y: labels, x: NAMED_MODELS.map((g) => shape[g].excess_dispersion_sd), text: NAMED_MODELS.map((g) => fmt(shape[g].excess_dispersion_sd, 2)), textposition: "auto",
    marker: { color: NAMED_MODELS.map((g) => css(GEN_COLOR[g])) }, hovertemplate: "%{y}: %{x:.3f}<extra></extra>" }], D, PLOT_CFG);

  const select = document.getElementById("key-scatter-model");
  select.innerHTML = NAMED_MODELS.map((g) => `<option value="${g}">${esc(SET_LABEL[g])}</option>`).join("");
  select.value = "instruct";
  const image = (s) => `<figure style="margin:0"><figcaption class="note">${esc(SET_LABEL[s])} vs Dolma train</figcaption><a href="${d.figures[s].scatter}" target="_blank"><img src="${d.figures[s].scatter}" alt="Per-concept χ, ${esc(SET_LABEL[s])} vs Dolma train" style="width:100%"></a></figure>`;
  const drawScatter = () => { document.getElementById("key-scatter").innerHTML = image("V") + image(select.value); };
  select.onchange = drawScatter;
  drawScatter();

  const sets = ["V", ...NAMED_MODELS];
  const S = layoutBase();
  S.barmode = "stack"; S.margin.l = 170; S.margin.b = 45; S.legend.y = -0.28;
  S.xaxis = { ...S.xaxis, title: "share of the per-concept change", tickformat: ".0%", range: [0, 1] };
  S.yaxis = { ...S.yaxis, autorange: "reversed" };
  const shareBar = (name, key, color) => ({ type: "bar", orientation: "h", name, y: sets.map((s) => SET_LABEL[s]), x: sets.map((s) => shape[s][key]), text: sets.map((s) => Math.round(100 * shape[s][key]) + "%"), textposition: "inside",
    marker: { color: css(color) }, hovertemplate: `${name}, %{y}: %{x:.1%}<extra></extra>` });
  await Plotly.newPlot("key-shuffle", [shareBar("rank shuffle (histogram unchanged)", "shuffle_share", "--accent"), shareBar("histogram shape", "shape_share", "--middle")], S, PLOT_CFG);

  const series = [["all_docs", "all docs", "--accent", -0.12], ["garbled_removed", "garbled docs removed", "--over", 0.12]];
  const traces = series.map(([key, name, color, off]) => {
    const t = d.delta[key], rows = NAMED_MODELS.map((g) => t.sets[g]);
    return { type: "scatter", mode: "markers", name: `${name} (${t.docs.toLocaleString()} docs per set)`, x: rows.map((r) => r.delta_bias_corrected), y: NAMED_MODELS.map((_, i) => i + off), marker: { size: 11, color: css(color) },
      error_x: { type: "data", symmetric: false, array: rows.map((r) => Math.max(0, r.ci95_basic[1] - r.delta_bias_corrected)), arrayminus: rows.map((r) => Math.max(0, r.delta_bias_corrected - r.ci95_basic[0])), color: css(color), thickness: 1.5 },
      customdata: rows.map((r, i) => [SET_LABEL[NAMED_MODELS[i]], r.ci95_basic[0], r.ci95_basic[1]]), hovertemplate: `%{customdata[0]}, ${name}<br>Δ %{x:.3f} [%{customdata[1]:.3f}, %{customdata[2]:.3f}]<extra></extra>` };
  });
  const L = layoutBase();
  L.margin.l = 170; L.legend.y = -0.25;
  L.xaxis = { ...L.xaxis, title: "Δ slope vs held-out Dolma (bias-corrected, 95% interval)" };
  L.yaxis = { ...L.yaxis, tickvals: NAMED_MODELS.map((_, i) => i), ticktext: labels, autorange: "reversed" };
  L.shapes = [{ type: "line", yref: "paper", y0: 0, y1: 1, x0: 0, x1: 0, line: { width: 1.5, color: css("--muted") } }];
  await Plotly.newPlot("key-delta", traces, L, PLOT_CFG);
}

// Exp 2 diagnostics tables (design.md G61), read from data/exp2_diagnostics.json, which s17_space_diag.py builds from the committed results files.
async function drawDiagnostics() {
  const d = await load("data/exp2_diagnostics.json");
  const name = (s) => SET_LABEL[s] || s;
  const sgn = (x, k = 3) => (x === null || x === undefined ? "–" : (x < 0 ? "−" : "+") + Math.abs(x).toFixed(k));
  const table = (head, rows) => `<div class="table-wrap"><table class="diag"><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  // G40 figures, one row per set
  document.getElementById("diag-figures").innerHTML = d.sets.map((s) => `
    <h3>${esc(name(s))}</h3>
    <div class="diag-figs">${["scatter", "hist_shifted"].map((k) => `<a href="${d.figures[s][k]}" target="_blank">
      <img src="${d.figures[s][k]}" alt="${k === "scatter" ? "per-concept scatter" : "shifted histograms"}, ${esc(name(s))}" loading="lazy"></a>`).join("")}</div>`).join("");
  // G40 and G42
  document.getElementById("diag-shape").innerHTML = table(
    ["set", "rank-shuffle share of D<sub>pair</sub>", "shape share", "Spearman ρ", "Var(r)", "trend share of Var(r)", "excess dispersion sd"],
    d.shape_dispersion.map((r) => [esc(name(r.set)), fmt(r.shuffle_share, 3), fmt(r.shape_share, 3), fmt(r.spearman, 3), fmt(r.var_r, 3),
      fmt(r.trend_share, 4), r.set === "V" ? "0 (reference)" : fmt(r.excess_dispersion_sd, 3)]));
  // G47-G53: names only, no window text
  const m = d.moved;
  const KIND = { gainer: "gainers", loser: "losers", control: "controls" };
  const agree = (a) => (a === true ? "yes" : a === false ? "<b>no</b>" : "not scored");
  document.getElementById("diag-moved").innerHTML = table(
    ["group", "concepts", "scored", "agree share", "mean gap on Dolma", "mean gap on rollouts"],
    m.groups.map((g) => [KIND[g.kind], g.concepts, g.scored, fmt(g.agree_share, 2), sgn(g.mean_gap_on_dolma, 3), sgn(g.mean_gap_on_rollouts, 3)]))
    + m.groups.map((g) => `<h3>${KIND[g.kind]}</h3>` + table(
      ["concept", "set", "rank in train", "name from Dolma V windows", "name from rollout windows", "gap on Dolma", "gap on rollouts", "agree"],
      m.concepts.filter((c) => c.kind === g.kind).map((c) => [c.concept, esc(c.set), c.rank_train.toLocaleString(), nameCell(c.dolma_name),
        nameCell(c.rollout_name), sgn(c.gap_on_dolma, 2), sgn(c.gap_on_rollouts, 2), agree(c.agree)]))).join("");
  // G43, G58, G60
  const t = d.delta;
  const cell = (x) => `<b>${sgn(x.delta_bias_corrected, 4)}</b><br><span class="note">Δ ${sgn(x.delta, 4)}, CI ${sgn(x.ci95_basic[0], 3)} to ${sgn(x.ci95_basic[1], 3)}</span>`;
  const ctl = (x) => `<b>${sgn(x.control_mean, 4)}</b> ± ${fmt(x.control_sd, 4)}<br><span class="note">range ${sgn(x.control_min, 4)} to ${sgn(x.control_max, 4)}</span>`;
  const n = (x) => x.docs.toLocaleString() + " docs";
  document.getElementById("diag-delta").innerHTML = table(
    ["set", `all docs<br><span class="note">${n(t.all_docs)}</span>`, `length-matched<br><span class="note">${n(t.length_matched)}</span>`,
      `garbled removed<br><span class="note">${n(t.garbled_removed)}</span>`, `count control<br><span class="note">${n(t.count_control)}, ${t.count_control.draws} draws</span>`],
    Object.keys(t.all_docs.sets).map((g) => [esc(name(g)), cell(t.all_docs.sets[g]), cell(t.length_matched.sets[g]), cell(t.garbled_removed.sets[g]),
      ctl(t.count_control.sets[g])]));
}

// Names per model (design.md G76, G80, G81): read from data/exp2_named.json and data/exp2_named_lists.json, built by
// s23_space_named.py from the committed results files. Names and numbers only, no window text.
const NAMED_CELLS = ["random_over", "random_middle", "random_under", "extreme_over", "extreme_under_filtered", "extreme_under_unfiltered"];
const NAMED_CELL_LABEL = { random_over: "Random, over", random_middle: "Random, middle", random_under: "Random, under", extreme_over: "Extreme, over",
  extreme_under_filtered: "Extreme, under, filtered", extreme_under_unfiltered: "Extreme, under, unfiltered" };
const NAMED_MODEL_LABEL = SET_LABEL;
const NAMED_GROUP_LABEL = { base: "base (stage1, main)", instruct: "instruct (SFT, DPO, Instruct)" };
const NAMED_LIST_LABEL = { random: "random", extreme_unfiltered: "extreme, unfiltered", extreme_filtered: "extreme, filtered" };
const sgnN = (x, k = 3) => (x === null || x === undefined ? "–" : (x < 0 ? "−" : "+") + Math.abs(x).toFixed(k));
const ciN = (c, k = 3) => (c ? `[${sgnN(c[0], k)}, ${sgnN(c[1], k)}]` : "–");
const escN = (s) => esc(s === null || s === undefined || s === "" ? "–" : String(s));
function tableN(head, rows) {  // rows: arrays of cells, or { cells, cls } for a row class
  return `<div class="table-wrap"><table class="diag"><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => {
    const cells = Array.isArray(r) ? r : r.cells;
    return `<tr${r.cls ? ` class="${r.cls}"` : ""}>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`;
  }).join("")}</tbody></table></div>`;
}
const hoverN = (t, n = 60) => {  // one sentence, wrapped (W8, G81)
  if (!t) return "no name";
  const out = []; let line = "";
  for (const w of shortName(t).split(" ")) { if ((line + " " + w).length > n && line) { out.push(line); line = w; } else line = line ? line + " " + w : w; }
  out.push(line);
  return out.map((x) => x.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")).join("<br>");
};
const statsRow = (label, t, cls) => ({ cls, cells: [label, t.drawn, t.scored_pairs,
  Object.entries(t.status).filter(([k]) => k !== "scored").map(([k, v]) => `${esc(k.replace(/_/g, " "))}: ${v}`).join("<br>") || "0",
  fmt(t.mean_dolma_name), fmt(t.mean_rollout_name), `<b>${sgnN(t.mean_gap)}</b> ${ciN(t.gap_ci95)}`, `${fmt(t.share_dolma_below_0_6)} ${t.share_ci95 ? `[${fmt(t.share_ci95[0])}, ${fmt(t.share_ci95[1])}]` : "–"}`] });
const STATS_HEAD = ["set", "drawn", "scored", "unscored", "Dolma name, mean", "rollout name, mean", "gap [95%]", "Dolma names below 0.6 [95%]"];
const groupColors = () => ({ base: css("--sft"), instruct: css("--accent") });

// Visible result 5: gap per cell
function drawNamedForest(d) {
  const c = d.tables.cells, groupColor = groupColors();
  const forest = ["base", "instruct"].map((g, gi) => {
    const rows = NAMED_CELLS.map((k, i) => ({ t: c[`${g}_${k}`], y: i + (gi ? 0.14 : -0.14), k }));
    return { type: "scatter", mode: "markers", name: NAMED_GROUP_LABEL[g], x: rows.map((r) => r.t.mean_gap), y: rows.map((r) => r.y),
      error_x: { type: "data", symmetric: false, array: rows.map((r) => r.t.gap_ci95[1] - r.t.mean_gap), arrayminus: rows.map((r) => r.t.mean_gap - r.t.gap_ci95[0]), color: groupColor[g], thickness: 1.5 },
      marker: { size: 10, color: groupColor[g] },
      customdata: rows.map((r) => [NAMED_CELL_LABEL[r.k], r.t.scored_pairs, r.t.gap_ci95[0], r.t.gap_ci95[1]]),
      hovertemplate: `${g}, %{customdata[0]}<br>gap %{x:.3f} [%{customdata[2]:.3f}, %{customdata[3]:.3f}]<br>%{customdata[1]} scored<extra></extra>` };
  });
  const L = layoutBase();
  L.margin.l = 190;
  L.xaxis = { ...L.xaxis, title: "gap: Dolma name score − rollout name score" };
  L.yaxis = { ...L.yaxis, tickvals: NAMED_CELLS.map((_, i) => i), ticktext: NAMED_CELLS.map((k) => NAMED_CELL_LABEL[k]), autorange: "reversed" };
  L.shapes = [{ type: "line", yref: "paper", y0: 0, y1: 1, x0: 0, x1: 0, line: { width: 1.5, color: css("--muted") } }];
  return Plotly.newPlot("named-forest", forest, L, PLOT_CFG);
}

function drawNamedScorePlots(d) {  // inside the all-cells dropdown
  const c = d.tables.cells, groupColor = groupColors();
  const means = [["base", "mean_dolma_name", "base, Dolma name", "--sft", 1], ["base", "mean_rollout_name", "base, rollout name", "--sft", 0.45],
    ["instruct", "mean_dolma_name", "instruct, Dolma name", "--accent", 1], ["instruct", "mean_rollout_name", "instruct, rollout name", "--accent", 0.45]].map(([g, f, name, col, op]) => ({
    type: "bar", name, x: NAMED_CELLS.map((k) => NAMED_CELL_LABEL[k]), y: NAMED_CELLS.map((k) => c[`${g}_${k}`][f]), marker: { color: css(col), opacity: op }, hovertemplate: `${name}<br>%{x}: %{y:.3f}<extra></extra>` }));
  const M = layoutBase();
  M.barmode = "group";
  M.yaxis = { ...M.yaxis, title: "balanced accuracy", range: [0.4, 1] };
  M.legend.y = -0.22;
  Plotly.newPlot("named-means", means, M, PLOT_CFG);
  const low = ["base", "instruct"].map((g) => {
    const t = NAMED_CELLS.map((k) => c[`${g}_${k}`]);
    return { type: "bar", name: NAMED_GROUP_LABEL[g], x: NAMED_CELLS.map((k) => NAMED_CELL_LABEL[k]), y: t.map((x) => x.share_dolma_below_0_6), marker: { color: groupColor[g] },
      error_y: { type: "data", symmetric: false, array: t.map((x) => x.share_ci95[1] - x.share_dolma_below_0_6), arrayminus: t.map((x) => x.share_dolma_below_0_6 - x.share_ci95[0]) }, hovertemplate: "%{x}: %{y:.3f}<extra></extra>" };
  });
  const S = layoutBase();
  S.barmode = "group";
  S.yaxis = { ...S.yaxis, title: "share below 0.6" };
  S.legend.y = -0.25;
  Plotly.newPlot("named-low", low, S, PLOT_CFG);
}

const pairHover = (p) => `<b>concept ${p.concept}</b>, ${p.model}, ${p.cell.replace(/_/g, " ")}<br><b>Dolma:</b> ${hoverN(p.dolma_name)}<br><b>Rollout:</b> ${hoverN(p.rollout_name)}`;
function drawNamedDocsPlot(d) {  // inside the gap vs rollout docs dropdown
  const groupColor = groupColors(), scored = d.pairs.filter((p) => p.gap !== null);
  const docs = ["base", "instruct"].map((g) => {
    const p = scored.filter((x) => x.group === g);
    return { type: "scatter", mode: "markers", name: NAMED_GROUP_LABEL[g], x: p.map((x) => x.n_fire_model), y: p.map((x) => x.gap), text: p.map(pairHover), marker: { size: 8, color: groupColor[g], opacity: 0.75 }, hovertemplate: "%{text}<br>%{x} rollout docs, gap %{y:.3f}<extra></extra>" };
  });
  const D = layoutBase();
  D.xaxis = { ...D.xaxis, type: "log", title: "firing docs in the model's rollouts (log scale)" };
  D.yaxis = { ...D.yaxis, title: "gap: Dolma name score − rollout name score" };
  D.shapes = [{ type: "line", yref: "paper", y0: 0, y1: 1, x0: 40, x1: 40, line: { dash: "dash", width: 1, color: css("--muted") } },
    { type: "line", xref: "paper", x0: 0, x1: 1, y0: 0, y1: 0, line: { width: 1, color: css("--muted") } }];
  Plotly.newPlot("named-docs", docs, D, PLOT_CFG);
}

function drawNamedScoresPlot(d) {  // inside the score against score dropdown
  const scored = d.pairs.filter((p) => p.gap !== null);
  const side = (k) => (k.includes("over") ? "over" : k.includes("under") ? "under" : "middle");
  const scatter = ["over", "middle", "under"].map((cl) => {
    const p = scored.filter((x) => side(x.cell) === cl);
    return { type: "scatter", mode: "markers", name: cl, x: p.map((x) => x.dolma_score), y: p.map((x) => x.rollout_score), text: p.map(pairHover), marker: { size: 8, color: css("--" + cl), opacity: 0.75 }, hovertemplate: "%{text}<br>Dolma %{x:.3f}, rollout %{y:.3f}<extra></extra>" };
  });
  const X = layoutBase();
  X.xaxis = { ...X.xaxis, title: "Dolma name score", range: [0.3, 1.02] };
  X.yaxis = { ...X.yaxis, title: "rollout name score", range: [0.3, 1.02], scaleanchor: "x" };
  X.shapes = [{ type: "line", x0: 0.3, y0: 0.3, x1: 1.02, y1: 1.02, line: { dash: "dot", width: 1, color: css("--muted") } }];
  Plotly.newPlot("named-scores", scatter, X, PLOT_CFG);
}

function drawNoisePlots(d) {  // inside the noise rerun dropdown
  const classColor = { over: "--over", middle: "--middle", under: "--under" };
  const nc = ["over", "middle", "under"].map((k) => ({ type: "bar", name: k, x: NAMED_MODELS, y: NAMED_MODELS.map((g) => d.noise.models[g].classes[k].mean_share_stays), marker: { color: css(classColor[k]) }, hovertemplate: `${k}, %{x}: %{y:.3f}<extra></extra>` }));
  const NC = layoutBase();
  NC.barmode = "group"; NC.yaxis = { ...NC.yaxis, title: "share staying in the class", range: [0, 1] }; NC.legend.y = -0.2;
  Plotly.newPlot("noise-classes", nc, NC, PLOT_CFG);
  const lists = [["extreme_unfiltered_over", "over, unfiltered", "--over", 1], ["extreme_filtered_over", "over, filtered", "--over", 0.5], ["extreme_unfiltered_under", "under, unfiltered", "--under", 1], ["extreme_filtered_under", "under, filtered", "--under", 0.5]];
  const nl = lists.map(([k, name, col, op]) => ({ type: "bar", name, x: NAMED_MODELS, y: NAMED_MODELS.map((g) => d.noise.models[g].extreme_lists[k].mean_overlap_with_baseline), marker: { color: css(col), opacity: op }, hovertemplate: `${name}, %{x}: %{y:.3f}<extra></extra>` }));
  const NL = layoutBase();
  NL.barmode = "group"; NL.yaxis = { ...NL.yaxis, title: "share of the 50 still in the list", range: [0, 1] }; NL.legend.y = -0.2;
  Plotly.newPlot("noise-lists", nl, NL, PLOT_CFG);
}

function namedTables(d) {
  const T = d.tables, cellLabel = (k) => { const g = k.split("_")[0], c = k.slice(g.length + 1); return `${g}, ${(NAMED_CELL_LABEL[c] || c).toLowerCase()}`; };
  const cellKeys = ["base", "instruct"].flatMap((g) => NAMED_CELLS.map((k) => `${g}_${k}`));
  document.getElementById("named-cells").innerHTML = tableN(STATS_HEAD,
    cellKeys.map((k) => statsRow(cellLabel(k), T.cells[k], ""))
      .concat(Object.entries(T.groups).map(([k, t], i) => statsRow(k.replace("_", ", ") + " (all cells of this kind)", t, i === 0 ? "pooled" : "")))
      .concat(NAMED_CELLS.map((k, i) => statsRow(`both groups, ${NAMED_CELL_LABEL[k].toLowerCase()}`, T.pooled_cells[k], i === 0 ? "pooled" : ""))));
  const split = (tab, suffixes) => tableN(STATS_HEAD, Object.entries(tab).map(([k, t]) => {
    const suffix = suffixes.find(([s]) => k.endsWith(s));
    return statsRow(`${cellLabel(k.slice(0, -suffix[0].length - 1))}: ${suffix[1]}`, t);
  }));
  document.getElementById("named-split-docs").innerHTML = split(T.by_rollout_docs, [["under_40_docs", "under 40 docs"], ["40_or_more_docs", "40+ docs"]]);
  document.getElementById("named-split-missing").innerHTML = split(T.by_missing_from_rollouts, [["missing_from_rollouts", "below e⁻⁵ in rollouts"], ["above_e-5_in_rollouts", "above e⁻⁵ in rollouts"]]);

  // Check entries
  const gs = document.getElementById("pairs-group"), cs = document.getElementById("pairs-cell");
  gs.innerHTML = '<option value="">all</option>' + Object.entries(NAMED_GROUP_LABEL).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  cs.innerHTML = '<option value="">all</option>' + NAMED_CELLS.map((k) => `<option value="${k}">${esc(NAMED_CELL_LABEL[k])}</option>`).join("");
  const pairs = () => {
    const rows = d.pairs.filter((p) => (!gs.value || p.group === gs.value) && (!cs.value || p.cell === cs.value))
      .sort((a, b) => a.group.localeCompare(b.group) || NAMED_CELLS.indexOf(a.cell) - NAMED_CELLS.indexOf(b.cell) || (b.gap ?? -9) - (a.gap ?? -9));
    document.getElementById("pairs-count").textContent = `${rows.length} entries, largest gap first within each cell.`;
    document.getElementById("named-pairs").innerHTML = tableN(["group", "cell", "concept", "model", "r", "noflag class", "train docs", "rollout docs", "below e⁻⁵ in rollouts", "Dolma name", "rollout name", "Dolma docs named", "rollout docs named", "V firing windows", "Dolma score", "rollout score", "gap", "status"],
      rows.map((p) => [p.group, esc(NAMED_CELL_LABEL[p.cell]), p.concept, esc(p.model), fmt(p.r), escN(p.class_noflag), p.n_fire_train.toLocaleString(), p.n_fire_model.toLocaleString(), p.missing_from_rollouts ? "yes" : "no",
        nameCell(p.dolma_name), nameCell(p.rollout_name), p.dolma_docs_named, p.rollout_docs_named, p.quiz_firing_windows, fmt(p.dolma_score), fmt(p.rollout_score), `<b>${sgnN(p.gap)}</b>`, esc(p.status.replace(/_/g, " "))]));
  };
  gs.onchange = cs.onchange = pairs;
  pairs();

  // Noise
  const n = d.noise;
  document.getElementById("noise-note").textContent = `${n.reruns} reruns, each dropping a random ${Math.round(100 * n.drop)}% of docs per set (${n.train_docs.toLocaleString()} train docs; ${n.matched_docs.stage1.toLocaleString()} matched docs per model), recomputing χ, r, the e⁻⁵ cut, classes and extreme lists. The filter's 50-doc cut stays fixed while docs shrink, so filtered lists lose concepts near the cut even when r holds: of the ${n.filter_effect.entries} filtered under entries, the ${n.filter_effect.near} with under ${n.filter_effect.near_cut_docs} rollout docs stay in ${Math.round(100 * n.filter_effect.near_mean_stay)}% of reruns on average, the others in ${Math.round(100 * n.filter_effect.above_mean_stay)}%. No names or quizzes were rerun. Per-concept figures are in the table of all 2,200 entries.`;
  const pc = (x) => (x === null || x === undefined ? "–" : (100 * x).toFixed(1) + "%");
  document.getElementById("noise-table").innerHTML =
    tableN(["model", "class", "concepts", "mean share staying", "concepts staying in all reruns", "median sd of r", "90th percentile sd of r"],
      NAMED_MODELS.flatMap((g) => ["over", "middle", "under"].map((k) => { const x = n.models[g].classes[k]; return [esc(NAMED_MODEL_LABEL[g]), k, x.concepts.toLocaleString(), pc(x.mean_share_stays), pc(x.share_of_concepts_always_stays), fmt(x.median_r_sd), fmt(x.p90_r_sd)]; })))
    + tableN(["model", "list", "mean share of the 50 still in the list", "median concept stays", "least stable concept stays", "median sd of r"],
      NAMED_MODELS.flatMap((g) => Object.entries(n.models[g].extreme_lists).map(([k, x]) => [esc(NAMED_MODEL_LABEL[g]), esc(k.replace("extreme_", "").replace("_", ", ")), pc(x.mean_overlap_with_baseline), pc(x.median_share_stays), pc(x.lowest_share_stays), fmt(x.median_r_sd)])));

  // Selection counts (G83: no cost figures)
  const s = d.selection, u = d.counts, kv = (rows) => tableN(["", ""], rows.map(([a, b]) => [a, b]));
  document.getElementById("named-selection").innerHTML =
    tableN(["model", "ranked (χ<sub>train</sub> ≥ e⁻⁵)", "missing (χ<sub>train</sub> &lt; e⁻⁵)", "per class (over, under)", "χ<sub>model</sub> = 0", "χ<sub>model</sub> &lt; e⁻⁵", "pass the 50-doc filter", "random draws kept from the earlier sample (over, under, middle)"],
      NAMED_MODELS.map((g) => { const x = s.by_model[g]; return [esc(NAMED_MODEL_LABEL[g]), x.ranked_concepts.toLocaleString(), x.missing_chi_train.toLocaleString(), x.class_size.toLocaleString(), x.chi_zero_ranked, x.missing_from_rollouts_ranked.toLocaleString(), x.pass_filter.toLocaleString(), ["over", "under", "middle"].map((k) => x.kept_g62_draws[k]).join(", ")]; }))
    + "<h3>Firing docs of the extreme lists</h3>"
    + tableN(["model", "list", "median train docs", "median rollout docs", "concepts with 0 rollout docs"],
      NAMED_MODELS.flatMap((g) => Object.entries(s.by_model[g].lists).map(([k, x]) => [esc(NAMED_MODEL_LABEL[g]), esc(k.replace("extreme_", "").replace("_", ", ")), x.median_train_docs.toLocaleString(), x.median_rollout_docs.toLocaleString(), x.zero_rollout_docs])))
    + "<h3>Counts</h3>"
    + kv([["list entries", s.entries.toLocaleString()], ["distinct concepts", s.distinct_concepts.toLocaleString()], ["new names planned", u.new_names_planned.toLocaleString()], ["new names returned", u.new_names_returned.toLocaleString()],
      ["new names refused, left unnamed", u.new_names_failed], ["new names from all-train windows (under 40 T1 firing docs)", s.new_from_train], ["of those, from under 40 docs", s.train_docs_named_under_40],
      ["names reused from earlier runs", s.reused_names], ["names written earlier, concept no longer selected", u.names_bought_not_selected], ["check entries", u.check_entries], ["distinct concepts in the check", u.check_distinct],
      ["entries with under 30 firing V windows", d.pairs.filter((p) => p.quiz_firing_windows < 30).length], ["rollout names written", u.rollout_names_new], ["quiz prompts", u.quiz_prompts.toLocaleString()],
      ["check candidates passed over for a failed name", Object.values(u.skipped_for_failed_name).reduce((a, b) => a + b, 0)]])
    + "<h3>Sources of reused names</h3>" + kv(Object.entries(u.reused_by_source).map(([k, v]) => [esc(k), v]))
    + "<h3>Class of the random draws without the flagged garbled docs (recorded only, selects nothing)</h3>"
    + tableN(["model", "class → class without flagged docs: entries"], NAMED_MODELS.map((g) => [esc(NAMED_MODEL_LABEL[g]), esc(Object.entries(d.noflag[g]).sort().map(([k, v]) => `${k.replace("->", " → ")}: ${v}`).join(", "))]));
}

async function drawNamedLists() {
  const rows = await load("data/exp2_named_lists.json");
  const m = document.getElementById("lists-model"), l = document.getElementById("lists-list"), c = document.getElementById("lists-class");
  m.innerHTML = NAMED_MODELS.map((g) => `<option value="${g}">${esc(NAMED_MODEL_LABEL[g])}</option>`).join("");
  l.innerHTML = Object.entries(NAMED_LIST_LABEL).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  c.innerHTML = '<option value="">all</option><option>over</option><option>middle</option><option>under</option>';
  m.value = "instruct"; l.value = "extreme_filtered"; c.value = "under";
  const draw = () => {
    const mine = rows.filter((r) => r.model === m.value);
    const shown = mine.filter((r) => r.list === l.value && (!c.value || r.class === c.value))
      .sort((a, b) => (a.class === "over" && b.class === "over" ? (b.r ?? -99) - (a.r ?? -99) : (a.r ?? -99) - (b.r ?? -99)));
    const noR = mine.filter((r) => r.r === null).length;
    document.getElementById("lists-count").textContent = `${shown.length} entries in the table, strongest first. The chart shows all of this model's entries` + (noR ? `, leaving out ${noR} with χ = 0 (r has no finite value).` : ".");
    document.getElementById("lists-table").innerHTML = tableN(["concept", "class", "r", "r sd", "r 95% over reruns", "stays in class", "stays in list", "train docs", "rollout docs", "T1 docs", "V docs", "χ train", "χ model", "below e⁻⁵ in rollouts", "class without flagged docs", "in check", "Dolma name", "name source"],
      shown.map((r) => [r.concept, r.class, fmt(r.r), fmt(r.r_sd), r.r_lo === null ? "–" : `${fmt(r.r_lo, 2)} to ${fmt(r.r_hi, 2)}`, fmt(r.stay_class, 2), fmt(r.stay_list, 2), r.train_docs.toLocaleString(), r.rollout_docs.toLocaleString(), r.n_T1.toLocaleString(), r.n_V.toLocaleString(), fmt(r.chi_train, 4), fmt(r.chi_model, 4), r.missing ? "yes" : "no", escN(r.class_noflag), r.in_check ? "yes" : "no", nameCell(r.name), escN(r.source)]));
    const colors = { random: "--middle", extreme_filtered: "--accent", extreme_unfiltered: "--over" };
    const traces = Object.keys(NAMED_LIST_LABEL).map((k) => {
      const p = mine.filter((r) => r.list === k && r.r !== null);
      return { type: "scatter", mode: "markers", name: NAMED_LIST_LABEL[k], x: p.map((r) => r.r), y: p.map((r) => r.rollout_docs + 1), customdata: p.map((r) => r.rollout_docs), text: p.map((r) => `<b>concept ${r.concept}</b>, ${r.class}<br>${hoverN(r.name)}`), marker: { size: 7, color: css(colors[k]), opacity: 0.7 }, hovertemplate: "%{text}<br>r %{x:.2f}, %{customdata} rollout docs<extra></extra>" };
    });
    const L = layoutBase();
    L.xaxis = { ...L.xaxis, title: "r = ln(χ model / χ train)" };
    L.yaxis = { ...L.yaxis, type: "log", title: "rollout firing docs + 1 (log scale)" };
    Plotly.react("lists-plot", traces, L, PLOT_CFG);
  };
  m.onchange = l.onchange = c.onchange = draw;
  draw();
}

// G82: a plot inside a dropdown is drawn when it first opens, so it gets the dropdown's width. Tables and figure lists are built on load, so Ctrl+F reaches them.
const NAMED_JSON = "data/exp2_named.json";
const ON_FIRST_OPEN = {
  "sec-rollout-graphs": () => drawCurves("data/rollouts.json", "rollout-gen", "rollout-plot", "rollout-stats"),
  "sec-post": () => drawCurves("data/rollouts_post.json", "post-gen", "post-plot", "post-stats"),
  "sec-named-table": async () => drawNamedScorePlots(await load(NAMED_JSON)),
  "sec-named-docs": async () => drawNamedDocsPlot(await load(NAMED_JSON)),
  "sec-named-scores": async () => drawNamedScoresPlot(await load(NAMED_JSON)),
  "sec-named-noise": async () => drawNoisePlots(await load(NAMED_JSON)),
  "sec-named-lists": drawNamedLists,
};
function wireDropdowns() {
  for (const [id, draw] of Object.entries(ON_FIRST_OPEN)) {
    const el = document.getElementById(id);
    const onToggle = () => { if (el.open) { el.removeEventListener("toggle", onToggle); draw().catch((e) => console.error(e)); } };
    el.addEventListener("toggle", onToggle);
  }
}

async function drawRolloutsTab() {
  const named = await load(NAMED_JSON);
  namedTables(named);
  await drawKeyMoved();
  await drawKeyDistribution();
  await drawNamedForest(named);
  await drawDiagnostics();
  await drawSeries("data/rollouts.json", "rollout-hist", "hist_", "Histograms");
  await drawSeries("data/rollouts_post.json", "post-hist", "hist_", "Histograms");
  await drawSeries("data/rollouts.json", "rollout-gallery", "", "Curves");
  await drawSeries("data/rollouts_post.json", "post-gallery", "", "Curves");
}

// G75, G79, G80: one tab per experiment; a hash may name a tab, a section (sec-<hash>) or a concept page. temp is the old name of rollouts.
// A section inside dropdowns opens them, so old links still land on their result.
async function route() {
  const h = (location.hash.replace("#", "") || "rollouts").replace(/^temp$/, "rollouts");
  const section = document.getElementById("sec-" + h);
  const tab = h.startsWith("c=") ? "concept" : section ? section.closest(".tab").id.slice(4) : h;
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === "tab-" + tab));
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  if (tab === "concept") return drawConcept(h.slice(2));
  for (let el = section; el; el = el.parentElement) if (el.tagName === "DETAILS") el.open = true;
  if (section) section.scrollIntoView();
  if (!drawn[tab]) {
    drawn[tab] = true;
    const steps = tab === "pile" ? [drawOverview, drawNoise, drawPatterns, drawTopics, drawTable]
      : tab === "rollouts" ? [drawRolloutsTab] : [];
    for (const step of steps) await step().catch((e) => console.error(e));  // one failed chart leaves the others drawn
    if (section) section.scrollIntoView();
  }
}
wireDropdowns();
document.getElementById("class-filter").onchange = drawTable;
window.addEventListener("hashchange", route);
route();
