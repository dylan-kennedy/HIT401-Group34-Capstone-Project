/* webapp/static/app.js — HIT401 Group 34 Data Explorer
 *
 * Single-page app: fetches everything from the FastAPI server in webapp/server.py.
 * No build step — vanilla JS, Leaflet + markercluster for the map, Plotly.js for charts.
 */

(() => {
"use strict";

// ---------------------------------------------------------------------------
// STATE
// ---------------------------------------------------------------------------

const state = {
  meta: null,
  locations: { bores: [], gauges: [], bom_stations: [] },
  boresById: new Map(),
  gaugesById: new Map(),
  bomById: new Map(),
  selected: null,        // { type, id }
  activeTab: "overview",
  compareIds: [],         // up to 5 bore ids
  compareColours: {},
  colourBy: "status",
  chemicalParam: null,
  chemicalValues: null,   // {parameter, statistic, values:{bore_no:value}, default_threshold,...}
  threshold: 0,
  extentOnly: false,
  view: "map",            // "map" | "climate"
  panelMode: "empty",     // "empty" | "detail" | "compare" — which thing the right panel is showing
};

const COMPARE_COLOURS = [
  "#303030", "#72b026", "#f69730", "#d252b9", "#0067a3",
];

const CATEGORY_COLOURS = {
  status: { Current: "#2f6f4e", Historical: "#9a9a9a", _other: "#5b8ab0" },
  purpose: {
    Production: "#2f6f4e", Monitoring: "#0067a3", Investigation: "#f69730",
    Unknown: "#9a9a9a", _other: "#d252b9",
  },
  has_water_level: { true: "#2f6f4e", false: "#c9c9c9" },
  has_water_quality: { true: "#0067a3", false: "#c9c9c9" },
};

// ---------------------------------------------------------------------------
// SMALL HELPERS
// ---------------------------------------------------------------------------

async function fetchJSON(url, params) {
  const u = new URL(url, window.location.origin);
  if (params) Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") u.searchParams.set(k, v);
  });
  const resp = await fetch(u);
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`${resp.status} ${resp.statusText}: ${body.slice(0, 200)}`);
  }
  return resp.json();
}

function showLoading(on) {
  document.getElementById("loading-indicator").classList.toggle("hidden", !on);
}

function fmt(value, suffix = "") {
  if (value === null || value === undefined || value === "" || Number.isNaN(value)) return "Not recorded";
  if (typeof value === "number") return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
  return `${value}${suffix}`;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  });
  (Array.isArray(children) ? children : [children]).forEach((c) => {
    if (c === null || c === undefined) return;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  });
  return node;
}

function downloadCSV(filename, rows) {
  if (!rows || !rows.length) { alert("No data to download."); return; }
  const cols = Object.keys(rows[0]);
  const lines = [cols.join(",")].concat(
    rows.map((r) => cols.map((c) => JSON.stringify(r[c] ?? "")).join(","))
  );
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function arraysToRows(xKey, xs, series) {
  // series: {label: ys[]} -> rows [{xKey: x, label1: y, label2: y, ...}]
  return xs.map((x, i) => {
    const row = { [xKey]: x };
    Object.entries(series).forEach(([label, ys]) => { row[label] = ys[i]; });
    return row;
  });
}

// ---------------------------------------------------------------------------
// DARK MODE (localStorage is a per-browser convenience only; wrapped defensively)
// ---------------------------------------------------------------------------

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch (e) { /* ignore */ }
  if (saved === "dark" || saved === "light") {
    document.documentElement.setAttribute("data-theme", saved);
  }
  document.getElementById("btn-dark").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) { /* ignore */ }
    refreshAllMarkerColours();
  });
}

// ---------------------------------------------------------------------------
// URL STATE (shareable link: ?loc=bore:RN006543&tab=waterquality&view=map)
// ---------------------------------------------------------------------------

function readURLState() {
  const params = new URLSearchParams(window.location.search);
  const loc = params.get("loc");
  const tab = params.get("tab");
  const view = params.get("view");
  let selected = null;
  if (loc && loc.includes(":")) {
    const [type, id] = loc.split(":");
    selected = { type, id };
  }
  return { selected, tab, view };
}

function writeURLState() {
  const params = new URLSearchParams();
  if (state.selected) params.set("loc", `${state.selected.type}:${state.selected.id}`);
  if (state.activeTab) params.set("tab", state.activeTab);
  if (state.view !== "map") params.set("view", state.view);
  const newURL = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", newURL);
}

// ---------------------------------------------------------------------------
// LAYOUT: draggable splitter, expand/collapse, panel empty state, chart resize
//
// Pure layout/interaction — no data, API or chart-content logic lives here. The split
// width is a CSS % on #drawer (map fills the rest via flex:1), persisted to
// localStorage (wrapped in try/catch, per-browser convenience only, never required for
// the page to work correctly if it's unavailable or cleared).
// ---------------------------------------------------------------------------

const PANEL_WIDTH_STORAGE_KEY = "webapp_panel_pct";
const PANEL_DEFAULT_PCT = 42;   // within the requested 40-45% panel / 55-60% map split
const PANEL_MIN_PCT = 26;
const PANEL_MAX_PCT = 60;

function resizeAllCharts() {
  document.querySelectorAll(".chart").forEach((el) => {
    if (el.data) {           // Plotly stamps .data onto a div once it has drawn a chart there
      try { Plotly.Plots.resize(el); } catch (e) { /* not plotted yet, nothing to resize */ }
    }
  });
}

function readStoredPanelPct() {
  try {
    const raw = localStorage.getItem(PANEL_WIDTH_STORAGE_KEY);
    const n = raw === null ? NaN : parseFloat(raw);
    if (Number.isFinite(n) && n >= PANEL_MIN_PCT && n <= PANEL_MAX_PCT) return n;
  } catch (e) { /* localStorage unavailable (private mode, cleared site data, etc.) */ }
  return PANEL_DEFAULT_PCT;
}

function applyPanelWidth(pct) {
  const clamped = Math.max(PANEL_MIN_PCT, Math.min(PANEL_MAX_PCT, pct));
  const drawer = document.getElementById("drawer");
  drawer.style.width = `${clamped}%`;
  try { localStorage.setItem(PANEL_WIDTH_STORAGE_KEY, String(clamped)); } catch (e) { /* ignore */ }
  resizeAllCharts();
  return clamped;
}

function setLayoutMode(mode) {
  // mode: "split" | "panel" | "map"
  const wrap = document.getElementById("map-drawer-wrap");
  const panelBtn = document.getElementById("btn-panel-expand");
  const mapBtn = document.getElementById("btn-map-expand");
  wrap.classList.remove("panel-expanded", "map-expanded");
  if (mode === "panel") wrap.classList.add("panel-expanded");
  if (mode === "map") wrap.classList.add("map-expanded");
  panelBtn.setAttribute("aria-pressed", String(mode === "panel"));
  mapBtn.setAttribute("aria-pressed", String(mode === "map"));
  // The panel (and its own "Expand map" button) is hidden entirely in map-expanded
  // mode, so this floating button is the only way back — see its comment in index.html.
  document.getElementById("btn-exit-map-expand").classList.toggle("hidden", mode !== "map");
  // Let the new widths land before resizing Leaflet/Plotly against them.
  setTimeout(() => {
    resizeAllCharts();
    if (map) map.invalidateSize();
  }, 60);
}

