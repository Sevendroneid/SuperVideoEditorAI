# Real-world test

## Preconditions

- Docker Desktop or Docker Engine with Compose is installed for local verification.
- The repository is cloned locally.
- At least one short test video exists locally.
- No paid AI provider is required for the deterministic baseline pipeline.

## Production target

The current production API target is the persistent Render service:

`https://supervideoeditorai-api-v2.onrender.com`

The frontend uses the same API by default. The v4 Render service is retained as a diagnostic/development deployment and is not the release target because its current environment does not expose persistent Supabase storage.

## Start

```bash
cp .env.example .env
bash scripts/setup.sh
```

Open `http://localhost:3000`.

## Test sequence

1. Click **Create Project**.
2. Select one or more MP4/MOV/MKV/WebM/M4V/AVI files.
3. Upload them.
4. Click **Analyze Footage**.
5. Wait for `completed` and inspect the returned clip/segment/timeline evidence.
6. Click **Render MP4**.
7. Open the rendered video link.
8. Enter a director instruction. With `AI_PROVIDER=disabled`, the system must explicitly report that the deterministic baseline was retained; it must not pretend an AI provider ran.

## API checks

- `GET /health` must return HTTP 200 and `status=ok`.
- `/health` must report both `persistent_storage=true` and `ffmpeg_ready=true` in the production target.
- `POST /api/v1/projects` creates a project.
- Upload rejects unsupported extensions with HTTP 415.
- Upload rejects files above `MAX_UPLOAD_BYTES` with HTTP 413.
- Analysis is queued with HTTP 202.
- Render is blocked with HTTP 409 until analysis exists.
- Output is HTTP 404 until rendering completes.

## Evidence required for release

A real-world release is not considered verified until all of these are observed:

- API health succeeds.
- A real video upload succeeds and is persistent.
- Analysis creates `analysis.json` containing clip and segment evidence.
- The timeline contains valid segment boundaries.
- The analysis job reaches `completed`.
- The render job reaches `completed` and produces an MP4 from the timeline.
- The resulting MP4 can be opened and inspected.
- CI reports passing automated tests.
- The public-preview workflow passes the complete upload → analysis → director → render → MP4 verification when run with `[preview-ci]` or manually from GitHub Actions.

The production Render service currently executes the heavy analysis/render task through the FastAPI background-task path. Celery task definitions remain available for the Docker/worker deployment profile.

The baseline is intentionally deterministic. Cinematic AI, generative video/image adapters, speech-to-text, embeddings, and advanced story reasoning must be added only after this pipeline is proven with real footage.
