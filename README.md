# WorkSight Command Deck

WorkSight turns live camera activity into manager-ready decisions.

Think of it as a mission control room for team execution: live signals in, clear managerial actions out.

It is a privacy-first AI operations intelligence platform designed for software and IT workplaces where managers need fast, evidence-backed answers, not delayed manual status updates.

## What This Project Is

WorkSight is not a simple camera dashboard.

It is an end-to-end operational intelligence system that:

- observes worker activity signals from live frames,
- converts those signals into utilization/progress/interruption metrics,
- builds short rolling reports every 2 minutes,
- answers manager questions like `from 4:01 to 4:05 what happened?`,
- recommends flow recovery actions,
- maps bottlenecks,
- and proves privacy posture with an audit-ready trust layer.

In short: WorkSight is a manager copilot for real-time team execution.

## 60-Second Pitch (Judge Mode)

WorkSight is a privacy-first AI command deck for software teams. We capture live activity signals from worker-side camera feeds, convert them into utilization, progress, and interruption intelligence, then auto-generate 2-minute manager reports. The manager can ask plain questions like "from 4:01 to 4:05 what happened" and receive evidence-backed answers from the real timeline. Beyond monitoring, WorkSight recommends flow recovery actions, maps bottlenecks, and provides a privacy proof layer with challenge workflow. Even if external AI is unavailable, local fallback keeps reporting and Q&A online. This is not surveillance software. It is operational decision intelligence with trust by design.

## Why It Matters

Most teams either rely on manual standups or noisy surveillance-like feeds.

WorkSight provides a better path:

- measurable, team-level productivity visibility,
- interruption awareness,
- trend and health intelligence across camera zones,
- operational guidance with fallback reliability,
- privacy guardrails by design.

## Signature Experience

1. Start live camera analysis from the dashboard.
2. WorkSight calibrates a baseline and begins scoring activity confidence.
3. Live metrics update: workers, utilization, progress, interruptions.
4. Timeline events are stored continuously for manager reasoning.
5. Manager panel auto-refreshes 2-minute reports.
6. Manager asks natural-language questions over exact time windows.
7. Advanced copilot modules suggest flow recovery and bottleneck fixes.
8. Privacy proof and challenge workflow close the trust loop.

## Feature Highlights

### 1) Live Vision + Activity Intelligence

- Real webcam frame analysis via `/vision/analyze-camera-frame`
- Motion scoring and worker tracking overlays
- Eye-idle and keyboard-break behavior signals
- Strict single-person mode for controlled demos
- Detector provenance and confidence-aware evidence scoring

### 2) Live Calibration and Evidence Quality

- Per-camera baseline calibration
- Dynamic expected worker adjustment
- `data_mode`, `calibration_ready`, `calibration_frames_remaining`
- Evidence score alerts for poor camera conditions

### 3) Manager Monitoring MVP

- Automatic timeline ingestion from worker-side live analysis
- Rolling 2-minute manager report via `/manager/report/latest`
- Manager Q&A via `/manager/chat`
- Time-window parsing (for example: `4:01 to 4:05`)
- Local deterministic fallback when external LLM is unavailable

### 4) Advanced Analytics Suite

- Portfolio ranking and fleet score via `/analytics/portfolio`
- Camera health status via `/analytics/camera-health`
- Event stream intelligence via `/analytics/event-feed`
- Utilization/progress/interruption trends via `/analytics/trends`

### 5) Copilot Intelligence Modules

- Flow recovery copilot via `/copilot/flow-recovery`
- Team bottleneck graph via `/copilot/bottleneck-graph`
- Judge wow narrative mode via `/copilot/judge-wow`

### 6) Privacy-First Trust Layer

- Privacy proof report via `/trust/privacy-proof`
- Challenge channel via `/trust/privacy-proof/challenge`
- No face ID, no identity payroll actions, team-level analytics focus

### 7) Reliable UX Under Demo Pressure

- Manager quick-ask chips if typing is blocked in embedded browsers
- Backend-only API key strategy (no key entry required in manager UI)
- Render-safe client behavior with retries for transient upstream failures

## API Surface

### Core

- `GET /health`
- `GET /demo/seed`

### Vision

- `POST /vision/mock-infer`
- `POST /vision/analyze-camera-frame`
- `POST /vision/reset-live-session`

### Analysis and Reporting

- `POST /analysis/ingest`
- `POST /analysis/report`

### Analytics

- `POST /analytics/portfolio`
- `POST /analytics/camera-health`
- `POST /analytics/event-feed`
- `POST /analytics/trends`

### Copilot

- `POST /copilot/flow-recovery`
- `POST /copilot/bottleneck-graph`
- `POST /copilot/judge-wow`

### Manager and Trust

- `POST /manager/report/latest`
- `POST /manager/chat`
- `POST /trust/privacy-proof`
- `POST /trust/privacy-proof/challenge`

## AI Configuration

Manager copilot uses backend-managed LLM settings only.

Primary variables:

- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL` (default `https://openrouter.ai/api/v1`)
- `OPENROUTER_MODEL` (default `qwen/qwen3.6-plus:free`)

Fallback-compatible variables are also supported:

- `KIMI_API_KEY`, `KIMI_BASE_URL`, `KIMI_MODEL`
- `NVCF_RUN_KEY` or `NVIDIA_API_KEY`

If external LLM calls fail, manager report/chat still return local fallback answers.

## Local Run (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

- Dashboard: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`

## Free Deploy on Render (Blueprint)

This repo includes `render.yaml` for one-click deployment.

Steps:

1. Push this repo to GitHub.
2. In Render, click **New +** then **Blueprint**.
3. Select repo and branch.
4. Render auto-detects `render.yaml`.
5. Add secret env var `OPENROUTER_API_KEY`.
6. Deploy.

Configured by blueprint:

- root dir: `backend`
- build: `pip install -r requirements.txt`
- start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- health check: `/health`

## Judge Demo Script (Animative, 2-3 Min)

1. Open with the "problem moment": managers usually guess status from fragmented updates.
2. Start live camera and narrate the calibration moment: "system is learning baseline confidence in real time."
3. Show live cards updating (workers, utilization, progress, interruptions) and call out evidence score.
4. Trigger Advanced Analytics and walk left-to-right: portfolio ranking, camera health, event feed, trend direction.
5. Open Flow Recovery Copilot and Bottleneck Graph as the "decision engine" layer.
6. Hit Manager Report and highlight that reports are automatic every 2 minutes.
7. Ask a time-window question in Manager Chat and show supporting points from the timeline.
8. Close on trust: open Privacy Proof, mention challenge workflow, and emphasize no face-ID policy.
9. Final line: "WorkSight turns live activity into accountable action, not just observation."

## Guardrails

- Team-level analytics only
- No face identity recognition
- No person-name linkage
- No salary deduction automation
- Transparent confidence and fallback behavior

## Project Structure

- `backend/app/main.py`: FastAPI routing and orchestration
- `backend/app/schemas.py`: API contracts
- `backend/app/services/camera_analyzer.py`: live camera analysis pipeline
- `backend/app/services/progress_engine.py`: utilization/progress/interruption scoring
- `backend/app/services/manager_assistant.py`: timeline store, report, and Q&A logic
- `backend/app/services/novelty_engine.py`: flow recovery, bottleneck, privacy proof
- `backend/app/services/kimi_copilot.py`: judge wow narrative generation
- `backend/app/ui/`: manager-facing dashboard
- `backend/app/data/seed_data.json`: demo data

## One-Line Pitch

WorkSight is a privacy-safe manager copilot that converts live worker activity into actionable 2-minute decisions, explainable Q&A, and trust-ready analytics.