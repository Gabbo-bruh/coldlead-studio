// ColdLead Studio dashboard — vanilla JS, no build step, works offline.
// All scoring happens server-side through the same pure Python engine used by the CLI and MCP.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ---------------------------------------------------------------- safe templating
// `html` escapes every interpolated value unless it is itself an `html` fragment.
// Lead data comes from the open web, so nothing is ever inserted unescaped.
class SafeHTML { constructor(value) { this.value = value; } }
const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const escapeText = (value) => String(value).replace(/[&<>"']/g, (c) => ESCAPES[c]);
function toMarkup(value) {
  if (value instanceof SafeHTML) return value.value;
  if (Array.isArray(value)) return value.map(toMarkup).join("");
  if (value === null || value === undefined || value === false) return "";
  return escapeText(value);
}
const html = (strings, ...values) =>
  new SafeHTML(strings.reduce((out, str, i) => out + str + (i < values.length ? toMarkup(values[i]) : ""), ""));
function mount(el, fragment) {
  const range = document.createRange();
  range.selectNodeContents(el); // parse in the element's context (HTML or SVG)
  el.replaceChildren(range.createContextualFragment(toMarkup(fragment)));
}

const STORE_KEY = "coldlead.ui.v1";
const state = {
  meta: null,
  sessionId: null,
  preset: null,
  weights: {},
  season: null,
  thresholds: {},
  lockin: false,
  data: null,
  kit: { lead: null, tab: "loom_script_90s", lang: "it", content: null },
  pin: null, // { lat, lon, radius } when searching around a map pin
};

// ---------------------------------------------------------------- utilities
const storage = {
  load() { try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch { return {}; } },
  save(patch) { try { localStorage.setItem(STORE_KEY, JSON.stringify({ ...storage.load(), ...patch })); } catch { /* private mode */ } },
};

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try { const j = await res.json(); message = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* not json */ }
    throw new Error(message);
  }
  return res;
}

let toastTimer;
function toast(message, error = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", error);
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), error ? 5200 : 2400);
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

const STOPS = [[0, [43, 89, 195]], [40, [31, 181, 201]], [65, [233, 196, 106]], [82, [244, 132, 95]], [100, [230, 57, 70]]];
function thermal(score) {
  const s = Math.max(0, Math.min(100, score));
  for (let i = 1; i < STOPS.length; i++) {
    const [p1, c1] = STOPS[i]; const [p0, c0] = STOPS[i - 1];
    if (s <= p1) {
      const t = (s - p0) / (p1 - p0);
      return `rgb(${c0.map((v, k) => Math.round(v + (c1[k] - v) * t)).join(",")})`;
    }
  }
  return "rgb(230,57,70)";
}

const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

function tween(el, from, to, ms = 450) {
  if (from === to || reducedMotion()) { el.textContent = to.toFixed(1); return; }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / ms);
    el.textContent = (from + (to - from) * (1 - Math.pow(1 - t, 3))).toFixed(1);
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ---------------------------------------------------------------- controls
function presetDefaults(name) {
  const p = state.meta.presets[name];
  return { weights: { ...p.weights }, thresholds: { ...p.thresholds } };
}

function renderPresets() {
  const box = $("#presets");
  mount(box, Object.entries(state.meta.presets).map(([key, p]) => html`
    <button type="button" class="preset" role="radio" data-preset="${key}" aria-checked="${key === state.preset}"
      title="${p.description || ""}">${p.name || key}<small>${key}</small></button>`));
  $$(".preset", box).forEach((btn) => btn.addEventListener("click", () => selectPreset(btn.dataset.preset)));
}

function markPresetState() {
  const base = state.meta.presets[state.preset]?.weights || {};
  const tweaked = Object.keys(base).some((k) => Math.abs(base[k] - state.weights[k]) > 1e-9);
  $$(".preset").forEach((b) => {
    const active = b.dataset.preset === state.preset;
    b.setAttribute("aria-checked", String(active));
    b.classList.toggle("custom-active", active && tweaked);
  });
}

const weightShare = (w) => {
  const total = Object.values(state.weights).reduce((a, b) => a + b, 0) || 1;
  return Math.round((w / total) * 100);
};

