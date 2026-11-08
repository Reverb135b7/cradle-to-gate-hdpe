/* ==========================================================================
   HDPE PCF Control Room — client
   Plain ES2020, no framework. The engine is the single source of truth: every
   interaction posts the full parameter set to /api/simulate and re-renders.
   ========================================================================== */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const state = {
  meta: null,
  params: {},
  data: null,
  tab: "mass",
  preset: "baseline",
  plant: { annualKt: 120, price: 85, target: 5.5 },
  inFlight: 0,
};

const COLORS = {
  scope1: "#ffb545",
  scope2: "#35c6d8",
  scope3: "#9b8cff",
};

/* ------------------------------------------------------------------ utils */
const nf = (v, d = 1) =>
  Number.isFinite(v)
    ? v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })
    : "—";

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

const kfmt = (v) => (Math.abs(v) >= 1000 ? (v / 1000).toFixed(1) + "k" : nf(v, 0));

const trunc = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + "…" : String(s));

function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 3200);
}

function debounce(fn, wait) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

function download(name, text, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const csvCell = (v) => {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const scale = (d0, d1, r0, r1) => (v) =>
  d1 === d0 ? r0 : r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);

/* ------------------------------------------------------------------- boot */
async function boot() {
  try {
    state.meta = await (await fetch("/api/meta")).json();
  } catch (err) {
    toast("Cannot reach the engine API", true);
    return;
  }
  state.params = { ...state.meta.defaults };
  buildPresets();
  buildControls();
  buildPlantBar();
  bindActions();
  await simulate();
}

/* --------------------------------------------------------------- controls */
function buildPresets() {
  const host = $("#presets");
  host.innerHTML = "";
  state.meta.presets.forEach((p) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = p.label.replace(/\s*\(.*?\)\s*/g, " ").trim();
    b.title = p.description;
    b.dataset.key = p.key;
    b.onclick = () => applyPreset(p);
    host.appendChild(b);
  });
}

function applyPreset(preset) {
  state.preset = preset.key;
  state.params = { ...state.meta.defaults };
  Object.entries(preset.overrides).forEach(([k, v]) => {
    if (k in state.params) state.params[k] = Number(v);
  });
  syncControls();
  markPreset();
  simulate();
}

function markPreset() {
  $$("#presets button").forEach((b) => b.classList.toggle("active", b.dataset.key === state.preset));
}

function buildControls() {
  const host = $("#controls");
  host.innerHTML = "";
  state.meta.groups.forEach((group) => {
    const g = document.createElement("section");
    g.className = "group";
    g.innerHTML = `<div class="group-head">${esc(group.label)}<span>${group.fields.length}</span></div>`;
    group.fields.forEach((f) => g.appendChild(controlFor(f)));
    host.appendChild(g);
  });
}

function controlFor(field) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  const decimals = field.decimals ?? 2;
  wrap.innerHTML = `
    <div class="field-top">
      <label for="r-${field.key}" title="${esc(field.hint || "")}">${esc(field.label)}</label>
      <span>
        <input class="field-val" id="n-${field.key}" type="text" inputmode="decimal" />
        <span class="field-unit">${esc(field.unit)}</span>
      </span>
    </div>
    <input type="range" id="r-${field.key}" min="${field.min}" max="${field.max}" step="${field.step}" />`;

  const range = $("#r-" + field.key, wrap);
  const num = $("#n-" + field.key, wrap);

  const commit = (value, from) => {
    const v = clamp(Number(value), field.min, field.max);
    if (!Number.isFinite(v)) return;
    state.params[field.key] = v;
    state.preset = "";
    markPreset();
    if (from !== "range") range.value = v;
    if (from !== "num") num.value = v.toFixed(decimals);
    scheduleSimulate();
  };

  range.addEventListener("input", (e) => commit(e.target.value, "range"));
  num.addEventListener("change", (e) => commit(e.target.value, "num"));
  num.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      commit(e.target.value, "num");
      e.target.blur();
    }
  });

  range.value = state.params[field.key];
  num.value = Number(state.params[field.key]).toFixed(decimals);
  return wrap;
}

function syncControls() {
  state.meta.groups.forEach((group) =>
    group.fields.forEach((f) => {
      const v = state.params[f.key];
      const r = $("#r-" + f.key);
      const n = $("#n-" + f.key);
      if (r) r.value = v;
      if (n) n.value = Number(v).toFixed(f.decimals ?? 2);
    })
  );
}

function buildPlantBar() {
  const bar = document.createElement("div");
  bar.className = "plantbar";
  bar.innerHTML = `
    <div class="plantbar-label">Plant operating case</div>
    <label>Annual output <input id="p-annual" type="number" min="1" max="5000" step="5" value="${state.plant.annualKt}" /> <span class="muted">kt/yr</span></label>
    <label>Carbon price <input id="p-price" type="number" min="0" max="500" step="1" value="${state.plant.price}" /> <span class="muted">EUR/t</span></label>
    <label>Target intensity <input id="p-target" type="number" min="0" max="12" step="0.05" value="${state.plant.target}" /> <span class="muted">t CO2e/t</span></label>
    <div class="plantbar-out" id="plant-out"></div>`;
  $("#kpis").insertAdjacentElement("afterend", bar);

  const link = (id, key) => {
    const el = $("#" + id, bar);
    el.addEventListener("input", () => {
      state.plant[key] = Number(el.value) || 0;
      renderPlantCase();
    });
  };
  link("p-annual", "annualKt");
  link("p-price", "price");
  link("p-target", "target");
}