function initSplitter() {
  const splitter = document.getElementById("splitter");
  const wrap = document.getElementById("map-drawer-wrap");
  let dragging = false;

  applyPanelWidth(readStoredPanelPct());

  function onMove(clientX) {
    const rect = wrap.getBoundingClientRect();
    if (rect.width <= 0) return;
    const pct = ((rect.right - clientX) / rect.width) * 100;   // drawer is on the right
    applyPanelWidth(pct);
  }

  splitter.addEventListener("mousedown", (e) => {
    dragging = true;
    splitter.classList.add("dragging");
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => { if (dragging) onMove(e.clientX); });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    splitter.classList.remove("dragging");
  });

  splitter.addEventListener("touchstart", () => {
    dragging = true;
    splitter.classList.add("dragging");
  }, { passive: true });
  window.addEventListener("touchmove", (e) => {
    if (dragging && e.touches[0]) onMove(e.touches[0].clientX);
  }, { passive: true });
  window.addEventListener("touchend", () => {
    dragging = false;
    splitter.classList.remove("dragging");
  });

  // Keyboard resizing: focus the splitter (it's a role="separator" with tabindex="0"),
  // then use the arrow keys — the same interaction pattern browsers expect for sliders.
  splitter.addEventListener("keydown", (e) => {
    const current = parseFloat(document.getElementById("drawer").style.width) || PANEL_DEFAULT_PCT;
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") { applyPanelWidth(current + 2); e.preventDefault(); }
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { applyPanelWidth(current - 2); e.preventDefault(); }
  });

  document.getElementById("btn-panel-expand").addEventListener("click", () => {
    setLayoutMode(wrap.classList.contains("panel-expanded") ? "split" : "panel");
  });
  document.getElementById("btn-map-expand").addEventListener("click", () => {
    setLayoutMode(wrap.classList.contains("map-expanded") ? "split" : "map");
  });
  document.getElementById("btn-exit-map-expand").addEventListener("click", () => setLayoutMode("split"));
  document.getElementById("btn-reset-layout").addEventListener("click", () => {
    try { localStorage.removeItem(PANEL_WIDTH_STORAGE_KEY); } catch (e) { /* ignore */ }
    applyPanelWidth(PANEL_DEFAULT_PCT);
    setLayoutMode("split");
  });

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resizeAllCharts, 150);
  });
}

/**
 * The right-hand panel is always visible, in one of three states: nothing selected and
 * nothing being compared ("empty" — #drawer-empty-state shown), a location's detail
 * view ("detail" — #drawer-header/#drawer-tabs/#drawer-body), or the compare overlay
 * ("compare" — same three elements, repurposed by openCompareView()). This only ever
 * toggles .hidden on existing elements; it never touches what selectLocation()/
 * openCompareView() put inside them.
 */
function updatePanelEmptyState() {
  const showContent = state.panelMode !== "empty";
  document.getElementById("drawer-empty-state").classList.toggle("hidden", showContent);
  ["drawer-header", "drawer-tabs", "drawer-body", "drawer-close"].forEach((id) => {
    document.getElementById(id).classList.toggle("hidden", !showContent);
  });
}

// ---------------------------------------------------------------------------
// MAP
// ---------------------------------------------------------------------------

let map, boreCluster, gaugeCluster, bomCluster, aquiferLayers = {};

function initMap() {
  map = L.map("map", { center: [-19.5, 133.5], zoom: 6, preferCanvas: true });

  const topo = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
    maxZoom: 17, attribution: "Map data © OpenStreetMap contributors, SRTM | Map style © OpenTopoMap",
  }).addTo(map);
  const satellite = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { attribution: "Tiles © Esri" }
  );
  const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
  });

  boreCluster = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 50 });
  gaugeCluster = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 50 });
  bomCluster = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 60 });

  const baseLayers = { "Terrain (OpenTopoMap)": topo, "Satellite (Esri)": satellite, "OpenStreetMap": osm };
  const overlays = { "Bores": boreCluster, "River / stream gauges": gaugeCluster, "BOM stations": bomCluster };

  Promise.all(
    ["boundary", "salinity", "aquifer_thickness", "water_depth", "contours"].map((key) =>
      fetch(`/aquifer_geo/${key}.geojson`).then((r) => r.json()).then((gj) => [key, gj])
    )
  ).then((pairs) => {
    const styles = {
      boundary: { color: "#172554", weight: 3, fillOpacity: 0 },
      salinity: { color: "#d97706", weight: 1, fillColor: "#fbbf24", fillOpacity: 0.22 },
      aquifer_thickness: { color: "#0891b2", weight: 1, fillColor: "#67e8f9", fillOpacity: 0.22 },
      water_depth: { color: "#2563eb", weight: 1, fillColor: "#60a5fa", fillOpacity: 0.18 },
      contours: { color: "#7c3aed", weight: 2, fillOpacity: 0 },
    };
    const niceNames = {
      boundary: "Ti Tree basin boundary", salinity: "Ti Tree salinity zones",
      aquifer_thickness: "Ti Tree aquifer thickness", water_depth: "Ti Tree depth to groundwater",
      contours: "Ti Tree groundwater contours",
    };
    pairs.forEach(([key, gj]) => {
      const layer = L.geoJSON(gj, { style: () => styles[key] });
      aquiferLayers[key] = layer;
      overlays[niceNames[key]] = layer;
      if (key === "boundary") layer.addTo(map);
    });
    L.control.layers(baseLayers, overlays, { collapsed: true, position: "bottomright" }).addTo(map);
  });

  boreCluster.addTo(map);
  gaugeCluster.addTo(map);
  bomCluster.addTo(map);

  map.on("click", (e) => {
    if (e.originalEvent._stoppedForMarker) return;
    showPlaceSummary(e.latlng.lat, e.latlng.lng);
  });
  map.on("moveend", () => { if (state.extentOnly) renderMarkers(); });
}

function colourFor(type, props) {
  if (type !== "bore") {
    return type === "river_stream_gauge" ? (props.has_flow_series ? "#0067a3" : "#9a9a9a")
                                        : (props.is_nt ? "#2f6f4e" : "#9a9a9a");
  }
  const mode = state.colourBy;
  if (mode === "status" || mode === "purpose") {
    const map_ = CATEGORY_COLOURS[mode];
    return map_[props[mode]] || map_._other;
  }
  if (mode === "has_water_level" || mode === "has_water_quality") {
    return CATEGORY_COLOURS[mode][String(Boolean(props[mode]))];
  }
  if (mode === "yield_ls" || mode === "waterlevel_m") {
    const v = props[mode];
    if (v === null || v === undefined) return "#9a9a9a";
    return v > state.threshold ? "#b4242c" : "#2f6f4e";
  }
  if (mode === "chemical") {
    if (!state.chemicalValues) return "#9a9a9a";
    const v = state.chemicalValues.values[props.id];
    if (v === undefined) return "#9a9a9a";
    return v > state.threshold ? "#b4242c" : "#2f6f4e";
  }
  return "#2f6f4e";
}