function renderSliders() {
  mount($("#sliders"), state.meta.variables.map((v) => {
    const w = state.weights[v.weight_key] ?? 0;
    return html`<div class="slider" title="${v.description}">
      <label for="w-${v.weight_key}"><b>${v.key}</b>${v.short}</label>
      <output id="o-${v.weight_key}">${w.toFixed(1)} <small>${weightShare(w)}%</small></output>
      <input type="range" id="w-${v.weight_key}" data-key="${v.weight_key}" min="0" max="10" step="0.5" value="${w}"
        style="--fill:${w * 10}%" aria-label="${v.name} weight">
    </div>`;
  }));
  $$("#sliders input").forEach((input) => input.addEventListener("input", () => {
    state.weights[input.dataset.key] = Number(input.value);
    input.style.setProperty("--fill", `${Number(input.value) * 10}%`);
    updateSliderOutputs();
    markPresetState();
    rescoreSoon();
  }));
}

function updateSliderOutputs() {
  state.meta.variables.forEach((v) => {
    const w = state.weights[v.weight_key];
    mount($(`#o-${v.weight_key}`), html`${w.toFixed(1)} <small>${weightShare(w)}%</small>`);
  });
}

function syncControls() {
  renderSliders();
  markPresetState();
  $("#season").value = state.season;
  $("#t1").value = state.thresholds.tier_1_min;
  $("#t2").value = state.thresholds.tier_2_min;
  $("#lockin").checked = state.lockin;
}

function selectPreset(name) {
  state.preset = name;
  Object.assign(state, presetDefaults(name));
  syncControls();
  rescore();
}

async function loadSessions(selectId) {
  const sessions = await (await api("/api/sessions")).json();
  const select = $("#session-select");
  mount(select, sessions.map((s) =>
    html`<option value="${s.id}">${s.niche} · ${s.location} — ${s.lead_count} (${s.source})</option>`));
  $("#delete-session").disabled = !sessions.length;
  if (!sessions.length) { state.sessionId = null; showEmpty(true); return false; }
  const wanted = selectId && sessions.some((s) => s.id === selectId) ? selectId : sessions[0].id;
  select.value = wanted;
  state.sessionId = wanted;
  showEmpty(false);
  return true;
}

function showEmpty(empty) {
  $("#empty").hidden = !empty;
  $(".thermo").hidden = empty;
  $("#readouts").hidden = empty;
  if (empty) {
    $("#leads").replaceChildren();
    $("#notices").replaceChildren();
    $("#markers").replaceChildren();
    $("#session-meta").textContent = "no session";
    mount($("#session-title"), html`Scrape once. <em>Re-score forever.</em>`);
  }
}

// ---------------------------------------------------------------- scoring
let inflight = 0;
async function rescore() {
  if (!state.sessionId) return;
  storage.save({ preset: state.preset, weights: state.weights, season: state.season, thresholds: state.thresholds, lockin: state.lockin });
  const ticket = ++inflight;
  const t0 = performance.now();
  try {
    const res = await api("/api/score", {
      method: "POST",
      body: {
        session_id: state.sessionId, preset: state.preset, weights: state.weights, season: state.season,
        thresholds: state.thresholds, discard_on_lockin: state.lockin,
      },
    });
    const data = await res.json();
    if (ticket !== inflight) return; // a newer request superseded this one
    state.data = data;
    render(data);
    $("#latency").textContent = `engine ${data.elapsed_ms.toFixed(1)} ms · round-trip ${Math.round(performance.now() - t0)} ms`;
  } catch (err) {
    toast(err.message, true);
  }
}
const rescoreSoon = debounce(rescore, 90);

function chipsFor(s) {
  const chips = [];
  if (!s.has_website) chips.push(["no website", "bad"]);
  else {
    const perf = s.lighthouse_performance;
    if (perf != null) chips.push([`perf ${perf}${s.performance_source === "estimated" ? "~" : ""}`, perf < 50 ? "bad" : perf < 80 ? "warn" : "good"]);
    if (s.mobile_friendly === false) chips.push(["not mobile", "bad"]);
    if (s.has_ssl === false) chips.push(["no https", "bad"]);
    if (s.cms_stack) chips.push([s.cms_stack, ""]);
    if (s.has_multilingual === false) chips.push(["single-language", "warn"]);
    if (s.has_booking_system === false) chips.push(["no booking", "warn"]);
    if (s.has_pdf_menu) chips.push(["pdf menu", "warn"]);
  }
  if (s.is_running_ads) chips.push(["running ads", "good"]);
  if (s.average_rating) chips.push([`${s.average_rating}★ · ${s.reviews_count ?? 0}`, ""]);
  return chips.map(([label, cls]) => html`<span class="chip ${cls}">${label}</span>`);
}

