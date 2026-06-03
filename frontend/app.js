/**
 * BugLens Frontend — vanilla JS, talks to FastAPI on same origin.
 */

const API = "";  // same origin when served by FastAPI

const STATUS_ORDER = ["sandboxing", "exploring", "capturing", "analyzing", "done"];
const STATUS_PROGRESS = {
  pending: 5,
  sandboxing: 20,
  exploring: 40,
  capturing: 60,
  analyzing: 80,
  done: 100,
  failed: 100,
};

const STATUS_LABELS = {
  pending: "Queued",
  sandboxing: "Setting up sandbox…",
  exploring: "Discovering routes…",
  capturing: "Capturing evidence…",
  analyzing: "Running AI analysis…",
  done: "Complete",
  failed: "Failed",
};

// ── DOM refs ──────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

const dropzone = $("dropzone");
const fileInput = $("fileInput");
const dropzoneTitle = $("dropzoneTitle");
const startBtn = $("startBtn");
const cancelBtn = $("cancelBtn");
const pipelineSection = $("pipelineSection");
const terminalSection = $("terminalSection");
const terminalBody = $("terminalBody");
const logCount = $("logCount");
const progressFill = $("progressFill");
const sessionMeta = $("sessionMeta");
const reportSection = $("reportSection");
const errorSection = $("errorSection");
const errorMessage = $("errorMessage");
const healthBadge = $("healthBadge");
const historyList = $("historyList");

let selectedFile = null;
let currentSessionId = null;
let pollTimer = null;
let lastLogCount = 0;

// ── Init ──────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  loadHistory();
  setupUpload();
  setupButtons();
});

// ── Health check ──────────────────────────────────────────────────────

async function checkHealth() {
  try {
    const res = await fetch(`${API}/health`);
    if (res.ok) {
      healthBadge.textContent = "API Online";
      healthBadge.className = "badge badge-ok";
    } else {
      throw new Error("unhealthy");
    }
  } catch {
    healthBadge.textContent = "API Offline";
    healthBadge.className = "badge badge-err";
  }
}

// ── Upload handling ───────────────────────────────────────────────────

function setupUpload() {
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) setFile(fileInput.files[0]);
  });

  ["dragenter", "dragover"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (ev === "drop" && e.dataTransfer.files.length) {
        setFile(e.dataTransfer.files[0]);
      }
    });
  });
}

function setFile(file) {
  if (!file.name.endsWith(".zip")) {
    alert("Please upload a .zip file of your project.");
    return;
  }
  selectedFile = file;
  dropzone.classList.add("has-file");
  dropzoneTitle.textContent = file.name;
  startBtn.disabled = false;
}

function setupButtons() {
  startBtn.addEventListener("click", startSession);
  cancelBtn.addEventListener("click", cancelSession);
  $("newSessionBtn").addEventListener("click", resetUI);
  $("retryBtn").addEventListener("click", resetUI);
}

// ── Session lifecycle ─────────────────────────────────────────────────

