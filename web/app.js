const API = window.SUPERVIDEO_API || "http://localhost:8000";
let projectId = null;

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
  try { setProject((await request("/api/v1/projects", {method:"POST"})).project_id); $("job").textContent = "Project ready."; }
  catch (e) { $("job").textContent = e.message; }
};
$("upload").onclick = async () => {
  if (!projectId) return;
  $("uploads").textContent = "Uploading…";
  try {
    const files = [...$("files").files];
    if (!files.length) throw new Error("Select at least one video.");
    const results = [];
    for (const file of files) {
      const form = new FormData(); form.append("file", file, file.name);
      results.push(await request(`/api/v1/projects/${projectId}/clips`, {method:"POST", body:form}));
    }
    $("uploads").innerHTML = results.map(r => `<div class="item">✓ ${r.filename} — ${r.bytes} bytes</div>`).join("");
  } catch (e) { $("uploads").textContent = e.message; }
};
async function poll(jobId) {
  for (;;) {
    const job = await request(`/api/v1/jobs/${jobId}`);
    $("job").textContent = `${job.status} — ${job.progress}% — ${job.message}`;
    if (job.status === "completed") return job;
    if (job.status === "failed") throw new Error(job.error || "Job failed");
    await new Promise(r => setTimeout(r, 1200));
  }
}
$("analyze").onclick = async () => {
  try {
    const job = await request(`/api/v1/projects/${projectId}/analyze`, {method:"POST"});
    const done = await poll(job.id);
    $("result").textContent = JSON.stringify(done.result, null, 2);
    $("render").disabled = false;
  } catch (e) { $("job").textContent = e.message; }
};
$("render").onclick = async () => {
  try {
    const job = await request(`/api/v1/projects/${projectId}/render`, {method:"POST"});
    await poll(job.id);
    const link = $("download"); link.href = `${API}/api/v1/projects/${projectId}/output`; link.hidden = false;
  } catch (e) { $("job").textContent = e.message; }
};
$("direct").onclick = async () => {
  try {
    const text = $("instruction").value.trim();
    if (!text) throw new Error("Enter a creative direction.");
    const data = await request(`/api/v1/projects/${projectId}/director?instruction=${encodeURIComponent(text)}`, {method:"POST"});
    $("direction").textContent = JSON.stringify(data, null, 2);
  } catch (e) { $("direction").textContent = e.message; }
};
request("/health").then(() => $("health").textContent = "API online").catch(() => $("health").textContent = "API offline");