function renderPlantCase() {
  const host = $("#plant-out");
  if (!host || !state.data) return;
  const { annualKt, price, target } = state.plant;
  const t = state.data.kpis.total_t;
  const annualT = annualKt * 1000 * t;
  const cost = annualT * price;
  const gap = t - target;
  const gapT = annualKt * 1000 * gap;

  host.innerHTML = `
    <div class="plant-out-item"><span>Annual load</span><b>${nf(annualT / 1000, 0)} kt CO<sub>2</sub>e</b></div>
    <div class="plant-out-item"><span>Carbon liability</span><b>${cost >= 1e6 ? "€" + nf(cost / 1e6, 2) + "M" : "€" + nf(cost / 1000, 0) + "k"}</b></div>
    <div class="plant-out-item ${gap > 0 ? "over" : "under"}"><span>Gap to target</span><b>${gap > 0 ? "+" : "−"}${nf(Math.abs(gapT) / 1000, 1)} kt ${gap > 0 ? "above" : "below"}</b></div>`;
}

/* -------------------------------------------------------------- simulation */
let seq = 0;
async function simulate() {
  const my = ++seq;
  state.inFlight += 1;
  $(".workspace").classList.add("is-loading");
  $("#v-status").textContent = "computing";
  $("#v-status").className = "chip";

  try {
    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params: state.params }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "simulation failed");
    if (my !== seq) return;
    state.data = body;
    renderAll();
  } catch (err) {
    toast(err.message, true);
    $("#v-status").textContent = "error";
    $("#v-status").className = "chip fail";
  } finally {
    state.inFlight -= 1;
    if (state.inFlight === 0) $(".workspace").classList.remove("is-loading");
  }
}
const scheduleSimulate = debounce(simulate, 130);

function renderAll() {
  const p = state.data;
  renderHeader(p);
  renderKpis(p);
  renderPlantCase();
  renderFlowsheet(p);
  renderScope(p);
  renderWaterfall(p);
  renderHotspots(p);
  renderSweep(p);
  renderScenarios(p);
  renderTornado(p);
  renderAllocation(p);
  renderUtility(p);
  renderCarbon(p);
  renderChecks(p);
  renderFindings(p);
  renderTabs();
  renderDataTable();
}

function renderHeader(p) {
  const chip = $("#v-status");
  chip.textContent = p.validation.status;
  chip.className = "chip " + p.validation.status.toLowerCase();
  $("#h-total").textContent = nf(p.kpis.total_t, 3);
  $("#h-batch").textContent = `${nf(p.kpis.hdpe_t, 0)} t batch · ${nf(p.kpis.per_kg, 2)} kg/kg`;
  const d = p.kpis.delta_vs_spec_pct;
  const el = $("#h-delta");
  el.textContent = `${d >= 0 ? "+" : ""}${nf(d, 3)} % vs spec`;
  el.className = "delta " + (Math.abs(d) < 0.5 ? "good" : "bad");
}

function renderKpis(p) {
  const k = p.kpis;
  const v = p.validation;
  const failed = v.checks.filter((c) => c.status === "FAIL").length;
  const cards = [
    { label: "Cradle-to-gate PCF", value: nf(k.total_t, 3), unit: "t CO2e/t", foot: `${nf(k.total_kg, 0)} kg CO2e per t resin`, cls: "accent" },
    { label: "Scope 1 · direct", value: nf(k.scope1_kg, 0), unit: "kg", foot: `${nf(k.scope1_share, 1)} % of footprint`, cls: "" },
    { label: "Scope 2 · energy", value: nf(k.scope2_kg, 0), unit: "kg", foot: `${nf(k.scope2_share, 1)} % · grid ${nf(state.params.ef_grid, 3)} kg/kWh`, cls: "cyan" },
    { label: "Scope 3 · upstream", value: nf(k.scope3_kg, 0), unit: "kg", foot: `${nf(k.scope3_share, 1)} % · ${nf(k.ng_t, 3)} t NG`, cls: "" },
    { label: "Primary energy", value: nf(k.energy_per_t, 1), unit: "GJ/t", foot: `${nf(k.methanol_t, 3)} t MeOH · ${nf(k.ethylene_t, 3)} t C2H4`, cls: "" },
    {
      label: "Specification match",
      value: `${v.checks.filter((c) => c.status !== "FAIL").length}/${v.checks.length}`,
      unit: "checks",
      foot: failed ? `${failed} failed · ${v.findings.length} findings` : `${v.findings.length} findings logged`,
      cls: v.status === "PASS" ? "green" : "",
    },
  ];
  $("#kpis").innerHTML = cards
    .map(
      (c) => `<article class="kpi ${c.cls}">
        <div class="kpi-label">${c.label}</div>
        <div class="kpi-value">${c.value}<small>${c.unit}</small></div>
        <div class="kpi-foot">${c.foot}</div>
      </article>`
    )
    .join("");
}

