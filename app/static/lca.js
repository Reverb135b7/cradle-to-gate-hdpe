/* ==========================================================================
   LCA study console — client
   A reader over one LcaResult. Every value on the page arrives in /api/lca;
   the charts are drawn here only so they stay live when the study is rebuilt.
   ========================================================================== */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const SLUG = (s) => String(s ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "");
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const nf = (v, d = 1) =>
  Number.isFinite(Number(v))
    ? Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })
    : "—";

const tag = (status) => `<span class="tag ${SLUG(status)}">${esc(status)}</span>`;
const trunc = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + "…" : String(s));

const bytes = (n) => {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
};

const state = {
  data: null,
  flowFilter: "all",
  flowQuery: "",
  flowSort: { key: "flow_id", dir: 1 },
  impactMode: "gwp",
};

const COLORS = {
  gwp: "#ffb545",
  energy: "#35c6d8",
  evidence: "#35c6d8",
  scenario: "#ffb545",
  method: "#9b8cff",
  judgement: "#8fa0ad",
  ink: "#e8eef3",
  dim: "#6d7f8e",
  line: "#2f3c48",
};

const SECTIONS = [
  ["s-study", "01", "Goal & scope"],
  ["s-boundary", "02", "Boundary"],
  ["s-impact", "03", "Impact"],
  ["s-inventory", "04", "Inventory"],
  ["s-sensitivity", "05", "Sensitivity"],
  ["s-uncertainty", "06", "Uncertainty"],
  ["s-scenarios", "07", "Scenarios"],
  ["s-assurance", "08", "Assurance"],
  ["s-files", "09", "Deliverables"],
];