const TIER_LABEL = { hot: "hot", warm: "warm", cold: "low", red_flag: "red flag" };
const CIRCUMFERENCE = 2 * Math.PI * 28;

function cardMarkup(d) {
  const ev = d.pos_evaluation;
  const c = d.company;
  const offset = CIRCUMFERENCE * (1 - ev.final_score / 100);
  const bars = state.meta.variables.map((v) => {
    const val = ev.variables[v.key];
    return html`<div class="bar" title="${v.name}: ${val}"><i style="height:${Math.max(3, val * 4.4)}px"></i><span>${v.key[0]}</span></div>`;
  });
  const flags = ev.discard_reasons.map((f) =>
    html`<div class="flag ${f.severity === "MEDIUM" ? "medium" : ""}">⚠ ${f.code} — ${f.description}</div>`);
  return html`
    <div class="rank">${String(d.rank).padStart(2, "0")}</div>
    <div class="dial" aria-label="POS ${ev.final_score}">
      <svg viewBox="0 0 64 64"><circle class="track" cx="32" cy="32" r="28" fill="none" stroke-width="5"/>
        <circle class="arc" cx="32" cy="32" r="28" fill="none" stroke-width="5" stroke-linecap="round"
          stroke="${thermal(ev.final_score)}" stroke-dasharray="${CIRCUMFERENCE.toFixed(2)}" stroke-dashoffset="${offset.toFixed(2)}"/></svg>
      <div class="score"><span class="num">${ev.final_score.toFixed(1)}</span></div>
    </div>
    <div class="body">
      <div class="head"><h3>${c.name}</h3><span class="tier">${TIER_LABEL[ev.tier_code]}</span></div>
      <p class="meta mono">${c.city} · ${c.niche} · ${d.source}${c.phone ? ` · ${c.phone}` : ""}</p>
      <div class="chips">${chipsFor(d.raw_signals)}</div>
      <p class="opp">${d.enrichment.vibe_opportunity_summary || "—"}</p>
      ${flags.length ? html`<div class="flags">${flags}</div>` : ""}
    </div>
    <div class="bars" aria-hidden="true">${bars}</div>
    <div class="actions">
      <button class="chip-btn" data-action="explain">🕸 Radar</button>
      <button class="chip-btn" data-action="kit">🚀 Action Kit</button>
    </div>`;
}

function render(data) {
  const { session, counts, leads, config } = data;
  $("#session-meta").textContent = `${session.source} · ${session.id} · preset ${config.preset} · season ${config.season}`;
  mount($("#session-title"), html`${session.niche} <em>in ${session.location}</em>`);
  for (const key of ["total", "hot", "warm", "cold", "red_flag"]) $(`#c-${key}`).textContent = counts[key];
  mount($("#notices"), (session.notices || []).map((n) => html`<div class="notice">ℹ ${n}</div>`));

  // thermal scale: one tick per lead, sliding as scores change
  $("#th-warm").style.left = `${config.thresholds.tier_2_min}%`;
  $("#th-hot").style.left = `${config.thresholds.tier_1_min}%`;
  const markers = $("#markers");
  const staleMarkers = new Map($$(".marker", markers).map((m) => [m.dataset.id, m]));
  for (const d of leads) {
    let m = staleMarkers.get(d.id);
    if (!m) { m = document.createElement("div"); m.className = "marker"; m.dataset.id = d.id; markers.appendChild(m); }
    staleMarkers.delete(d.id);
    m.style.left = `${d.pos_evaluation.final_score}%`;
    m.classList.toggle("flagged", d.pos_evaluation.is_discarded);
    m.title = `${d.company.name} — ${d.pos_evaluation.final_score}`;
  }
  staleMarkers.forEach((m) => m.remove());

  // cards: update in place, then reorder with a FLIP animation
  const list = $("#leads");
  const before = new Map($$(".lead", list).map((el) => [el.dataset.id, el.getBoundingClientRect().top]));
  const existing = new Map($$(".lead", list).map((el) => [el.dataset.id, el]));
  const ordered = leads.map((d, index) => {
    let el = existing.get(d.id);
    const oldScore = el ? Number(el.dataset.score) : null;
    if (!el) {
      el = document.createElement("article");
      el.className = "lead enter";
      el.dataset.id = d.id;
      el.style.setProperty("--i", index);
      el.addEventListener("animationend", () => el.classList.remove("enter"), { once: true });
    }
    existing.delete(d.id);
    el.dataset.tier = d.pos_evaluation.tier_code;
    el.dataset.score = d.pos_evaluation.final_score;
    mount(el, cardMarkup(d));
    if (oldScore !== null) tween($(".num", el), oldScore, d.pos_evaluation.final_score);
    return el;
  });
  existing.forEach((el) => el.remove());
  // Only touch the DOM order when it actually changed (moving nodes is what the FLIP animates).
  ordered.forEach((el, i) => { if (list.children[i] !== el) list.insertBefore(el, list.children[i] || null); });
  if (reducedMotion()) return;
  for (const el of ordered) {
    const prev = before.get(el.dataset.id);
    if (prev === undefined) continue;
    const delta = prev - el.getBoundingClientRect().top;
    if (Math.abs(delta) < 1) continue;
    el.animate([{ transform: `translateY(${delta}px)` }, { transform: "none" }],
      { duration: 480, easing: "cubic-bezier(.2,.8,.2,1)" });
  }
}

