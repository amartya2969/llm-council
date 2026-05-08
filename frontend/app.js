const state = {
  models: {},
  activeModels: new Set(["claude-haiku-4-5", "claude-sonnet-4-6"]),
  chairmanModel: "claude-opus-4-7",
  lastResult: null,
};

const API = "http://localhost:8000";

// ── Boot ──────────────────────────────────────────────────────────────────────

async function boot() {
  await Promise.all([fetchModels(), fetchKeyStatus()]);
  renderChairmanSelect();
  renderModelCheckboxes();
  updateModelCountLabel();
  bindEvents();
}

// ── API ───────────────────────────────────────────────────────────────────────

async function fetchModels() {
  try {
    const res = await fetch(`${API}/api/models`);
    state.models = await res.json();
  } catch (e) {
    console.error("Could not fetch models:", e);
  }
}

async function fetchKeyStatus() {
  try {
    const res = await fetch(`${API}/api/keys/status`);
    const status = await res.json();
    updateKeyStatusBadges(status);
  } catch (_) {}
}

async function saveKeys() {
  const payload = {
    anthropic: document.getElementById("key-anthropic").value.trim() || null,
    openai:    document.getElementById("key-openai").value.trim()    || null,
    gemini:    document.getElementById("key-gemini").value.trim()    || null,
  };
  await fetch(`${API}/api/keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await fetchKeyStatus();
  ["key-anthropic", "key-openai", "key-gemini"].forEach(id => {
    document.getElementById(id).value = "";
  });
}

async function runCouncil() {
  const query = document.getElementById("query-input").value.trim();
  if (!query) return;

  const active = Array.from(state.activeModels);
  if (active.length === 0) {
    alert("Select at least one council member in Settings.");
    return;
  }

  showLoading();
  setRunButton(false);

  try {
    // Advance stage pip indicators to match approximate server timing
    setTimeout(() => advancePip(2), 6000);
    setTimeout(() => advancePip(3), 14000);

    const res = await fetch(`${API}/api/council/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        active_models: active,
        chairman_model: state.chairmanModel,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Council run failed");
    }

    const result = await res.json();
    state.lastResult = result;
    renderResults(result);
  } catch (e) {
    hideLoading();
    alert(`Error: ${e.message}`);
  } finally {
    setRunButton(true);
  }
}

// ── Loading stage pips ────────────────────────────────────────────────────────

let currentPip = 1;

function showLoading() {
  currentPip = 1;
  document.getElementById("results").classList.add("hidden");
  document.getElementById("loading").classList.remove("hidden");
  setLoadingLabel("Stage 1 · Gathering individual responses…");

  // Reset all pips
  [1, 2, 3].forEach(i => {
    const el = document.getElementById(`pip-${i}`);
    el.classList.remove("active", "done");
  });
  document.getElementById("pip-1").classList.add("active");
}

function advancePip(n) {
  if (n > 3) return;
  const labels = ["", "Gathering responses…", "Peer reviews in progress…", "Chairman synthesizing…"];
  setLoadingLabel(`Stage ${n} · ${labels[n]}`);

  for (let i = 1; i < n; i++) {
    document.getElementById(`pip-${i}`).classList.remove("active");
    document.getElementById(`pip-${i}`).classList.add("done");
  }
  document.getElementById(`pip-${n}`).classList.add("active");
  currentPip = n;
}

function hideLoading() {
  document.getElementById("loading").classList.add("hidden");
}

function setLoadingLabel(text) {
  document.getElementById("loading-label").textContent = text;
}

// ── Render ────────────────────────────────────────────────────────────────────

function providerOf(modelKey) {
  return state.models[modelKey]?.provider ?? "anthropic";
}

function renderChairmanSelect() {
  const sel = document.getElementById("chairman-select");
  sel.textContent = "";
  Object.entries(state.models).forEach(([key, meta]) => {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = `${meta.display} (${meta.provider})`;
    if (key === state.chairmanModel) opt.selected = true;
    sel.appendChild(opt);
  });
  sel.addEventListener("change", () => {
    state.chairmanModel = sel.value;
    updateModelCountLabel();
    // Uncheck the newly chosen chairman from council members
    document.querySelectorAll("#model-checkboxes input[type=checkbox]").forEach(cb => {
      if (cb.value === state.chairmanModel) {
        cb.checked = false;
        state.activeModels.delete(cb.value);
      }
    });
    updateModelCountLabel();
  });
}

function renderModelCheckboxes() {
  const container = document.getElementById("model-checkboxes");
  container.textContent = "";

  Object.entries(state.models).forEach(([key, meta]) => {
    const isChairman = meta.is_chairman;
    const row = document.createElement("label");
    row.className = `model-row${isChairman ? " is-chairman" : ""}`;

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = key;
    cb.checked = state.activeModels.has(key);
    cb.disabled = isChairman;
    cb.addEventListener("change", () => {
      if (cb.checked) state.activeModels.add(key);
      else state.activeModels.delete(key);
      updateModelCountLabel();
    });

    const badge = document.createElement("span");
    badge.className = `provider-badge ${meta.provider}`;
    badge.textContent = meta.provider;

    const name = document.createElement("span");
    name.className = "model-row-name";
    name.textContent = meta.display;

    row.appendChild(cb);
    row.appendChild(badge);
    row.appendChild(name);
    container.appendChild(row);
  });
}

