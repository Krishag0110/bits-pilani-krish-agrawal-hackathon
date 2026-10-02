"use strict";

const app = {
  state: null,
  selectedSignalId: null,
  filter: "all",
  busy: false,
  toastTimer: null,
};

const examples = {
  credit: {
    source: "news",
    entity: "Aster Manufacturing",
    text: "Aster Manufacturing missed a bond interest payment and faces a credit downgrade after lenders warned of a possible default.",
  },
  macro: {
    source: "news",
    entity: "Interest rates",
    text: "The central bank raised interest rates by 75 basis points as inflation accelerated, sending bond yields sharply higher.",
  },
  product: {
    source: "social",
    entity: "Solstice Systems",
    text: "Solstice Systems launched a new analytics product and shares rose after customers reported strong early demand.",
  },
};

const el = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]);
const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const money = (value, digits = 1) => Number.isFinite(Number(value))
  ? `$${Number(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}m`
  : "—";
const signedMoney = (value) => Number.isFinite(Number(value))
  ? `${Number(value) > 0 ? "+" : Number(value) < 0 ? "−" : ""}${money(Math.abs(Number(value)), 2)}`
  : "—";
const signedNumber = (value, decimals = 2) => {
  if (!Number.isFinite(Number(value))) return "—";
  const number = Number(value);
  return `${number > 0 ? "+" : number < 0 ? "−" : ""}${Math.abs(number).toFixed(decimals)}`;
};
const sentimentName = (score) => score < -0.15 ? "Negative" : score > 0.15 ? "Positive" : "Neutral";
const sentimentClass = (score) => score < -0.15 ? "negative" : score > 0.15 ? "positive" : "";
const displayTime = (value) => {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
};
const safeUrl = (value) => {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : "";
  } catch { return ""; }
};

async function api(path, payload) {
  const options = payload === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
  const response = await fetch(path, options);
  let body;
  try { body = await response.json(); } catch { throw new Error(`Server returned ${response.status}.`); }
  if (!response.ok) throw new Error(body.error || body.message || `Request failed (${response.status}).`);
  return body;
}

function notify(message, error = false) {
  const toast = el("toast");
  toast.textContent = message;
  toast.className = `toast${error ? " error" : ""}`;
  toast.hidden = false;
  clearTimeout(app.toastTimer);
  app.toastTimer = setTimeout(() => { toast.hidden = true; }, 4900);
}

function setBusy(value) {
  app.busy = value;
  ["refresh-live", "reset-demo", "run-stress"].forEach((id) => { el(id).disabled = value; });
  const submit = document.querySelector("#analyze-form button[type=submit]");
  submit.disabled = value;
}

function signals() {
  const list = app.state?.signals || [];
  return [...list].sort((a, b) => new Date(b.ingested_at || b.published_at || 0) - new Date(a.ingested_at || a.published_at || 0));
}

function currentSignal() {
  const list = signals();
  return list.find((signal) => String(signal.id) === String(app.selectedSignalId)) || list[0] || null;
}

function currentRun() {
  const signal = currentSignal();
  if (!signal) return null;
  const list = app.state?.runs || [];
  return list.find((run) => String(run.signal_id) === String(signal.id)) ||
    (String(app.state?.latest_run?.signal_id) === String(signal.id) ? app.state.latest_run : null);
}

function sourceName(source) { return source === "social" ? "SOCIAL" : "NEWS"; }

function renderMetrics() {
  const state = app.state || {};
  const metrics = state.metrics || {};
  const rows = state.portfolio || [];
  const before = Number.isFinite(Number(metrics.portfolio_value_usd_m))
    ? Number(metrics.portfolio_value_usd_m)
    : rows.reduce((sum, row) => sum + finite(row.market_value_usd_m), 0);
  const latest = state.latest_run;
  const loss = latest ? finite(latest.loss_usd_m, -finite(latest.pnl_usd_m)) : metrics.latest_loss_usd_m;
  el("metric-value").textContent = money(before);
  el("metric-loss").textContent = latest || Number.isFinite(Number(loss)) ? money(loss, 2) : "—";
  el("metric-loss-detail").textContent = latest ? `${finite(latest.loss_pct).toFixed(2)}% of portfolio · latest run` : "Waiting for a scenario";
  el("metric-alerts").textContent = String(metrics.high_impact_signals ?? signals().filter((signal) => finite(signal.impact_score) > 7).length);
  el("metric-signals").textContent = String(metrics.total_signals ?? signals().length);
  const newsCount = signals().filter((signal) => signal.source === "news").length;
  const socialCount = signals().filter((signal) => signal.source === "social").length;
  el("metric-source-split").textContent = `${newsCount} news · ${socialCount} social`;
  el("as-of").textContent = displayTime(metrics.last_updated_at || new Date().toISOString());
}