/* --------------------------------------------------------------- flowsheet */
function renderFlowsheet(p) {
  const s = p.stages;
  const k = p.kpis;
  const W = 760;
  const H = 258;
  const bw = 146;
  const gap = (W - 42 - 4 * bw) / 3;
  const xs = [0, 1, 2, 3].map((i) => i * (bw + gap));
  const yTop = 46;
  const bh = 62;
  const flows = [`${nf(k.ng_t, 3)} t`, `${nf(k.methanol_t, 3)} t`, `${nf(k.ethylene_t, 3)} t`, `${nf(k.hdpe_t, 3)} t`];
  const names = ["Natural gas", "Methanol", "Ethylene (MTO)", "HDPE resin"];
  const subs = ["Scope 3.1 only", "SMR / ATR + synthesis", "SAPO-34 + separation", "Polymerisation"];
  const inflow = [`${nf(k.ng_t, 3)} t NG`, "", "", ""];

  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Process flowsheet">`;
  svg += `<defs><marker id="ah" markerWidth="7" markerHeight="7" refX="5.6" refY="3.2" orient="auto">
      <path d="M0,0 L6,3.2 L0,6.4 z" fill="#35c6d8"/></marker>
      <marker id="aha" markerWidth="7" markerHeight="7" refX="5.6" refY="3.2" orient="auto">
      <path d="M0,0 L6,3.2 L0,6.4 z" fill="#ffb545"/></marker></defs>`;

  // feedstock arrow entering node 1
  svg += `<text x="0" y="26" class="axis-text">feedstock</text>`;
  svg += `<text x="${W}" y="26" class="axis-text" text-anchor="end">functional unit: 1 t pelletised HDPE, factory gate</text>`;

  s.forEach((stage, i) => {
    const x = xs[i];
    const hot = stage.share_pct > 45;
    svg += `<rect x="${x}" y="${yTop}" width="${bw}" height="${bh}" rx="2" class="node-box ${hot ? "hot" : ""}"/>`;
    svg += `<rect x="${x}" y="${yTop}" width="3" height="${bh}" fill="${hot ? "#ffb545" : "#35c6d8"}"/>`;
    svg += `<text x="${x + 12}" y="${yTop + 19}" class="node-title">${esc(names[i])}</text>`;
    svg += `<text x="${x + 12}" y="${yTop + 34}" class="node-sub">${esc(subs[i])}</text>`;
    svg += `<text x="${x + 12}" y="${yTop + 52}" class="node-sub" fill="#a8b7c4">${esc(trunc(stage.label.split("&")[0].trim(), 23))}</text>`;

    // emissions badge
    const by = yTop + bh + 22;
    svg += `<rect x="${x}" y="${by}" width="${bw}" height="46" rx="2" fill="#11171d" stroke="#26313b"/>`;
    svg += `<text x="${x + 10}" y="${by + 17}" class="node-sub" fill="#6d7f8e">${esc(stage.key.toUpperCase())}</text>`;
    svg += `<text x="${x + bw - 10}" y="${by + 17}" text-anchor="end" class="peak-label">${nf(stage.total, 0)} kg</text>`;
    const wAvail = bw - 20;
    let cx = x + 10;
    [
      ["scope1", stage.scope1],
      ["scope2", stage.scope2],
      ["scope3", stage.scope3],
    ].forEach(([key, val]) => {
      if (stage.total <= 0) return;
      const w = Math.max(val > 0 ? 2 : 0, (val / stage.total) * wAvail);
      svg += `<rect x="${cx}" y="${by + 24}" width="${w}" height="7" fill="${COLORS[key]}"/>`;
      cx += w;
    });
    svg += `<text x="${x + 10}" y="${by + 42}" class="node-sub" fill="#6d7f8e">${nf(stage.share_pct, 1)}%</text>`;
    svg += `<text x="${x + bw - 10}" y="${by + 42}" text-anchor="end" class="node-sub" fill="#6d7f8e">S1 ${kfmt(stage.scope1)} · S2 ${kfmt(stage.scope2)}</text>`;

    // arrows
    if (i < 3) {
      const x0 = x + bw + 6;
      const x1 = xs[i + 1] - 8;
      const y = yTop + bh / 2;
      svg += `<line x1="${x0}" y1="${y}" x2="${x1}" y2="${y}" class="flow" marker-end="url(#ah)"/>`;
      svg += `<text x="${(x0 + x1) / 2}" y="${y - 8}" class="peak-label" text-anchor="middle">${flows[i + 1]}</text>`;
      svg += `<text x="${(x0 + x1) / 2}" y="${y + 14}" class="axis-text" text-anchor="middle">${["CH3OH", "C2H4", "polymer"][i]}</text>`;
    }
  });

  // product out
  const lastX = xs[3] + bw + 6;
  svg += `<line x1="${lastX}" y1="${yTop + bh / 2}" x2="${lastX + 30}" y2="${yTop + bh / 2}" class="flow-hot" marker-end="url(#aha)"/>`;
  svg += `<text x="${W}" y="${yTop + bh + 16}" text-anchor="end" class="peak-label">${nf(k.total_t, 2)} t CO2e at gate</text>`;

  // energy band
  const by = yTop + bh + 78;
  svg += `<line x1="0" y1="${by}" x2="${W}" y2="${by}" class="axis-line"/>`;
  svg += `<text x="0" y="${by + 16}" class="axis-text">utility load</text>`;
  const util = p.utility.nodes.map((n) => `${nf((n.electricity_kg + n.steam_kg) / 1000, 2)}`).join(" / ");
  svg += `<text x="90" y="${by + 16}" class="node-sub" fill="#a8b7c4">Scope 2 kg per stage: ${util}</text>`;
  svg += `<text x="${W}" y="${by + 16}" text-anchor="end" class="axis-text">${nf(k.energy_per_t, 1)} GJ per t resin</text>`;
  svg += `</svg>`;
  $("#flowsheet").innerHTML = svg;
}