// ---------------------------------------------------------------- explain / radar
const findLead = (id) => state.data.leads.find((d) => d.id === id);

function radarMarkup(ev) {
  const R = 118;
  const vars = state.meta.variables;
  const n = vars.length;
  const angle = (i) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const point = (i, value) => [Math.cos(angle(i)) * R * (value / 10), Math.sin(angle(i)) * R * (value / 10)];
  const poly = (values) => values.map((v, i) => point(i, v).map((x) => x.toFixed(1)).join(",")).join(" ");
  const rings = [2, 4, 6, 8, 10].map((r) => html`<polygon class="radar-grid" points="${poly(Array(n).fill(r))}"/>`);
  const axes = vars.map((_, i) => { const [x, y] = point(i, 10); return html`<line class="radar-axis" x1="0" y1="0" x2="${x}" y2="${y}"/>`; });
  const maxW = Math.max(...Object.values(ev.weights_applied), 0.0001);
  const weightPoly = poly(vars.map((v) => (ev.weights_applied[v.weight_key] / maxW) * 10));
  const leadValues = vars.map((v) => ev.variables[v.key]);
  const dots = leadValues.map((v, i) => { const [x, y] = point(i, v); return html`<circle class="radar-dot" cx="${x}" cy="${y}" r="3"/>`; });
  const labels = vars.map((v, i) => {
    const [x, y] = point(i, 12.2);
    const anchor = Math.abs(x) < 8 ? "middle" : x > 0 ? "start" : "end";
    return html`<text class="radar-label" x="${x}" y="${y}" text-anchor="${anchor}" dominant-baseline="middle">${v.key} <tspan class="v">${ev.variables[v.key].toFixed(1)}</tspan></text>`;
  });
  const grow = reducedMotion() ? "" : html`<animate attributeName="points" dur=".5s" from="${poly(Array(n).fill(0))}" to="${poly(leadValues)}" fill="freeze"/>`;
  return html`${rings}${axes}<polygon class="radar-weight" points="${weightPoly}"/>
    <polygon class="radar-lead" points="${poly(leadValues)}">${grow}</polygon>${dots}${labels}`;
}

