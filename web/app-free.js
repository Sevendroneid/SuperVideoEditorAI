const API = window.SUPERVIDEO_API || window.location.origin;
let projectId = null;
const $ = (id) => document.getElementById(id);

async function request(path, options = {}, attempts = 3, timeoutMs = 30000) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(`${API}${path}`, { ...options, signal: controller.signal });
      const text = await response.text();
      let data;
      try { data = JSON.parse(text); } catch { data = { detail: text }; }
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      return data;
    } catch (error) {
      lastError = error.name === "AbortError" ? new Error(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds.`) : error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, 1000 * attempt));
    } finally {
      clearTimeout(timer);
    }
  }
  throw lastError;
}

function setProject(id) {
  projectId = id;
  $("project").textContent = id;
  [$("upload"), $("analyze"), $("direct")].forEach((el) => el.disabled = false);
}

async function poll(jobId, maxMs) {
  const started = Date.now();
  for (;;) {
    if (Date.now() - started > maxMs) throw new Error("Job timeout: server did not report completion.");
    const job = await request(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
    $("job").textContent = `${job.status} — ${job.progress}% — ${job.message || ""}`;
    if (job.status === "completed") return job;
    if (job.status === "failed") throw new Error(job.error || "Job failed");
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

$("create").onclick = async () => {
  const button = $("create");
  const original = button.textContent;
  button.disabled = true;
  $("job").textContent = "Creating project… please wait.";
  try {
    const data = await request("/api/v1/projects", { method: "POST" }, 2, 30000);
    if (!data || !data.project_id) throw new Error("Server returned an invalid project response.");
    setProject(data.project_id);
    $("job").textContent = "Project ready. Local temporary storage mode — no paid service required.";
  } catch (e) {
    $("job").textContent = `Create project failed: ${e.message}`;
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
};

$("upload").onclick = async () => {
  if (!projectId) return;
  const files = [...$("files").files];
  if (!files.length) { $("uploads").textContent = "Select at least one video."; return; }
  $("uploads").innerHTML = files.map((f) => `<div class="item">Preparing ${escapeHtml(f.name)}…</div>`).join("");
  let success = 0;
  for (let i = 0; i < files.length; i += 1) {
    const file = files[i];
    try {
      if (file.size > 524288000) throw new Error("File exceeds 500 MB upload limit.");
      const form = new FormData();
      form.append("file", file, file.name);
      $("uploads").children[i].textContent = `Uploading ${file.name}…`;
      const result = await request(`/api/v1/projects/${projectId}/clips`, { method: "POST", body: form }, 1, 30 * 60 * 1000);
      success += 1;
      $("uploads").children[i].textContent = `✓ ${result.filename} — ${result.bytes} bytes — local temporary storage`;
    } catch (error) {
      $("uploads").children[i].textContent = `✗ ${file.name} — ${error.message}`;
    }
  }
  $("job").textContent = `${success}/${files.length} file(s) uploaded successfully.`;
};

$("analyze").onclick = async () => {
  try {
    const job = await request(`/api/v1/projects/${projectId}/analyze`, { method: "POST" });
    const done = await poll(job.id, 20 * 60 * 1000);
    $("result").textContent = JSON.stringify(done.result, null, 2);
    $("render").disabled = false;
  } catch (e) { $("job").textContent = e.message; }
};

$("render").onclick = async () => {
  try {
    const job = await request(`/api/v1/projects/${projectId}/render`, { method: "POST" });
    const done = await poll(job.id, 30 * 60 * 1000);
    const link = $("download");
    link.href = `${API}/api/v1/projects/${projectId}/output`;
    link.download = "supervideo-story.mp4";
    link.textContent = "Download / Open rendered MP4";
    link.hidden = false;
    $("job").textContent = `${done.message} — video ready`;
  } catch (e) { $("job").textContent = e.message; }
};

$("direct").onclick = async () => {
  try {
    const text = $("instruction").value.trim();
    if (!text) throw new Error("Enter a creative direction.");
    const data = await request(`/api/v1/projects/${projectId}/director`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ instruction: text }) });
    $("direction").textContent = JSON.stringify(data, null, 2);
    if (data.timeline) { $("result").textContent = JSON.stringify(data.timeline, null, 2); $("render").disabled = false; }
  } catch (e) { $("direction").textContent = e.message; }
};

function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[c])); }

request("/health", {}, 5, 15000).then((data) => {
  $("health").textContent = data.ffmpeg_ready ? "API online • FFmpeg ready • Rp0 mode" : "API online • FFmpeg unavailable";
  if (!data.ffmpeg_ready) $("health").classList.add("warning");
}).catch((error) => { $("health").textContent = `API offline — ${error.message}`; });