function renderSources() {
  const status = app.state?.source_status || {};
  el("source-health-list").innerHTML = [
    ["news", "News feed"],
    ["social", "Social posts"],
  ].map(([source, label]) => {
    const item = status[source] || {};
    const state = item.state === "error" ? "error" : item.state === "degraded" ? "degraded" : ["ok", "success", "live"].includes(item.state) ? "ok" : "idle";
    const stateText = state === "error" ? "Error" : state === "degraded" ? (source === "news" ? "Fallback" : "Partial") : item.last_success_at ? "Connected" : "Ready";
    const detail = item.error ? ` title="${escapeHtml(item.error)}"` : "";
    return `<div class="health-row"${detail}><span class="health-dot ${state}"></span>${label}<span class="health-state">${stateText}</span></div>`;
  }).join("");
}

function renderFocus() {
  const signal = currentSignal();
  if (!signal) {
    el("focus-title").textContent = "No signals yet";
    el("focus-text").textContent = "Analyze text below or refresh live feeds.";
    el("focus-explanation").textContent = "—";
    return;
  }
  const score = finite(signal.sentiment_score);
  const impact = clamp(finite(signal.impact_score), 1, 10);
  el("focus-source").textContent = sourceName(signal.source);
  el("focus-source").className = `source-tag${signal.source === "social" ? " social" : ""}`;
  el("focus-provenance").textContent = signal.provenance === "live" ? "LIVE" : signal.provenance === "manual" ? "MANUAL" : "DEMO REPLAY";
  el("focus-provenance").className = `provenance-tag ${signal.provenance || "demo"}`;
  el("focus-time").textContent = displayTime(signal.published_at || signal.ingested_at);
  el("focus-title").textContent = signal.title || signal.text?.slice(0, 140) || "Untitled signal";
  el("focus-text").textContent = signal.text && signal.text !== signal.title ? signal.text : "Source text analyzed by the risk engine.";
  el("focus-sentiment").textContent = signedNumber(score);
  el("focus-sentiment").className = sentimentClass(score);
  el("focus-sentiment-label").textContent = sentimentName(score);
  el("focus-event").textContent = signal.event_classification || "Other";
  el("focus-entity").textContent = signal.entity || "Broad market";
  el("focus-impact").textContent = `${impact.toFixed(0)} / 10`;
  el("focus-explanation").textContent = signal.explanation || "A transparent text model estimated this signal.";
  const evidence = (Array.isArray(signal.evidence) ? signal.evidence : []).slice(0, 5);
  el("focus-evidence").innerHTML = evidence.length ? evidence.map((hit) => `<span>${escapeHtml(typeof hit === "string" ? hit : hit.text || hit.phrase || hit.term || JSON.stringify(hit))}</span>`).join("") : "<span>Text classification</span>";
  const url = safeUrl(signal.url);
  const link = el("focus-link");
  link.hidden = !url;
  link.href = url || "#signals";
  el("focus-model-note").textContent = "Impact is a heuristic estimate";
}

function shockLabels(scenario) {
  const shocks = scenario?.shocks;
  const labels = [];
  const entries = [
    ["rates_bps", "Rates", "bp"],
    ["credit_spreads_bps", "Broad credit", "bp"],
    ["sector_credit_spreads_bps", scenario?.affected_sector ? `${scenario.affected_sector} credit` : "Sector credit", "bp"],
    ["equities_pct", "Equities", "%"],
    ["fx_pct", "FX", "%"],
  ];
  for (const [key, label, unit] of entries) {
    if (!Number.isFinite(Number(shocks?.[key])) || Number(shocks[key]) === 0) continue;
    const value = Number(shocks[key]);
    labels.push(`${label} ${value > 0 ? "+" : "−"}${Math.abs(value).toFixed(Math.abs(value) < 1 ? 1 : 0)}${unit}`);
  }
  if (finite(shocks?.issuer_haircut_pct) > 0) {
    labels.push(`${scenario?.affected_obligor || "Issuer"} haircut ${finite(shocks.issuer_haircut_pct).toFixed(0)}%`);
  }
  return labels;
}