/* ------------------------------------------------------------------- tables */
function tableHTML(columns, rows, options = {}) {
  const head = columns
    .map((c) => `<th class="${c.cls || ""}"${c.title ? ` title="${esc(c.title)}"` : ""}>${c.label}</th>`)
    .join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((c) => {
          const value = c.render ? c.render(row) : esc(row[c.key] ?? "");
          return `<td class="${c.cls || ""}">${value}</td>`;
        })
        .join("");
      return `<tr class="${options.rowClass ? options.rowClass(row) : ""}">${cells}</tr>`;
    })
    .join("");
  return `<table class="${options.tableClass || ""}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function svgWrap(width, height, inner, cls = "") {
  return `<svg class="${cls}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img">${inner}</svg>`;
}

/* ------------------------------------------------------------------- header */
function renderHeader(d) {
  $("#h-gwp").textContent = nf(d.kpis.gwp_t, 3);
  $("#h-energy").textContent = `${nf(d.kpis.energy_gj, 1)} GJ/t primary`;
  $("#h-method").textContent = "GWP100 · IPCC AR6";

  const chip = $("#v-status");
  chip.textContent = `validation ${d.validation.status}`;
  chip.className = `chip ${d.validation.status === "PASS" ? "pass" : d.validation.status === "WARN" ? "warn" : "fail"}`;
  chip.title = `${d.validation.findings} findings; see Assurance`;

  $("#dl-report").textContent = "Report";
  $("#dl-deck").textContent = "Deck";
}

/* ---------------------------------------------------------------------- nav */
function renderNav() {
  $("#nav").innerHTML = SECTIONS.map(
    ([id, no, label]) => `<a class="nav-link" href="#${id}" data-target="${id}"><b>${no}</b>${label}</a>`
  ).join("");

  const links = $$(".nav-link");
  const sections = $$(".lca-section");
  const setActive = (id) => links.forEach((a) => a.classList.toggle("active", a.dataset.target === id));

  const update = () => {
    const line = 140;
    let current = sections[0];
    sections.forEach((section) => {
      if (section.getBoundingClientRect().top <= line) current = section;
    });
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) {
      current = sections[sections.length - 1];
    }
    setActive(current.id);
  };

  window.addEventListener("scroll", update, { passive: true });
  document.addEventListener("scroll", update, { capture: true, passive: true });
  window.addEventListener("resize", update);
  window.addEventListener("hashchange", update);
  // Scroll events are not reliable when the viewport is scrolled programmatically
  // (or by an embedding host), so the highlight is also reconciled on a timer.
  setInterval(update, 250);
  update();
}

/* --------------------------------------------------------------------- KPIs */
function renderKpis(d) {
  const stageRows = d.stages.filter((s) => s.stage_key !== "total");
  const hotspot = stageRows.reduce((a, b) => (b.share_pct > a.share_pct ? b : a), stageRows[0]);
  const unc = d.uncertainty.evidence;

  const cards = [
    ["Footprint", nf(d.kpis.gwp_t, 3), "t CO<sub>2</sub>e / t HDPE", "GWP100 · IPCC AR6", "accent"],
    ["Primary energy", nf(d.kpis.energy_gj, 1), "GJ / t", `screening · ${nf(d.kpis.pe_factor, 1)} MJ/kWh`, ""],
    ["Hotspot", nf(hotspot.share_pct, 1), "% of GWP", trunc(hotspot.stage, 26), "cyan"],
    ["Uncertainty", `${nf(unc.p05_t, 2)}–${nf(unc.p95_t, 2)}`, "t P5–P95", `evidence only · n=${nf(unc.n, 0)}`, ""],
    ["Inventory", `${d.kpis.flows}`, "flows", `S1–S${d.kpis.sources} · mean DQI ${nf(d.kpis.dqi_mean, 2)}`, ""],
    ["Checks", `${d.kpis.checks.met}/${d.kpis.checks.total}`, "met", `${d.kpis.checks.partial} partial · ${d.kpis.checks.not_met} not met`, d.kpis.checks.not_met ? "green" : "green"],
  ];

  $("#kpis").innerHTML = cards
    .map(
      ([label, value, unit, foot, cls]) => `
      <div class="kpi ${cls}">
        <div class="kpi-label">${label}</div>
        <div class="kpi-value">${value}<small>${unit}</small></div>
        <div class="kpi-foot">${esc(foot)}</div>
      </div>`
    )
    .join("");
}

/* -------------------------------------------------------------------- study */
function renderStudy(d) {
  const s = d.study;

  $("#study-goal").innerHTML = `
    <div class="card-head"><h3>Question</h3><span class="hint">v${esc(s.version)} · ${esc(s.base_year)}</span></div>
    <p class="fu-text" style="font-size:12.5px">${esc(s.decision)}</p>
    <div class="sub-head">Audience</div>
    <p class="card-note" style="margin-top:0;color:var(--ink-2)">${esc(s.audience)}</p>
    <div class="sub-head">Frameworks</div>
    <p class="card-note" style="margin-top:0;color:var(--ink-2)">${esc(s.standards)}</p>`;

  $("#study-fu").innerHTML = `
    <div class="card-head"><h3>Functional unit</h3><span class="hint">measured at the gate</span></div>
    <p class="fu-text"><b>${esc(s.functional_unit)}</b></p>
    <div class="kv">
      <div class="kv-row"><span class="kv-key">Product</span><span class="kv-val">${esc(s.product)}</span></div>
      <div class="kv-row"><span class="kv-key">Declared unit</span><span class="kv-val">${esc(s.declared_unit)}</span></div>
      <div class="kv-row"><span class="kv-key">Geography</span><span class="kv-val">${esc(s.geography)}</span></div>
      <div class="kv-row"><span class="kv-key">Period</span><span class="kv-val">${esc(s.reference_period)}</span></div>
    </div>`;

  $("#study-method").innerHTML = `
    <div class="card-head"><h3>Method</h3><span class="hint">no normalisation, no weighting</span></div>
    <p class="card-note" style="margin-top:0;color:var(--ink-2)">${esc(s.method)}</p>
    <div class="sub-head">Software &amp; database</div>
    <p class="card-note" style="margin-top:0">${esc(s.software)}</p>`;

  $("#study-scope").innerHTML = `
    <div class="card-head"><h3>Allocation &amp; cut-off</h3><span class="hint">stated, then tested</span></div>
    <p class="card-note" style="margin-top:0;color:var(--ink-2)">${esc(s.allocation)}</p>
    <div class="sub-head">Cut-off</div>
    <p class="card-note" style="margin-top:0">${esc(s.cut_off)}</p>`;

  $("#study-limits").innerHTML = `
    <h4>Limitations — read before quoting any number</h4>
    <ul>${s.limitations.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`;
}

/* ----------------------------------------------------------------- boundary */
function renderBoundary(d) {
  $("#boundary-svg").innerHTML = boundarySvg(d);
  $("#boundary-legend").innerHTML = [
    ["included module", COLORS.gwp],
    ["gate", COLORS.energy],
    ["outside boundary", "#ff6b6b"],
  ]
    .map(([label, colour]) => `<span class="legend-item"><i class="swatch" style="background:${colour}"></i>${label}</span>`)
    .join("");

  const inclusions = d.study.inclusions
    .map((row) => `<tr><td>${esc(row.item)}</td><td>${esc(row.detail)}</td></tr>`)
    .join("");
  const exclusions = d.study.exclusions
    .map(
      (row) => `<li><span class="x">×</span><span>${esc(row.item)}<span class="why">${esc(row.why)} ${esc(
        row.consequence
      )}</span></span></li>`
    )
    .join("");

  $("#boundary-lists").innerHTML = `
    <div class="card-head"><h3>Modules</h3><span class="hint">${d.study.inclusions.length} in · ${d.study.exclusions.length} out</span></div>
    <div class="sub-head">Inside the boundary</div>
    <table class="inc-table"><colgroup><col class="c1"><col class="c2"></colgroup><tbody>${inclusions}</tbody></table>
    <div class="sub-head">Outside the boundary</div>
    <ul class="exc-list">${exclusions}</ul>`;

  $("#completeness").innerHTML = tableHTML(
    [
      { key: "module", label: "Module", cls: "wrap" },
      { key: "life_cycle_stage", label: "Life-cycle stage", cls: "wrap" },
      { key: "status", label: "Status", render: (r) => tag(r.status) },
      { key: "materiality_kg_co2e", label: "kg CO₂e", render: (r) => nf(r.materiality_kg_co2e, 0) },
      { key: "materiality_pct", label: "% of GWP", render: (r) => nf(r.materiality_pct, 1) },
      { key: "basis", label: "Basis", cls: "wrap" },
    ],
    d.completeness
  );
}

function boundarySvg(d) {
  const W = 1000;
  const H = 300;
  const stages = d.stages.filter((s) => s.stage_key !== "total");
  const mass = d.mass;
  const nodeW = 190;
  const xs = [26, 264, 502, 740];
  const top = 62;
  const boxH = 74;

  let out = `<defs><marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="${COLORS.gwp}"/></marker>
  <marker id="arwc" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="${COLORS.energy}"/></marker></defs>`;

  out += `<rect x="10" y="14" width="${W - 20}" height="188" rx="3" fill="#0f151a" stroke="${COLORS.line}" stroke-width="1"/>`;
  out += `<text x="20" y="30" class="axis-text" style="letter-spacing:.14em;font-size:8.5px">CRADLE-TO-GATE BOUNDARY · QUANTIFIED</text>`;
  out += `<text x="${W - 20}" y="30" text-anchor="end" class="axis-text" style="font-size:8.5px">1,000 kg HDPE resin · ex-works</text>`;

  const labels = ["Natural gas", "Methanol", "Ethylene (MTO)", "HDPE polymer"];
  const flows = [`${nf(mass.ng_t, 3)} t`, `${nf(mass.methanol_t, 3)} t`, `${nf(mass.ethylene_t, 3)} t`, `${nf(mass.hdpe_t, 3)} t`];
  const species = ["NG", "CH₃OH", "C₂H₄", "HDPE"];

  stages.forEach((stage, i) => {
    const x = xs[i];
    const hot = stage.share_pct >= 40;
    out += `<rect x="${x}" y="${top}" width="${nodeW}" height="${boxH}" rx="2" class="node-box ${hot ? "hot" : ""}"/>`;
    out += `<text x="${x + 10}" y="${top + 17}" class="node-title">${esc(trunc(labels[i], 21))}</text>`;
    out += `<text x="${x + 10}" y="${top + 39}" style="font:600 14px var(--mono);fill:${hot ? COLORS.gwp : COLORS.ink}">${nf(
      stage.total_kg_co2e,
      0
    )}</text>`;
    out += `<text x="${x + 10}" y="${top + 52}" class="axis-text">kg CO₂e</text>`;
    out += `<text x="${x + 10}" y="${top + 66}" class="axis-text" style="fill:${COLORS.dim}">${nf(stage.share_pct, 1)}% of GWP</text>`;
    out += `<text x="${x + nodeW - 10}" y="${top + 66}" text-anchor="end" class="axis-text" style="fill:${COLORS.dim}">${nf(
      stage.energy_mj / 1000,
      0
    )} GJ</text>`;

    if (i < stages.length - 1) {
      const x1 = x + nodeW;
      const x2 = xs[i + 1] - 2;
      out += `<line x1="${x1 + 3}" y1="${top + 34}" x2="${x2}" y2="${top + 34}" stroke="${COLORS.gwp}" stroke-width="1.4" marker-end="url(#arw)"/>`;
      out += `<text x="${(x1 + x2) / 2}" y="${top + 26}" text-anchor="middle" style="font:400 8px var(--mono);fill:${COLORS.ink}">${flows[i]}</text>`;
      out += `<text x="${(x1 + x2) / 2}" y="${top + 49}" text-anchor="middle" style="font:400 7.5px var(--mono);fill:${COLORS.dim}">${species[i]}</text>`;
    }
  });

  const last = xs[3] + nodeW;
  out += `<line x1="${last + 2}" y1="${top + 34}" x2="${last + 24}" y2="${top + 34}" stroke="${COLORS.energy}" stroke-width="1.4" marker-end="url(#arwc)"/>`;
  out += `<line x1="${last + 28}" y1="${top - 6}" x2="${last + 28}" y2="${top + boxH + 8}" stroke="${COLORS.energy}" stroke-width="1" stroke-dasharray="3 3"/>`;
  out += `<text x="${last + 32}" y="${top + 12}" class="axis-text" style="fill:${COLORS.energy};font-size:8px">gate</text>`;
  out += `<text x="${W - 20}" y="${top + 66}" text-anchor="end" class="axis-text" style="fill:${COLORS.energy};font-size:8px"></text>`;

  // utility row inside the boundary
  out += `<line x1="26" y1="158" x2="${W - 26}" y2="158" stroke="${COLORS.line}" stroke-width="0.7" stroke-dasharray="2 3"/>`;
  out += `<text x="26" y="174" class="axis-text" style="font-size:8px">ELECTRICITY ${nf(
    mass.electricity_kwh,
    0
  )} kWh/t</text>`;
  out += `<text x="250" y="174" class="axis-text" style="font-size:8px">NG FUEL ${nf(
    mass.declared_fuel_gj,
    1
  )} GJ/t</text>`;
  out += `<text x="440" y="174" class="axis-text" style="font-size:8px">CO-MONOMER ${nf(
    mass.comonomer_t * 1000,
    0
  )} kg/t</text>`;
  out += `<text x="${W - 26}" y="174" text-anchor="end" class="axis-text" style="font-size:8px">${nf(
    d.kpis.gwp_kg,
    0
  )} kg CO₂e per functional unit</text>`;

  out += `<text x="20" y="226" class="axis-text" style="fill:${COLORS.dim};font-size:8.5px;letter-spacing:.12em">OUTSIDE THE BOUNDARY — NAMED, NOT MODELLED</text>`;
  const chips = ["Packaging", "Outbound transport", "Use phase", "End-of-life", "Water & wastewater", "Catalysts", "Capital goods"];
  let cx = 20;
  chips.forEach((label) => {
    const w = 40 + label.length * 5.1;
    out += `<rect x="${cx}" y="236" width="${w}" height="22" rx="2" fill="#151a1f" stroke="#4a2a2a" stroke-dasharray="3 3"/>`;
    out += `<text x="${cx + w / 2}" y="251" text-anchor="middle" style="font:400 8.5px var(--mono);fill:#c98a8a">${esc(label)}</text>`;
    cx += w + 8;
  });

  return svgWrap(W, H, out);
}

/* ------------------------------------------------------------------- impact */
function renderImpact(d) {
  $("#categories").innerHTML = tableHTML(
    [
      { key: "category", label: "Category", cls: "wrap" },
      { key: "indicator", label: "Indicator", cls: "wrap" },
      { key: "status", label: "Status", render: (r) => tag(r.status) },
      { key: "note", label: "Basis", cls: "wrap" },
    ],
    d.categories
  );

  drawImpactChart();

  const rows = d.stages.filter((s) => s.stage_key !== "total");
  $("#stage-table").innerHTML = `
    <div class="mini-title">Stage values</div>
    ${tableHTML(
      [
        { key: "stage", label: "Stage", cls: "wrap" },
        { key: "total_kg_co2e", label: "kg CO₂e", render: (r) => nf(r.total_kg_co2e, 0) },
        { key: "share_pct", label: "Share", render: (r) => `${nf(r.share_pct, 1)}%` },
        { key: "energy_mj", label: "GJ", render: (r) => nf(r.energy_mj / 1000, 1) },
        { key: "electricity_kwh", label: "kWh", render: (r) => nf(r.electricity_kwh, 0) },
      ],
      rows
    )}`;

  const quantified = d.categories.filter((c) => c.status === "Quantified").length;
  $("#impact-notes").innerHTML = `
    <div class="card-head"><h3>Interpretation</h3><span class="hint">${quantified} of ${d.categories.length} categories quantified</span></div>
    <p class="card-note" style="margin-top:0;color:var(--ink-2)">
      Climate change is quantified on IPCC AR6 GWP100 values; fossil primary energy is a screening resource
      indicator, not a midpoint category. The other six categories are declared and left empty on purpose:
      the inventory carries aggregated CO<sub>2</sub>e per node, not species-resolved SO<sub>2</sub>, NO<sub>x</sub>,
      NH<sub>3</sub>, NMVOC, PM, phosphorus or water, so any value for them would be invented rather than assessed.
      No normalisation, weighting or single aggregate score is applied — the footprint, the energy indicator
      and the contribution profile are reported side by side.
    </p>`;
}

function drawImpactChart() {
  const d = state.data;
  const rows = d.stages
    .filter((s) => s.stage_key !== "total")
    .map((s) => ({
      label: s.stage,
      value: state.impactMode === "gwp" ? s.total_kg_co2e : s.energy_mj / 1000,
      share: state.impactMode === "gwp" ? s.share_pct : (s.energy_mj / d.kpis.energy_mj) * 100,
    }))
    .sort((a, b) => b.value - a.value);

  const W = 620;
  const rowH = 40;
  const H = rows.length * rowH + 34;
  const padL = 176;
  const padR = 66;
  const max = Math.max(...rows.map((r) => r.value)) * 1.08;
  const barW = W - padL - padR;
  const colour = state.impactMode === "gwp" ? COLORS.gwp : COLORS.energy;
  const unit = state.impactMode === "gwp" ? "kg CO₂e" : "GJ";

  let out = "";
  rows.forEach((row, i) => {
    const y = 10 + i * rowH;
    const w = Math.max(2, (row.value / max) * barW);
    out += `<text x="${padL - 10}" y="${y + 17}" text-anchor="end" class="axis-text" style="fill:${COLORS.ink};font-size:9.5px">${esc(
      trunc(row.label, 26)
    )}</text>`;
    out += `<rect x="${padL}" y="${y + 4}" width="${barW}" height="17" fill="#161d24" rx="1"/>`;
    out += `<rect x="${padL}" y="${y + 4}" width="${w}" height="17" fill="${colour}" opacity="${0.9 - i * 0.06}" rx="1"/>`;
    out += `<text x="${padL + w + 8}" y="${y + 17}" class="axis-text" style="fill:${COLORS.ink};font-size:9px">${nf(
      row.value,
      state.impactMode === "gwp" ? 0 : 1
    )}</text>`;
    out += `<text x="${W - 8}" y="${y + 17}" text-anchor="end" class="axis-text" style="font-size:9px">${nf(row.share, 1)}%</text>`;
  });
  out += `<text x="${padL}" y="${H - 6}" class="axis-text" style="font-size:8px">${unit} per functional unit · share of total</text>`;

  $("#impact-chart").innerHTML = svgWrap(W, H, out);
}

/* ---------------------------------------------------------------- inventory */
const FLOW_GROUPS = {
  all: () => true,
  materials: (f) => ["feedstock", "material", "intermediate"].includes(f.kind),
  energy: (f) => f.kind === "energy",
  emissions: (f) => f.kind === "emission",
  product: (f) => f.kind === "product",
};

function renderInventory(d) {
  const chips = [
    ["all", "All"],
    ["materials", "Materials"],
    ["energy", "Energy"],
    ["emissions", "Emissions"],
    ["product", "Product"],
  ];
  $("#flow-filters").innerHTML = chips
    .map(([key, label]) => {
      const n = d.flows.filter((f) => FLOW_GROUPS[key](f)).length;
      return `<button type="button" data-group="${key}" class="${state.flowFilter === key ? "on" : ""}">${label} ${n}</button>`;
    })
    .join("");

  drawFlows();

  $("#sources").innerHTML = tableHTML(
    [
      { key: "source_id", label: "ID" },
      { key: "source", label: "Source", cls: "wrap" },
      { key: "type", label: "Type" },
      { key: "supplies", label: "Supplies", cls: "wrap" },
      { key: "period", label: "Period" },
    ],
    d.sources.map((s) => ({ ...s, _note: s.note })),
    { rowClass: (r) => (r._note ? "" : "") }
  );
  $("#src-count").textContent = `${d.sources.length} sources`;

  const order = ["A", "B", "C", "D", "E"];
  const counts = d.kpis.dqi_counts || {};
  const palette = { A: "#4ad991", B: "#8fd06a", C: "#ffb545", D: "#ff8b5e", E: "#ff6b6b" };
  const maxCount = Math.max(...order.map((k) => counts[k] || 0), 1);
  $("#dqi-summary").innerHTML = `
    <div class="dqi-bars">
      ${order
        .map(
          (k) => `<div class="dqi-row">
            <span class="dqi-key">${k}</span>
            <span class="dqi-track"><span class="dqi-fill" style="width:${((counts[k] || 0) / maxCount) * 100}%;background:${palette[k]}"></span></span>
            <span class="dqi-n">${counts[k] || 0}</span>
          </div>`
        )
        .join("")}
    </div>
    <p class="card-note" style="margin-top:0">
      Mean ${nf(d.kpis.dqi_mean, 2)} on a 1–5 scale (1 best). A flow scores worse where it is a derived
      factor, a global average rather than a supplier value, or a proxy; the per-flow scores are below.
    </p>`;

  const worst = [...d.flows].sort((a, b) => b.dqi_score - a.dqi_score).slice(0, 5);
  $("#dqi-detail").innerHTML = tableHTML(
    [
      { key: "flow_id", label: "ID" },
      { key: "flow", label: "Weakest flows", cls: "wrap" },
      { key: "dqi_score", label: "Score", render: (r) => nf(r.dqi_score, 1) },
      { key: "dqi_rating", label: "Rating" },
      { key: "proxy", label: "Proxy", render: (r) => (r.proxy === "yes" || r.proxy === true ? tag("yes") : "") },
    ],
    worst
  );
}

function drawFlows() {
  const d = state.data;
  const query = state.flowQuery.trim().toLowerCase();
  let rows = d.flows.filter(FLOW_GROUPS[state.flowFilter]);
  if (query) {
    rows = rows.filter((f) =>
      [f.flow, f.stage, f.source_id, f.geography, f.flow_id, f.kind, f.data_type].join(" ").toLowerCase().includes(query)
    );
  }
  const { key, dir } = state.flowSort;
  rows.sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
    return String(av).localeCompare(String(bv)) * dir;
  });

  const arrow = (k) => (state.flowSort.key === k ? (state.flowSort.dir > 0 ? " ▲" : " ▼") : "");
  $("#flows").innerHTML = tableHTML(
    [
      { key: "flow_id", label: `ID${arrow("flow_id")}` },
      { key: "stage", label: `Stage${arrow("stage")}`, cls: "wrap" },
      { key: "flow", label: `Flow${arrow("flow")}`, cls: "wrap" },
      { key: "direction", label: "Dir" },
      { key: "quantity", label: `Quantity${arrow("quantity")}`, render: (r) => nf(r.quantity, r.quantity < 10 ? 3 : 1) },
      { key: "unit", label: "Unit" },
      { key: "source_id", label: "Source" },
      { key: "data_type", label: "Data" },
      { key: "geography", label: "Geography", cls: "wrap" },
      { key: "period", label: "Period" },
      { key: "dqi_score", label: `DQI${arrow("dqi_score")}`, render: (r) => nf(r.dqi_score, 1) },
      { key: "dqi_rating", label: "Rating" },
      { key: "proxy", label: "Proxy", render: (r) => (r.proxy === "yes" || r.proxy === true ? tag("yes") : "") },
    ],
    rows
  );

  $$("#flows thead th").forEach((th, i) => {
    const keys = ["flow_id", "stage", "flow", "direction", "quantity", null, null, null, null, null, "dqi_score"];
    const k = keys[i];
    if (!k) return;
    th.style.cursor = "pointer";
    th.onclick = () => {
      state.flowSort = { key: k, dir: state.flowSort.key === k ? -state.flowSort.dir : 1 };
      drawFlows();
    };
  });
}

/* -------------------------------------------------------------- sensitivity */
function renderSensitivity(d) {
  $("#tornado").innerHTML = tornadoSvg(d.sensitivity);
  $("#sens-legend").innerHTML = ["evidence", "scenario", "method", "judgement"]
    .map((basis) => `<span class="legend-item"><i class="swatch" style="background:${COLORS[basis]}"></i>${basis}</span>`)
    .join("");

  const rows = [...d.sensitivity].sort((a, b) => b.swing_t - a.swing_t);
  $("#sens-table").innerHTML = tableHTML(
    [
      { key: "label", label: "Assumption", cls: "wrap" },
      { key: "basis", label: "Basis", render: (r) => tag(r.basis) },
      {
        key: "low_value",
        label: "Tested range",
        render: (r) => `${nf(r.low_value, r.low_value < 10 ? 3 : 0)} – ${nf(r.high_value, r.high_value < 10 ? 3 : 0)}`,
      },
      { key: "base_value", label: "Base", render: (r) => nf(r.base_value, r.base_value < 10 ? 3 : 2) },
      { key: "swing_t", label: "Swing t", render: (r) => nf(r.swing_t, 3) },
      { key: "swing_pct", label: "Swing %", render: (r) => nf(r.swing_pct, 1) },
      { key: "rationale", label: "Why this range", cls: "wrap" },
    ],
    rows
  );

  $("#recon").innerHTML = reconSvg(d.reconciliation, d.kpis.gwp_t);
  const first = d.reconciliation[0];
  const last = d.reconciliation[d.reconciliation.length - 1];
  const delta = ((last.total_t - first.total_t) / first.total_t) * 100;
  $("#recon-note").textContent =
    `Moving the inventory from the specification as written to the carbon-consistent variant raises the ` +
    `result by ${nf(delta, 1)} % (${nf(first.total_t, 3)} → ${nf(last.total_t, 3)} t). That is the size of the ` +
    `inventory problem, and it is smaller than the grid scenario.`;
}

function tornadoSvg(rows) {
  const data = [...rows].sort((a, b) => b.swing_t - a.swing_t);
  const W = 660;
  const rowH = 30;
  const H = data.length * rowH + 30;
  const padL = 206;
  const padR = 58;
  const lows = Math.min(...data.map((r) => r.pcf_low_t));
  const highs = Math.max(...data.map((r) => r.pcf_high_t));
  const min = Math.min(lows, 0);
  const max = Math.max(highs, 0);
  const span = max - min || 1;
  const x = (v) => padL + ((v - min) / span) * (W - padL - padR);

  let out = "";
  data.forEach((row, i) => {
    const y = 8 + i * rowH;
    const colour = COLORS[row.basis] || COLORS.judgement;
    const left = Math.min(row.pcf_low_t, row.pcf_high_t);
    const right = Math.max(row.pcf_low_t, row.pcf_high_t);
    out += `<text x="${padL - 10}" y="${y + 14}" text-anchor="end" class="axis-text" style="fill:${COLORS.ink};font-size:9px">${esc(
      trunc(row.label, 30)
    )}</text>`;
    out += `<rect x="${x(left)}" y="${y + 3}" width="${Math.max(2, x(right) - x(left))}" height="12" fill="${colour}" opacity="0.85" rx="1"/>`;
    out += `<text x="${x(right) + 6}" y="${y + 13}" class="axis-text" style="font-size:8.5px">${nf(row.swing_t, 3)}</text>`;
  });
  out += `<line x1="${x(0)}" y1="2" x2="${x(0)}" y2="${H - 18}" stroke="${COLORS.dim}" stroke-width="0.8" stroke-dasharray="2 3"/>`;
  out += `<text x="${x(0)}" y="${H - 6}" text-anchor="middle" class="axis-text" style="font-size:8px">base 0</text>`;
  return svgWrap(W, H, out);
}

function reconSvg(points, base) {
  const W = 520;
  const H = 250;
  const pad = { l: 52, r: 18, t: 16, b: 34 };
  const xs = points.map((p) => p.theta);
  const ys = points.map((p) => p.total_t);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const padY = (maxY - minY) * 0.25 || 0.01;
  const lo = minY - padY;
  const hi = maxY + padY;
  const px = (v) => pad.l + ((v - minX) / (maxX - minX || 1)) * (W - pad.l - pad.r);
  const py = (v) => H - pad.b - ((v - lo) / (hi - lo)) * (H - pad.t - pad.b);

  let out = "";
  for (let i = 0; i <= 3; i++) {
    const v = lo + ((hi - lo) * i) / 3;
    out += `<line x1="${pad.l}" y1="${py(v)}" x2="${W - pad.r}" y2="${py(v)}" class="grid-line"/>`;
    out += `<text x="${pad.l - 6}" y="${py(v) + 3}" text-anchor="end" class="axis-text" style="font-size:8px">${nf(v, 2)}</text>`;
  }
  const path = points.map((p, i) => `${i ? "L" : "M"}${px(p.theta).toFixed(1)},${py(p.total_t).toFixed(1)}`).join(" ");
  out += `<path d="${path}" fill="none" stroke="${COLORS.evidence}" stroke-width="1.8"/>`;
  out += `<line x1="${px(0)}" y1="${py(base)}" x2="${W - pad.r}" y2="${py(base)}" stroke="${COLORS.gwp}" stroke-width="0.9" stroke-dasharray="3 3"/>`;

  const first = points[0];
  const last = points[points.length - 1];
  [
    [first.theta, first.total_t, "spec"],
    [last.theta, last.total_t, "consistent"],
  ].forEach(([tx, ty, label], i) => {
    out += `<circle cx="${px(tx)}" cy="${py(ty)}" r="3" fill="${COLORS.evidence}"/>`;
    out += `<text x="${px(tx) + (i ? -8 : 8)}" y="${py(ty) - 7}" text-anchor="${i ? "end" : "start"}" class="axis-text" style="fill:${COLORS.ink};font-size:8.5px">${nf(
      ty,
      3
    )} t</text>`;
    out += `<text x="${px(tx) + (i ? -8 : 8)}" y="${py(ty) + 14}" text-anchor="${i ? "end" : "start"}" class="axis-text" style="font-size:8px">${label}</text>`;
  });

  out += `<text x="${W / 2}" y="${H - 8}" text-anchor="middle" class="axis-text" style="font-size:8px">θ = 0 specification as written → θ = 1 carbon-consistent inventory</text>`;
  return svgWrap(W, H, out);
}

/* --------------------------------------------------------------- uncertainty */
function renderUncertainty(d) {
  const e = d.uncertainty.evidence;
  const s = d.uncertainty.screening;
  $("#unc-evidence").innerHTML = histSvg(d.uncertainty.evidence_hist, e, COLORS.evidence);
  $("#unc-screening").innerHTML = histSvg(d.uncertainty.screening_hist, s, COLORS.gwp);

  const rows = [e, s];
  $("#unc-table").innerHTML = `
    <div class="card-head"><h3>Summary</h3><span class="hint">t CO<sub>2</sub>e / t HDPE · ${nf(e.n, 0)} draws each, fixed seed</span></div>
    ${tableHTML(
      [
        { key: "label", label: "Run", cls: "wrap" },
        { key: "mean_t", label: "Mean", render: (r) => nf(r.mean_t, 3) },
        { key: "sd_t", label: "SD", render: (r) => nf(r.sd_t, 3) },
        { key: "p05_t", label: "P5", render: (r) => nf(r.p05_t, 3) },
        { key: "p50_t", label: "P50", render: (r) => nf(r.p50_t, 3) },
        { key: "p95_t", label: "P95", render: (r) => nf(r.p95_t, 3) },
        { key: "min_t", label: "Min", render: (r) => nf(r.min_t, 3) },
        { key: "max_t", label: "Max", render: (r) => nf(r.max_t, 3) },
      ],
      rows
    )}
    <p class="card-note">
      The first run samples only the reconciliation path — the inventory moved toward its own carbon balance,
      with MTO Scope 1, methanol demand and ethylene demand moving together because the node balances couple
      them. The second adds the three judgement brackets (upstream gas factor, methanol yield, polymerisation
      Scope 1) and is a screening distribution, not measured variability. Grid factor and allocation are
      excluded from both: they are decisions, and appear as scenarios.
    </p>`;
}

function histSvg(hist, summary, colour) {
  const W = 520;
  const H = 200;
  const pad = { l: 44, r: 12, t: 12, b: 34 };
  const edges = hist.edges;
  const counts = hist.counts;
  const max = Math.max(...counts);
  const lo = edges[0];
  const hi = edges[edges.length - 1];
  const px = (v) => pad.l + ((v - lo) / (hi - lo)) * (W - pad.l - pad.r);
  const py = (v) => H - pad.b - (v / max) * (H - pad.t - pad.b);

  let out = "";
  const barW = Math.max(1, (W - pad.l - pad.r) / counts.length - 1);
  counts.forEach((c, i) => {
    out += `<rect x="${px(edges[i])}" y="${py(c)}" width="${barW}" height="${H - pad.b - py(c)}" fill="${colour}" opacity="0.75"/>`;
  });

  [["p05_t", "P5"], ["p50_t", "P50"], ["p95_t", "P95"]].forEach(([key, label]) => {
    const v = summary[key];
    out += `<line x1="${px(v)}" y1="${pad.t}" x2="${px(v)}" y2="${H - pad.b}" stroke="${COLORS.ink}" stroke-width="0.8" stroke-dasharray="2 3" opacity="0.55"/>`;
    out += `<text x="${px(v)}" y="${H - pad.b + 13}" text-anchor="middle" class="axis-text" style="font-size:8px">${label}</text>`;
  });

  out += `<line x1="${pad.l}" y1="${H - pad.b}" x2="${W - pad.r}" y2="${H - pad.b}" class="axis-line"/>`;
  out += `<text x="${pad.l}" y="${H - 4}" class="axis-text" style="font-size:8px">${nf(lo, 2)}</text>`;
  out += `<text x="${W - pad.r}" y="${H - 4}" text-anchor="end" class="axis-text" style="font-size:8px">${nf(hi, 2)} t</text>`;
  out += `<text x="${pad.l}" y="${H - pad.b + 26}" class="axis-text" style="font-size:8.5px;fill:${COLORS.ink}">mean ${nf(
    summary.mean_t,
    3
  )} · SD ${nf(summary.sd_t, 3)}</text>`;
  return svgWrap(W, H, out);
}

/* ---------------------------------------------------------------- scenarios */
function renderScenarios(d) {
  $("#scenarios").innerHTML = tableHTML(
    [
      { key: "label", label: "Case", cls: "wrap" },
      { key: "kind", label: "Kind", render: (r) => tag(r.kind) },
      { key: "pcf_t", label: "t CO₂e/t", render: (r) => nf(r.pcf_t, 3) },
      { key: "delta_vs_baseline_t", label: "Δ t", render: (r) => (r.delta_vs_baseline_t ? nf(r.delta_vs_baseline_t, 3) : "—") },
      { key: "reduction_vs_baseline_pct", label: "Δ %", render: (r) => (r.reduction_vs_baseline_pct ? nf(r.reduction_vs_baseline_pct, 1) : "—") },
      { key: "scope1_kg", label: "Scope 1", render: (r) => nf(r.scope1_kg, 0) },
      { key: "scope2_kg", label: "Scope 2", render: (r) => nf(r.scope2_kg, 0) },
      { key: "scope3_kg", label: "Scope 3", render: (r) => nf(r.scope3_kg, 0) },
    ],
    d.scenarios
  );

  const sorted = [...d.scenarios].sort((a, b) => a.pcf_t - b.pcf_t);
  const low = sorted[0];
  const high = sorted[sorted.length - 1];
  const grid = d.scenarios.filter((s) => s.scenario === "renewable_grid")[0];
  const mass = d.scenarios.filter((s) => s.scenario === "mass_allocation")[0];
  const econ = d.scenarios.filter((s) => s.scenario === "economic_allocation")[0];
  $("#scen-note").textContent =
    `The envelope runs from ${nf(low.pcf_t, 2)} t (${low.label}) to ${nf(high.pcf_t, 2)} t (${high.label}). ` +
    (grid ? `A zero-carbon grid alone reaches ${nf(grid.pcf_t, 2)} t. ` : "") +
    (mass && econ
      ? `Allocation choice moves the result to ${nf(mass.pcf_t, 2)} t on mass and ${nf(econ.pcf_t, 2)} t on reference prices. `
      : "") +
    `All of these are decisions about which system is described, not measurement error: the evidence-constrained ` +
    `uncertainty band is only ${nf(d.uncertainty.evidence.p05_t, 2)}–${nf(d.uncertainty.evidence.p95_t, 2)} t wide.`;
}

/* ----------------------------------------------------------------- assurance */
function renderAssurance(d) {
  const q = d.kpis.checks;
  $("#q-summary").textContent = `${q.met} met · ${q.partial} partial · ${q.not_met} not met`;

  $("#quality").innerHTML = tableHTML(
    [
      { key: "id", label: "ID" },
      { key: "check", label: "Check", cls: "wrap" },
      { key: "status", label: "Status", render: (r) => tag(r.status) },
      { key: "evidence", label: "Evidence", cls: "wrap" },
      { key: "what_is_needed", label: "What is needed", cls: "wrap" },
    ],
    d.quality,
    { tableClass: "wide" }
  );

  renderOpenLca(d.openlca, d.openlca_characterisation);

  const carbon = d.validation.carbon;
  $("#carbon").innerHTML = tableHTML(
    [
      { key: "node", label: "Node", cls: "wrap" },
      { key: "C in (kg)", label: "C in", render: (r) => nf(r["C in (kg)"], 0) },
      { key: "C out (kg)", label: "C out", render: (r) => nf(r["C out (kg)"], 0) },
      { key: "raw closure %", label: "Raw %", render: (r) => nf(r["raw closure %"], 2) },
      { key: "closure %", label: "Closure", render: (r) => nf(r["closure %"], 2) },
      { key: "status", label: "Status", render: (r) => tag(r.status) },
    ],
    carbon
  );

  $("#findings").innerHTML = d.validation.findings
    .map(
      (f) => `<div class="finding ${f.severity}">
        <span class="finding-id">${esc(f.id)}</span>
        <div><h4>${esc(f.title)}</h4><p>${esc(f.detail)}</p></div>
        <span class="finding-impact">${f.impact_kg_co2e ? nf(f.impact_kg_co2e, 0) + " kg" : ""}</span>
      </div>`
    )
    .join("");

  const passed = d.validation.checks.filter((c) => c.status === "PASS").length;
  $("#check-summary").textContent = `${passed} pass · ${d.validation.checks.length - passed} fail`;
  $("#checks").innerHTML = tableHTML(
    [
      { key: "id", label: "ID" },
      { key: "check", label: "Check", cls: "wrap" },
      { key: "model", label: "Model", render: (r) => nf(r.model, 3) },
      { key: "specified", label: "Specified", render: (r) => nf(r.specified, 3) },
      { key: "dev_%", label: "Dev %", render: (r) => nf(r["dev_%"], 2) },
      { key: "tol_%", label: "Tol %", render: (r) => nf(r["tol_%"], 2) },
      { key: "status", label: "Status", render: (r) => tag(r.status) },
      { key: "note", label: "Note", cls: "wrap" },
    ],
    d.validation.checks,
    { tableClass: "wide" }
  );
}

function renderPrimaryData(d) {
  const el = $("#primary-data-card");
  if (!el || !d) {
    $("#primary-data-summary").textContent = "no primary-data result";
    $("#primary-data-body").innerHTML = "";
    $("#primary-data-status").textContent = "not computed";
    return;
  }

  const ok = d.validation && d.validation.status === "PASS";
  const status = d.validation ? d.validation.status : "FAIL";
  $("#primary-data-status").textContent = status;
  $("#primary-data-status").className = `chip ${status === "PASS" ? "pass" : status === "WARN" ? "warn" : "fail"}`;

  $("#primary-data-summary").textContent =
    `${nf(d.kpis.gwp_t, 3)} t CO<sub>2</sub>e/t · ${nf(d.kpis.gwp_kg, 0)} kg CO<sub>2</sub>e · ${nf(d.kpis.energy_gj, 1)} GJ primary`;

  const flows = d.params || [];
  $("#primary-data-flows").innerHTML = tableHTML(
    [
      { key: "flow", label: "Primary data flow" },
      { key: "quantity", label: "Value", render: (r) => nf(r.quantity, r.quantity < 10 ? 3 : 1) },
      { key: "unit", label: "Unit" },
    ],
    flows
  );

  $("#primary-data-table").innerHTML = tableHTML(
    [
      { key: "category", label: "Category" },
      { key: "indicator", label: "Indicator" },
      { key: "status", label: "Status", render: (r) => tag(r.status) },
      { key: "note", label: "Basis", cls: "wrap" },
    ],
    d.categories
  );

  const rows = d.stages.filter((s) => s.stage_key !== "total");
  $("#primary-data-stages").innerHTML = `
    <div class="mini-title">Stage values</div>
    ${tableHTML(
      [
        { key: "stage", label: "Stage" },
        { key: "total_kg_co2e", label: "kg CO₂e", render: (r) => nf(r.total_kg_co2e, 0) },
        { key: "share_pct", label: "Share", render: (r) => `${nf(r.share_pct, 1)}%` },
        { key: "energy_mj", label: "GJ", render: (r) => nf(r.energy_mj / 1000, 1) },
      ],
      rows
    )}`;

  $("#primary-data-contribution").innerHTML = (
    `<div class="mini-title">Contribution by stage</div>` +
    svgWrap(620, rows.length * 40 + 34, contributionChartSvg(d), "chart-box")
  );

  $("#primary-data-coverage").innerHTML = `<div class="card-head"><h3>Characterisation note</h3>${esc(d.coverage_note || "")}</div>`;

  $("#primary-data-findings").innerHTML = (
    `<div class="card-head"><h3>Findings</h3><span class="hint">${d.validation.findings.length} findings</span></div>` +
    d.validation.findings
      .map(
        (f) => `<div class="finding ${f.severity}">
          <span class="finding-id">${esc(f.id)}</span>
          <div><h4>${esc(f.title)}</h4><p>${esc(f.detail)}</p></div>
          <span class="finding-impact">${f.impact_kg_co2e ? nf(f.impact_kg_co2e, 0) + " kg" : ""}</span>
        </div>`
      )
      .join("")
  );
}

function contributionChartSvg(d) {
  const rows = d.stages
    .filter((s) => s.stage_key !== "total")
    .map((s) => ({
      label: s.stage,
      value: s.total_kg_co2e,
      share: 100 * s.total_kg_co2e / (d.kpis.gwp_kg || 1),
    }))
    .sort((a, b) => b.value - a.value);

  const W = 620;
  const rowH = 40;
  const H = rows.length * rowH + 34;
  const padL = 176;
  const padR = 66;
  const max = Math.max(...rows.map((r) => r.value)) * 1.08 || 1;
  const barW = W - padL - padR;

  let out = "";
  rows.forEach((row, i) => {
    const y = 10 + i * rowH;
    const w = Math.max(2, (row.value / max) * barW);
    out += `<text x="${padL - 10}" y="${y + 17}" text-anchor="end" class="axis-text" style="fill:var(--ink)">${esc(trunc(row.label, 26))}</text>`;
    out += `<rect x="${padL}" y="${y + 4}" width="${barW}" height="17" fill="#161d24" rx="1"/>`;
    out += `<rect x="${padL}" y="${y + 4}" width="${w}" height="17" fill="${COLORS.gwp}" opacity="${0.9 - i * 0.06}" rx="1"/>`;
    out += `<text x="${padL + w + 8}" y="${y + 17}" class="axis-text" style="fill:var(--ink)">${nf(row.value, 0)}</text>`;
    out += `<text x="${W - 8}" y="${y + 17}" text-anchor="end" class="axis-text">${nf(row.share, 1)}%</text>`;
  });
  out += `<text x="${padL}" y="${H - 6}" class="axis-text" style="font-size:8px">kg CO₂e per functional unit · share of total</text>`;
  return out;
}

function renderOpenLca(o, pe) {
  const note = $("#openlca-note");
  if (!o || !o.available) {
    $("#openlca-summary").textContent = "no run recorded";
    $("#openlca").innerHTML = "";
    note.textContent = (o && o.note) || "No openLCA run recorded.";
    return;
  }

  const match = Math.abs(o.delta_pct) < 0.05;
  $("#openlca-summary").textContent =
    `${nf(o.total_t, 4)} t · python ${nf(o.python_t, 4)} t · Δ ${nf(o.delta_pct, 3)} %`;

  $("#openlca").innerHTML = tableHTML(
    [
      { key: "process", label: "Unit process", cls: "wrap" },
      { key: "amount_kg", label: "kg CO₂e / t HDPE", render: (r) => nf(r.amount_kg, 1) },
      { key: "share_pct", label: "Share of total", render: (r) => `${nf(r.share_pct, 1)} %` },
    ],
    o.rows
  );

  const coverage = (o.method_characterisation && o.method_characterisation.coverage) || [];
  const coverable = coverage.filter((c) => c.coverable_from_foreground);
  const uncovered = coverage.filter((c) => !c.coverable_from_foreground);
  const fgFlows = (o.foreground_elementary_flows || []);

  const providers = (o.providers || []).map(
    (p) => `${p.flow === "ng" ? "natural gas" : "electricity"} from ${p.name}`
  );
  const basis = providers.length
    ? `Background providers linked: ${esc(providers.join("; "))}. The difference against the Python total is ` +
      `the background-data reconciliation, not a model error. `
    : `No background dataset is linked: gas and electricity are the study's own factor-based proxies, so ` +
      `agreement is by construction and this is not an ecoinvent footprint. `;
  const verdict = match
    ? `Difference ${nf(o.delta_pct, 3)} %. `
    : `<b>The engines disagree by ${nf(o.delta_pct, 2)} %; investigate before quoting either total.</b> `;

  note.innerHTML =
    `Independent calculation in database <code>${esc(o.database)}</code> with <b>${esc(o.method)}</b>, ` +
    `run ${esc(o.run_at)}, for the ${esc(o.functional_unit)}. ` +
    basis + verdict + esc(o.method_note);

  const el = $("#openlca-characterisation");
  const peCoverage = (pe && pe.coverage) || (o.openlca_characterisation && o.openlca_characterisation.coverage) || [];
  const peCoverable = peCoverage.filter((c) => c.coverable_from_foreground);
  const peUncovered = peCoverage.filter((c) => !c.coverable_from_foreground);
  const peNote = pe && pe.note ? pe.note : (o.openlca_characterisation && o.openlca_characterisation.note);
  if (peCoverage.length) {
    el.innerHTML = (
      `<div class="card-head"><h3>Characterisation coverage (openLCA impact methods vs foreground)</h3>` +
      `<span class="hint">${peCoverage.length} categories in the open database · ${fgFlows.length} foreground elementary flow(s)</span></div>` +
      `<p class="card-note" style="margin-top:0">${esc(peNote || `The open database carries ${peCoverage.length} impact categories; the foreground carries ${fgFlows.length} elementary flow(s).`)}</p>` +
      (peCoverable.length
        ? `<div class="sub-head">Characterisable from the foreground</div>` +
          `<ul class="card-note" style="margin-top:0">` +
          peCoverable.map((c) => `<li>${esc(c.impact_category)} — flows: ${esc(c.covering_foreground_flows || "none")}</li>`).join("") +
          `</ul>`
        : `<div class="sub-head">Nothing characterisable from the foreground</div>` +
          `<p class="card-note" style="margin-top:0">` +
          `The foreground carries no elementary flow that any installed impact method can characterise. ` +
          `Any further result would be invented, not assessed.</p>`) +
      (peUncovered.length
        ? `<div class="sub-head">Not characterisable from the foreground</div>` +
          `<p class="card-note" style="margin-top:0">` +
          esc(
            peUncovered.length +
            " categories available in the open database but not coverable from the foreground: " +
            peUncovered.map((c) => c.impact_category).join(", ") +
            ". The foreground would need the corresponding elementary flows (for example SO₂, NOₓ, NH₃, NMVOC, PM, P, N or water) before those categories could be reported."
          ) +
          `</p>`
        : "")
    );
    el.style.display = "";
  } else {
    el.innerHTML = "";
    el.style.display = "none";
  }
}