function makeMarker(type, props) {
  const colour = colourFor(type, props);
  const isSelected = state.selected && state.selected.type === type && state.selected.id === props.id;
  const isCompared = type === "bore" && state.compareIds.includes(props.id);
  let finalColour = colour;
  if (isCompared) finalColour = state.compareColours[props.id];
  const radius = isSelected ? 8 : 5.5;
  const marker = L.circleMarker([props.lat, props.lon], {
    radius, color: isSelected ? "#000" : "rgba(0,0,0,0.35)", weight: isSelected ? 2 : 1,
    fillColor: finalColour, fillOpacity: 0.9,
  });
  marker.bindTooltip(`${props.id}${props.name ? " — " + props.name : ""}`);
  marker.on("click", (e) => {
    e.originalEvent._stoppedForMarker = true;
    L.DomEvent.stopPropagation(e);
    selectLocation(type, props.id);
  });
  return marker;
}

function withinExtent(lat, lon) {
  if (!state.extentOnly) return true;
  const b = map.getBounds();
  return b.contains([lat, lon]);
}

function matchesFilters(bore) {
  const statusSel = getMultiSelectValues("filter-status");
  const purposeSel = getMultiSelectValues("filter-purpose");
  if (statusSel.length && !statusSel.includes(bore.status)) return false;
  if (purposeSel.length && !purposeSel.includes(bore.purpose)) return false;
  if (document.getElementById("chk-monitoring-only").checked && !bore.is_monitoring_location) return false;
  return true;
}

function getMultiSelectValues(id) {
  return Array.from(document.getElementById(id).selectedOptions).map((o) => o.value);
}

function renderMarkers() {
  boreCluster.clearLayers();
  gaugeCluster.clearLayers();
  bomCluster.clearLayers();

  if (document.getElementById("chk-bores").checked) {
    const markers = state.locations.bores
      .filter((b) => withinExtent(b.lat, b.lon) && matchesFilters(b))
      .map((b) => makeMarker("bore", b));
    boreCluster.addLayers(markers);
  }
  if (document.getElementById("chk-gauges").checked) {
    const markers = state.locations.gauges
      .filter((g) => withinExtent(g.lat, g.lon))
      .map((g) => makeMarker("river_stream_gauge", g));
    gaugeCluster.addLayers(markers);
  }
  const showNT = document.getElementById("chk-bom-nt").checked;
  const showOther = document.getElementById("chk-bom-other").checked;
  const bomMarkers = state.locations.bom_stations
    .filter((s) => withinExtent(s.lat, s.lon) && ((s.is_nt && showNT) || (!s.is_nt && showOther)))
    .map((s) => makeMarker("bom_station", s));
  bomCluster.addLayers(bomMarkers);

  updateCounts();
}

function refreshAllMarkerColours() { renderMarkers(); }

function updateCounts() {
  document.getElementById("count-bores").textContent = `(${state.locations.bores.length.toLocaleString()})`;
  document.getElementById("count-gauges").textContent = `(${state.locations.gauges.length})`;
  document.getElementById("count-bom-nt").textContent = `(${state.locations.bom_stations.filter((s) => s.is_nt).length})`;
  document.getElementById("count-bom-other").textContent = `(${state.locations.bom_stations.filter((s) => !s.is_nt).length})`;
}

// ---------------------------------------------------------------------------
// PLACE SUMMARY (click anywhere on the map that isn't a marker)
// ---------------------------------------------------------------------------

async function showPlaceSummary(lat, lon) {
  const panel = document.getElementById("place-summary");
  panel.classList.remove("hidden");
  panel.innerHTML = "Loading…";
  try {
    const data = await fetchJSON("/api/place", { lat, lon });
    const nb = data.nearby;
    const rows = [
      el("button", { class: "close-x", type: "button", "aria-label": "Close place summary", onclick: () => panel.classList.add("hidden") }, "✕"),
      el("div", {}, [el("strong", {}, "Place summary")]),
      el("div", { class: "caption" }, `${lat.toFixed(4)}, ${lon.toFixed(4)}`),
    ];
    if (nb.bores.length) {
      const b = nb.bores[0];
      rows.push(el("div", {}, `Nearest bore: ${b.bore_no} (${b.distance_km.toFixed(1)} km)`));
    }
    if (nb.nt_bom_station) {
      rows.push(el("div", {}, `Nearest NT rainfall station: ${nb.nt_bom_station.name} (${nb.nt_bom_station.distance_km.toFixed(1)} km${nb.nt_bom_station.far_warning ? " ⚠️ far" : ""})`));
    }
    if (nb.gauge) {
      rows.push(el("div", {}, `Nearest gauge: ${nb.gauge.name || nb.gauge.station_id} (${nb.gauge.distance_km.toFixed(1)} km)`));
    }
    if (data.aquifer_context.inside_ti_tree_basin) {
      rows.push(el("div", { class: "caption" }, "Inside the Ti Tree basin — see a nearby bore's Aquifer context tab for salinity/depth detail."));
    } else {
      rows.push(el("div", { class: "caption" }, "Outside the Ti Tree basin — no mapped aquifer layer here."));
    }
    panel.innerHTML = "";
    rows.forEach((r) => panel.appendChild(r));
  } catch (err) {
    panel.innerHTML = `<button type="button" class="close-x" aria-label="Close place summary" onclick="this.parentElement.classList.add('hidden')">✕</button>Could not load this point: ${err.message}`;
  }
}

// ---------------------------------------------------------------------------
// SEARCH
// ---------------------------------------------------------------------------

function initSearch() {
  const input = document.getElementById("search-input");
  const results = document.getElementById("search-results");
  let timer = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { results.classList.add("hidden"); return; }
    timer = setTimeout(async () => {
      try {
        const data = await fetchJSON("/api/search", { q });
        results.innerHTML = "";
        data.results.forEach((r) => {
          const row = el("div", { class: r.type === "none" ? "result-row no-match" : "result-row" }, r.label);
          if (r.type !== "none") {
            row.addEventListener("click", () => {
              results.classList.add("hidden");
              input.value = "";
              map.setView([r.lat, r.lon], 13);
              selectLocation(r.type, r.id);
            });
          }
          results.appendChild(row);
        });
        results.classList.remove("hidden");
      } catch (err) { /* ignore transient search errors */ }
    }, 220);
  });
  document.addEventListener("click", (e) => {
    if (!document.getElementById("search-wrap").contains(e.target)) results.classList.add("hidden");
  });
}

// ---------------------------------------------------------------------------
// SIDEBAR WIRING
// ---------------------------------------------------------------------------

function initSidebar() {
  document.getElementById("sidebar-collapse").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("collapsed");
  });

  ["chk-bores", "chk-gauges", "chk-bom-nt", "chk-bom-other", "chk-monitoring-only"].forEach((id) => {
    document.getElementById(id).addEventListener("change", renderMarkers);
  });
  document.getElementById("chk-extent").addEventListener("change", (e) => {
    state.extentOnly = e.target.checked;
    renderMarkers();
  });
  document.getElementById("filter-status").addEventListener("change", renderMarkers);
  document.getElementById("filter-purpose").addEventListener("change", renderMarkers);

  const colourSelect = document.getElementById("colour-by");
  colourSelect.addEventListener("change", async (e) => {
    state.colourBy = e.target.value;
    await updateColourControls();
    renderMarkers();
  });

  document.getElementById("chemical-parameter").addEventListener("change", onChemicalParamChange);
  document.getElementById("chemical-statistic").addEventListener("change", onChemicalParamChange);
  document.getElementById("threshold-slider").addEventListener("input", (e) => {
    state.threshold = parseFloat(e.target.value);
    document.getElementById("threshold-value").textContent = state.threshold;
    renderMarkers();
    updateLegend();
  });

  document.getElementById("btn-compare").addEventListener("click", openCompareView);
}

