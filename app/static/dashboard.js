const form = document.getElementById("generate-form");
const submitButton = document.getElementById("submit-button");
const submitStatus = document.getElementById("submit-status");
const jobsList = document.getElementById("jobs-list");
const jobsEmpty = document.getElementById("jobs-empty");
const refreshButton = document.getElementById("refresh-jobs");

const ACTIVE_STATUSES = new Set(["queued", "planning", "generating", "assembling"]);

function setStatus(message, tone = "idle") {
  submitStatus.textContent = message;
  submitStatus.dataset.tone = tone;
}

function timeLabel(value) {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function renderJobs(jobs) {
  jobsList.innerHTML = "";
  jobsEmpty.style.display = jobs.length ? "none" : "block";

  jobs.forEach((job) => {
    const card = document.createElement("article");
    card.className = "job-card";
    const spec = job.runner_spec || {};
    const playLink = job.play_url ? `<a href="${job.play_url}" target="_blank" rel="noreferrer">Open game</a>` : "";
    const manifestLink = job.manifest_url ? `<a href="${job.manifest_url}" target="_blank" rel="noreferrer">Manifest</a>` : "";
    const rawJobLink = `<a href="/games/${job.job_id}" target="_blank" rel="noreferrer">Job JSON</a>`;
    const planSummary = job.asset_plan
      ? `${job.asset_plan.obstacles.length} obstacles, ${job.asset_plan.backgrounds.length} backgrounds`
      : "Planning assets";
    const validation = job.validation
      ? `<span>Validation ${(job.validation.coherence_score * 100).toFixed(0)}%</span>`
      : "";
    card.innerHTML = `
      <div class="job-card__header">
        <div>
          <p class="job-card__eyebrow">${job.job_id.slice(0, 8)}</p>
          <h3>${spec.title || "Game generation job"}</h3>
        </div>
        <span class="job-badge job-badge--${job.status}">${job.status}</span>
      </div>
      <p class="job-card__prompt">${job.request.prompt}</p>
      <div class="job-meta">
        <span>Difficulty ${job.request.difficulty}</span>
        <span>Audience ${job.request.audience}</span>
        <span>${job.request.session_length_sec}s</span>
        <span>${planSummary}</span>
        ${validation}
      </div>
      ${job.error ? `<p class="job-error">${job.error}</p>` : ""}
      <div class="job-links">
        ${playLink}
        ${manifestLink}
        ${rawJobLink}
      </div>
      <p class="job-updated">Updated ${timeLabel(job.updated_at)}</p>
    `;
    jobsList.appendChild(card);
  });
}

async function fetchJobs() {
  const response = await fetch("/games");
  if (!response.ok) {
    throw new Error("Failed to load jobs.");
  }
  const jobs = await response.json();
  renderJobs(jobs);
  return jobs;
}

async function pollActiveJobs() {
  try {
    const jobs = await fetchJobs();
    if (jobs.some((job) => ACTIVE_STATUSES.has(job.status))) {
      window.setTimeout(pollActiveJobs, 2000);
    }
  } catch (_) {
    window.setTimeout(pollActiveJobs, 2500);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  setStatus("Uploading", "busy");

  const payload = new FormData(form);

  try {
    const response = await fetch("/games/generate-form", {
      method: "POST",
      body: payload,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({ detail: "Generation failed." }));
      throw new Error(detail.detail || "Generation failed.");
    }
    const job = await response.json();
    setStatus(`Queued ${job.job_id.slice(0, 8)}`, "success");
    form.reset();
    await fetchJobs();
    pollActiveJobs();
  } catch (error) {
    setStatus(error.message || "Generation failed", "error");
  } finally {
    submitButton.disabled = false;
  }
});

refreshButton.addEventListener("click", () => {
  setStatus("Refreshing", "idle");
  fetchJobs()
    .then(() => setStatus("Idle", "idle"))
    .catch((error) => setStatus(error.message || "Refresh failed", "error"));
});

fetchJobs().then((jobs) => {
  if (jobs.some((job) => ACTIVE_STATUSES.has(job.status))) {
    pollActiveJobs();
  }
});