function openExplain(id) {
  const d = findLead(id);
  const ev = d.pos_evaluation;
  $("#explain-eyebrow").textContent = `#${d.rank} · ${ev.tier} · ${d.id}`;
  $("#explain-title").textContent = d.company.name;
  mount($("#radar"), radarMarkup(ev));
  mount($("#explain-list"), state.meta.variables.map((v) => {
    const val = ev.variables[v.key];
    const w = ev.weights_applied[v.weight_key];
    return html`<div class="ev">
      <div class="ev-name"><b>${v.key}</b><small>${v.short}</small></div>
      <div class="ev-val"><span class="track"><i style="width:${val * 10}%"></i></span>${val.toFixed(1)} <small>× w ${w} = ${(val * w).toFixed(1)}</small></div>
      <ul>${(ev.explanations[v.key] || []).map((r) => html`<li>${r}</li>`)}</ul>
    </div>`;
  }));
  const m = ev.multipliers_applied;
  mount($("#explain-formula"), html`Σ(w·V)/Σw × 10 = <b>${ev.raw_score.toFixed(1)}</b> × ads ${m.m_ads} × friction ${m.m_friction} × season ${m.t_win} × lock-in ${m.m_lockin} = ${ev.uncapped_score.toFixed(2)} → <b>POS ${ev.final_score.toFixed(1)}</b>`);
  mount($("#explain-flags"), html`${ev.discard_reasons.map((f) =>
    html`<p class="flag ${f.severity === "MEDIUM" ? "medium" : ""}">⚠ ${f.code} [${f.severity}] ${f.description} — ${f.evidence}</p>`)}
    <p class="opp">${ev.recommendation}</p>`);
  $("#explain-modal").showModal();
}

// ---------------------------------------------------------------- action kit
async function loadKit(ai = false) {
  const { lead, lang } = state.kit;
  $("#kit-text").textContent = ai ? "Polishing with AI…" : "Generating…";
  try {
    const res = await api(`/api/kit/${encodeURIComponent(state.sessionId)}/${encodeURIComponent(lead)}?lang=${lang}&ai=${ai}`);
    state.kit.content = await res.json();
    $("#kit-opp").textContent = state.kit.content.vibe_opportunity_summary;
    renderKitTab();
  } catch (err) {
    $("#kit-text").textContent = err.message;
  }
}

function renderKitTab() {
  const k = state.kit.content;
  if (!k) return;
  const tab = state.kit.tab;
  $$(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  $$(".lang button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === state.kit.lang)));
  $("#kit-text").textContent = tab === "cold_email" ? `Subject: ${k.cold_email_subject}\n\n${k.cold_email}` : k[tab];
  const count = tab === "whatsapp_opener" ? `${k.whatsapp_opener.length}/300 characters · ` : "";
  $("#kit-meta").textContent = `${count}${k.language.toUpperCase()} · generated by ${k.generated_by}`;
}

function openKit(id) {
  const d = findLead(id);
  state.kit = { ...state.kit, lead: id, tab: "loom_script_90s", content: null };
  $("#kit-title").textContent = d.company.name;
  $("#kit-opp").textContent = "";
  $("#kit-ai").hidden = !state.meta.llm;
  $("#kit-modal").showModal();
  loadKit();
}

async function copyKit() {
  const text = $("#kit-text").textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const range = document.createRange();
    range.selectNodeContents($("#kit-text"));
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range);
    document.execCommand("copy");
    sel.removeAllRanges();
  }
  toast("Copied to clipboard");
}

// ---------------------------------------------------------------- map pin
// Leaflet is vendored (static/vendor/leaflet); tiles come from openstreetmap.org, so the map
// itself needs a connection — everything else in the dashboard keeps working offline.
const mapState = { map: null, marker: null, circle: null, draft: null, radius: 5 };

function pinIcon() {
  return L.divIcon({ className: "pin-icon", html: "<span></span>", iconSize: [26, 26], iconAnchor: [13, 28] });
}

function updatePinCoords() {
  const d = mapState.draft;
  $("#pin-coords").textContent = d
    ? `📍 ${d.lat.toFixed(5)}, ${d.lon.toFixed(5)} · radius ${mapState.radius} km`
    : "no pin yet — click the map";
  $("#pin-use").disabled = !d;
}

function placePin(lat, lon, fit = false) {
  const m = mapState;
  m.draft = { lat, lon };
  if (!m.marker) {
    m.marker = L.marker([lat, lon], { draggable: true, icon: pinIcon(), keyboard: true }).addTo(m.map);
    m.circle = L.circle([lat, lon], {
      radius: m.radius * 1000, color: "#f4845f", weight: 1.5, fillColor: "#f4845f", fillOpacity: 0.12,
    }).addTo(m.map);
    m.marker.on("drag", (e) => {
      const p = e.target.getLatLng();
      m.draft = { lat: p.lat, lon: p.lng };
      m.circle.setLatLng(p);
      updatePinCoords();
    });
  } else {
    m.marker.setLatLng([lat, lon]);
    m.circle.setLatLng([lat, lon]);
  }
  if (fit) m.map.fitBounds(m.circle.getBounds(), { padding: [30, 30] });
  updatePinCoords();
}