function populateFilterOptions() {
  const statusSelect = document.getElementById("filter-status");
  const purposeSelect = document.getElementById("filter-purpose");
  statusSelect.innerHTML = "";
  purposeSelect.innerHTML = "";
  (state.meta.status_options || []).forEach((v) => statusSelect.appendChild(el("option", { value: v }, v)));
  (state.meta.purpose_options || []).forEach((v) => purposeSelect.appendChild(el("option", { value: v }, v)));

  const chemSelect = document.getElementById("chemical-parameter");
  chemSelect.innerHTML = "";
  state.meta.measurements.names.forEach((name, i) => {
    const code = state.meta.measurements.columns[i];
    chemSelect.appendChild(el("option", { value: code }, name));
  });
}

async function updateColourControls() {
  const chemControls = document.getElementById("chemical-controls");
  const threshControls = document.getElementById("threshold-controls");
  const mode = state.colourBy;
  chemControls.classList.toggle("hidden", mode !== "chemical");
  threshControls.classList.toggle("hidden", !(mode === "chemical" || mode === "yield_ls" || mode === "waterlevel_m"));

  if (mode === "chemical") {
    await onChemicalParamChange();
  } else if (mode === "yield_ls" || mode === "waterlevel_m") {
    const values = state.locations.bores.map((b) => b[mode]).filter((v) => v !== null && v !== undefined);
    const med = values.length ? values.slice().sort((a, b) => a - b)[Math.floor(values.length / 2)] : 0;
    state.threshold = Math.round(med * 100) / 100;
    const slider = document.getElementById("threshold-slider");
    const max = Math.max(...values, 1);
    slider.min = 0; slider.max = max; slider.step = Math.max(max / 100, 0.01); slider.value = state.threshold;
    document.getElementById("threshold-value").textContent = state.threshold;
  }
  updateLegend();
}

async function onChemicalParamChange() {
  const param = document.getElementById("chemical-parameter").value;
  const statistic = document.getElementById("chemical-statistic").value;
  showLoading(true);
  try {
    state.chemicalValues = await fetchJSON("/api/water-quality-map", { parameter: param, statistic });
    state.threshold = state.chemicalValues.default_threshold;
    const slider = document.getElementById("threshold-slider");
    slider.min = state.chemicalValues.min ?? 0;
    slider.max = state.chemicalValues.max ?? 100;
    slider.step = Math.max((slider.max - slider.min) / 100, 0.01);
    slider.value = state.threshold;
    document.getElementById("threshold-value").textContent = state.threshold;
  } finally { showLoading(false); }
  renderMarkers();
  updateLegend();
}

function updateLegend() {
  const legend = document.getElementById("colour-legend");
  legend.innerHTML = "";
  const mode = state.colourBy;
  const rows = [];
  if (mode === "status") {
    rows.push(["Current", CATEGORY_COLOURS.status.Current], ["Historical", CATEGORY_COLOURS.status.Historical]);
  } else if (mode === "purpose") {
    Object.entries(CATEGORY_COLOURS.purpose).forEach(([k, v]) => { if (k !== "_other") rows.push([k, v]); });
    rows.push(["Other", CATEGORY_COLOURS.purpose._other]);
  } else if (mode === "has_water_level") {
    rows.push(["Has series", CATEGORY_COLOURS.has_water_level.true], ["No series", CATEGORY_COLOURS.has_water_level.false]);
  } else if (mode === "has_water_quality") {
    rows.push(["Has samples", CATEGORY_COLOURS.has_water_quality.true], ["No samples", CATEGORY_COLOURS.has_water_quality.false]);
  } else {
    rows.push(["Above threshold", "#b4242c"], ["At or below", "#2f6f4e"], ["No value", "#9a9a9a"]);
  }
  rows.forEach(([label, colour]) => {
    legend.appendChild(el("div", { class: "legend-row" }, [
      el("span", { class: "legend-dot", style: `background:${colour}` }),
      el("span", {}, label),
    ]));
  });
}

// ---------------------------------------------------------------------------
// DRAWER
// ---------------------------------------------------------------------------

const BORE_TABS = ["overview", "waterlevel", "waterquality", "rainfall", "riverflow", "nearby", "dataquality", "aquifer"];
const GAUGE_TABS = ["overview", "riverflow", "nearby", "dataquality"];
const BOM_TABS = ["overview", "rainfall", "nearby", "dataquality"];
const TAB_LABELS = {
  overview: "Overview", waterlevel: "Water level", waterquality: "Water quality",
  rainfall: "Rainfall", riverflow: "River flow", nearby: "Nearby",
  dataquality: "Data quality", aquifer: "Aquifer context",
};

async function selectLocation(type, id) {
  state.selected = { type, id };
  state.activeTab = "overview";
  state.panelMode = "detail";
  updatePanelEmptyState();
  writeURLState();
  await openDrawer();
  renderMarkers();
}

async function openDrawer() {
  document.getElementById("drawer-title").textContent = "Loading…";
  document.getElementById("drawer-body").innerHTML = "";
  showLoading(true);
  try {
    const { type, id } = state.selected;
    const detail = await fetchJSON(`/api/location/${type}/${id}`);
    state.currentDetail = detail;
    renderDrawerHeader(type, id, detail);
    renderDrawerTabs(type);
    await renderActiveTab();
  } catch (err) {
    document.getElementById("drawer-title").textContent = "Not found";
    document.getElementById("drawer-body").innerHTML = `<p class="empty-state">${err.message}</p>`;
  } finally { showLoading(false); }
}

function renderDrawerHeader(type, id, detail) {
  const title = document.getElementById("drawer-title");
  const subtitle = document.getElementById("drawer-subtitle");
  const addBtn = document.getElementById("drawer-add-compare");
  title.textContent = id;
  const name = detail.overview.name || detail.overview.monitor_name || "";
  subtitle.textContent = `${{ bore: "Bore", river_stream_gauge: "River/stream gauge", bom_station: "BOM rainfall station" }[type]}${name ? " — " + name : ""}`;
  addBtn.classList.toggle("hidden", type !== "bore");
  addBtn.textContent = state.compareIds.includes(id) ? "✓ In compare tray" : "+ Add to compare tray";
  addBtn.onclick = () => toggleCompare(id);
}

function renderDrawerTabs(type) {
  const tabs = { bore: BORE_TABS, river_stream_gauge: GAUGE_TABS, bom_station: BOM_TABS }[type];
  const nav = document.getElementById("drawer-tabs");
  nav.innerHTML = "";
  tabs.forEach((tab) => {
    const btn = el("button", {
      class: tab === state.activeTab ? "active" : "",
      onclick: async () => { state.activeTab = tab; writeURLState(); await renderActiveTab(); },
    }, TAB_LABELS[tab]);
    nav.appendChild(btn);
  });
}

async function renderActiveTab() {
  Array.from(document.querySelectorAll("#drawer-tabs button")).forEach((b, i) => {
    const tabs = { bore: BORE_TABS, river_stream_gauge: GAUGE_TABS, bom_station: BOM_TABS }[state.selected.type];
    b.classList.toggle("active", tabs[i] === state.activeTab);
  });
  const body = document.getElementById("drawer-body");
  body.innerHTML = "";
  showLoading(true);
  try {
    const renderer = TAB_RENDERERS[state.activeTab];
    await renderer(body, state.selected, state.currentDetail);
  } finally { showLoading(false); }
}