function renderScenario() {
  const signal = currentSignal();
  const run = currentRun();
  const impact = clamp(finite(signal?.impact_score), 0, 10);
  const degrees = impact * 36;
  el("risk-dial").style.background = `conic-gradient(${impact > 7 ? "#f3a666" : "#59dcc5"} 0deg ${degrees}deg, #293e53 ${degrees}deg 360deg)`;
  el("dial-impact").textContent = signal ? String(impact.toFixed(0)) : "—";
  el("scenario-status").textContent = run ? (impact > 7 ? "AUTO-TRIGGERED" : "MANUAL SCENARIO") : "NOT RUN";
  el("scenario-status").className = `scenario-status${run && impact <= 7 ? " manual" : ""}`;
  el("scenario-loss").textContent = run ? money(finite(run.loss_usd_m, -finite(run.pnl_usd_m)), 2) : "—";
  el("scenario-name").textContent = run?.scenario?.name || (signal ? "Stress simulation available for this signal." : "Select a signal to view its scenario.");
  el("before-value").textContent = run ? money(run.before_value_usd_m, 2) : "—";
  el("after-value").textContent = run ? money(run.after_value_usd_m, 2) : "—";
  const before = finite(run?.before_value_usd_m);
  const after = finite(run?.after_value_usd_m);
  el("after-bar").style.width = run && before > 0 ? `${clamp(after / before * 100, 0, 100)}%` : "0%";
  const shocks = shockLabels(run?.scenario);
  el("shock-chips").innerHTML = shocks.length ? shocks.map((value) => `<span>${escapeHtml(value)}</span>`).join("") : "<span>No scenario run yet</span>";
  el("run-stress").disabled = app.busy || !signal;
  el("run-stress").innerHTML = `${run ? "Rerun stress test" : "Run stress test"} <span>↗</span>`;
}

function renderSignalList() {
  let list = signals();
  if (app.filter !== "all") list = list.filter((signal) => signal.source === app.filter);
  el("feed-count").textContent = `${list.length} SIGNAL${list.length === 1 ? "" : "S"}`;
  el("signal-list").innerHTML = list.length ? list.map((signal) => {
    const score = finite(signal.sentiment_score);
    const klass = sentimentClass(score);
    const selected = String(signal.id) === String(currentSignal()?.id);
    return `<button class="signal-row${selected ? " selected" : ""}" type="button" data-signal-id="${escapeHtml(signal.id)}" aria-pressed="${selected}">
      <span class="row-impact">${clamp(finite(signal.impact_score), 1, 10).toFixed(0)}<small>/ 10</small></span>
      <span class="row-content"><strong>${escapeHtml(signal.title || signal.text?.slice(0, 130) || "Untitled signal")}</strong><span class="row-meta"><span class="row-source${signal.source === "social" ? " social" : ""}">${sourceName(signal.source)}</span><span>·</span><span>${escapeHtml(signal.event_classification || "Other")}</span><span>·</span><span>${escapeHtml(displayTime(signal.published_at || signal.ingested_at))}</span></span></span>
      <span class="row-sentiment ${klass}">${signedNumber(score)}</span>
    </button>`;
  }).join("") : `<div class="empty-state">No ${app.filter === "all" ? "" : app.filter + " "}signals available.</div>`;
}

function renderAssetImpact() {
  const run = currentRun();
  const rows = run?.positions || [];
  if (!rows.length) {
    el("asset-impact").innerHTML = `<div class="empty-state">Run a scenario to see loss attribution.</div>`;
    return;
  }
  const groups = new Map();
  for (const row of rows) {
    const key = row.asset_type || "other";
    const group = groups.get(key) || { pnl: 0, count: 0 };
    group.pnl += finite(row.pnl_usd_m);
    group.count += 1;
    groups.set(key, group);
  }
  const sorted = [...groups.entries()].sort((a, b) => a[1].pnl - b[1].pnl);
  const max = Math.max(...sorted.map(([, group]) => Math.abs(group.pnl)), 0.001);
  el("asset-impact").innerHTML = sorted.map(([type, group]) => {
    const gain = group.pnl >= 0;
    const width = clamp(Math.abs(group.pnl) / max * 100, 2, 100);
    return `<div class="asset-group"><div class="asset-group-top"><span>${escapeHtml(type)}s</span><strong class="${gain ? "gain" : ""}">${signedMoney(group.pnl)}</strong></div><div class="asset-bar"><div class="${gain ? "gain" : ""}" style="width:${width.toFixed(1)}%"></div></div><div class="asset-group-caption">${group.count} position${group.count === 1 ? "" : "s"}</div></div>`;
  }).join("");
}

