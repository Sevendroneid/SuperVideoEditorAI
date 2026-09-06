const API = window.SUPERVIDEO_API || "https://supervideoeditorai-api-v2.onrender.com";
const CHUNK_SIZE = 40 * 1024 * 1024;
let projectId = null;
let persistentStorage = false;
const $ = (id) => document.getElementById(id);

async function request(path, options = {}, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(`${API}${path}`, options);
      const text = await response.text();
      let data;
      try { data = JSON.parse(text); } catch { data = { detail: text }; }
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      return data;
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, 1500 * attempt));
    }
  }
  throw lastError;
}

function setProject(id) {
  projectId = id;
  $("project").textContent = id;
  [$("upload"), $("analyze"), $("direct")].forEach((el) => el.disabled = false);
}

function resumableUpload(file, session, index, totalFiles) {
  return new Promise((resolve, reject) => {
    if (!window.tus) return reject(new Error("Resumable upload engine failed to load. Refresh and try again."));
    if (!session.resumable_endpoint || !session.token || session.token.split(".").length !== 3) {
      return reject(new Error("Server returned an invalid signed upload token. Please refresh and retry."));
    }
    const upload = new tus.Upload(file, {
      endpoint: session.resumable_endpoint,
      chunkSize: 6 * 1024 * 1024,
      retryDelays: [0, 3000, 5000, 10000, 20000],
      headers: { "x-signature": session.token, "x-upsert": "true" },
      uploadDataDuringCreation: true,
      removeFingerprintOnSuccess: true,
      metadata: { bucketName: "supervideo", objectName: session.path, contentType: file.type || "video/mp4", cacheControl: "3600" },
      onError: (error) => reject(error),
      onProgress: (bytesUploaded, bytesTotal) => {
        const percent = Math.floor((bytesUploaded / bytesTotal) * 100);
        $("uploads").children[index].textContent = `Uploading ${file.name} — ${percent}% (${index + 1}/${totalFiles})`;
      },
      onSuccess: () => resolve(),
    });
    upload.start();
  });
}

