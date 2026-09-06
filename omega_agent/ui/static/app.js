/** OMEGA Web UI — POST start + GET EventSource (native SSE, no fetch buffering) */

const $ = (id) => document.getElementById(id);

let sessionId = null;
let running = false;
let elapsedTimer = null;
let runStart = 0;
let activeSource = null;

function setRunning(isRunning) {
  running = isRunning;
  $("sendBtn").disabled = isRunning;
  const badge = $("runBadge");
  badge.textContent = isRunning ? "Running" : "Ready";
  badge.classList.toggle("running", isRunning);
  $("progressFill").classList.toggle("active", isRunning);
}

function startElapsed() {
  runStart = Date.now();
  if (elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = setInterval(() => {
    const s = ((Date.now() - runStart) / 1000).toFixed(1);
    $("elapsed").textContent = `Elapsed: ${s}s`;
  }, 100);
}

function stopElapsed() {
  if (elapsedTimer) {
    clearInterval(elapsedTimer);
    elapsedTimer = null;
  }
}

function closeSource() {
  if (activeSource) {
    activeSource.close();
    activeSource = null;
  }
}

function setProgress(percent, status, log) {
  const pct = Math.max(0, Math.min(100, Number(percent) || 0));
  $("progressPct").textContent = `${pct}%`;
  $("progressFill").style.width = `${pct}%`;
  if (status) $("statusText").textContent = status;
  if (log !== undefined && log !== null) {
    const box = $("execLog");
    box.textContent = log;
    box.scrollTop = box.scrollHeight;
  }
}

function renderChat(messages) {
  const el = $("chatMessages");
  el.innerHTML = "";
  for (const m of messages || []) {
    const div = document.createElement("div");
    div.className = `msg ${m.role === "user" ? "user" : "assistant"}`;
    div.textContent = m.content || "";
    el.appendChild(div);
  }
  el.scrollTop = el.scrollHeight;
}

function applyDeliverable(d) {
  if (!d) return;
  $("dDomain").textContent = d.domain || "—";
  $("dQuality").textContent = d.quality || "—";
  $("dLatency").textContent = d.latency || "—";
  $("dBuild").textContent = d.build_verified || "—";
  const link = $("zipLink");
  if (d.archive_url) {
    link.href = d.archive_url;
    link.textContent = `Download project.zip`;
    link.style.display = "inline-block";
  } else {
    link.style.display = "none";
  }
}

function handlePayload(event, data) {
  if (data.session_id) sessionId = data.session_id;

  if (event === "progress" || event === "heartbeat") {
    const pct = data.percent ?? Math.round((data.fraction || 0) * 100);
    const status =
      event === "heartbeat"
        ? `Running (${pct}%) — ${data.message || "working…"} [${data.elapsed || 0}s]`
        : data.status || data.message;
    setProgress(pct, status, data.log);
    return;
  }

  if (event === "complete") {
    setProgress(data.percent ?? 100, data.status, data.log);
    $("awaitingText").textContent = data.awaiting || "No";
    renderChat(data.chat_messages);
    applyDeliverable(data.deliverable);
    return;
  }

  if (event === "error") {
    throw new Error(data.message || "Unknown error");
  }
}

function streamChat(message) {
  const max_time = Number($("maxTime").value) || 600;

  return new Promise((resolve, reject) => {
    fetch("/api/chat/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        goal: message,
        session_id: sessionId,
        max_time,
      }),
    })
      .then((res) => {
        if (!res.ok) {
          return res.text().then((t) => {
            throw new Error(t || `HTTP ${res.status}`);
          });
        }
        return res.json();
      })
      .then((start) => {
        if (start.session_id) sessionId = start.session_id;
        const url = start.events_url || `/api/chat/events/${start.job_id}`;
        setProgress(1, "Stream connected", _STARTUP_PLACEHOLDER);

        closeSource();
        activeSource = new EventSource(url);

        activeSource.addEventListener("progress", (ev) => {
          try {
            handlePayload("progress", JSON.parse(ev.data));
          } catch (e) {
            console.warn(e);
          }
        });

        activeSource.addEventListener("heartbeat", (ev) => {
          try {
            handlePayload("heartbeat", JSON.parse(ev.data));
          } catch (e) {
            console.warn(e);
          }
        });

        activeSource.addEventListener("complete", (ev) => {
          try {
            handlePayload("complete", JSON.parse(ev.data));
          } catch (e) {
            reject(e);
            return;
          }
          closeSource();
          resolve();
        });

        activeSource.addEventListener("error", (ev) => {
          try {
            if (ev.data) {
              handlePayload("error", JSON.parse(ev.data));
            }
          } catch (e) {
            reject(e);
            return;
          }
          closeSource();
          reject(new Error("Run failed"));
        });

        activeSource.onerror = () => {
          if (!running) return;
          if (activeSource && activeSource.readyState === EventSource.CLOSED) {
            closeSource();
            reject(new Error("Lost connection to server stream"));
          }
        };
      })
      .catch(reject);
  });
}

const _STARTUP_PLACEHOLDER =
  ">> Connecting to live event stream…\n-> Updates appear here in real time.";

async function onSend() {
  const text = $("messageInput").value.trim();
  if (!text || running) return;

  const userMsg = { role: "user", content: text };
  const prev = [];
  $("chatMessages").querySelectorAll(".msg").forEach((n) => {
    prev.push({
      role: n.classList.contains("user") ? "user" : "assistant",
      content: n.textContent,
    });
  });
  renderChat([...prev, userMsg]);
  $("messageInput").value = "";

  setRunning(true);
  startElapsed();
  setProgress(0, "Starting job…", "Calling /api/chat/start…");

  try {
    await streamChat(text);
  } catch (e) {
    console.error(e);
    setProgress(0, "Error", String(e.message || e));
    renderChat([
      ...prev,
      userMsg,
      { role: "assistant", content: `OMEGA error: ${e.message || e}` },
    ]);
  } finally {
    closeSource();
    setRunning(false);
    stopElapsed();
  }
}

async function onReset() {
  if (running) return;
  closeSource();
  await fetch("/api/session/reset", { method: "POST" });
  sessionId = null;
  renderChat([]);
  setProgress(0, "Ready — describe your automation goal.", "");
  $("awaitingText").textContent = "No";
  $("dDomain").textContent = "—";
  $("dQuality").textContent = "—";
  $("dLatency").textContent = "—";
  $("dBuild").textContent = "—";
  $("zipLink").style.display = "none";
  $("elapsed").textContent = "Elapsed: 0.0s";
}

$("sendBtn").addEventListener("click", onSend);
$("messageInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    onSend();
  }
});
$("resetBtn").addEventListener("click", onReset);
$("maxTime").addEventListener("input", () => {
  $("maxTimeLabel").textContent = `${$("maxTime").value}s`;
});