function ensureMap() {
  if (mapState.map) return;
  if (typeof L === "undefined") throw new Error("Map library failed to load");
  const map = L.map("map", { zoomControl: true, worldCopyJump: true }).setView([42.6, 12.5], 6);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  map.on("click", (e) => placePin(e.latlng.lat, e.latlng.lng));
  mapState.map = map;
}

async function goToPlace(query, dropPin) {
  if (!query.trim()) return;
  try {
    const place = await (await api(`/api/geocode?q=${encodeURIComponent(query)}`)).json();
    mapState.map.setView([place.lat, place.lon], 13);
    if (dropPin) placePin(place.lat, place.lon, true);
    $("#map-q").value = place.name;
  } catch (err) {
    toast(err.message, true);
  }
}

async function openMap() {
  try {
    ensureMap();
  } catch (err) {
    toast(err.message, true);
    return;
  }
  $("#map-modal").showModal();
  setTimeout(() => mapState.map.invalidateSize(), 60); // the map was hidden while sized
  if (state.pin) {
    mapState.radius = state.pin.radius;
    $("#radius").value = state.pin.radius;
    $("#radius-out").textContent = `${state.pin.radius} km`;
    if (mapState.circle) mapState.circle.setRadius(state.pin.radius * 1000);
    setTimeout(() => placePin(state.pin.lat, state.pin.lon, true), 80);
  } else {
    const typed = $('#scout-form [name="location"]').value;
    if (typed && !mapState.draft) setTimeout(() => goToPlace(typed, false), 80);
  }
  updatePinCoords();
}

function setPin(pin) {
  state.pin = pin;
  const location = $('#scout-form [name="location"]');
  $("#pin-chip").hidden = !pin;
  $("#pin-btn").textContent = pin ? "📍 Move pin" : "📍 Pin on map";
  location.required = !pin;
  location.placeholder = pin ? "optional — searching around the pin" : "Portofino";
  if (pin) $("#pin-text").textContent = `📍 ${pin.lat.toFixed(4)}, ${pin.lon.toFixed(4)} · ${pin.radius} km`;
}

// ---------------------------------------------------------------- actions
async function runScout(payload, button) {
  button.classList.add("busy");
  try {
    const res = await api("/api/scout", { method: "POST", body: payload });
    const data = await res.json();
    await loadSessions(data.session.id);
    await rescore();
    if (data.session.source === "demo" && payload.source !== "demo") {
      toast("No live source reachable: showing DEMO data (fictitious businesses)", true);
    } else {
      toast(`${data.session.lead_count} leads collected from ${data.session.source}`);
    }
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.classList.remove("busy");
  }
}

