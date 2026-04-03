import json
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.schemas import (
    AnalyticsRequest,
    CameraImageAnalysisResponse,
    CameraImageRequest,
    CameraHealthResponse,
    EventFeedResponse,
    IngestRequest,
    IngestResponse,
    MockVisionRequest,
    MockVisionResponse,
    PortfolioResponse,
    ReportRequest,
    ReportResponse,
    TrendResponse,
)
from app.services.camera_analyzer import analyze_camera_image
from app.services.progress_engine import (
    aggregate_analyses,
    analyze_frame,
    analyze_frames,
    build_camera_health,
    build_event_feed,
    build_portfolio_analytics,
    build_report_insights,
    build_trend_response,
)
from app.services.vision_pipeline import mock_infer_frame


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "seed_data.json"
UI_DIR = BASE_DIR / "ui"

app = FastAPI(
    title="WorkSight Progress API",
    description="Privacy-safe AI worker progress and safety analytics",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "service": "WorkSight Progress API",
        "privacy_mode": "team-level-no-face-id",
    }


@app.get("/demo/seed")
def demo_seed() -> Dict[str, Any]:
    if not DATA_PATH.exists():
        raise HTTPException(status_code=404, detail="Seed data not found")

    with DATA_PATH.open("r", encoding="utf-8") as file_pointer:
        return json.load(file_pointer)


@app.post("/vision/mock-infer", response_model=MockVisionResponse)
def vision_mock_infer(request: MockVisionRequest) -> MockVisionResponse:
    return MockVisionResponse(frame=mock_infer_frame(request))


@app.post("/vision/analyze-camera-frame", response_model=CameraImageAnalysisResponse)
def vision_analyze_camera_frame(request: CameraImageRequest) -> CameraImageAnalysisResponse:
    frame, detector, motion_score = analyze_camera_image(request)
    analysis = analyze_frame(frame)
    classes_detected = sorted({detection.category for detection in frame.detections})
    safety_detections = sum(
        1
        for detection in frame.detections
        if detection.category in {"helmet", "no_helmet", "phone_use", "restricted_zone_entry"}
    )

    return CameraImageAnalysisResponse(
        frame=frame,
        analysis=analysis,
        detector=detector,
        motion_score=motion_score,
        safety_detections=safety_detections,
        classes_detected=classes_detected,
    )


@app.post("/analysis/ingest", response_model=IngestResponse)
def analysis_ingest(request: IngestRequest) -> IngestResponse:
    analyses = [analyze_frame(frame) for frame in request.frames]
    summary = aggregate_analyses(analyses)

    return IngestResponse(analyses=analyses, summary=summary)


@app.post("/analysis/report", response_model=ReportResponse)
def analysis_report(request: ReportRequest) -> ReportResponse:
    analyses = [analyze_frame(frame) for frame in request.frames]
    summary = aggregate_analyses(analyses)
    insights = build_report_insights(analyses, summary)

    return ReportResponse(summary=summary, insights=insights)


@app.post("/analytics/portfolio", response_model=PortfolioResponse)
def analytics_portfolio(request: AnalyticsRequest) -> PortfolioResponse:
    analyses = analyze_frames(request.frames)
    return build_portfolio_analytics(request.frames, analyses)


@app.post("/analytics/camera-health", response_model=CameraHealthResponse)
def analytics_camera_health(request: AnalyticsRequest) -> CameraHealthResponse:
    analyses = analyze_frames(request.frames)
    return build_camera_health(request.frames, analyses)


@app.post("/analytics/event-feed", response_model=EventFeedResponse)
def analytics_event_feed(request: AnalyticsRequest) -> EventFeedResponse:
    analyses = analyze_frames(request.frames)
    return build_event_feed(analyses)


@app.post("/analytics/trends", response_model=TrendResponse)
def analytics_trends(request: AnalyticsRequest) -> TrendResponse:
    analyses = analyze_frames(request.frames)
    return build_trend_response(request.frames, analyses)


if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
