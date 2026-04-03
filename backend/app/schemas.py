from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


DetectionCategory = Literal[
    "worker",
    "helmet",
    "no_helmet",
    "phone_use",
    "restricted_zone_entry",
    "vehicle",
]

DataMode = Literal["live-calibrated", "manual-assisted"]


class BoundingBox(BaseModel):
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    w: float = Field(..., gt=0, le=1)
    h: float = Field(..., gt=0, le=1)


class Detection(BaseModel):
    category: DetectionCategory
    confidence: float = Field(..., ge=0, le=1)
    bbox: BoundingBox
    face_bbox: Optional[BoundingBox] = None
    zone: Optional[str] = None
    moving: bool = True
    track_id: Optional[str] = Field(default=None, max_length=32)
    face_detected: Optional[bool] = None
    eyes_closed: Optional[bool] = None
    eyes_closed_seconds: Optional[float] = Field(default=None, ge=0, le=600)
    hand_on_keyboard: Optional[bool] = None
    hand_off_keyboard_seconds: Optional[float] = Field(default=None, ge=0, le=600)


class CameraFrame(BaseModel):
    camera_id: str
    timestamp: datetime
    site_area: str = Field(default="general")
    expected_workers: int = Field(default=0, ge=0)
    tasks_planned: int = Field(default=0, ge=0)
    tasks_completed: int = Field(default=0, ge=0)
    detections: List[Detection]


class FrameAnalysis(BaseModel):
    camera_id: str
    timestamp: datetime
    worker_count: int = 0
    active_workers: int = 0
    idle_workers: int = 0
    keyboard_break_workers: int = 0
    utilization_pct: float = Field(default=0, ge=0, le=100)
    progress_pct: float = Field(default=0, ge=0, le=100)
    safety_violations: int = 0
    alerts: List[str] = Field(default_factory=list)


class AnalysisSummary(BaseModel):
    frames_processed: int = 0
    total_workers: int = 0
    total_active_workers: int = 0
    avg_utilization_pct: float = Field(default=0, ge=0, le=100)
    avg_progress_pct: float = Field(default=0, ge=0, le=100)
    safety_violations: int = 0
    privacy_mode: str = "team-level-no-face-id"


class IngestRequest(BaseModel):
    frames: List[CameraFrame]


class IngestResponse(BaseModel):
    analyses: List[FrameAnalysis]
    summary: AnalysisSummary


class AnalyticsRequest(BaseModel):
    frames: List[CameraFrame]


class MockVisionRequest(BaseModel):
    camera_id: str
    site_area: str = "general"
    expected_workers: int = Field(default=10, ge=0)
    people_count: int = Field(default=8, ge=0)
    idle_ratio: float = Field(default=0.2, ge=0, le=1)
    no_helmet_count: int = Field(default=0, ge=0)
    phone_use_count: int = Field(default=0, ge=0)
    restricted_entry_count: int = Field(default=0, ge=0)
    tasks_planned: int = Field(default=10, ge=0)
    tasks_completed: int = Field(default=5, ge=0)


class MockVisionResponse(BaseModel):
    frame: CameraFrame


class CameraImageRequest(BaseModel):
    camera_id: str
    image_base64: str
    previous_image_base64: Optional[str] = None
    site_area: str = "general"
    expected_workers: int = Field(default=10, ge=0)
    tasks_planned: int = Field(default=10, ge=0)
    tasks_completed: int = Field(default=0, ge=0)
    single_person_mode: bool = False


class CameraImageAnalysisResponse(BaseModel):
    frame: CameraFrame
    analysis: FrameAnalysis
    detector: str
    data_source: Literal["live-camera"] = "live-camera"
    is_mock: bool = False
    single_person_mode_applied: bool = False
    eye_idle_workers: int = Field(default=0, ge=0)
    hand_break_workers: int = Field(default=0, ge=0)
    motion_score: float = Field(default=0.0, ge=0, le=1)
    safety_detections: int = Field(default=0, ge=0)
    classes_detected: List[DetectionCategory] = Field(default_factory=list)
    evidence_score: float = Field(default=0.0, ge=0, le=100)
    activity_index_pct: float = Field(default=0.0, ge=0, le=100)
    data_mode: DataMode = "live-calibrated"
    calibration_ready: bool = False
    calibration_frames_remaining: int = Field(default=0, ge=0)
    calibrated_expected_workers: int = Field(default=0, ge=0)


class ResetLiveSessionRequest(BaseModel):
    camera_id: Optional[str] = None


class ResetLiveSessionResponse(BaseModel):
    reset_count: int = Field(default=0, ge=0)


class ReportRequest(BaseModel):
    frames: List[CameraFrame]


class ReportInsight(BaseModel):
    title: str
    detail: str


class ReportResponse(BaseModel):
    summary: AnalysisSummary
    insights: List[ReportInsight]


class CameraPortfolioCard(BaseModel):
    camera_id: str
    site_area: str
    utilization_pct: float = Field(..., ge=0, le=100)
    progress_pct: float = Field(..., ge=0, le=100)
    safety_violations: int = Field(..., ge=0)
    performance_score: float = Field(..., ge=0, le=100)
    trend: Literal["up", "stable", "down"]
    status: Literal["excellent", "watch", "critical"]


class PortfolioResponse(BaseModel):
    generated_at: datetime
    fleet_score: float = Field(..., ge=0, le=100)
    cameras: List[CameraPortfolioCard]