async function startSession() {
  if (!selectedFile) return;

  resetForNewSession();
  startBtn.disabled = true;
  cancelBtn.classList.remove("hidden");

  appendLog("Uploading " + selectedFile.name + "…", "info");

  try {
    const form = new FormData();
    form.append("file", selectedFile);

    const res = await fetch(`${API}/sessions`, { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Upload failed (${res.status})`);
    }

    const data = await res.json();
    currentSessionId = data.session_id;

    pipelineSection.classList.remove("hidden");
    terminalSection.classList.remove("hidden");
    updatePipeline("pending");
    updateSessionMeta(currentSessionId, data.status);

    appendLog("Session started: " + currentSessionId, "info");
    startPolling();
  } catch (err) {
    showError(err.message);
    startBtn.disabled = false;
    cancelBtn.classList.add("hidden");
  }
}

function startPolling() {
  pollSession();
  pollTimer = setInterval(pollSession, 2000);
}

async function pollSession() {
  if (!currentSessionId) return;

  try {
    const res = await fetch(`${API}/sessions/${currentSessionId}`);
    if (!res.ok) throw new Error("Session not found");
    const data = await res.json();

    updatePipeline(data.status);
    updateSessionMeta(data.session_id, data.status, data.framework);

    // Append new logs only
    if (data.logs && data.logs.length > lastLogCount) {
      for (let i = lastLogCount; i < data.logs.length; i++) {
        const entry = data.logs[i];
        appendLog(entry.message, entry.level);
      }
      lastLogCount = data.logs.length;
    }

    if (data.status === "done") {
      stopPolling();
      cancelBtn.classList.add("hidden");
      await loadReport(data.report_id);
      loadHistory();
    } else if (data.status === "failed") {
      stopPolling();
      cancelBtn.classList.add("hidden");
      showError(data.error || "Session failed. Check the logs above.");
    }
  } catch (err) {
    appendLog("Poll error: " + err.message, "error");
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function cancelSession() {
  if (!currentSessionId) return;
  stopPolling();
  try {
    await fetch(`${API}/sessions/${currentSessionId}`, { method: "DELETE" });
    appendLog("Session cancelled.", "warning");
  } catch {
    appendLog("Could not cancel session.", "error");
  }
  currentSessionId = null;
  cancelBtn.classList.add("hidden");
  startBtn.disabled = false;
}

// ── Report rendering ──────────────────────────────────────────────────

async function loadReport(reportId) {
  if (!reportId) {
    showError("Session completed but no report was generated.");
    return;
  }

  try {
    const res = await fetch(`${API}/reports/${reportId}`);
    if (!res.ok) throw new Error("Report not found");
    const report = await res.json();
    renderReport(report);
  } catch (err) {
    showError("Failed to load report: " + err.message);
  }
}

function renderReport(report) {
  errorSection.classList.add("hidden");
  reportSection.classList.remove("hidden");

  const s = report.summary;
  $("fullReportLink").href = report.view_url;

  $("summaryGrid").innerHTML = `
    <div class="stat-card">
      <div class="stat-value" style="color:${scoreColor(s.top_disaster_score)}">${s.top_disaster_score.toFixed(1)}</div>
      <div class="stat-label">Top Score</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color:var(--red)">${s.critical}</div>
      <div class="stat-label">Critical</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color:var(--orange)">${s.high}</div>
      <div class="stat-label">High</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color:var(--purple)">${s.total_bugs}</div>
      <div class="stat-label">Total Bugs</div>
    </div>
  `;

  const routes = report.routes_explored || [];
  const routesBlock = $("routesBlock");
  if (routes.length) {
    routesBlock.classList.remove("hidden");
    $("routeTags").innerHTML = routes
      .map((r) => `<span class="route-tag">${esc(r)}</span>`)
      .join("");
  } else {
    routesBlock.classList.add("hidden");
  }

  const bugsList = $("bugsList");
  if (!report.bugs || report.bugs.length === 0) {
    bugsList.innerHTML = `
      <div class="no-bugs">
        <div class="no-bugs-icon">✅</div>
        <p><strong>No bugs found</strong></p>
        <p>BugLens explored every route and found nothing. Ship it.</p>
      </div>`;
    return;
  }

  bugsList.innerHTML = report.bugs
    .map((bug) => {
      const score = bug.disaster_score;
      const sev = bug.severity || "low";
      const fileHtml = bug.file
        ? `<div class="bug-file">${esc(bug.file)}</div>`
        : "";

      return `
        <article class="bug-card">
          <div class="bug-card-header">
            <span class="severity severity-${sev}">${sev}</span>
            <span class="bug-title">${esc(bug.title)}</span>
            <span class="bug-route">${esc(bug.route)}</span>
            <span class="bug-score" style="color:${scoreColor(score)}">${score.toFixed(1)}</span>
          </div>
          <div class="bug-card-body">
            <div class="bug-grid">
              <div>
                <div class="bug-field-label">Problem</div>
                <div class="bug-field-value">${esc(bug.problem)}</div>
              </div>
              <div>
                <div class="bug-field-label">Cause</div>
                <div class="bug-field-value">${esc(bug.cause)}</div>
              </div>
            </div>
            ${fileHtml}
            <div class="bug-fix">
              <div class="bug-fix-label">Suggested Fix</div>
              <pre>${esc(bug.fix)}</pre>
            </div>
            <div class="bug-meta">Reproduced: ${esc(bug.reproduced || "—")}</div>
          </div>
        </article>`;
    })
    .join("");

  reportSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── History ───────────────────────────────────────────────────────────

async function loadHistory() {
  try {
    const res = await fetch(`${API}/reports`);
    if (!res.ok) return;
    const reports = await res.json();

    if (!reports.length) {
      historyList.innerHTML = '<p class="empty-state">No reports yet. Upload a project to get started.</p>';
      return;
    }

    historyList.innerHTML = reports
      .map((r) => {
        const date = (r.created_at || "").slice(0, 16).replace("T", " ");
        return `
          <a class="history-item" href="${r.view_url}" target="_blank" rel="noopener">
            <div class="history-info">
              <div class="history-id">${esc(r.id.slice(0, 8))}…</div>
              <div class="history-meta">${esc(r.framework || "unknown")} · ${date}</div>
            </div>
            <div class="history-stats">
              <span class="history-stat">${r.bug_count} bugs</span>
              <span class="history-stat" style="color:${scoreColor(r.top_disaster_score)}">${r.top_disaster_score.toFixed(1)}</span>
            </div>
          </a>`;
      })
      .join("");
  } catch {
    /* ignore */
  }
}

// ── UI helpers ────────────────────────────────────────────────────────

function updatePipeline(status) {
  const idx = STATUS_ORDER.indexOf(status);
  const isFailed = status === "failed";

  document.querySelectorAll(".step").forEach((step) => {
    const stepStatus = step.dataset.status;
    const stepIdx = STATUS_ORDER.indexOf(stepStatus);
    step.classList.remove("active", "done", "error");

    if (isFailed && stepIdx === Math.max(0, idx)) {
      step.classList.add("error");
    } else if (status === "done" || stepIdx < idx) {
      step.classList.add("done");
    } else if (stepIdx === idx || (status === "pending" && stepStatus === "sandboxing")) {
      step.classList.add("active");
    }
  });

  progressFill.style.width = (STATUS_PROGRESS[status] || 0) + "%";
}

function updateSessionMeta(id, status, framework) {
  let text = `Session ${id.slice(0, 8)}… · ${STATUS_LABELS[status] || status}`;
  if (framework) text += ` · ${framework}`;
  sessionMeta.textContent = text;
}

function appendLog(message, level) {
  const line = document.createElement("div");
  line.className = "log-line";
  const time = new Date().toLocaleTimeString([], { hour12: false });
  line.innerHTML = `<span class="log-time">${time}</span><span class="log-msg ${level}">${esc(message)}</span>`;
  terminalBody.appendChild(line);
  terminalBody.scrollTop = terminalBody.scrollHeight;
  logCount.textContent = terminalBody.children.length + " lines";
}

function showError(msg) {
  errorSection.classList.remove("hidden");
  reportSection.classList.add("hidden");
  errorMessage.textContent = msg;
  startBtn.disabled = false;
}

function resetForNewSession() {
  stopPolling();
  lastLogCount = 0;
  terminalBody.innerHTML = "";
  logCount.textContent = "0 lines";
  reportSection.classList.add("hidden");
  errorSection.classList.add("hidden");
  currentSessionId = null;
}

function resetUI() {
  resetForNewSession();
  pipelineSection.classList.add("hidden");
  terminalSection.classList.add("hidden");
  cancelBtn.classList.add("hidden");
  selectedFile = null;
  fileInput.value = "";
  dropzone.classList.remove("has-file");
  dropzoneTitle.textContent = "Drop your project .zip here";
  startBtn.disabled = true;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function scoreColor(score) {
  if (score >= 9) return "var(--red)";
  if (score >= 6) return "var(--orange)";
  if (score >= 3) return "var(--yellow)";
  return "var(--green)";
}

function esc(str) {
  const d = document.createElement("div");
  d.textContent = str || "";
  return d.innerHTML;
}