function renderPortfolio() {
  const rows = app.state?.portfolio || [];
  const run = currentRun();
  const outcome = new Map((run?.positions || []).map((position) => [String(position.id), position]));
  el("portfolio-count").textContent = `${rows.length} positions`;
  el("portfolio-body").innerHTML = rows.length ? rows.map((row) => {
    const result = outcome.get(String(row.id));
    const pnl = result ? finite(result.pnl_usd_m) : NaN;
    return `<tr><td>${escapeHtml(row.obligor || row.id)}</td><td><span class="asset-pill ${escapeHtml(row.asset_type)}">${escapeHtml(row.asset_type)}</span></td><td>${escapeHtml(row.sector || "—")}</td><td class="numeric">${money(row.market_value_usd_m, 2)}</td><td class="numeric">${result ? money(result.after_value_usd_m, 2) : "—"}</td><td class="numeric ${Number.isFinite(pnl) ? (pnl < 0 ? "pnl-negative" : "pnl-positive") : ""}">${result ? signedMoney(pnl) : "—"}</td></tr>`;
  }).join("") : `<tr><td colspan="6" class="loading-row">Portfolio data is unavailable.</td></tr>`;
}

function render() {
  renderMetrics();
  renderSources();
  renderFocus();
  renderScenario();
  renderSignalList();
  renderAssetImpact();
  renderPortfolio();
}

function applyState(state, preferredId) {
  app.state = state;
  if (preferredId !== undefined && preferredId !== null) app.selectedSignalId = preferredId;
  if (!signals().some((signal) => String(signal.id) === String(app.selectedSignalId))) app.selectedSignalId = signals()[0]?.id ?? null;
  render();
}

async function loadState() {
  try { applyState(await api("/api/state")); }
  catch (error) { notify(`Could not load the dashboard: ${error.message}`, true); }
}

async function action(path, payload, successMessage, preferredId) {
  if (app.busy) return;
  setBusy(true);
  try {
    const result = await api(path, payload);
    applyState(result.state || await api("/api/state"), preferredId ?? result.signal?.id);
    notify(typeof successMessage === "function" ? successMessage(result) : successMessage);
    return result;
  } catch (error) {
    notify(error.message, true);
    return null;
  } finally { setBusy(false); }
}

document.addEventListener("DOMContentLoaded", () => {
  loadState();
  el("refresh-live").addEventListener("click", () => action("/api/refresh", { limit: 8 }, (result) => {
    const count = result.added?.length || 0;
    const sourceItems = Object.entries(result.source_status || result.state?.source_status || {});
    const failures = sourceItems.filter(([, item]) => item.state === "error").map(([source]) => source);
    const degraded = sourceItems.filter(([, item]) => item.state === "degraded").map(([source]) => source === "news" ? "news used RSS fallback" : "social feed was partial");
    if (count) return `${count} new live signal${count === 1 ? "" : "s"} added${degraded.length ? `; ${degraded.join(" and ")}` : ""}${failures.length ? `; ${failures.join(" and ")} unavailable` : ""}.`;
    return failures.length ? `No new items. ${failures.join(" and ")} source unavailable; demo data remains ready.` : "Live feeds checked; no new items found.";
  }));
  el("reset-demo").addEventListener("click", async () => {
    const result = await action("/api/demo/reset", {}, "Reproducible demo restored.");
    if (result) { app.selectedSignalId = null; applyState(result.state); }
  });
  el("run-stress").addEventListener("click", () => {
    const signal = currentSignal();
    if (signal) action("/api/stress", { signal_id: signal.id }, "Stress test complete.", signal.id);
  });
  el("signal-list").addEventListener("click", (event) => {
    const row = event.target.closest("[data-signal-id]");
    if (!row) return;
    app.selectedSignalId = row.dataset.signalId;
    render();
    document.getElementById("stress").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => {
    app.filter = button.dataset.filter;
    document.querySelectorAll(".filter").forEach((other) => other.classList.toggle("active", other === button));
    renderSignalList();
  }));
  document.querySelectorAll(".example").forEach((button) => button.addEventListener("click", () => {
    const example = examples[button.dataset.example];
    if (!example) return;
    el("input-text").value = example.text;
    el("input-entity").value = example.entity;
    const radio = document.querySelector(`input[name=source][value=${example.source}]`);
    if (radio) radio.checked = true;
    el("input-text").focus();
  }));
  el("analyze-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = el("input-text").value.trim();
    const entity = el("input-entity").value.trim();
    const source = document.querySelector("input[name=source]:checked")?.value || "news";
    if (text.length < 12) return notify("Enter at least 12 characters of source text.", true);
    const result = await action("/api/analyze", { source, text, entity }, "New signal generated.");
    if (result) {
      el("input-text").value = "";
      el("input-entity").value = "";
      document.getElementById("stress").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  document.querySelectorAll(".nav-link").forEach((link) => link.addEventListener("click", () => {
    document.querySelectorAll(".nav-link").forEach((item) => item.classList.toggle("active", item === link));
  }));
  setInterval(() => { if (!app.busy) loadState(); }, 30000);
});