function signedDirectUpload(file, session, index, totalFiles, label = file.name) {
  return new Promise((resolve, reject) => {
    if (!session.signed_url || !session.signed_url.includes("token=")) return reject(new Error("Server did not return a valid signed upload URL."));
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", session.signed_url, true);
    xhr.setRequestHeader("Content-Type", file.type || "video/mp4");
    xhr.setRequestHeader("x-upsert", "true");
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.floor((event.loaded / event.total) * 100);
      $("uploads").children[index].textContent = `Uploading ${label} — ${percent}% (${index + 1}/${totalFiles})`;
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Signed upload failed: HTTP ${xhr.status}${xhr.responseText ? ` — ${xhr.responseText.slice(0, 240)}` : ""}`));
    };
    xhr.onerror = () => reject(new Error("Network error while uploading directly to storage."));
    xhr.onabort = () => reject(new Error("Upload was cancelled."));
    xhr.send(file);
  });
}

async function uploadChunked(file, index, totalFiles) {
  const partCount = Math.ceil(file.size / CHUNK_SIZE);
  const parts = [];
  for (let partIndex = 0; partIndex < partCount; partIndex += 1) {
    const start = partIndex * CHUNK_SIZE;
    const end = Math.min(file.size, start + CHUNK_SIZE);
    const chunk = file.slice(start, end);
    const session = await request(`/api/v1/projects/${projectId}/clips/chunk-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, size: file.size, part_index: partIndex, part_count: partCount }),
    });
    const label = `${file.name} — part ${partIndex + 1}/${partCount}`;
    $("uploads").children[index].textContent = `Uploading ${label} — 0% (${index + 1}/${totalFiles})`;
    await signedDirectUpload(chunk, session, index, totalFiles, label);
    parts.push(session.path);
  }
  const manifestPath = `${projectId}/${crypto.randomUUID()}.parts.json`;
  return await request(`/api/v1/projects/${projectId}/clips/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, storage_path: manifestPath, bytes: file.size, parts }),
  });
}

async function uploadWithResumableFallback(file, session, index, totalFiles) {
  try {
    await resumableUpload(file, session, index, totalFiles);
    return "resumable";
  } catch (tusError) {
    $("uploads").children[index].textContent = `Resumable upload unavailable; switching to secure direct upload — ${file.name}`;
    await signedDirectUpload(file, session, index, totalFiles);
    return "signed-direct";
  }
}

$("create").onclick = async () => {
  try {
    const data = await request("/api/v1/projects", { method: "POST" });
    setProject(data.project_id);
    $("job").textContent = persistentStorage ? "Project ready. Persistent storage is enabled." : "Project ready. WARNING: persistent storage is not enabled.";
  } catch (e) { $("job").textContent = e.message; }
};

$("upload").onclick = async () => {
  if (!projectId) return;
  const files = [...$("files").files];
  if (!files.length) { $("uploads").textContent = "Select at least one video."; return; }
  $("uploads").innerHTML = files.map((file) => `<div class="item">Preparing ${escapeHtml(file.name)}…</div>`).join("");
  let success = 0;
  let directFallbacks = 0;
  let chunkedUploads = 0;
  for (let index = 0; index < files.length; index += 1) {
    const file = files[index];
    try {
      if (file.size > CHUNK_SIZE) {
        const result = await uploadChunked(file, index, files.length);
        success += 1;
        chunkedUploads += 1;
        $("uploads").children[index].textContent = `✓ ${result.filename} — ${result.bytes} bytes — persistent (chunked)`;
        continue;
      }
      const session = await request(`/api/v1/projects/${projectId}/clips/upload-session?filename=${encodeURIComponent(file.name)}&size=${file.size}`, { method: "POST" });
      $("uploads").children[index].textContent = `Uploading ${file.name} — 0% (${index + 1}/${files.length})`;
      const uploadMode = await uploadWithResumableFallback(file, session, index, files.length);
      const result = await request(`/api/v1/projects/${projectId}/clips/complete`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, storage_path: session.path, bytes: file.size }),
      });
      success += 1;
      if (uploadMode === "signed-direct") directFallbacks += 1;
      const modeLabel = uploadMode === "resumable" ? "resumable" : "secure direct";
      $("uploads").children[index].textContent = `✓ ${result.filename} — ${result.bytes} bytes — persistent (${modeLabel})`;
    } catch (error) {
      $("uploads").children[index].textContent = `✗ ${file.name} — ${error.message}`;
    }
  }
  const notes = [];
  if (directFallbacks) notes.push(`${directFallbacks} secure direct fallback`);
  if (chunkedUploads) notes.push(`${chunkedUploads} chunked`);
  $("job").textContent = `${success}/${files.length} file(s) uploaded successfully.${notes.length ? ` ${notes.join(", ")}.` : ""}`;
};

function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[char])); }

async function poll(jobId, maxMs = 30 * 60 * 1000) {
  const started = Date.now();
  let consecutiveFetchErrors = 0;
  for (;;) {
    if (Date.now() - started > maxMs) throw new Error("Job timed out after 30 minutes. The server did not report completion.");
    try {
      const job = await request(`/api/v1/jobs/${encodeURIComponent(jobId)}`, {}, 4);
      consecutiveFetchErrors = 0;
      $("job").textContent = `${job.status} — ${job.progress}% — ${job.message || ""}`;
      if (job.status === "completed") return job;
      if (job.status === "failed") throw new Error(job.error || "Job failed");
    } catch (error) {
      consecutiveFetchErrors += 1;
      if (consecutiveFetchErrors >= 5) throw new Error(`Unable to read job status: ${error.message}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

$("analyze").onclick = async () => {
  try {
    if (!persistentStorage) throw new Error("Persistent storage is not enabled. Analysis is blocked for release safety.");
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
    const output = await request(`/api/v1/projects/${projectId}/output-url`, {}, 5);
    const link = $("download"); link.href = output.url; link.download = "supervideo-story.mp4";
    link.textContent = "Download / Open rendered MP4"; link.hidden = false;
    $("job").textContent = `${done.message} — video ready`;
  } catch (e) { $("job").textContent = e.message; }
};

$("direct").onclick = async () => {
  try {
    const text = $("instruction").value.trim();
    if (!text) throw new Error("Enter a creative direction.");
    const data = await request(`/api/v1/projects/${projectId}/director`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ instruction: text }),
    });
    $("direction").textContent = JSON.stringify(data, null, 2);
    if (data.timeline) { $("result").textContent = JSON.stringify(data.timeline, null, 2); $("render").disabled = false; }
  } catch (e) { $("direction").textContent = e.message; }
};

request("/health", {}, 5)
  .then((data) => {
    persistentStorage = Boolean(data.persistent_storage);
    $("health").textContent = persistentStorage ? "API online • storage persistent" : "API online • storage NOT persistent";
    if (!persistentStorage) $("health").classList.add("warning");
  })
  .catch((error) => { $("health").textContent = `API offline — ${error.message}`; });