/* --------------------------------------------------------------------- primary data */
function renderPrimaryData(d) {
  const el = $("#primary-data-card");
  if (!el || !d) {
    $("#primary-data-summary").textContent = "no primary-data result";
    $("#primary-data-status").textContent = "not computed";
    return;
  }

  const statusText = d.validation ? d.validation.status : "FAIL";
  $("#primary-data-status").textContent = statusText;
  $("#primary-data-status").className = `chip ${statusText === "PASS" ? "pass" : statusText === "WARN" ? "warn" : "fail"}`;

  $("#primary-data-summary").textContent =
    `${nf(d.kpis.gwp_t, 3)} t CO<sub>2</sub>e/t · ${nf(d.kpis.gwp_kg, 0)} kg CO<sub>2</sub>e · ${nf(d.kpis.energy_gj, 1)} GJ primary`;

  $("#primary-data-flows").innerHTML = tableHTML(
    [
      { key: "flow", label: "Primary data flow" },
      { key: "quantity", label: "Value", render: (r) => nf(r.quantity, r.quantity < 10 ? 3 : 1) },
      { key: "unit", label: "Unit" },
    ],
    d.params || []
  );

  $("#primary-data-table").innerHTML = tableHTML(
    [
      { key: "category", label: "Category" },
      { key: "indicator", label: "Indicator" },
      { key: "status", label: "Status", render: (r) => tag(r.status) },
      { key: "note", label: "Basis", cls: "wrap" },
    ],
    d.categories || []
  );

  const rows = (d.stages || []).filter((s) => s.stage_key !== "total");
  $("#primary-data-stages").innerHTML = `
    <div class="mini-title">Stage values</div>
    ${tableHTML(
      [
        { key: "stage", label: "Stage" },
        { key: "total_kg_co2e", label: "kg CO₂e", render: (r) => nf(r.total_kg_co2e, 0) },
        { key: "share_pct", label: "Share", render: (r) => `${nf(r.share_pct, 1)}%` },
        { key: "energy_mj", label: "GJ", render: (r) => nf(r.energy_mj / 1000, 1) },
      ],
      rows
    )}`;

  $("#primary-data-chart").innerHTML = (
    `<div class="mini-title">Contribution by stage</div>` +
    svgWrap(620, Math.max(1, rows.length) * 40 + 34, contributionChartSvg(d), "chart-box")
  );

  $("#primary-data-coverage").innerHTML = `<div class="card-head"><h3>Characterisation note</h3>${esc(d.coverage_note || "")}</div>`;

  $("#primary-data-findings").innerHTML = (
    `<div class="card-head"><h3>Findings</h3><span class="hint">${(d.validation && d.validation.findings ? d.validation.findings.length : 0)} findings</span></div>` +
    (d.validation && d.validation.findings
      ? d.validation.findings
          .map(
            (f) => `<div class="finding ${f.severity}">
            <span class="finding-id">${esc(f.id)}</span>
            <div><h4>${esc(f.title)}</h4><p>${esc(f.detail)}</p></div>
            <span class="finding-impact">${f.impact_kg_co2e ? nf(f.impact_kg_co2e, 0) + " kg" : ""}</span>
          </div>`
          )
          .join("")
      : "")
  );
}