class CameraHealthItem(BaseModel):
    camera_id: str
    site_area: str
    status: Literal["online", "delayed", "offline"]
    last_seen_seconds: int = Field(..., ge=0)
    detection_density: float = Field(..., ge=0)
    reliability_score: float = Field(..., ge=0, le=100)


class CameraHealthResponse(BaseModel):
    generated_at: datetime
    online: int = Field(..., ge=0)
    delayed: int = Field(..., ge=0)
    offline: int = Field(..., ge=0)
    cameras: List[CameraHealthItem]


class EventFeedItem(BaseModel):
    timestamp: datetime
    camera_id: str
    severity: Literal["info", "warn", "critical"]
    event_type: str
    message: str
    action: str


class EventFeedResponse(BaseModel):
    generated_at: datetime
    events: List[EventFeedItem]


class TrendPoint(BaseModel):
    timestamp: datetime
    utilization_pct: float = Field(..., ge=0, le=100)
    progress_pct: float = Field(..., ge=0, le=100)
    safety_violations: int = Field(..., ge=0)


class CameraTrend(BaseModel):
    camera_id: str
    site_area: str
    direction: Literal["up", "stable", "down"]
    points: List[TrendPoint]


class TrendResponse(BaseModel):
    generated_at: datetime
    cameras: List[CameraTrend]


class FlowRecoveryIssue(BaseModel):
    camera_id: str
    severity: Literal["low", "medium", "high"]
    blocked_score: float = Field(..., ge=0, le=100)
    likely_cause: str
    signals: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    estimated_recovery_minutes: int = Field(..., ge=0, le=240)


class FlowRecoveryResponse(BaseModel):
    generated_at: datetime
    projected_utilization_gain_pct: float = Field(..., ge=0, le=100)
    top_recommendation: str
    issues: List[FlowRecoveryIssue] = Field(default_factory=list)


class BottleneckNode(BaseModel):
    node_id: str
    label: str
    node_type: Literal["camera", "queue", "meeting", "review"]
    load_pct: float = Field(..., ge=0, le=100)


class BottleneckEdge(BaseModel):
    source: str
    target: str
    weight: float = Field(..., ge=0, le=100)
    reason: str


class BottleneckIntervention(BaseModel):
    title: str
    detail: str
    expected_gain_pct: float = Field(..., ge=0, le=100)


class BottleneckGraphResponse(BaseModel):
    generated_at: datetime
    bottleneck_index_pct: float = Field(..., ge=0, le=100)
    nodes: List[BottleneckNode] = Field(default_factory=list)
    edges: List[BottleneckEdge] = Field(default_factory=list)
    interventions: List[BottleneckIntervention] = Field(default_factory=list)


class PrivacyControl(BaseModel):
    key: str
    status: Literal["enabled", "disabled", "partial"]
    detail: str


class PrivacyAuditEvent(BaseModel):
    event_id: str
    timestamp: datetime
    severity: Literal["info", "warn", "critical"]
    detail: str


class PrivacyProofResponse(BaseModel):
    generated_at: datetime
    privacy_score: float = Field(..., ge=0, le=100)
    confidence_score: float = Field(..., ge=0, le=100)
    data_retention_policy: str
    controls: List[PrivacyControl] = Field(default_factory=list)
    audit_log: List[PrivacyAuditEvent] = Field(default_factory=list)
    challenge_count: int = Field(default=0, ge=0)


class PrivacyChallengeRequest(BaseModel):
    camera_id: str
    reason: str = Field(..., min_length=3, max_length=400)


class PrivacyChallengeResponse(BaseModel):
    challenge_id: str
    status: Literal["accepted", "rejected"]
    message: str


class JudgeWowRequest(BaseModel):
    frames: List[CameraFrame]
    api_key: Optional[str] = Field(default=None, min_length=10, max_length=200)
    base_url: Optional[str] = Field(default=None, min_length=10, max_length=200)
    model: Optional[str] = Field(default=None, min_length=3, max_length=80)
    judge_focus: str = Field(default="impact", min_length=2, max_length=120)
    demo_context: str = Field(default="software delivery floor", min_length=3, max_length=200)


class JudgeWowResponse(BaseModel):
    generated_at: datetime
    provider: str
    model: str
    data_mode: Literal["live-kimi", "local-fallback"]
    one_liner: str
    pitch: str
    wow_moments: List[str] = Field(default_factory=list)
    live_script: List[str] = Field(default_factory=list)
    risk_watchouts: List[str] = Field(default_factory=list)


class ManagerReportRequest(BaseModel):
    camera_id: str = Field(default="CAM-LIVE-01", min_length=3, max_length=64)


class ManagerReportResponse(BaseModel):
    generated_at: datetime
    camera_id: str
    window_start: datetime
    window_end: datetime
    source_mode: Literal["live-llm", "local-fallback"]
    summary: str
    highlights: List[str] = Field(default_factory=list)
    avg_utilization_pct: float = Field(default=0, ge=0, le=100)
    avg_progress_pct: float = Field(default=0, ge=0, le=100)
    interruptions: int = Field(default=0, ge=0)


class ManagerChatRequest(BaseModel):
    question: str = Field(..., min_length=4, max_length=500)
    camera_id: str = Field(default="CAM-LIVE-01", min_length=3, max_length=64)


class ManagerChatResponse(BaseModel):
    generated_at: datetime
    camera_id: str
    source_mode: Literal["live-llm", "local-fallback"]
    answer: str
    supporting_points: List[str] = Field(default_factory=list)
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
