# WorkSight Command Deck

WorkSight is a privacy-safe worker progress analytics prototype for camera-based operations in construction, manufacturing, and office environments.

It focuses on:
- Team-level productivity visibility
- Safety compliance analytics
- Shift-level progress insights
- Portfolio-level camera ranking and trend tracking
- Camera health heartbeat and event intelligence
- YOLO-capable safety class detection from live camera frames
- Timeline line charts for utilization/progress/safety trends
- No facial recognition and no individual payroll actions

## Features

- `POST /vision/mock-infer`: Generate realistic mock CV detections for a camera stream
- `POST /vision/analyze-camera-frame`: Analyze a real webcam frame sent from browser
- `POST /analysis/ingest`: Analyze frame batches for utilization, progress, and safety alerts
- `POST /analysis/report`: Build shift report insights from frame data
- `POST /analytics/portfolio`: Cross-camera performance ranking and fleet score
- `POST /analytics/camera-health`: Online/delayed/offline camera health and reliability
- `POST /analytics/event-feed`: Time-ordered warning/critical/info event feed
- `POST /analytics/trends`: Per-camera utilization/progress/safety trend points
- Built-in dashboard at `/` for one-click demo

## YOLO Safety Model

- Place ONNX model and class labels in [backend/app/models/README.md](backend/app/models/README.md) described location.
- If model files are absent, worker detection falls back to HOG/contour and app remains functional.

## Project Structure

- `backend/app/main.py`: FastAPI routes and UI mounting
- `backend/app/schemas.py`: Data contracts for frames, detections, and reports
- `backend/app/services/vision_pipeline.py`: Mock computer-vision inference generator
- `backend/app/services/progress_engine.py`: Progress/safety scoring and report insights
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

## Demo Flow

1. Click **Load Seed Frames**
2. Click **Run Mock Vision Inference**
3. Click **Analyze Progress**
4. Click **Generate Shift Report**

## Live Camera Flow

1. Open dashboard in browser and allow camera permission.
2. In **Live Camera Analysis**, configure camera/task fields.
3. Click **Start Camera**.
4. The app captures frames at interval and calls `/vision/analyze-camera-frame`.
5. Camera analysis rows and summary update in near real time.

## Guardrails

- Designed for team-level analytics
- Does not identify people by face or name
- Does not automate salary deductions