function renderResults(result) {
  hideLoading();

  if (result.error) {
    alert(`Council error: ${result.error}`);
    return;
  }

  renderCards("stage1-cards", result.stage1);
  renderCards("stage2-cards", result.stage2);
  renderChairman(result.chairman_synthesis, result.chairman_model);

  const meta = document.getElementById("results-meta");
  meta.textContent = `${result.stage1.length} members · ${new Date().toLocaleTimeString()}`;

  document.getElementById("results").classList.remove("hidden");
  switchTab("stage1");
  document.getElementById("results").scrollIntoView({ behavior: "smooth" });
}

function renderCards(containerId, responses) {
  const container = document.getElementById(containerId);
  container.textContent = "";

  responses.forEach(r => {
    const provider = providerOf(r.model_key);

    const card = document.createElement("div");
    card.className = "card";

    // Header
    const header = document.createElement("div");
    header.className = "card-header";

    const dot = document.createElement("span");
    dot.className = `provider-dot ${provider}`;

    const modelName = document.createElement("span");
    modelName.className = "card-model-name";
    modelName.textContent = r.display_name;

    const tag = document.createElement("span");
    tag.className = `card-provider-tag ${provider}`;
    tag.textContent = provider;

    header.appendChild(dot);
    header.appendChild(modelName);
    header.appendChild(tag);

    // Inner row (left border + body)
    const inner = document.createElement("div");
    inner.className = "card-inner";

    const border = document.createElement("div");
    border.className = `card-left-border ${provider}`;

    const body = document.createElement("div");
    body.className = `card-body${r.error ? " error" : ""}`;
    body.textContent = r.error ? `Error: ${r.error}` : r.response;

    inner.appendChild(border);
    inner.appendChild(body);

    card.appendChild(header);
    card.appendChild(inner);
    container.appendChild(card);
  });
}

function renderChairman(synthesis, chairmanModelKey) {
  const el = document.getElementById("chairman-content");
  el.textContent = "";

  const chairmanDisplay = state.models[chairmanModelKey]?.display ?? chairmanModelKey;

  const wrapper = document.createElement("div");
  wrapper.className = "chairman-wrapper";

  const hdr = document.createElement("div");
  hdr.className = "chairman-header";

  const crown = document.createElement("span");
  crown.className = "chairman-crown";
  crown.textContent = "⚖️";

  const title = document.createElement("span");
  title.className = "chairman-title";
  title.textContent = "Chairman's Synthesis";

  const sub = document.createElement("span");
  sub.className = "chairman-subtitle";
  sub.textContent = chairmanDisplay;

  hdr.appendChild(crown);
  hdr.appendChild(title);
  hdr.appendChild(sub);

  const body = document.createElement("div");
  body.className = "chairman-body";
  body.textContent = synthesis;

  wrapper.appendChild(hdr);
  wrapper.appendChild(body);
  el.appendChild(wrapper);
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

function switchTab(stageId) {
  document.querySelectorAll(".tab").forEach(t => {
    t.classList.toggle("active", t.dataset.stage === stageId);
  });
  document.querySelectorAll(".stage-panel").forEach(p => {
    p.classList.toggle("hidden", p.id !== stageId);
  });
}

// ── UI helpers ────────────────────────────────────────────────────────────────

function setRunButton(enabled) {
  const btn = document.getElementById("btn-run");
  btn.disabled = !enabled;
  btn.textContent = enabled ? "Convene Council ▶" : "Running…";
}

function updateModelCountLabel() {
  const count = state.activeModels.size;
  const chairmanDisplay = state.models[state.chairmanModel]?.display ?? state.chairmanModel;
  document.getElementById("model-count-label").textContent =
    `${count} council member${count !== 1 ? "s" : ""} · ${chairmanDisplay} as chairman`;
}

function updateKeyStatusBadges(status) {
  Object.entries(status).forEach(([provider, configured]) => {
    const el = document.getElementById(`status-${provider}`);
    if (!el) return;
    el.textContent = configured ? "✓ configured" : "not set";
    el.className = `key-status ${configured ? "ok" : "missing"}`;
  });
}

// ── Events ────────────────────────────────────────────────────────────────────

function bindEvents() {
  document.getElementById("btn-settings").addEventListener("click", () => {
    document.getElementById("modal-overlay").classList.remove("hidden");
    fetchKeyStatus();
  });

  document.getElementById("btn-close-modal").addEventListener("click", () => {
    document.getElementById("modal-overlay").classList.add("hidden");
  });

  document.getElementById("modal-overlay").addEventListener("click", e => {
    if (e.target === document.getElementById("modal-overlay")) {
      document.getElementById("modal-overlay").classList.add("hidden");
    }
  });

  document.getElementById("btn-save-keys").addEventListener("click", saveKeys);
  document.getElementById("btn-run").addEventListener("click", runCouncil);

  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.stage));
  });

  document.getElementById("query-input").addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runCouncil();
  });
}

boot();