const TAB_RENDERERS = {
  overview: renderOverviewTab,
  waterlevel: renderWaterLevelTab,
  waterquality: renderWaterQualityTab,
  rainfall: renderRainfallTab,
  riverflow: renderRiverFlowTab,
  nearby: renderNearbyTab,
  dataquality: renderDataQualityTab,
  aquifer: renderAquiferTab,
};

function overviewFieldLabels(type) {
  if (type === "bore") return {
    name: "Name", status: "Status", purpose: "Purpose", construction: "Construction",
    yield_ls: ["Yield", " L/s"], drilled_depth_m: ["Drilled depth", " m"],
    completion_depth_m: ["Completion depth", " m"], depth_to_water_m: ["Depth to water at drilling", " m"],
    waterlevel_m: ["Recorded water level", " m"], risk_class: "Risk class",
    completion_date: "Completion date", position_accuracy: "Position accuracy",
    monitor_type: "Monitor type", monitor_commence: "Monitoring commenced", monitor_cease: "Monitoring ceased",
  };
  if (type === "river_stream_gauge") return { name: "Name", monitor_type: "Type", commence: "Commenced", cease: "Ceased", active: "Active" };
  return { name: "Name", lat: "Latitude", lon: "Longitude", is_nt: "In the NT", first_date: "First date on file", last_date: "Last date on file", n_days: "Days on file" };
}

function renderOverviewTab(body, { type, id }, detail) {
  const labels = overviewFieldLabels(type);
  const checklist = Object.entries(detail.data_available).map(([k, v]) => {
    const niceKey = k.replace(/_/g, " ");
    return el("div", { class: "checklist-row" }, [
      el("span", { class: v ? "dot-yes" : "dot-no" }, v ? "●" : "○"),
      el("span", {}, niceKey),
    ]);
  });
  body.appendChild(el("h3", {}, "Data available"));
  checklist.forEach((c) => body.appendChild(c));

  body.appendChild(el("h3", {}, "Fields"));
  Object.entries(labels).forEach(([key, label]) => {
    const [text, suffix] = Array.isArray(label) ? label : [label, ""];
    if (!(key in detail.overview)) return;
    body.appendChild(el("div", { class: "field-row" }, [
      el("span", { class: "k" }, text), el("span", { class: "v" }, fmt(detail.overview[key], suffix)),
    ]));
  });
  if (detail.overview.bore_report_url) {
    body.appendChild(el("p", {}, [el("a", { href: detail.overview.bore_report_url, target: "_blank" }, "Bore report ↗")]));
  }
  // GAURAB: rendered as-is from the source shapefile's WATER_DATA field. Some stored
  // URLs use the old water.nt.gov.au domain instead of ntg.aquaticinformatics.net — see
  // webapp/README.md "Known gaps". Rewrite the `portal` value here if fixing that.
  const portal = detail.overview.water_data_portal || detail.overview.monitor_portal_url;
  if (portal && String(portal).startsWith("http")) {
    body.appendChild(el("p", {}, [el("a", { href: portal, target: "_blank" }, "Open in NT Water Data Portal ↗")]));
  }
}

function plotlyDownloadButtons(body, divId, csvRows, filenameBase) {
  const actions = el("div", { class: "chart-actions" });
  actions.appendChild(el("button", { onclick: () => Plotly.downloadImage(divId, { format: "png", filename: filenameBase, width: 1200, height: 600, scale: 2 }) }, "Download PNG"));
  actions.appendChild(el("button", { onclick: () => downloadCSV(`${filenameBase}.csv`, csvRows) }, "Download CSV"));
  body.appendChild(actions);
}

function plotlyTheme() {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  return {
    paper_bgcolor: dark ? "#1e2124" : "#ffffff", plot_bgcolor: dark ? "#1e2124" : "#ffffff",
    font: { color: dark ? "#ecefe9" : "#1c1e1b" },
  };
}

async function renderWaterLevelTab(body, { id }, detail) {
  if (!detail.data_available.water_level) {
    body.appendChild(el("p", { class: "empty-state" },
      detail.data_available.water_level_claimed_but_missing
        ? "Listed as having a water-level series, but it is not in this project's data."
        : "No water-level series for this bore."));
    return;
  }
  const options = detail.water_level_series_available;
  const select = el("select", {}, options.map((o) =>
    el("option", { value: `${o.kind}|||${o.series}` }, `${o.kind} — ${o.series}`)
  ));
  body.appendChild(el("p", { class: "caption" }, "Monthly mean. A gap in the line means no reading that month, not zero."));
  body.appendChild(select);
  const chartDiv = el("div", { id: "wl-chart", class: "chart" });
  body.appendChild(chartDiv);

  async function draw() {
    const [kind, series] = select.value.split("|||");
    const data = await fetchJSON(`/api/water-level/${id}`, { kind, series });
    Plotly.newPlot("wl-chart", [{
      x: data.months, y: data.values, mode: "lines+markers", connectgaps: false,
      line: { color: "#0067a3" }, marker: { size: 4 },
    }], { ...plotlyTheme(), margin: { t: 20, r: 10, l: 50, b: 40 }, yaxis: { title: kind.includes("depth") ? "Depth below ground (m)" : "Water elevation (m AHD)" } },
      { displaylogo: false, responsive: true });
    const rows = data.months.map((m, i) => ({ month: m, value: data.values[i] }));
    body.querySelectorAll(".chart-actions").forEach((n) => n.remove());
    plotlyDownloadButtons(body, "wl-chart", rows, `${id}_waterlevel_${kind}_${series}`);
  }
  select.addEventListener("change", draw);
  await draw();
}

async function renderWaterQualityTab(body, { id }, detail) {
  if (!detail.data_available.water_quality) {
    body.appendChild(el("p", { class: "empty-state" }, "No water-quality samples for this bore."));
    return;
  }
  const summary = detail.water_quality_summary;
  body.appendChild(el("h3", {}, "Latest result per parameter"));
  summary.forEach((row) => {
    body.appendChild(el("div", { class: "field-row" }, [
      el("span", { class: "k" }, row.parameter),
      el("span", { class: "v" }, `${fmt(row.latest)} (n=${row.count}, ${row.first_date}→${row.last_date})`),
    ]));
  });

  const select = el("select", {}, summary.map((row) => el("option", { value: row.parameter }, row.parameter)));
  body.appendChild(el("h3", {}, "Time series"));
  body.appendChild(select);
  const chartDiv = el("div", { id: "wq-chart", class: "chart" });
  body.appendChild(chartDiv);

  async function draw() {
    const param = select.value;
    const data = await fetchJSON(`/api/water-quality/${id}`, { parameter: param });
    Plotly.newPlot("wq-chart", [{
      x: data.dates, y: data.values, mode: "lines+markers", line: { color: "#2f6f4e" },
    }], { ...plotlyTheme(), margin: { t: 20, r: 10, l: 50, b: 40 }, yaxis: { title: param } }, { displaylogo: false, responsive: true });
    const rows = data.dates.map((d, i) => ({ sample_date: d, [param]: data.values[i] }));
    body.querySelectorAll(".chart-actions").forEach((n) => n.remove());
    plotlyDownloadButtons(body, "wq-chart", rows, `${id}_${param}`);
  }
  select.addEventListener("change", draw);
  await draw();
}

