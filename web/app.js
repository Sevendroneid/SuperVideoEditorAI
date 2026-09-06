const API = window.SUPERVIDEO_API || window.location.origin;
let projectId = null;
let persistentStorage = false;
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

$("create").onclick = async () => {
  const button = $("create");
  const original = button.textContent;
  button.disabled = true;
  $("job").textContent = "Creating project… please wait.";
  try {
    const data = await request("/api/v1/projects", { method: "POST" }, 2, 30000);
    if (!data || !data.project_id) throw new Error("Server returned an invalid project response.");
    setProject(data.project_id);
    $("job").textContent = persistentStorage ? "Project ready. Persistent storage is enabled." : "Project ready. Local runtime storage is active for this test.";
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
  $("uploads").innerHTML = files.map((file) => `<div class="item">Preparing ${escapeHtml(file.name)}…</div>`).join("");
  let success = 0;
  for (let index = 0; index < files.length; index += 1) {
    const file = files[index];
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      const xhr = new XMLHttpRequest();
      const result = await new Promise((resolve, reject) => {
        xhr.open("POST", `${API}/api/v1/projects/${projectId}/clips`, true);
        xhr.timeout = 30 * 60 * 1000;
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) $("uploads").children[index].textContent = `Uploading ${file.name} — ${Math.floor(event.loaded / event.total * 100)}% (${index + 1}/${files.length})`;
        };
        xhr.onload = () => {
          let data = {};
          try { data = JSON.parse(xhr.responseText); } catch {}
          if (xhr.status >= 200 && xhr.status < 300) resolve(data);
          else reject(new Error(data.detail || `HTTP ${xhr.status}`));
        };
        xhr.onerror = () => reject(new Error("Network error while uploading video."));
        xhr.ontimeout = () => reject(new Error("Upload timed out after 30 minutes."));
        xhr.send(form);
      });
      success += 1;
      $("uploads").children[index].textContent = `✓ ${result.filename} — ${result.bytes} bytes — local runtime storage`;
    } catch (error) {
      $("uploads").children[index].textContent = `✗ ${file.name} — ${error.message}`;
    }
  }
  $("job").textContent = `${success}/${files.length} file(s) uploaded successfully.`;
};

function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[char])); }

async function poll(jobId, maxMs = 30 * 60 * 1000) {
  const started = Date.now();
  for (;;) {
    if (Date.now() - started > maxMs) throw new Error("Job timed out after 30 minutes. The server did not report completion.");
    const job = await request(`/api/v1/jobs/${encodeURIComponent(jobId)}`, {}, 4);
    $("job").textContent = `${job.status} — ${job.progress}% — ${job.message || ""}`;
    if (job.status === "completed") return job;
    if (job.status === "failed") throw new Error(job.error || "Job failed");
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

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

request("/health", {}, 5, 15000).then((data) => {
  persistentStorage = Boolean(data.persistent_storage);
  $("health").textContent = persistentStorage ? "API online • storage persistent" : "API online • local test storage";
  if (!persistentStorage) $("health").classList.add("warning");
}).catch((error) => { $("health").textContent = `API offline — ${error.message}`; });