function contributionChartSvg(d) {
  const gwpKg = d.kpis && d.kpis.gwp_kg ? d.kpis.gwp_kg : 1;
  const rows = (d.stages || [])
    .filter((s) => s.stage_key !== "total")
    .map((s) => ({
      label: s.stage,
      value: s.total_kg_co2e,
      share: 100 * (s.total_kg_co2e || 0) / gwpKg,
    }))
    .sort((a, b) => b.value - a.value);

  const W = 620;
  const rowH = 40;
  const H = Math.max(1, rows.length) * rowH + 34;
  const padL = 176;
  const padR = 66;
  const max = Math.max(...rows.map((r) => r.value), 0) * 1.08 || 1;
  const barW = W - padL - padR;

  let out = "";
  rows.forEach((row, i) => {
    const y = 10 + i * rowH;
    const w = Math.max(2, (row.value / max) * barW);
    out += `<text x="${padL - 10}" y="${y + 17}" text-anchor="end" class="axis-text" style="fill:var(--ink)">${esc(trunc(row.label, 26))}</text>`;
    out += `<rect x="${padL}" y="${y + 4}" width="${barW}" height="17" fill="#161d24" rx="1"/>`;
    out += `<rect x="${padL}" y="${y + 4}" width="${w}" height="17" fill="${COLORS.gwp}" opacity="${0.9 - i * 0.06}" rx="1"/>`;
    out += `<text x="${padL + w + 8}" y="${y + 17}" class="axis-text" style="fill:var(--ink)">${nf(row.value, 0)}</text>`;
    out += `<text x="${W - 8}" y="${y + 17}" text-anchor="end" class="axis-text">${nf(row.share, 1)}%</text>`;
  });
  out += `<text x="${padL}" y="${H - 6}" class="axis-text" style="font-size:8px">kg CO₂e per functional unit · share of total</text>`;
  return out;
}