/* ------------------------------------------------------------------ scope */
function renderScope(p) {
  const k = p.kpis;
  const segs = [
    ["scope1", "Scope 1", k.scope1_kg, k.scope1_share],
    ["scope2", "Scope 2", k.scope2_kg, k.scope2_share],
    ["scope3", "Scope 3", k.scope3_kg, k.scope3_share],
  ];
  $("#scopebar").innerHTML = `<div class="scopebar-track">${segs
    .map(
      ([key, , , share]) =>
        `<div class="scopebar-seg" style="width:${share}%;background:${COLORS[key]}">${share > 9 ? nf(share, 1) + "%" : ""}</div>`
    )
    .join("")}</div>`;

  $("#scopelist").innerHTML =
    segs
      .map(
        ([key, label, value, share]) => `<div class="scope-row">
          <span class="scope-swatch" style="background:${COLORS[key]}"></span>
          <span>${label}</span>
          <b>${nf(value, 0)} kg</b>
          <span class="muted">${nf(share, 1)} %</span>
        </div>`
      )
      .join("") +
    `<div class="scope-row" style="border-bottom:0;margin-top:2px">
      <span class="scope-swatch" style="background:#e8eef3"></span>
      <span>Total</span><b>${nf(k.total_kg, 0)} kg</b><span class="muted">100 %</span>
    </div>`;
}

/* --------------------------------------------------------------- waterfall */
function renderWaterfall(p) {
  const s = p.stages;
  const W = 700, H = 210;
  const pad = { l: 34, r: 8, t: 16, b: 30 };
  const max = Math.max(...s.map((x) => x.cumulative)) * 1.06;
  const x = scale(0, s.length, pad.l + 10, W - pad.r - 20);
  const y = scale(0, max, H - pad.b, pad.t);
  const barW = Math.min(72, (W - pad.l - pad.r) / (s.length + 1) - 18);

  let svg = `<svg viewBox="0 0 ${W} ${H}">`;
  for (let i = 0; i <= 4; i++) {
    const val = (max / 4) * i;
    svg += `<line x1="${pad.l}" y1="${y(val)}" x2="${W - pad.r}" y2="${y(val)}" class="grid-line"/>`;
    svg += `<text x="${pad.l - 6}" y="${y(val) + 3}" text-anchor="end" class="axis-text">${nf(val, 0)}</text>`;
  }
  svg += `<text x="${pad.l - 6}" y="${pad.t - 4}" text-anchor="end" class="axis-text">kg</text>`;

  s.forEach((stage, i) => {
    const cx = x(i + 0.5);
    const base = stage.cumulative - stage.total;
    const yTop = y(stage.cumulative);
    const yBase = y(base);
    svg += `<rect x="${cx - barW / 2}" y="${yTop}" width="${barW}" height="${Math.max(1.5, yBase - yTop)}" fill="${COLORS.scope1}" opacity="0.9" class="bar"/>`;
    // stacked scope split
    let acc = base;
    const parts = [
      ["scope3", stage.scope3],
      ["scope2", stage.scope2],
      ["scope1", stage.scope1],
    ];
    parts.forEach(([key, val]) => {
      if (val <= 0) return;
      const y1 = y(acc + val);
      const y2 = y(acc);
      svg += `<rect x="${cx - barW / 2}" y="${y1}" width="${barW}" height="${Math.max(0.8, y2 - y1)}" fill="${COLORS[key]}" opacity="0.92"/>`;
      acc += val;
    });
    svg += `<text x="${cx}" y="${yTop - 5}" text-anchor="middle" class="peak-label">${nf(stage.total, 0)}</text>`;
    svg += `<text x="${cx}" y="${H - pad.b + 13}" text-anchor="middle" class="axis-text">${esc(stage.key.replace(/_/g, " "))}</text>`;
    svg += `<text x="${cx}" y="${H - pad.b + 25}" text-anchor="middle" class="axis-text">${nf(stage.share_pct, 0)}%</text>`;
    if (i < s.length - 1) {
      svg += `<line x1="${cx + barW / 2}" y1="${y(stage.cumulative)}" x2="${x(i + 1.5) - barW / 2}" y2="${y(stage.cumulative)}" class="grid-line" stroke="#3a4854"/>`;
    }
  });
  const endX = x(s.length + 0.5) - barW / 2;
  const totalY = y(p.kpis.total_kg);
  svg += `<line x1="${x(s.length - 0.5) + barW / 2}" y1="${totalY}" x2="${W - pad.r - 6}" y2="${totalY}" stroke="#e8eef3" stroke-width="1"/>`;
  svg += `<text x="${W - pad.r - 6}" y="${totalY - 5}" text-anchor="end" class="peak-label">${nf(p.kpis.total_kg, 0)} kg</text>`;
  svg += `</svg>`;
  $("#waterfall").innerHTML = svg;
}

