const TOOLS = ["claude", "codex"];
const TERMINAL_PORTS = {
  claude: 7681,
  codex: 7682,
};

const apiKey = (() => {
  const existing = sessionStorage.getItem("session_loader_key");
  if (existing) return existing;
  const entered = window.prompt("API Key:");
  const key = entered ? entered.trim() : "";
  if (key) sessionStorage.setItem("session_loader_key", key);
  return key;
})();

const headers = {
  "x-api-key": apiKey,
  "Content-Type": "application/json",
};

let allJobs = [];
let latestStatus = null;
let latestSystemCheck = null;
const expiryEditors = new Set();

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) },
  });
  if (!response.ok) {
    throw new Error(`${response.status}: ${await response.text()}`);
  }
  return response.json();
}

function fmtDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtTime(value) {
  if (!value) return "-";
  const [hour, minute] = value.split(":").map(Number);
  const suffix = hour < 12 ? "AM" : "PM";
  return `${hour % 12 || 12}:${String(minute).padStart(2, "0")} ${suffix}`;
}

function parseExpiryDate(value) {
  if (!value) return null;
  const hasZone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function fmtRemaining(value) {
  const date = parseExpiryDate(value);
  if (!date) return "Reset time unavailable";
  const remainingMs = date.getTime() - Date.now();
  if (remainingMs <= 0) return "Session expired — start a new one";
  const totalMinutes = Math.ceil(remainingMs / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const resetTime = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return `Resets at ${resetTime} · in ${hours}h ${minutes}m`;
}

function fmtUpdatedAgo(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  return `Updated ${minutes}m ago`;
}

function pctValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0;
}

function inputTimeFromExpiry(value) {
  const date = parseExpiryDate(value);
  if (!date) return "";
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function expiryFromInputTime(value) {
  const match = value.trim().match(/^(\d{1,2}):(\d{2})(?:\s*([ap]m))?$/i);
  if (!match) throw new Error("Use a time like 6:10 AM.");
  let hour = Number(match[1]);
  const minute = Number(match[2]);
  const suffix = match[3] ? match[3].toUpperCase() : "";
  if (minute > 59 || hour < 0 || hour > (suffix ? 12 : 23) || (suffix && hour === 0)) {
    throw new Error("Use a time like 6:10 AM.");
  }
  if (suffix === "AM") hour = hour === 12 ? 0 : hour;
  if (suffix === "PM") hour = hour === 12 ? 12 : hour + 12;
  const expiresAt = new Date();
  expiresAt.setHours(hour, minute, 0, 0);
  if (expiresAt <= new Date()) expiresAt.setDate(expiresAt.getDate() + 1);
  return expiresAt.toISOString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderExpiry(tool) {
  const container = document.getElementById(`expiry-${tool}`);
  const status = latestStatus && latestStatus[tool];
  if (!container || !status) return;
  const expiresAt = status.expires_at;
  const hasRateInfo = tool === "claude" && status.remaining_pct !== undefined;

  if (hasRateInfo && expiresAt) {
    const usedPct = pctValue(status.used_pct);
    const remainingPct = pctValue(status.remaining_pct);
    const updatedAgo = fmtUpdatedAgo(status.captured_at);
    const expired = parseExpiryDate(expiresAt)?.getTime() <= Date.now();
    container.innerHTML = `
      <div class="expiry-primary">
        <span class="${expired ? "expired" : ""}">${escapeHtml(fmtRemaining(expiresAt))}</span>
      </div>
      <div class="usage-bar" aria-label="${escapeHtml(`${Math.round(usedPct)}% used | ${Math.round(remainingPct)}% remaining`)}">
        <span style="width: ${usedPct}%"></span>
      </div>
      <div class="usage-copy">${escapeHtml(`${Math.round(usedPct)}% used | ${Math.round(remainingPct)}% remaining`)}</div>
      ${updatedAgo ? `<div class="expiry-updated">${escapeHtml(updatedAgo)}</div>` : ""}
    `;
    return;
  }

  if (expiryEditors.has(tool)) {
    const prompt = tool === "codex"
      ? "When does Codex reset? (from ChatGPT → Usage)"
      : "When does your session reset?";
    const hint = tool === "codex" ? "" : '<span class="expiry-hint">Found in Claude menu → Usage</span>';
    container.innerHTML = `
      <form class="expiry-editor" data-expiry-form="${tool}">
        <label>
          <span>${escapeHtml(prompt)}</span>
          <input type="text" required placeholder="6:10 AM" value="${escapeHtml(inputTimeFromExpiry(expiresAt))}" aria-label="${tool} reset time" />
        </label>
        ${hint}
        <button type="submit" class="small-button">Save</button>
        <button type="button" class="text-button" data-cancel-expiry="${tool}">Cancel</button>
      </form>
    `;
    return;
  }

  if (!expiresAt) {
    const label = tool === "codex" ? "Set Codex reset time" : (status.running ? "Set it" : "Set reset time");
    container.innerHTML = tool === "codex"
      ? `<button class="expiry-link expiry-action" type="button" data-edit-expiry="${tool}">${label}</button>`
      : status.running
        ? `Reset time unknown &mdash; <button class="expiry-link" type="button" data-edit-expiry="${tool}">${label}</button>`
        : `<button class="expiry-link" type="button" data-edit-expiry="${tool}">${label}</button>`;
    return;
  }

  const expired = parseExpiryDate(expiresAt)?.getTime() <= Date.now();
  container.innerHTML = `
    <span class="${expired ? "expired" : ""}">${escapeHtml(fmtRemaining(expiresAt))}</span>
    <button class="expiry-edit" type="button" data-edit-expiry="${tool}">Edit</button>
  `;
}

function updateExpiryDisplays() {
  for (const tool of TOOLS) renderExpiry(tool);
}

async function refreshStatus() {
  const data = await apiFetch("/status");
  latestStatus = data;
  for (const tool of TOOLS) {
    const item = data[tool];
    const pids = item.pids || [];
    const dot = document.getElementById(`dot-${tool}`);
    const label = document.getElementById(`status-label-${tool}`);
    const times = document.getElementById(`times-${tool}`);
    const button = document.getElementById(`start-${tool}`);

    dot.classList.toggle("running", item.running);
    label.textContent = item.running
      ? `Running${pids.length ? ` (${pids.length} ${pids.length === 1 ? "process" : "processes"})` : ""}`
      : "Not running";
    button.disabled = false;
    button.textContent = item.running ? "Restart / Warm up" : "Start Now";

    if (item.running) {
      times.textContent = `Started ${fmtDateTime(item.started_at)}`;
    } else {
      times.textContent = item.next_session ? `Next scheduled: ${item.next_session}` : "No schedule";
    }
  }
  updateExpiryDisplays();
  updateTerminalLinks();
}

async function saveExpiry(tool, timeValue) {
  await apiFetch(`/expiry/${tool}`, {
    method: "POST",
    body: JSON.stringify({ expires_at: expiryFromInputTime(timeValue) }),
  });
  expiryEditors.delete(tool);
  await refreshStatus();
}

async function runTool(tool) {
  const button = document.getElementById(`start-${tool}`);
  button.disabled = true;
  button.textContent = "Starting";
  try {
    const result = await apiFetch(`/run/${tool}`, { method: "POST" });
    if (result.status === "warmed_existing") {
      button.textContent = "Warmup Sent";
    } else if (result.status === "already_running") {
      button.textContent = "Already Running";
    } else if (result.status === "started") {
      button.textContent = "Started";
    } else {
      throw new Error(result.error || `Unexpected start status: ${result.status}`);
    }
  } catch (error) {
    button.textContent = "Failed";
    console.error(error);
  } finally {
    window.setTimeout(() => {
      button.disabled = false;
      refreshStatus().catch(console.error);
      refreshHistory().catch(console.error);
    }, 1600);
  }
}

async function refreshJobs() {
  allJobs = await apiFetch("/jobs");
  for (const tool of TOOLS) {
    const list = document.getElementById(`schedules-${tool}`);
    const jobs = allJobs.filter((job) => job.tool === tool);
    list.innerHTML = jobs.length ? jobs.map(renderJob).join("") : '<div class="empty-row">No schedules</div>';
  }
}

function renderJob(job) {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const frequency = job.trigger === "weekly"
    ? (job.days || []).map((day) => days[day]).join(", ")
    : job.trigger === "once"
      ? `once on ${job.date}`
      : "daily";
  return `
    <div class="schedule-row">
      <div class="schedule-time">${fmtTime(job.time)}</div>
      <div class="schedule-meta">
        <div>${escapeHtml(frequency)}${job.next_run ? ` | ${escapeHtml(job.next_run)}` : ""}</div>
        <div class="truncate">${escapeHtml(job.workspace || "")}</div>
      </div>
      <div class="schedule-actions">
        <label class="switch" title="${job.enabled ? "Disable" : "Enable"}">
          <input type="checkbox" ${job.enabled ? "checked" : ""} data-toggle-job="${job.id}" />
          <span></span>
        </label>
        <button class="icon-button" title="Edit" data-edit-job="${job.id}">Edit</button>
        <button class="icon-button" title="Delete" data-delete-job="${job.id}">Del</button>
      </div>
    </div>
  `;
}

async function toggleJob(jobId, enabled) {
  await apiFetch(`/jobs/${jobId}/${enabled ? "enable" : "disable"}`, { method: "PATCH" });
  await Promise.all([refreshJobs(), refreshStatus()]);
}

async function deleteJob(jobId) {
  if (!window.confirm("Delete this schedule?")) return;
  await apiFetch(`/jobs/${jobId}`, { method: "DELETE" });
  await Promise.all([refreshJobs(), refreshStatus()]);
}

function openAddModal(tool) {
  document.getElementById("modal-title").textContent = "Add Schedule";
  document.getElementById("modal-tool").value = tool;
  document.getElementById("modal-job-id").value = "";
  document.getElementById("modal-time").value = "";
  document.getElementById("modal-trigger").value = "daily";
  document.getElementById("modal-date").value = "";
  document.getElementById("modal-workspace").value = "";
  document.getElementById("modal-warmup").value = "";
  document.querySelectorAll(".days-picker input").forEach((input) => {
    input.checked = false;
  });
  updateModalFields();
  document.getElementById("modal-overlay").classList.remove("hidden");
}

function openEditModal(jobId) {
  const job = allJobs.find((item) => item.id === jobId);
  if (!job) return;
  document.getElementById("modal-title").textContent = "Edit Schedule";
  document.getElementById("modal-tool").value = job.tool;
  document.getElementById("modal-job-id").value = job.id;
  document.getElementById("modal-time").value = job.time;
  document.getElementById("modal-trigger").value = job.trigger;
  document.getElementById("modal-date").value = job.date || "";
  document.getElementById("modal-workspace").value = job.workspace || "";
  document.getElementById("modal-warmup").value = job.warmup_prompt || "";
  document.querySelectorAll(".days-picker input").forEach((input) => {
    input.checked = (job.days || []).includes(Number(input.value));
  });
  updateModalFields();
  document.getElementById("modal-overlay").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal-overlay").classList.add("hidden");
}

function updateModalFields() {
  const trigger = document.getElementById("modal-trigger").value;
  const dateInput = document.getElementById("modal-date");
  document.getElementById("modal-date-row").classList.toggle("hidden", trigger !== "once");
  document.getElementById("modal-days-row").classList.toggle("hidden", trigger !== "weekly");
  dateInput.required = trigger === "once";
}

async function submitSchedule(event) {
  event.preventDefault();
  const trigger = document.getElementById("modal-trigger").value;
  const jobId = document.getElementById("modal-job-id").value;
  const payload = {
    tool: document.getElementById("modal-tool").value,
    trigger,
    time: document.getElementById("modal-time").value,
    workspace: document.getElementById("modal-workspace").value || undefined,
    warmup_prompt: document.getElementById("modal-warmup").value || undefined,
  };
  if (trigger === "once") {
    payload.date = document.getElementById("modal-date").value;
  }
  if (trigger === "weekly") {
    payload.days = [...document.querySelectorAll(".days-picker input:checked")].map((input) => Number(input.value));
    if (!payload.days.length) {
      window.alert("Select at least one day for a weekly schedule.");
      return;
    }
  }

  const path = jobId ? `/jobs/${jobId}` : "/jobs";
  const method = jobId ? "PUT" : "POST";
  await apiFetch(path, { method, body: JSON.stringify(payload) });
  closeModal();
  await Promise.all([refreshJobs(), refreshStatus()]);
}

async function refreshHistory() {
  const history = await apiFetch("/history");
  const body = document.getElementById("history-body");
  body.innerHTML = history.slice(0, 20).map((entry) => `
    <tr>
      <td>${escapeHtml(entry.tool)}</td>
      <td>${escapeHtml(entry.trigger_type)}</td>
      <td>${fmtDateTime(entry.scheduled_time)}</td>
      <td>${fmtDateTime(entry.actual_start_time)}</td>
      <td><span class="badge badge-${escapeHtml(entry.status)}">${escapeHtml(entry.status)}</span></td>
      <td>${fmtDateTime(entry.estimated_end_time)}</td>
      <td class="truncate">${escapeHtml(entry.workspace)}</td>
    </tr>
  `).join("");
}

function terminalUrl(tool) {
  if (window.location.protocol === "https:") {
    const path = tool === "claude" ? "/terminal" : "/codex-terminal";
    return `${window.location.protocol}//${window.location.host}${path}`;
  }
  return `http://${window.location.hostname}:${TERMINAL_PORTS[tool]}`;
}

function updateTerminalLinks() {
  const fallback = document.getElementById("terminal-fallback");
  if (!latestSystemCheck) return;

  const deps = latestSystemCheck.deps || {};
  const terminalDepsAvailable = Boolean(deps.tmux && deps.ttyd);
  fallback.classList.toggle("hidden", !terminalDepsAvailable);
  if (!terminalDepsAvailable) return;

  for (const tool of TOOLS) {
    const link = document.getElementById(`terminal-${tool}-link`);
    const running = Boolean(latestStatus && latestStatus[tool] && latestStatus[tool].running);
    if (running) {
      link.href = terminalUrl(tool);
      link.classList.remove("disabled-link");
      link.removeAttribute("aria-disabled");
      link.title = `Open ${tool} terminal`;
    } else {
      link.removeAttribute("href");
      link.classList.add("disabled-link");
      link.setAttribute("aria-disabled", "true");
      link.title = "Start a session first";
    }
  }
}

async function refreshSystemCheck() {
  const data = await apiFetch("/system-check");
  latestSystemCheck = data;
  const banner = document.getElementById("warnings-banner");
  if (data.warnings && data.warnings.length) {
    banner.innerHTML = data.warnings.map(escapeHtml).join("<br>");
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }

  updateTerminalLinks();
}

async function refreshRemoteStatus() {
  const data = await apiFetch("/remote-status");
  const status = data.claude_remote_control || {};
  const dot = document.getElementById("claude-remote-dot");
  const label = document.getElementById("claude-remote-label");
  dot.classList.toggle("running", Boolean(status.running));
  label.textContent = status.running ? `Running (${status.pids.join(", ")})` : "Not running";
}

function bindEvents() {
  for (const tool of TOOLS) {
    document.getElementById(`start-${tool}`).addEventListener("click", () => runTool(tool));
  }
  document.querySelectorAll("[data-add-tool]").forEach((button) => {
    button.addEventListener("click", () => openAddModal(button.dataset.addTool));
  });
  document.getElementById("modal-trigger").addEventListener("change", updateModalFields);
  document.getElementById("schedule-form").addEventListener("submit", (event) => {
    submitSchedule(event).catch((error) => {
      window.alert(error.message);
    });
  });
  document.getElementById("cancel-modal").addEventListener("click", closeModal);
  document.getElementById("modal-overlay").addEventListener("click", (event) => {
    if (event.target.id === "modal-overlay") closeModal();
  });
  document.body.addEventListener("click", (event) => {
    const disabledTerminal = event.target.closest("a[aria-disabled='true']");
    if (disabledTerminal) {
      event.preventDefault();
      return;
    }
    const edit = event.target.closest("[data-edit-job]");
    const del = event.target.closest("[data-delete-job]");
    const editExpiry = event.target.closest("[data-edit-expiry]");
    const cancelExpiry = event.target.closest("[data-cancel-expiry]");
    if (edit) openEditModal(edit.dataset.editJob);
    if (del) deleteJob(del.dataset.deleteJob).catch(console.error);
    if (editExpiry) {
      expiryEditors.add(editExpiry.dataset.editExpiry);
      updateExpiryDisplays();
    }
    if (cancelExpiry) {
      expiryEditors.delete(cancelExpiry.dataset.cancelExpiry);
      updateExpiryDisplays();
    }
  });
  document.body.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-expiry-form]");
    if (!form) return;
    event.preventDefault();
    saveExpiry(form.dataset.expiryForm, form.querySelector("input").value).catch((error) => {
      window.alert(error.message);
    });
  });
  document.body.addEventListener("change", (event) => {
    const toggle = event.target.closest("[data-toggle-job]");
    if (toggle) toggleJob(toggle.dataset.toggleJob, toggle.checked).catch(console.error);
  });
  document.getElementById("copy-remote").addEventListener("click", () => {
    navigator.clipboard.writeText(document.getElementById("claude-remote-cmd").textContent);
  });
  document.getElementById("clear-key").addEventListener("click", () => {
    const entered = window.prompt("New API Key:");
    if (entered === null) return;
    const key = entered.trim();
    if (key) {
      sessionStorage.setItem("session_loader_key", key);
    } else {
      sessionStorage.removeItem("session_loader_key");
    }
    window.location.reload();
  });
}

async function init() {
  bindEvents();
  await Promise.all([
    refreshStatus(),
    refreshJobs(),
    refreshHistory(),
    refreshSystemCheck(),
    refreshRemoteStatus(),
  ]);
  window.setInterval(() => refreshStatus().catch(console.error), 15000);
  window.setInterval(updateExpiryDisplays, 30000);
  window.setInterval(() => refreshHistory().catch(console.error), 30000);
  window.setInterval(() => refreshRemoteStatus().catch(console.error), 15000);
}

init().catch((error) => {
  console.error(error);
  window.alert(error.message);
});
