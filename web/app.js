const API = window.SUPERVIDEO_API || "";
let projectId = null;
let persistentStorage = false;
const $ = (id) => document.getElementById(id);

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { detail: text }; }
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

function setProject(id) {
  projectId = id;
  $("project").textContent = id;
  [$("upload"), $("analyze"), $("direct")].forEach((el) => el.disabled = false);
}

$("create").onclick = async () => {
  try {
    const data = await request("/api/v1/projects", { method: "POST" });
    setProject(data.project_id);
    $("job").textContent = persistentStorage
      ? "Project ready. Persistent storage is enabled."
      : "Project ready. WARNING: persistent storage is not enabled.";
  } catch (e) { $("job").textContent = e.message; }
};

$("upload").onclick = async () => {
  if (!projectId) return;
  try {
    const files = [...$("files").files];
    if (!files.length) throw new Error("Select at least one video.");
    const items = files.map((file) => `<div class="item">Uploading ${escapeHtml(file.name)}…</div>`);
    $("uploads").innerHTML = items.join("");

    const results = [];
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      const form = new FormData();
      form.append("file", file, file.name);
      try {
        const result = await request(`/api/v1/projects/${projectId}/clips`, {
          method: "POST",
          body: form,
        });
        results.push(result);
        const persistence = result.persistent ? "persistent" : "TEMPORARY — not durable";
        items[index] = `<div class="item">✓ ${escapeHtml(result.filename)} — ${result.bytes} bytes — ${persistence}</div>`;
      } catch (error) {
        items[index] = `<div class="item">✗ ${escapeHtml(file.name)} — ${escapeHtml(error.message)}</div>`;
      }
      $("uploads").innerHTML = items.join("");
    }

    if (!results.length) {
      throw new Error("No files were uploaded successfully.");
    }
    if (results.some((result) => !result.persistent)) {
      $("job").textContent = "Upload completed, but persistent storage is NOT enabled. Do not use Analyze for a release test.";
    } else if (results.length === files.length) {
      $("job").textContent = `${results.length} file(s) uploaded and persisted successfully.`;
    } else {
      $("job").textContent = `${results.length}/${files.length} file(s) uploaded successfully.`;
    }
  } catch (e) {
    $("uploads").textContent = e.message;
  }
};

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[char]));
}

async function poll(jobId) {
  for (;;) {
    const job = await request(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
    $("job").textContent = `${job.status} — ${job.progress}% — ${job.message}`;
    if (job.status === "completed") return job;
    if (job.status === "failed") throw new Error(job.error || "Job failed");
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
}

$("analyze").onclick = async () => {
  try {
    if (!persistentStorage) {
      throw new Error("Persistent storage is not enabled. Uploads are not durable; analysis is blocked for release safety.");
    }
    const job = await request(`/api/v1/projects/${projectId}/analyze`, { method: "POST" });
    const done = await poll(job.id);
    $("result").textContent = JSON.stringify(done.result, null, 2);
    $("render").disabled = false;
  } catch (e) { $("job").textContent = e.message; }
};

$("render").onclick = async () => {
  try {
    const job = await request(`/api/v1/projects/${projectId}/render`, { method: "POST" });
    await poll(job.id);
    const link = $("download");
    link.href = `${API}/api/v1/projects/${projectId}/output`;
    link.hidden = false;
  } catch (e) { $("job").textContent = e.message; }
};

$("direct").onclick = async () => {
  try {
    const text = $("instruction").value.trim();
    if (!text) throw new Error("Enter a creative direction.");
    const data = await request(`/api/v1/projects/${projectId}/director`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction: text }),
    });
    $("direction").textContent = JSON.stringify(data, null, 2);
    if (data.timeline) {
      $("result").textContent = JSON.stringify(data.timeline, null, 2);
      $("render").disabled = false;
    }
  } catch (e) { $("direction").textContent = e.message; }
};

request("/health")
  .then((data) => {
    persistentStorage = Boolean(data.persistent_storage);
    $("health").textContent = persistentStorage ? "API online • storage persistent" : "API online • storage NOT persistent";
    if (!persistentStorage) {
      $("health").classList.add("warning");
    }
  })
  .catch(() => { $("health").textContent = "API offline"; });