async function renderRainfallTab(body, { type, id }, detail) {
  const nearest = detail.rainfall ? detail.rainfall.nearest_station : null;
  const stationId = type === "bom_station" ? id : (nearest && nearest.station);
  if (!stationId) {
    body.appendChild(el("p", { class: "empty-state" }, "No NT rainfall station could be found."));
    return;
  }
  if (type !== "bom_station") {
    body.appendChild(el("div", { class: nearest.far_warning ? "note-box" : "caption" },
      `Nearest NT rainfall station: ${nearest.name} (${stationId}), ${nearest.distance_km} km away.` +
      (nearest.far_warning ? ` This is over ${state.meta.constants.FAR_STATION_WARNING_KM} km — treat this as regional context, not local rainfall.` : "")));
  }
  const data = await fetchJSON(`/api/rainfall/${stationId}`);
  const chartDiv = el("div", { id: "rain-chart", class: "chart" });
  body.appendChild(chartDiv);
  Plotly.newPlot("rain-chart", [
    { x: data.months, y: data.total_mm, type: "bar", name: "Monthly total (mm)", marker: { color: "#0067a3" } },
  ], { ...plotlyTheme(), margin: { t: 20, r: 10, l: 50, b: 40 }, yaxis: { title: "mm" } }, { displaylogo: false, responsive: true });
  body.appendChild(el("p", { class: "caption" }, `A month counts as missing if more than ${data.max_blank_days_rule} days are blank; missing months are left as gaps.`));
  const rows = data.months.map((m, i) => ({ month: m, total_mm: data.total_mm[i], complete: data.complete[i] }));
  plotlyDownloadButtons(body, "rain-chart", rows, `rainfall_${stationId}`);
}

async function renderRiverFlowTab(body, { type, id }, detail) {
  const hasSeries = type === "river_stream_gauge" ? detail.data_available.flow_series
                                                  : (detail.river_flow && detail.river_flow.nearest_gauge && detail.river_flow.nearest_gauge.has_flow_series);
  const nearestGauge = type === "river_stream_gauge" ? { station_id: id, distance_km: 0 } : (detail.river_flow && detail.river_flow.nearest_gauge);
  if (!nearestGauge) { body.appendChild(el("p", { class: "empty-state" }, "No gauge found.")); return; }
  if (type !== "river_stream_gauge") {
    body.appendChild(el("div", { class: nearestGauge.far_warning ? "note-box" : "caption" },
      `Nearest gauge: ${nearestGauge.name || nearestGauge.station_id}, ${nearestGauge.distance_km} km away.`));
  }
  if (!hasSeries) {
    body.appendChild(el("p", { class: "empty-state" }, "No discharge time series for this gauge in this project's data. Only G0280010 has one."));
    return;
  }
  const data = await fetchJSON("/api/flow");
  const quality = data.quality_report;
  if (quality.headline_warning) body.appendChild(el("div", { class: "note-box" }, quality.headline_warning));
  const chartDiv = el("div", { id: "flow-chart", class: "chart" });
  body.appendChild(chartDiv);
  Plotly.newPlot("flow-chart", [
    { x: data.months, y: data.total_ML, type: "bar", name: "Monthly volume (ML)", marker: { color: "#2f6f4e" } },
  ], { ...plotlyTheme(), margin: { t: 20, r: 10, l: 50, b: 40 }, yaxis: { title: "ML/month" } }, { displaylogo: false, responsive: true });
  const rows = data.months.map((m, i) => ({ month: m, total_ML: data.total_ML[i], complete: data.complete[i] }));
  plotlyDownloadButtons(body, "flow-chart", rows, "flow_G0280010");
}

function renderNearbyTab(body, { type, id }, detail) {
  const nb = detail.nearby;
  body.appendChild(el("h3", {}, "Nearest bores"));
  if (nb.bores && nb.bores.length) {
    nb.bores.forEach((b) => {
      body.appendChild(el("div", { class: "field-row" }, [
        el("span", { class: "k" }, [el("a", { href: "#", onclick: (e) => { e.preventDefault(); selectLocation("bore", b.bore_no); } }, b.bore_no)]),
        el("span", { class: "v" }, `${b.distance_km} km`),
      ]));
    });
  } else body.appendChild(el("p", { class: "empty-state" }, "No other bores on file."));

  body.appendChild(el("h3", {}, "Nearest BOM rainfall station"));
  const st = nb.bom_station;
  if (st) {
    body.appendChild(el("div", { class: st.far_warning ? "note-box" : "field-row" },
      `${st.name} (${st.station}) — ${st.distance_km} km${st.far_warning ? " ⚠️" : ""}`));
  }

  body.appendChild(el("h3", {}, "Nearest gauge"));
  const g = nb.gauge;
  if (g) {
    body.appendChild(el("div", { class: g.far_warning ? "note-box" : "field-row" },
      `${g.name || g.station_id} — ${g.distance_km} km${g.has_flow_series ? "" : " (no flow series on file)"}`));
  }
}

function renderDataQualityTab(body, _loc, detail) {
  const notes = detail.data_quality_notes || [];
  if (!notes.length) { body.appendChild(el("p", { class: "empty-state" }, "No specific data-quality flags for this location.")); return; }
  notes.forEach((n) => body.appendChild(el("div", { class: "note-box" }, n)));
}

function renderAquiferTab(body, _loc, detail) {
  const ctx = detail.aquifer_context;
  if (!ctx || !ctx.inside_ti_tree_basin) {
    body.appendChild(el("p", { class: "empty-state" }, "Outside the Ti Tree basin — these regional layers only cover that area."));
    return;
  }
  body.appendChild(el("div", { class: "field-row" }, [el("span", { class: "k" }, "Salinity zone"), el("span", { class: "v" }, fmt(ctx.salinity_zone))]));
  body.appendChild(el("div", { class: "field-row" }, [el("span", { class: "k" }, "Aquifer thickness"), el("span", { class: "v" }, fmt(ctx.aquifer_thickness_m, " m"))]));
  body.appendChild(el("div", { class: "field-row" }, [el("span", { class: "k" }, "Mapped depth to groundwater"), el("span", { class: "v" }, fmt(ctx.mapped_depth_to_groundwater_m, " m"))]));
  body.appendChild(el("div", { class: "field-row" }, [el("span", { class: "k" }, "Nearest groundwater contour"), el("span", { class: "v" }, fmt(ctx.nearest_groundwater_contour_depth_ahd, " m AHD"))]));
  body.appendChild(el("p", { class: "caption" }, "Regional interpretations — may differ from this bore's own result."));
}

/**
 * The one handler for the drawer's close button, whatever state.panelMode currently is.
 * Closing the compare view restores whatever location was selected before it was
 * opened (if any) rather than unconditionally clearing the selection — openCompareView()
 * does not touch state.selected, so it's still there to go back to.
 */
function closeDrawerPanel() {
  if (state.panelMode === "compare") {
    document.getElementById("drawer-add-compare").classList.remove("hidden");
    if (state.selected) {
      state.panelMode = "detail";
      updatePanelEmptyState();
      openDrawer();
      return;
    }
  }
  state.selected = null;
  state.panelMode = "empty";
  updatePanelEmptyState();
  writeURLState();
  renderMarkers();
}
document.getElementById("drawer-close").addEventListener("click", closeDrawerPanel);