/* ---------------------------------------------------------------- hotspots */
function renderHotspots(p) {
  const rows = p.layers;
  const W = 460, H = 190;
  const pad = { l: 118, r: 52, t: 12, b: 22 };
  const max = Math.max(...rows.map((r) => r.total_t)) * 1.04;
  const x = scale(0, max, pad.l, W - pad.r);
  const rowH = (H - pad.t - pad.b) / rows.length;

  let svg = `<svg viewBox="0 0 ${W} ${H}">`;
  for (let i = 0; i <= 3; i++) {
    const val = (max / 3) * i;
    svg += `<line x1="${x(val)}" y1="${pad.t}" x2="${x(val)}" y2="${H - pad.b}" class="grid-line"/>`;
  }
  rows.forEach((r, i) => {
    const y0 = pad.t + i * rowH + rowH * 0.22;
    const h = rowH * 0.56;
    let acc = 0;
    [
      ["scope3", r.embedded_upstream_t, "embedded upstream"],
      ["scope2", r.scope2_t, "Scope 2"],
      ["scope1", r.scope1_t, "Scope 1"],
    ].forEach(([key, val]) => {
      if (!val) return;
      svg += `<rect x="${x(acc)}" y="${y0}" width="${Math.max(1, x(acc + val) - x(acc))}" height="${h}" fill="${COLORS[key]}"><title>${key}: ${nf(val, 3)} t</title></rect>`;
      acc += val;
    });
    const label = String(r.layer || r.node || "").replace(/_/g, " ");
    svg += `<text x="${pad.l - 8}" y="${y0 + h / 2 + 3}" text-anchor="end" class="axis-text" fill="#a8b7c4">${esc(trunc(label, 22))}</text>`;
    svg += `<text x="${x(r.total_t) + 5}" y="${y0 + h / 2 + 3}" class="peak-label">${nf(r.total_t, 2)}</text>`;
  });
  svg += `<text x="${pad.l}" y="${H - 4}" class="axis-text">t CO2e per functional unit · ${esc(rows[0]?.basis || "")}</text>`;
  svg += `</svg>`;
  $("#hotspots").innerHTML = svg;
}

