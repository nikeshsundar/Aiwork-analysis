import json
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.schemas import (
    AnalyticsRequest,
    BottleneckGraphResponse,
    CameraImageAnalysisResponse,
    CameraImageRequest,
    CameraHealthResponse,
    EventFeedResponse,
    FlowRecoveryResponse,
    IngestRequest,
    IngestResponse,
    JudgeWowRequest,
    JudgeWowResponse,
    ManagerChatRequest,
    ManagerChatResponse,
    ManagerReportRequest,
    ManagerReportResponse,
    MockVisionRequest,
    MockVisionResponse,
    PortfolioResponse,
    PrivacyChallengeRequest,
    PrivacyChallengeResponse,
    PrivacyProofResponse,
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
from app.services.novelty_engine import (
    build_flow_recovery_copilot,
    build_privacy_proof_layer,
    build_team_bottleneck_graph,
    privacy_challenge_store,
)
from app.services.kimi_copilot import build_judge_wow_response
from app.services.manager_assistant import (
    TimelineEvent,
    build_manager_chat_answer,
    build_manager_two_minute_report,
    manager_timeline_store,
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
        if detection.category in {"phone_use", "no_helmet", "restricted_zone_entry"}
    )

    manager_timeline_store.ingest(
        TimelineEvent(
            timestamp=frame.timestamp,
            camera_id=frame.camera_id,
            site_area=frame.site_area,
            worker_count=analysis.worker_count,
            active_workers=analysis.active_workers,
            utilization_pct=analysis.utilization_pct,
            progress_pct=analysis.progress_pct,
            interruptions=analysis.safety_violations,
            alerts=list(analysis.alerts),
            eye_idle_workers=eye_idle_workers,
            hand_break_workers=hand_break_workers,
            activity_index_pct=calibration.activity_index_pct,
            evidence_score=calibration.evidence_score,
        )
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


@app.post("/copilot/flow-recovery", response_model=FlowRecoveryResponse)
def copilot_flow_recovery(request: AnalyticsRequest) -> FlowRecoveryResponse:
    analyses = analyze_frames(request.frames)
    return build_flow_recovery_copilot(analyses)


@app.post("/copilot/bottleneck-graph", response_model=BottleneckGraphResponse)
def copilot_bottleneck_graph(request: AnalyticsRequest) -> BottleneckGraphResponse:
    analyses = analyze_frames(request.frames)
    return build_team_bottleneck_graph(request.frames, analyses)


@app.post("/copilot/judge-wow", response_model=JudgeWowResponse)
def copilot_judge_wow(request: JudgeWowRequest) -> JudgeWowResponse:
    analyses = analyze_frames(request.frames)
    summary = aggregate_analyses(analyses)
    return build_judge_wow_response(
        frames=request.frames,
        analyses=analyses,
        summary=summary,
        judge_focus=request.judge_focus,
        demo_context=request.demo_context,
        api_key=request.api_key,
        base_url=request.base_url,
        model=request.model,
    )


@app.post("/manager/report/latest", response_model=ManagerReportResponse)
def manager_report_latest(request: ManagerReportRequest) -> ManagerReportResponse:
    return build_manager_two_minute_report(
        camera_id=request.camera_id,
    )


@app.post("/manager/chat", response_model=ManagerChatResponse)
def manager_chat(request: ManagerChatRequest) -> ManagerChatResponse:
    return build_manager_chat_answer(
        question=request.question,
        camera_id=request.camera_id,
    )


@app.post("/trust/privacy-proof", response_model=PrivacyProofResponse)
def trust_privacy_proof(request: AnalyticsRequest) -> PrivacyProofResponse:
    analyses = analyze_frames(request.frames)
    return build_privacy_proof_layer(request.frames, analyses)


@app.post("/trust/privacy-proof/challenge", response_model=PrivacyChallengeResponse)
def trust_privacy_proof_challenge(request: PrivacyChallengeRequest) -> PrivacyChallengeResponse:
    return privacy_challenge_store.create(request)


if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