// ---------------------------------------------------------------------------
// COMPARE TRAY
// ---------------------------------------------------------------------------

function toggleCompare(boreId) {
  const idx = state.compareIds.indexOf(boreId);
  if (idx >= 0) {
    state.compareIds.splice(idx, 1);
    delete state.compareColours[boreId];
  } else {
    if (state.compareIds.length >= 5) { alert("Up to 5 bores can be compared at once."); return; }
    state.compareIds.push(boreId);
    state.compareColours[boreId] = COMPARE_COLOURS[state.compareIds.length - 1];
  }
  renderCompareTray();
  renderMarkers();
  if (state.selected && state.selected.type === "bore" && state.selected.id === boreId) {
    document.getElementById("drawer-add-compare").textContent = state.compareIds.includes(boreId) ? "✓ In compare tray" : "+ Add to compare tray";
  }
}

function renderCompareTray() {
  const list = document.getElementById("compare-list");
  list.innerHTML = "";
  state.compareIds.forEach((id) => {
    list.appendChild(el("span", { class: "compare-chip", style: `background:${state.compareColours[id]}` }, [
      id, el("button", { onclick: () => toggleCompare(id) }, "✕"),
    ]));
  });
  document.getElementById("compare-count").textContent = `(${state.compareIds.length}/5)`;
  document.getElementById("btn-compare").disabled = state.compareIds.length < 2;
}

async function openCompareView() {
  if (state.compareIds.length < 2) return;
  state.panelMode = "compare";
  updatePanelEmptyState();
  document.getElementById("drawer-title").textContent = "Compare bores";
  document.getElementById("drawer-subtitle").textContent = state.compareIds.join(", ");
  document.getElementById("drawer-add-compare").classList.add("hidden");
  document.getElementById("drawer-tabs").innerHTML = "";
  const body = document.getElementById("drawer-body");
  body.innerHTML = "";

  body.appendChild(el("h3", {}, "Compare: water quality"));
  const paramSelect = el("select", {}, state.meta.measurements.names.map((name, i) =>
    el("option", { value: state.meta.measurements.columns[i] }, name)));
  body.appendChild(paramSelect);
  const wqChart = el("div", { id: "cmp-wq-chart", class: "chart" });
  body.appendChild(wqChart);

  async function drawWQ() {
    showLoading(true);
    try {
      const param = paramSelect.value;
      const traces = [];
      const rowsByDate = {};
      for (const boreId of state.compareIds) {
        const data = await fetchJSON(`/api/water-quality/${boreId}`, { parameter: param });
        traces.push({ x: data.dates, y: data.values, mode: "lines+markers", name: boreId, line: { color: state.compareColours[boreId] } });
      }
      Plotly.newPlot("cmp-wq-chart", traces, { ...plotlyTheme(), margin: { t: 20, r: 10, l: 50, b: 40 }, yaxis: { title: param }, legend: { orientation: "h" } }, { displaylogo: false, responsive: true });
    } finally { showLoading(false); }
  }
  paramSelect.addEventListener("change", drawWQ);
  await drawWQ();

  body.appendChild(el("h3", {}, "Compare: water level (monthly mean, Water Elevation AHD, Publish where available)"));
  const wlChart = el("div", { id: "cmp-wl-chart", class: "chart" });
  body.appendChild(wlChart);
  const traces = [];
  for (const boreId of state.compareIds) {
    try {
      const data = await fetchJSON(`/api/water-level/${boreId}`, { kind: "water_elevation_ahd", series: "publish" });
      traces.push({ x: data.months, y: data.values, mode: "lines+markers", name: boreId, connectgaps: false, line: { color: state.compareColours[boreId] } });
    } catch (e) { /* this bore has no such series — simply not plotted */ }
  }
  if (traces.length) {
    Plotly.newPlot("cmp-wl-chart", traces, { ...plotlyTheme(), margin: { t: 20, r: 10, l: 50, b: 40 }, yaxis: { title: "m AHD" }, legend: { orientation: "h" } }, { displaylogo: false, responsive: true });
  } else {
    wlChart.innerHTML = "<p class='empty-state'>None of the selected bores have a Water Elevation (AHD) Publish series.</p>";
  }

  // GAURAB: a "Download data (CSV)" button for the whole comparison (all selected
  // bores' series together, not just one chart's PNG via the Plotly toolbar) is planned
  // here — see webapp/README.md "Known gaps". Each chart above (#cmp-wq-chart,
  // #cmp-wl-chart) already has its data in `traces`/the per-bore fetch results in this
  // function if you want to build the CSV from what's already loaded rather than
  // re-fetching. closeDrawerPanel() (near the top-level drawer-close listener) is what
  // runs when this view is closed — it already knows to come back here via panelMode.
}

// ---------------------------------------------------------------------------
// CLIMATE VIEW
// ---------------------------------------------------------------------------

