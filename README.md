# WorkSight Command Deck

WorkSight is a privacy-safe team productivity analytics prototype for camera-based software and IT workspaces.

It focuses on:
- Team-level productivity visibility
- Workflow interruption analytics
- Shift-level progress insights
- Portfolio-level camera ranking and trend tracking
- Camera health heartbeat and event intelligence
- YOLO-capable activity class detection from live camera frames
- Live baseline calibration and evidence scoring from real camera stream
- Strict single-person mode for selfie-style demos
- Face and eye tracking with eye-closure timer
- Eye-closure idle rule: if eyes remain closed for >10s, worker is marked idle
- Live evidence strip snapshots with timestamps and provenance badges
- Optional person YOLO model path for stronger worker localization
- Timeline line charts for utilization/progress/interruption trends
- No facial recognition and no individual payroll actions

## Features

- `POST /vision/mock-infer`: Generate realistic mock CV detections for a camera stream
- `POST /vision/analyze-camera-frame`: Analyze a real webcam frame sent from browser
- `POST /vision/reset-live-session`: Reset per-camera live calibration baseline
- `POST /analysis/ingest`: Analyze frame batches for utilization, progress, and interruption alerts
- `POST /analysis/report`: Build shift report insights from frame data
- `POST /analytics/portfolio`: Cross-camera performance ranking and fleet score
- `POST /analytics/camera-health`: Online/delayed/offline camera health and reliability
- `POST /analytics/event-feed`: Time-ordered warning/critical/info event feed
- `POST /analytics/trends`: Per-camera utilization/progress/interruption trend points
- `POST /copilot/judge-wow`: Kimi-powered judge surprise one-liner, pitch, and live script
- `POST /manager/report/latest`: Manager-facing rolling 2-minute worker report
- `POST /manager/chat`: Manager chat query (supports time windows like `4:01 to 4:05`)
- Built-in dashboard at `/` for one-click demo

## Manager Assistant Key Setup (Backend Only)

Manager endpoints no longer take API keys from browser input.

Configure server-side environment variables once:

- `OPENROUTER_API_KEY`: primary key used by manager assistant
- `OPENROUTER_BASE_URL` (optional): default `https://openrouter.ai/api/v1`
- `OPENROUTER_MODEL` (optional): default `qwen/qwen3.6-plus:free`

Fallback variables still supported on backend:

- `KIMI_API_KEY`, `KIMI_BASE_URL`, `KIMI_MODEL`
- `NVCF_RUN_KEY` or `NVIDIA_API_KEY` for NVIDIA hosted calls

## Kimi Judge Surprise Mode

Set these optional environment variables for live Kimi output:

- `KIMI_API_KEY`: your Moonshot/Kimi API key
- `KIMI_MODEL`: model name (default `moonshot-v1-8k`)
- `KIMI_BASE_URL`: API base URL (default `https://api.moonshot.cn/v1`)

If Kimi is unavailable, WorkSight automatically falls back to a local judge brief so demo flow never breaks.

NVIDIA NIM compatible setup:

- Local NIM (from NVIDIA container): set `KIMI_BASE_URL=http://127.0.0.1:8000/v1`
- Local NIM model name: set `KIMI_MODEL=moonshotai/kimi-k2.5`
- Local NIM usually does not require an API key for localhost calls
- Hosted NVIDIA API: set either `NVCF_RUN_KEY` or `NVIDIA_API_KEY`

## Manager Monitoring MVP

- Worker-side camera feeds are analyzed continuously.
- Backend keeps a timeline of worker activity events.
- Manager panel auto-refreshes 2-minute reports while live capture is running.
- Manager can ask natural-language questions such as `at 4:01 to 4:05 what he did?`.

Live camera responses now include explicit provenance fields:
- `data_source: live-camera`
- `is_mock: false`
- `single_person_mode_applied`
- `activity_index_pct` from observed activity

Task progress is intentionally conservative:
- If `tasks_planned` is not provided, `progress_pct` stays `0` and UI shows activity index instead.
- This avoids synthetic progress numbers when no real plan data is connected.

## Accuracy Controls

- Enable **Strict Single-Person Mode** in live panel for one-person camera views.
- Use **Reset Live Baseline** before each judge run.
- Keep **Mock** buttons only for fallback demo path, not the final live judging path.

## YOLO Activity Model

- Place ONNX model and class labels in [backend/app/models/README.md](backend/app/models/README.md) described location.
- If model files are absent, worker detection falls back to HOG/face-body/contour plus eye-idle tracking and app remains functional.

## Project Structure

- `backend/app/main.py`: FastAPI routes and UI mounting
- `backend/app/schemas.py`: Data contracts for frames, detections, and reports
- `backend/app/services/vision_pipeline.py`: Mock computer-vision inference generator
- `backend/app/services/progress_engine.py`: Progress/interruption scoring and report insights
- `backend/app/data/seed_data.json`: Demo frame data and mock inference requests
- `backend/app/ui/`: Dashboard frontend

## Run (Windows PowerShell)

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

## Deploy Free on Render (One-Click Blueprint)

This repository now includes `render.yaml` at project root.

Steps:

1. Push latest code to GitHub.
2. In Render, click **New +** -> **Blueprint**.
3. Select this repo and branch.
4. Render will detect `render.yaml` and create one free Python web service.
5. Set secret env var `OPENROUTER_API_KEY` in Render dashboard.
6. Deploy and open your Render URL.

Blueprint config uses:

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health path: `/health`

Note: live camera capture still runs from end-user browser and sends frames to backend APIs.

## Demo Flow (Live Evidence First)

1. Open **Live Camera Analysis** and click **Start Camera**.
2. Let calibration run for around 8 frames.
3. Show the **Evidence score**, **Data mode**, and **Calibration** badges.
4. Move workers/persons in frame and show tracked IDs + utilization/progress updates.
5. Click **Refresh Advanced Analytics** to show trends/events from real captured history.

## Optional Demo Data Flow

1. Click **Load Seed Frames**.
2. Click **Run Mock Vision Inference**.
3. Click **Analyze Progress**.
4. Click **Generate Shift Report**.

## Live Camera Flow

1. Open dashboard in browser and allow camera permission.
2. In **Live Camera Analysis**, configure camera/task fields.
3. Click **Start Camera**.
4. The app captures frames at interval and calls `/vision/analyze-camera-frame`.
5. Evidence-calibrated camera analysis rows and summary update in near real time.

## Guardrails

- Designed for team-level analytics
- Does not identify people by face or name
- Does not automate salary deductions
