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
    ResetLiveSessionRequest,
    ResetLiveSessionResponse,
    ReportRequest,
    ReportResponse,
    TrendResponse,
)
from app.services.live_calibrator import live_calibration_store
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
    frame, detector, motion_score, single_person_mode_applied = analyze_camera_image(request)
    analysis = analyze_frame(frame)
    worker_confidences = [
        detection.confidence
        for detection in frame.detections
        if detection.category == "worker"
    ]
    average_worker_confidence = (
        sum(worker_confidences) / len(worker_confidences) if worker_confidences else 0.0
    )

    calibration = live_calibration_store.calibrate(
        camera_id=frame.camera_id,
        timestamp=frame.timestamp,
        worker_count=analysis.worker_count,
        active_workers=analysis.active_workers,
        average_worker_confidence=average_worker_confidence,
        detector=detector,
        expected_workers_input=frame.expected_workers,
        tasks_planned_input=frame.tasks_planned,
        tasks_completed_input=frame.tasks_completed,
    )

    frame.expected_workers = calibration.calibrated_expected_workers

    analysis.utilization_pct = calibration.utilization_pct
    analysis.progress_pct = calibration.progress_pct

    if not calibration.calibration_ready and request.tasks_planned <= 0:
        if "live baseline calibrating" not in analysis.alerts:
            analysis.alerts.append(
                f"live baseline calibrating ({calibration.calibration_frames_remaining} frames remaining)"
            )

    if request.tasks_planned <= 0:
        analysis.alerts.append("task progress is not connected; use activity index for live effort")

    if calibration.evidence_score < 55:
        analysis.alerts.append("evidence confidence is low; improve lighting/camera angle")

    classes_detected = sorted({detection.category for detection in frame.detections})
    eye_idle_workers = sum(
        1
        for detection in frame.detections
        if detection.category == "worker"
        and detection.eyes_closed
        and (detection.eyes_closed_seconds or 0.0) >= 10.0
    )
    hand_break_workers = sum(
        1
        for detection in frame.detections
        if detection.category == "worker"
        and detection.hand_on_keyboard is False
        and (detection.hand_off_keyboard_seconds or 0.0) >= 10.0
    )
    safety_detections = sum(
        1
        for detection in frame.detections
        if detection.category in {"helmet", "no_helmet", "phone_use", "restricted_zone_entry"}
    )

    return CameraImageAnalysisResponse(
        frame=frame,
        analysis=analysis,
        detector=detector,
        data_source="live-camera",
        is_mock=False,
        single_person_mode_applied=single_person_mode_applied,
        eye_idle_workers=eye_idle_workers,
        hand_break_workers=hand_break_workers,
        motion_score=motion_score,
        safety_detections=safety_detections,
        classes_detected=classes_detected,
        evidence_score=calibration.evidence_score,
        activity_index_pct=calibration.activity_index_pct,
        data_mode=calibration.data_mode,
        calibration_ready=calibration.calibration_ready,
        calibration_frames_remaining=calibration.calibration_frames_remaining,
        calibrated_expected_workers=calibration.calibrated_expected_workers,
    )


@app.post("/vision/reset-live-session", response_model=ResetLiveSessionResponse)
def vision_reset_live_session(request: ResetLiveSessionRequest) -> ResetLiveSessionResponse:
    removed = live_calibration_store.reset(request.camera_id)
    return ResetLiveSessionResponse(reset_count=removed)


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
