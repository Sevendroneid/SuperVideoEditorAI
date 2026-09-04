# SuperVideoEditorAI

AI Director / AI Visual Storyteller prototype.

## What exists now

The repository contains an executable prototype stack:

- FastAPI API
- Redis + Celery background worker
- FFmpeg/ffprobe processing wrapper
- OpenCV-based deterministic smart-segment scoring
- Evidence-backed baseline story builder
- Timeline JSON as the handoff between reasoning and rendering
- Optional provider-agnostic AI Director HTTP adapter (disabled by default)
- Static dashboard served by Nginx
- Docker Compose development stack
- Pytest suite and GitHub Actions CI

The baseline pipeline does **not** pretend to perform cinematic AI. It uses measurable evidence and clearly labels the deterministic path. The optional AI adapter is disabled until a real provider configuration is supplied.

## Architecture

```text
Browser
  │
  ▼
Nginx dashboard ──────► FastAPI
                           │
                           ├── Project / upload API
                           ├── Job API
                           └── AI Director adapter
                           │
                           ▼
                         Redis
                           │
                           ▼
                     Celery worker
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
        ffprobe + OpenCV          Story planner
              │                         │
              └────────────┬────────────┘
                           ▼
                       Timeline JSON
                           │
                           ▼
                         FFmpeg
                           │
                           ▼
                        MP4 output
```

FastAPI is used for the HTTP layer; heavy work is delegated to Celery rather than held inside a request process. This follows the documented distinction between lightweight background work and heavier distributed task queues. citeturn0search0turn0search1

## Local start

```bash
cp .env.example .env
bash scripts/setup.sh
```

Dashboard: `http://localhost:3000`

API docs: `http://localhost:8000/docs`

Health: `http://localhost:8000/health`

## Test

```bash
python -m pip install -r requirements.txt
pytest -q
```

Or run the full container stack and then:

```bash
bash scripts/smoke_test.sh
```

## Real-world verification

Follow `docs/REAL_WORLD_TEST.md`. A real release is not considered verified merely because source files exist. The required evidence is successful upload, analysis, Celery completion, valid timeline, FFmpeg render, and inspection of the resulting MP4.

## Cost discipline

The default configuration uses no paid AI provider. `AI_PROVIDER=disabled` is intentional. Do not add a paid API key or external service without verifying its current pricing and terms first.

## Current scope boundary

This is the first executable foundation, not the finished commercial editor. Advanced visual semantics, speech transcription, embeddings, relationship graphs, emotional-arc reasoning, conversational timeline mutation, generative image/video adapters, authentication, persistent database storage, and production object storage are subsequent engineering modules. They must be implemented and verified rather than represented by UI claims.