/* --------------------------------------------------------------------- files */
function renderFiles(d) {
  const byName = new Map(d.files.map((f) => [f.name, f]));
  const resolve = (path) => {
    if (byName.has(path)) return byName.get(path);
    if (path.endsWith("/")) return byName.get(path + "README.md");
    const base = path.split(" / ")[0];
    if (byName.has(base)) return byName.get(base);
    return [...byName.values()].find((f) => f.name.endsWith(path.split("/").pop()));
  };

  const delivered = d.deliverables.filter((r) => r.status === "Delivered").length;
  $("#deliv-summary").textContent = `${delivered} of ${d.deliverables.length} delivered`;

  $("#deliverables").innerHTML = tableHTML(
    [
      { key: "deliverable", label: "Deliverable", cls: "wrap" },
      { key: "status", label: "Status", render: (r) => tag(r.status) },
      { key: "path", label: "Location", cls: "wrap", render: (r) => `<span class="mono">${esc(r.path)}</span>` },
      { key: "note", label: "Note", cls: "wrap" },
      {
        key: "path",
        label: "",
        render: (r) => {
          const file = resolve(r.path);
          return file ? `<a class="btn ghost" href="${esc(file.url)}" target="_blank" rel="noopener">open</a>` : "";
        },
      },
    ],
    d.deliverables,
    { tableClass: "wide" }
  );

  $("#file-summary").textContent = `${d.files.length} files`;
  $("#files").innerHTML = d.files
    .map(
      (f) => `<a class="file" href="${esc(f.url)}" target="_blank" rel="noopener" title="${esc(f.name)}">
        <span class="file-kind">${esc(f.kind)}</span>
        <span class="file-label">${esc(f.label)}</span>
        <span class="file-size">${bytes(f.bytes)}</span>
      </a>`
    )
    .join("");
}