// GAURAB: climate_models.py's seasonal_totals_observed/seasonal_totals_model,
// lag_correlations and plot_rain_flow_bores are not wired into any endpoint yet (only
// water_year_totals/anomalies/trailing_mean/change_table are, via /api/climate/anomaly
// and /api/climate/wetter-drier). A natural place for a new "Seasonal / lag" section is
// a new <h3> block appended inside #climate-body below, paired with new
// /api/climate/seasonal and /api/climate/lag endpoints in server.py. See
// webapp/README.md "Known gaps".
async function initClimateView() {
  const locationSelect = document.getElementById("climate-location");
  const runSelect = document.getElementById("climate-run");
  const meta = await fetchJSON("/api/climate/meta");
  if (!meta.available) {
    document.getElementById("climate-body").innerHTML = `<p class="empty-state">${meta.message}</p>`;
    return;
  }
  state.climateMeta = meta;

  async function refreshRuns() {
    const loc = locationSelect.value;
    const runs = meta.locations[loc].usable_runs;
    runSelect.innerHTML = "";
    runs.forEach((r) => runSelect.appendChild(el("option", { value: r }, r)));
    const preferred = runs.indexOf("ACCESS-ESM1-5 r6 (v2105)");
    runSelect.selectedIndex = preferred >= 0 ? preferred : 0;
    await drawAnomaly();
    await drawWetterDrier();
  }

  async function drawAnomaly() {
    const loc = locationSelect.value, run = runSelect.value;
    const data = await fetchJSON("/api/climate/anomaly", { location: loc, run });
    document.getElementById("climate-anomaly-caption").textContent = data.footnote;
    const shapes = [{
      type: "rect", xref: "x", yref: "paper", x0: data.reference_period[0] - 0.5, x1: data.reference_period[1] + 0.5,
      y0: 0, y1: 1, fillcolor: data.reference_shade_color, line: { width: 0 }, layer: "below",
    }];
    Plotly.newPlot("climate-anomaly-chart", [
      { x: data.years, y: data.anomaly_mm, type: "bar", showlegend: false,
        marker: { color: data.anomaly_mm.map((v) => (v >= 0 ? data.wetter_color : data.drier_color)) } },
      { x: data.trailing_mean.years, y: data.trailing_mean.anomaly_mm, mode: "lines",
        name: `${data.trailing_mean_window_years}-year moving mean`, line: { color: data.line_color, width: 1.8 } },
    ], { ...plotlyTheme(), title: data.title, shapes, margin: { t: 50, r: 20, l: 60, b: 40 },
         yaxis: { title: "Difference from reference average (mm)" } }, { displaylogo: false, responsive: true });
    state._anomalyRows = data.years.map((y, i) => ({ water_year: y, anomaly_mm: data.anomaly_mm[i] }));
  }

  async function drawWetterDrier() {
    const loc = locationSelect.value;
    const data = await fetchJSON("/api/climate/wetter-drier", { location: loc });
    document.getElementById("climate-wetter-caption").textContent =
      `${data.models_wetter} of ${data.models_total} models project more rain. ${data.footnote}`;
    Plotly.newPlot("climate-wetter-chart", [
      { x: data.mean_pct, y: data.labels, type: "bar", orientation: "h", showlegend: false,
        marker: { color: data.mean_pct.map((v) => (v >= 0 ? data.wetter_color : data.drier_color)) } },
      { x: data.median_pct, y: data.labels, mode: "markers", name: "Median year",
        marker: { symbol: "line-ns", size: 13, line: { color: data.line_color, width: 2 } } },
    ], { ...plotlyTheme(), title: `Is ${loc} getting wetter or drier?`, margin: { t: 50, r: 20, l: 160, b: 40 },
         xaxis: { title: "Change in average water-year rainfall (%)" } }, { displaylogo: false, responsive: true });
    state._wetterRows = data.labels.map((l, i) => ({ model_run: l, mean_pct: data.mean_pct[i], median_pct: data.median_pct[i] }));
  }

  async function drawResidualMass(stationOrFlow, chartId, isFlow) {
    const data = isFlow ? await fetchJSON("/api/flow") : await fetchJSON(`/api/rainfall/${stationOrFlow}`);
    const yKey = isFlow ? "total_ML" : "total_mm";
    Plotly.newPlot(chartId, [
      { x: data.months, y: data[yKey], type: "bar", name: isFlow ? "Monthly volume (ML)" : "Monthly total (mm)",
        marker: { color: "#8ab0c9" }, yaxis: "y1" },
      { x: data.months, y: data.cumulative_residual_mm ?? data.cumulative_residual_ML, mode: "lines",
        name: "Cumulative residual", line: { color: "#000", width: 2 }, yaxis: "y2" },
    ], { ...plotlyTheme(), margin: { t: 20, r: 50, l: 50, b: 40 },
         yaxis: { title: isFlow ? "ML/month" : "mm/month" }, yaxis2: { overlaying: "y", side: "right", title: "Cumulative residual" },
         legend: { orientation: "h" } }, { displaylogo: false, responsive: true });
  }

  locationSelect.addEventListener("change", refreshRuns);
  runSelect.addEventListener("change", async () => { await drawAnomaly(); });

  document.getElementById("btn-csv-anomaly").addEventListener("click", () => downloadCSV("anomaly.csv", state._anomalyRows));
  document.getElementById("btn-csv-wetter").addEventListener("click", () => downloadCSV("wetter_or_drier.csv", state._wetterRows));
  document.getElementById("btn-csv-rain-residual").addEventListener("click", async () => {
    const data = await fetchJSON("/api/rainfall/015643");
    downloadCSV("rainfall_residual_mass.csv", arraysToRows("month", data.months, { total_mm: data.total_mm, cumulative_residual_mm: data.cumulative_residual_mm }));
  });
  document.getElementById("btn-csv-flow-residual").addEventListener("click", async () => {
    const data = await fetchJSON("/api/flow");
    downloadCSV("flow_residual_mass.csv", arraysToRows("month", data.months, { total_ML: data.total_ML, cumulative_residual_ML: data.cumulative_residual_ML }));
  });
  document.querySelectorAll(".btn-download-png").forEach((btn) => {
    btn.addEventListener("click", () => Plotly.downloadImage(btn.dataset.target, { format: "png", filename: btn.dataset.name, width: 1200, height: 600, scale: 2 }));
  });

  await refreshRuns();
  await drawResidualMass("015643", "climate-rain-residual-chart", false);
  await drawResidualMass(null, "climate-flow-residual-chart", true);
}

// ---------------------------------------------------------------------------
// VIEW SWITCH + ABOUT
// ---------------------------------------------------------------------------

function initViewSwitch() {
  const btnMap = document.getElementById("btn-map-view");
  const btnClimate = document.getElementById("btn-climate-view");
  btnMap.addEventListener("click", () => setView("map"));
  btnClimate.addEventListener("click", () => setView("climate"));
}

let climateLoaded = false;
function setView(view) {
  state.view = view;
  writeURLState();
  document.getElementById("btn-map-view").classList.toggle("active", view === "map");
  document.getElementById("btn-climate-view").classList.toggle("active", view === "climate");
  document.getElementById("map-view").classList.toggle("hidden", view !== "map");
  document.getElementById("climate-view").classList.toggle("hidden", view !== "climate");
  if (view === "climate" && !climateLoaded) {
    climateLoaded = true;
    initClimateView();
  }
  if (view === "map") setTimeout(() => map.invalidateSize(), 50);
}

function initAbout() {
  document.getElementById("btn-about").addEventListener("click", async () => {
    const panel = document.getElementById("about-panel");
    panel.classList.remove("hidden");
    const body = document.getElementById("about-body");
    body.innerHTML = "Loading…";
    const data = await fetchJSON("/api/about");
    body.innerHTML = "";
    body.appendChild(el("h2", {}, "About this explorer"));
    body.appendChild(el("h3", {}, "Data sources"));
    const sourceList = el("ul", {}, data.sources.map((s) => el("li", {}, s)));
    body.appendChild(sourceList);
    body.appendChild(el("h3", {}, "Limitations"));
    body.appendChild(el("ul", {}, data.limitations.map((s) => el("li", {}, s))));
    if (data.citations_markdown) {
      body.appendChild(el("h3", {}, "CMIP6 citations and licences (full text)"));
      body.appendChild(el("pre", { style: "white-space:pre-wrap;font-size:11.5px;" }, data.citations_markdown));
    }
  });
  document.getElementById("about-close").addEventListener("click", () => document.getElementById("about-panel").classList.add("hidden"));
}

// ---------------------------------------------------------------------------
// INIT
// ---------------------------------------------------------------------------

async function init() {
  initTheme();
  initMap();
  initSplitter();
  updatePanelEmptyState();
  initSearch();
  initSidebar();
  initViewSwitch();
  initAbout();

  showLoading(true);
  try {
    state.meta = await fetchJSON("/api/meta");
    const locations = await fetchJSON("/api/locations");
    state.locations = locations;
    populateFilterOptions();
    await updateColourControls();
    updateLegend();
    renderMarkers();
  } finally { showLoading(false); }

  const urlState = readURLState();
  if (urlState.view === "climate") setView("climate");
  if (urlState.tab) state.activeTab = urlState.tab;
  if (urlState.selected) {
    const loc = state.locations.bores.find((b) => b.id === urlState.selected.id)
      || state.locations.gauges.find((g) => g.id === urlState.selected.id)
      || state.locations.bom_stations.find((s) => s.id === urlState.selected.id);
    if (loc) { map.setView([loc.lat, loc.lon], 13); await selectLocation(urlState.selected.type, urlState.selected.id); }
  }
}

document.addEventListener("DOMContentLoaded", init);

})();