/* ------------------------------------------------------------------- sweep */
function renderSweep(p) {
  const rows = p.sweep;
  const W = 640, H = 210;
  const pad = { l: 40, r: 14, t: 16, b: 30 };
  const xs = rows.map((r) => r.ef_grid);
  const ys = rows.map((r) => r.pcf_t);
  const yMin = 0;
  const yMax = Math.max(...ys) * 1.08;
  const x = scale(Math.min(...xs), Math.max(...xs), pad.l, W - pad.r);
  const y = scale(yMin, yMax, H - pad.b, pad.t);

  let svg = `<svg viewBox="0 0 ${W} ${H}">`;
  for (let i = 0; i <= 3; i++) {
    const val = (yMax / 3) * i;
    svg += `<line x1="${pad.l}" y1="${y(val)}" x2="${W - pad.r}" y2="${y(val)}" class="grid-line"/>`;
    svg += `<text x="${pad.l - 6}" y="${y(val) + 3}" text-anchor="end" class="axis-text">${nf(val, 1)}</text>`;
  }
  [0, 0.2, 0.4, 0.6].forEach((g) => {
    if (g < Math.min(...xs) || g > Math.max(...xs)) return;
    svg += `<text x="${x(g)}" y="${H - pad.b + 14}" text-anchor="middle" class="axis-text">${g.toFixed(2)}</text>`;
  });

  const path = ys.map((v, i) => `${i ? "L" : "M"}${x(xs[i]).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  svg += `<path d="${path}" fill="none" stroke="#35c6d8" stroke-width="1.8"/>`;
  svg += `<path d="${path} L${x(xs[xs.length - 1])},${y(0)} L${x(xs[0])},${y(0)} Z" fill="url(#grad)" opacity="0.28"/>`;
  svg += `<defs><linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#35c6d8"/><stop offset="100%" stop-color="#35c6d8" stop-opacity="0"/>
    </linearGradient></defs>`;

  // spec reference
  const specX = 0.475;
  svg += `<line x1="${x(specX)}" y1="${pad.t}" x2="${x(specX)}" y2="${H - pad.b}" stroke="#ffb545" stroke-width="1" stroke-dasharray="3 3"/>`;
  svg += `<text x="${x(specX) + 4}" y="${pad.t + 9}" class="axis-text" fill="#ffb545">spec grid 0.475</text>`;

  // current operating point
  const cur = p.kpis;
  svg += `<circle cx="${x(state.params.ef_grid)}" cy="${y(cur.total_t)}" r="3.6" fill="#ffb545"/>`;
  svg += `<text x="${x(state.params.ef_grid) + 7}" y="${y(cur.total_t) - 5}" class="peak-label">${nf(cur.total_t, 2)}</text>`;

  const slope = rows[0]?.slope_t_per_ef ?? 0;
  svg += `<text x="${pad.l}" y="${H - 4}" class="axis-text">kg CO2e/kWh → dPCF/dGrid = ${nf(slope, 3)} t per unit factor</text>`;
  svg += `</svg>`;
  $("#sweep").innerHTML = svg;
}

/* --------------------------------------------------------------- scenarios */
function renderScenarios(p) {
  const rows = p.scenarios;
  const head = `<tr><th>Scenario</th><th>t CO2e/t</th><th>vs base</th><th>Spec</th><th>Dev</th></tr>`;
  const body = rows
    .map((r) => {
      const preset = state.meta.presets.find((x) => x.key === r.scenario);
      const selected = state.preset === r.scenario;
      const dev = r.deviation_vs_reference_pct;
      return `<tr class="clickable ${selected ? "selected" : ""}" data-preset="${esc(r.scenario)}" title="${esc(r.description || "")}">
        <td>${esc(r.label)}</td>
        <td>${nf(r.pcf_t, 3)}</td>
        <td style="color:${r.reduction_vs_baseline_pct > 0 ? "#4ad991" : "inherit"}">${r.reduction_vs_baseline_pct > 0 ? "−" : ""}${nf(Math.abs(r.reduction_vs_baseline_pct), 1)}%</td>
        <td class="muted">${r.spec_reference_t ? nf(r.spec_reference_t, 2) : "—"}</td>
        <td class="muted">${dev == null ? "—" : nf(dev, 2) + "%"}</td>
      </tr>`;
    })
    .join("");
  $("#scenarios").innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;

  $$("#scenarios tr.clickable").forEach((tr) => {
    tr.onclick = () => {
      const preset = state.meta.presets.find((x) => x.key === tr.dataset.preset);
      if (preset) applyPreset(preset);
      else toast("No parameter set is registered for this scenario");
    };
  });
}

/* ----------------------------------------------------------------- tornado */
function renderTornado(p) {
  const rows = [...p.tornado].sort((a, b) => b.swing_t - a.swing_t).slice(0, 7);
  const W = 620, H = 208;
  const pad = { l: 148, r: 46, t: 10, b: 22 };
  const base = p.kpis.total_t;
  const span = Math.max(...rows.map((r) => Math.max(Math.abs(r.pcf_low_t - base), Math.abs(r.pcf_high_t - base)))) * 1.25 || 0.2;
  const x = scale(base - span, base + span, pad.l, W - pad.r);
  const rowH = (H - pad.t - pad.b) / rows.length;

  let svg = `<svg viewBox="0 0 ${W} ${H}">`;
  svg += `<line x1="${x(base)}" y1="${pad.t}" x2="${x(base)}" y2="${H - pad.b}" stroke="#3a4854" stroke-dasharray="3 3"/>`;
  rows.forEach((r, i) => {
    const y0 = pad.t + i * rowH + rowH * 0.18;
    const h = rowH * 0.64;
    const lo = Math.min(r.pcf_low_t, r.pcf_high_t);
    const hi = Math.max(r.pcf_low_t, r.pcf_high_t);
    svg += `<rect x="${x(lo)}" y="${y0}" width="${Math.max(1, x(base) - x(lo))}" height="${h}" fill="#35c6d8" opacity="0.7"><title>${esc(r.label)} −10%: ${nf(r.pcf_low_t, 3)}</title></rect>`;
    svg += `<rect x="${x(base)}" y="${y0}" width="${Math.max(1, x(hi) - x(base))}" height="${h}" fill="#ffb545" opacity="0.8"><title>${esc(r.label)} +10%: ${nf(r.pcf_high_t, 3)}</title></rect>`;
    svg += `<text x="${pad.l - 8}" y="${y0 + h / 2 + 3}" text-anchor="end" class="axis-text" fill="#a8b7c4">${esc(r.label.length > 30 ? r.label.slice(0, 29) + "…" : r.label)}</text>`;
    svg += `<text x="${W - pad.r + 4}" y="${y0 + h / 2 + 3}" class="axis-text" fill="#ffb545">${nf(r.swing_pct, 2)}%</text>`;
  });
  svg += `<text x="${pad.l}" y="${H - 4}" class="axis-text">swing in t CO2e/t for ±10% on each parameter · base ${nf(base, 3)}</text>`;
  svg += `</svg>`;
  $("#tornado").innerHTML = svg;
}

/* ---------------------------------------------------- allocation & utility */
function renderAllocation(p) {
  const rows = p.allocation;
  const head = `<tr><th>Basis</th><th>t CO2e/t</th><th>Δ vs base</th><th>Δ%</th></tr>`;
  const body = rows
    .map(
      (r) => `<tr title="${esc(r.rationale || "")}">
      <td>${esc(r.label)}</td><td>${nf(r.pcf_t, 3)}</td>
      <td>${r.delta_t >= 0 ? "+" : ""}${nf(r.delta_t, 3)}</td>
      <td class="muted">${r.delta_pct >= 0 ? "+" : ""}${nf(r.delta_pct, 2)}%</td></tr>`
    )
    .join("");
  $("#allocation").innerHTML = `<div class="mini-title">Allocation basis</div>
    <table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function renderUtility(p) {
  const rows = p.utility.nodes;
  const head = `<tr><th>Node</th><th>kWh</th><th>Steam kg</th><th>Explicit</th><th>Grid-eq</th><th>Δ</th></tr>`;
  const body = rows
    .map(
      (r) => `<tr>
        <td>${esc(r.node)}</td>
        <td>${nf(r.electricity_kg, 0)}</td>
        <td>${nf(r.steam_kg, 0)}</td>
        <td>${nf(r.explicit_scope2_kg, 0)}</td>
        <td class="muted">${nf(r.grid_equivalent_kg, 0)}</td>
        <td style="color:${Math.abs(r.delta_pct) > 1 ? "#ffb545" : "inherit"}">${r.delta_kg >= 0 ? "+" : ""}${nf(r.delta_kg, 1)}</td>
      </tr>`
    )
    .join("");
  const cmp = p.utility.comparison
    .map(
      (r) => `<tr><td>${esc(r.label)}</td>
        <td>${nf(r.steam_share_pct, 1)}%</td>
        <td>${nf(r.pcf_baseline, 2)}</td>
        <td>${nf(r.pcf_mid_transition, 2)}</td>
        <td>${nf(r.pcf_zero_carbon_grid, 2)}</td></tr>`
    )
    .join("");
  $("#utility").innerHTML = `<div class="mini-title">Scope 2 decomposition · kg CO2e</div>
    <table><thead>${head}</thead><tbody>${body}</tbody></table>
    <div class="mini-title" style="margin-top:10px">Basis comparison · t CO2e/t</div>
    <table><thead><tr><th>Basis</th><th>Steam</th><th>Base</th><th>Mid-grid</th><th>Zero-C</th></tr></thead><tbody>${cmp}</tbody></table>`;
}

/* --------------------------------------------------------------- validation */
function renderCarbon(p) {
  const rows = p.validation.carbon;
  const head = `<tr><th>Node</th><th>C in</th><th>C out</th><th>Raw %</th><th>Status</th></tr>`;
  const body = rows
    .map(
      (r) => `<tr title="${esc(r.note || "")}">
      <td>${esc(r.node)}</td>
      <td>${nf(r["C in (kg)"], 1)}</td>
      <td>${nf(r["C out (kg)"], 1)}</td>
      <td>${nf(r["raw closure %"], 2)}</td>
      <td><span class="tag ${esc(r.status)}">${esc(r.status)}</span></td></tr>`
    )
    .join("");
  $("#carbon").innerHTML = `<div class="mini-title">Carbon balance · kg C per functional unit</div>
    <table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function renderChecks(p) {
  const rows = p.validation.checks;
  const head = `<tr><th>ID</th><th>Check</th><th>Model</th><th>Specified</th><th>Dev %</th><th>Status</th></tr>`;
  const body = rows
    .map(
      (r) => `<tr title="${esc(r.note || "")}">
      <td>${esc(r.id)}</td>
      <td style="text-align:left">${esc(r.check)}</td>
      <td>${nf(r.model, 3)}</td>
      <td class="muted">${nf(r.specified, 3)}</td>
      <td>${nf(r["dev_%"], 3)}</td>
      <td><span class="tag ${esc(r.status)}">${esc(r.status)}</span></td></tr>`
    )
    .join("");
  $("#checks").innerHTML = `<div class="mini-title">Specification reproduction · ${rows.length} checks</div>
    <table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function renderFindings(p) {
  const rows = p.validation.findings;
  $("#findings").innerHTML = rows
    .map(
      (f) => `<div class="finding ${esc(f.severity)}">
        <div class="finding-id">${esc(f.id)}</div>
        <div><span class="tag ${esc(f.severity)}">${esc(f.severity)}</span></div>
        <div><h4>${esc(f.title)}</h4><p>${esc(f.detail)}</p></div>
        <div class="finding-impact">${f.impact_kg_co2e ? nf(f.impact_kg_co2e, 0) + "<br><span class='muted' style='font-weight:400'>kg CO2e</span>" : "<span class='muted'>—</span>"}</div>
      </div>`
    )
    .join("");
}

/* ------------------------------------------------------------- data tables */
const TABLES = [
  { key: "mass", label: "Mass balance", get: (p) => p.mass_balance },
  { key: "layers", label: "Layers", get: (p) => p.layers },
  { key: "scenarios", label: "Scenarios", get: (p) => p.scenarios },
  { key: "sweep", label: "Grid sweep", get: (p) => p.sweep },
  { key: "tornado", label: "Sensitivity", get: (p) => p.tornado },
  { key: "utility", label: "Utilities", get: (p) => p.utility.nodes },
  { key: "basis", label: "Utility basis", get: (p) => p.utility.comparison },
  { key: "allocation", label: "Allocation", get: (p) => p.allocation },
  { key: "checks", label: "Checks", get: (p) => p.validation.checks },
  { key: "carbon", label: "Carbon", get: (p) => p.validation.carbon },
  { key: "findings", label: "Findings", get: (p) => p.validation.findings },
];

function renderTabs() {
  $("#tabs").innerHTML = TABLES.map(
    (t) => `<button type="button" data-tab="${t.key}" class="${state.tab === t.key ? "active" : ""}">${t.label}</button>`
  ).join("");
  $$("#tabs button").forEach((b) => {
    b.onclick = () => {
      state.tab = b.dataset.tab;
      renderTabs();
      renderDataTable();
    };
  });
}

function cell(value) {
  if (typeof value === "number") return nf(value, Math.abs(value) < 10 ? 4 : 2);
  if (value === true || value === false) return value ? "yes" : "no";
  return esc(value);
}

function renderDataTable() {
  const spec = TABLES.find((t) => t.key === state.tab);
  const rows = spec.get(state.data);
  if (!rows.length) {
    $("#datatable").innerHTML = `<p class="muted">No rows.</p>`;
    return;
  }
  const cols = Object.keys(rows[0]).filter((c) => c !== "description" || state.tab === "scenarios");
  const head = `<tr>${cols.map((c) => `<th>${esc(c.replace(/_/g, " "))}</th>`).join("")}</tr>`;
  const body = rows
    .map(
      (r) =>
        `<tr>${cols
          .map((c) => {
            const v = r[c];
            if (c === "status" || c === "severity") return `<td><span class="tag ${esc(v)}">${esc(v)}</span></td>`;
            if (typeof v === "string" && v.length > 90) return `<td title="${esc(v)}" style="text-align:left;white-space:normal;max-width:420px">${esc(v)}</td>`;
            return `<td>${cell(v)}</td>`;
          })
          .join("")}</tr>`
    )
    .join("");
  $("#datatable").innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

/* --------------------------------------------------------------- exporting */
function buildCsv(p) {
  const sections = [
    ["KPI", [p.kpis]],
    ["STAGES", p.stages],
    ["MASS BALANCE", p.mass_balance],
    ["LAYERS", p.layers],
    ["SCENARIOS", p.scenarios],
    ["GRID SWEEP", p.sweep],
    ["SENSITIVITY", p.tornado],
    ["ALLOCATION", p.allocation],
    ["UTILITY NODES", p.utility.nodes],
    ["UTILITY BASIS", p.utility.comparison],
    ["CHECKS", p.validation.checks],
    ["CARBON BALANCE", p.validation.carbon],
    ["FINDINGS", p.validation.findings],
  ];
  const out = [];
  out.push(`# HDPE PCF control room export, ${p.generated_at}`);
  out.push(`# parameters, ${Object.entries(p.params).map(([k, v]) => `${k}=${v}`).join(" ")}`);
  sections.forEach(([title, rows]) => {
    if (!rows.length) return;
    out.push("");
    out.push(`## ${title}`);
    const cols = Object.keys(rows[0]);
    out.push(cols.map(csvCell).join(","));
    rows.forEach((r) => out.push(cols.map((c) => csvCell(r[c])).join(",")));
  });
  return out.join("\n");
}

function bindActions() {
  $("#btn-reset").onclick = () => {
    state.params = { ...state.meta.defaults };
    state.preset = "baseline";
    syncControls();
    markPreset();
    simulate();
  };

  $("#btn-csv").onclick = () => {
    if (!state.data) return;
    download("hdpe_pcf_export.csv", buildCsv(state.data), "text/csv");
    toast("CSV exported");
  };

  $("#btn-json").onclick = () => {
    if (!state.data) return;
    download("hdpe_pcf_export.json", JSON.stringify(state.data, null, 2), "application/json");
    toast("JSON exported");
  };

  $("#btn-pdf").onclick = async () => {
    const btn = $("#btn-pdf");
    btn.disabled = true;
    btn.textContent = "Building…";
    try {
      const res = await fetch("/api/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ params: state.params }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "report failed");
      const a = document.createElement("a");
      a.href = body.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.click();
      toast(`Report generated (${nf(body.total_t, 3)} t CO2e/t)`);
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "PDF report";
    }
  };

  document.addEventListener("keydown", (e) => {
    if (e.key === "r" && (e.metaKey || e.ctrlKey) && e.shiftKey) {
      e.preventDefault();
      $("#btn-reset").click();
    }
  });
}

boot();