function renderFooter(d) {
  $("#foot-meta").textContent = `GWP ${nf(d.kpis.gwp_t, 4)} t CO₂e/t · ${d.kpis.flows} flows · ${d.files.length} files · generated ${d.generated_at}`;
}

/* -------------------------------------------------------------------- wiring */
function bind() {
  $("#flow-search").addEventListener("input", (e) => {
    state.flowQuery = e.target.value;
    drawFlows();
  });

  $("#flow-filters").addEventListener("click", (e) => {
    const button = e.target.closest("button[data-group]");
    if (!button) return;
    state.flowFilter = button.dataset.group;
    $$("#flow-filters button").forEach((b) => b.classList.toggle("on", b === button));
    drawFlows();
  });

  $("#impact-switch").addEventListener("click", (e) => {
    const button = e.target.closest("button[data-mode]");
    if (!button) return;
    state.impactMode = button.dataset.mode;
    $$("#impact-switch button").forEach((b) => b.classList.toggle("on", b === button));
    drawImpactChart();
  });

  $("#primary-data-submit").addEventListener("click", async () => {
    const rows = $$("#primary-data-params input");
    const params = {};
    rows.forEach((input) => {
      const key = input.dataset.key;
      const value = input.value.trim();
      if (key && value !== "") {
        params[key] = value;
      }
    });
    try {
      const response = await fetch("/api/lca/compute", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ params }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(response.statusText + " " + text);
      }
      const data = await response.json();
      renderPrimaryData(data);
      const toast = $("#toast");
      toast.textContent = `Primary-data run: ${data.kpis.gwp_t} t CO₂e/t HDPE`;
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 4500);
    } catch (error) {
      const toast = $("#toast");
      toast.textContent = `Primary-data run failed: ${error.message}`;
      toast.classList.add("show", "error");
    }
  });
}

async function boot() {
  try {
    const response = await fetch("/api/lca");
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();
    state.data = data;

    renderHeader(data);
    renderNav();
    renderKpis(data);
    renderStudy(data);
    renderBoundary(data);
    renderImpact(data);
    renderInventory(data);
    renderSensitivity(data);
    renderUncertainty(data);
    renderScenarios(data);
    renderAssurance(data);
    renderFiles(data);
    renderFooter(data);
    bind();
    renderPrimaryData(null);
    document.body.classList.remove("is-loading");
  } catch (error) {
    $("#v-status").textContent = "API error";
    $("#v-status").className = "chip fail";
    const toast = $("#toast");
    toast.textContent = `Could not load the study: ${error.message}`;
    toast.classList.add("show", "error");
  }
}

boot();