async function exportAs(format) {
  if (!state.sessionId) return;
  try {
    const res = await api("/api/export", {
      method: "POST",
      body: { session_id: state.sessionId, preset: state.preset, weights: state.weights, season: state.season,
              thresholds: state.thresholds, discard_on_lockin: state.lockin, format, with_kits: format === "markdown" },
    });
    const blob = await res.blob();
    const name = (res.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || `coldlead.${format}`;
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast(`Exported ${name}`);
  } catch (err) {
    toast(err.message, true);
  }
}

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

function wire() {
  $("#scout-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const payload = { niche: f.get("niche"), location: f.get("location").trim(), limit: Number(f.get("limit")) || 10,
                      source: f.get("source"), lang: state.meta.language, expand: f.get("expand") === "on" };
    if (state.pin) Object.assign(payload, { lat: state.pin.lat, lon: state.pin.lon, radius_km: state.pin.radius });
    runScout(payload, $("#scout-form .btn"));
  });
  $("#demo-btn").addEventListener("click", (e) =>
    runScout({ niche: "Charter nautico", location: "Portofino", limit: 12, source: "demo" }, e.currentTarget));
  $("#session-select").addEventListener("change", (e) => { state.sessionId = e.target.value; rescore(); });
  $("#delete-session").addEventListener("click", async () => {
    if (!state.sessionId || !confirm("Delete this cached session? Its raw signals will be lost.")) return;
    await api(`/api/sessions/${encodeURIComponent(state.sessionId)}`, { method: "DELETE" });
    if (await loadSessions()) rescore();
  });
  $("#reset").addEventListener("click", () => selectPreset(state.preset));
  $("#season").addEventListener("change", (e) => { state.season = e.target.value; rescore(); });
  for (const [id, key] of [["#t1", "tier_1_min"], ["#t2", "tier_2_min"]]) {
    $(id).addEventListener("input", (e) => {
      const v = Number(e.target.value);
      if (e.target.value !== "" && Number.isFinite(v) && v >= 0 && v <= 100) { state.thresholds[key] = v; rescoreSoon(); }
    });
  }
  $("#lockin").addEventListener("change", (e) => { state.lockin = e.target.checked; rescore(); });
  $$(".exports button").forEach((b) => b.addEventListener("click", () => exportAs(b.dataset.format)));

  $("#leads").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const id = btn.closest(".lead").dataset.id;
    if (btn.dataset.action === "explain") openExplain(id); else openKit(id);
  });
  $("#leads").addEventListener("mouseover", (e) => {
    const card = e.target.closest(".lead");
    $$(".marker").forEach((m) => m.classList.toggle("hl", !!card && m.dataset.id === card.dataset.id));
  });
  $("#leads").addEventListener("mouseleave", () => $$(".marker").forEach((m) => m.classList.remove("hl")));

  $$(".tabs button").forEach((b) => b.addEventListener("click", () => { state.kit.tab = b.dataset.tab; renderKitTab(); }));
  $$(".lang button").forEach((b) => b.addEventListener("click", () => { state.kit.lang = b.dataset.lang; loadKit(); }));
  $("#kit-ai").addEventListener("click", () => loadKit(true));
  $("#kit-copy").addEventListener("click", copyKit);
  for (const dialog of $$("dialog")) {
    dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  }

  $("#pin-btn").addEventListener("click", openMap);
  $("#pin-clear").addEventListener("click", () => setPin(null));
  $("#pin-use").addEventListener("click", () => {
    const d = mapState.draft;
    if (!d) return;
    setPin({ lat: d.lat, lon: d.lon, radius: mapState.radius });
    $("#map-modal").close();
  });
  $("#radius").addEventListener("input", (e) => {
    mapState.radius = Number(e.target.value);
    $("#radius-out").textContent = `${mapState.radius} km`;
    if (mapState.circle) mapState.circle.setRadius(mapState.radius * 1000);
    updatePinCoords();
  });
  $("#radius").addEventListener("change", () => {
    if (mapState.circle) mapState.map.fitBounds(mapState.circle.getBounds(), { padding: [30, 30] });
  });
  $("#map-search").addEventListener("submit", (e) => {
    e.preventDefault();
    goToPlace($("#map-q").value, true);
  });

  $("#theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.dataset.theme
      || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    const next = current === "light" ? "dark" : "light";
    applyTheme(next);
    storage.save({ theme: next });
  });
}

async function init() {
  const saved = storage.load();
  applyTheme(saved.theme);
  wire();
  try {
    state.meta = await (await api("/api/meta")).json();
  } catch (err) {
    toast(`Cannot reach the ColdLead server: ${err.message}`, true);
    return;
  }
  const m = state.meta;
  $("#version").textContent = `v${m.version}`;
  mount($("#season"), m.seasons.map((s) => html`<option value="${s}">${s.replace("_", " ")}</option>`));
  $("#source-hint").textContent = m.live_discovery === "google"
    ? "auto → Google Places (key found) → demo fallback"
    : "auto → OpenStreetMap (free) → demo fallback. Add GOOGLE_PLACES_API_KEY for Google data.";
  state.kit.lang = m.language === "en" ? "en" : "it";

  const presetOk = saved.preset && m.presets[saved.preset];
  state.preset = presetOk ? saved.preset : m.default.preset;
  const defaults = presetDefaults(state.preset);
  state.weights = presetOk && saved.weights ? { ...defaults.weights, ...saved.weights } : { ...m.default.weights };
  state.thresholds = presetOk && saved.thresholds ? saved.thresholds : { ...m.default.thresholds };
  state.season = saved.season && m.seasons.includes(saved.season) ? saved.season : "auto";
  state.lockin = Boolean(saved.lockin);
  renderPresets();
  syncControls();
  if (await loadSessions()) await rescore();
}

init();
