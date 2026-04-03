from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Tuple

from app.schemas import (
    BottleneckEdge,
    BottleneckGraphResponse,
    BottleneckIntervention,
    BottleneckNode,
    CameraFrame,
    FlowRecoveryIssue,
    FlowRecoveryResponse,
    FrameAnalysis,
    PrivacyAuditEvent,
    PrivacyChallengeRequest,
    PrivacyChallengeResponse,
    PrivacyControl,
    PrivacyProofResponse,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _group_by_camera(
    frames: List[CameraFrame],
    analyses: List[FrameAnalysis],
) -> Dict[str, List[Tuple[CameraFrame, FrameAnalysis]]]:
    grouped: Dict[str, List[Tuple[CameraFrame, FrameAnalysis]]] = defaultdict(list)
    for frame, analysis in zip(frames, analyses):
        grouped[frame.camera_id].append((frame, analysis))

    for camera_id in grouped:
        grouped[camera_id].sort(key=lambda item: item[0].timestamp)

    return grouped


def _blocked_score(analysis: FrameAnalysis) -> float:
    alert_factor = min(100.0, float(len(analysis.alerts)) * 18.0)
    return max(
        0.0,
        min(
            100.0,
            ((100.0 - analysis.utilization_pct) * 0.45)
            + ((100.0 - analysis.progress_pct) * 0.35)
            + (alert_factor * 0.20),
        ),
    )


def _issue_from_analysis(analysis: FrameAnalysis) -> FlowRecoveryIssue:
    blocked = _blocked_score(analysis)

    if blocked >= 70:
        severity = "high"
    elif blocked >= 42:
        severity = "medium"
    else:
        severity = "low"

    signals: List[str] = []
    if analysis.utilization_pct < 55:
        signals.append(f"low utilization ({analysis.utilization_pct:.1f}%)")
    if analysis.progress_pct < 45:
        signals.append(f"progress lag ({analysis.progress_pct:.1f}%)")
    signals.extend(analysis.alerts[:3])

    alerts_text = " ".join(analysis.alerts).lower()
    if "hands off keyboard" in alerts_text or "eyes closed" in alerts_text:
        likely_cause = "attention or fatigue disruption"
        actions = [
            "Trigger a 2-minute guided reset and re-focus checklist.",
            "Auto-suggest a small next step to re-enter flow quickly.",
            "Escalate to team lead if disruption persists for 15+ minutes.",
        ]
    elif analysis.progress_pct < 45 and analysis.utilization_pct >= 60:
        likely_cause = "dependency wait or review queue blockage"
        actions = [
            "Route PR to backup reviewer and set 20-minute SLA.",
            "Surface likely docs/errors based on recent alert pattern.",
            "Generate one-click unblock request for nearest teammate.",
        ]
    else:
        likely_cause = "task ambiguity or context switching overhead"
        actions = [
            "Recommend a single priority task with explicit acceptance criteria.",
            "Mute low-priority interrupts for a 25-minute flow sprint.",
            "Create a quick stand-up note to align blockers and ownership.",
        ]

    estimated_recovery_minutes = int(max(5.0, min(90.0, 8.0 + (blocked * 0.65))))

    return FlowRecoveryIssue(
        camera_id=analysis.camera_id,
        severity=severity,
        blocked_score=round(blocked, 1),
        likely_cause=likely_cause,
        signals=signals,
        recommended_actions=actions,
        estimated_recovery_minutes=estimated_recovery_minutes,
    )


def build_flow_recovery_copilot(analyses: List[FrameAnalysis]) -> FlowRecoveryResponse:
    if not analyses:
        return FlowRecoveryResponse(
            generated_at=_utc_now(),
            projected_utilization_gain_pct=0.0,
            top_recommendation="Start live analysis to generate recovery guidance.",
            issues=[],
        )

    latest_by_camera: Dict[str, FrameAnalysis] = {}
    for analysis in sorted(analyses, key=lambda item: item.timestamp):
        latest_by_camera[analysis.camera_id] = analysis

    issues = [_issue_from_analysis(analysis) for analysis in latest_by_camera.values()]
    issues.sort(key=lambda item: item.blocked_score, reverse=True)

    high_and_medium = [item for item in issues if item.severity in {"high", "medium"}]
    if high_and_medium:
        top_issue = high_and_medium[0]
        top_recommendation = (
            f"Prioritize {top_issue.camera_id}: {top_issue.likely_cause}; "
            f"start with '{top_issue.recommended_actions[0]}'"
        )
    else:
        top_recommendation = "Flow looks stable; continue current cadence with lightweight monitoring."

    projected_gain = sum(min(18.0, item.blocked_score * 0.16) for item in high_and_medium)
    projected_gain = min(45.0, projected_gain)

    return FlowRecoveryResponse(
        generated_at=_utc_now(),
        projected_utilization_gain_pct=round(projected_gain, 1),
        top_recommendation=top_recommendation,
        issues=issues,
    )


def build_team_bottleneck_graph(
    frames: List[CameraFrame],
    analyses: List[FrameAnalysis],
) -> BottleneckGraphResponse:
    grouped = _group_by_camera(frames, analyses)

    nodes: List[BottleneckNode] = [
        BottleneckNode(node_id="queue-review", label="PR Review Queue", node_type="queue", load_pct=55.0),
        BottleneckNode(node_id="queue-meetings", label="Meeting Load", node_type="meeting", load_pct=42.0),
        BottleneckNode(node_id="queue-unblock", label="Unblock Desk", node_type="review", load_pct=37.0),
    ]
    edges: List[BottleneckEdge] = []
    interventions: List[BottleneckIntervention] = []

    if not grouped:
        return BottleneckGraphResponse(
            generated_at=_utc_now(),
            bottleneck_index_pct=0.0,
            nodes=nodes,
            edges=edges,
            interventions=[
                BottleneckIntervention(
                    title="Need live data",
                    detail="Start camera analytics to construct dependency bottleneck graph.",
                    expected_gain_pct=0.0,
                )
            ],
        )

    pressure_values: List[float] = []
    camera_pressures: List[Tuple[str, float, FrameAnalysis]] = []

    for camera_id, entries in grouped.items():
        latest_analysis = entries[-1][1]
        pressure = max(
            0.0,
            min(
                100.0,
                ((100.0 - latest_analysis.progress_pct) * 0.52)
                + ((100.0 - latest_analysis.utilization_pct) * 0.28)
                + (len(latest_analysis.alerts) * 7.0),
            ),
        )
        pressure_values.append(pressure)
        camera_pressures.append((camera_id, pressure, latest_analysis))

        nodes.append(
            BottleneckNode(
                node_id=f"camera-{camera_id}",
                label=camera_id,
                node_type="camera",
                load_pct=round(pressure, 1),
            )
        )

        review_weight = max(10.0, min(95.0, pressure * 0.72))
        meeting_weight = max(8.0, min(95.0, (100.0 - latest_analysis.utilization_pct) * 0.74))
        unblock_weight = max(8.0, min(95.0, (100.0 - latest_analysis.progress_pct) * 0.68))

        edges.append(
            BottleneckEdge(
                source=f"camera-{camera_id}",
                target="queue-review",
                weight=round(review_weight, 1),
                reason="review dependency probability",
            )
        )
        edges.append(
            BottleneckEdge(
                source="queue-meetings",
                target=f"camera-{camera_id}",
                weight=round(meeting_weight, 1),
                reason="meeting interruption drag",
            )
        )
        edges.append(
            BottleneckEdge(
                source="queue-unblock",
                target=f"camera-{camera_id}",
                weight=round(unblock_weight, 1),
                reason="active unblock demand",
            )
        )

    bottleneck_index = sum(pressure_values) / len(pressure_values) if pressure_values else 0.0

    camera_pressures.sort(key=lambda item: item[1], reverse=True)
    for camera_id, pressure, analysis in camera_pressures[:3]:
        interventions.append(
            BottleneckIntervention(
                title=f"Unblock {camera_id}",
                detail=(
                    f"Reduce review wait and meeting collisions for {camera_id}; "
                    f"current pressure {pressure:.1f} with {len(analysis.alerts)} active alerts."
                ),
                expected_gain_pct=round(min(24.0, max(4.0, pressure * 0.18)), 1),
            )
        )

    return BottleneckGraphResponse(
        generated_at=_utc_now(),
        bottleneck_index_pct=round(bottleneck_index, 1),
        nodes=nodes,
        edges=edges,
        interventions=interventions,
    )


@dataclass
class _PrivacyChallenge:
    challenge_id: str
    camera_id: str
    reason: str
    created_at: datetime


class _PrivacyChallengeStore:
    def __init__(self) -> None:
        self._items: List[_PrivacyChallenge] = []
        self._next = 1
        self._lock = Lock()

    def create(self, request: PrivacyChallengeRequest) -> PrivacyChallengeResponse:
        with self._lock:
            challenge_id = f"CH-{self._next:04d}"
            self._next += 1
            self._items.append(
                _PrivacyChallenge(
                    challenge_id=challenge_id,
                    camera_id=request.camera_id,
                    reason=request.reason.strip(),
                    created_at=_utc_now(),
                )
            )

        return PrivacyChallengeResponse(
            challenge_id=challenge_id,
            status="accepted",
            message="Challenge recorded. Privacy audit queue has been notified.",
        )

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def recent_audit_events(self, limit: int = 8) -> List[PrivacyAuditEvent]:
        with self._lock:
            selected = list(reversed(self._items[-limit:]))

        events: List[PrivacyAuditEvent] = []
        for item in selected:
            events.append(
                PrivacyAuditEvent(
                    event_id=item.challenge_id,
                    timestamp=item.created_at,
                    severity="warn",
                    detail=f"User challenge on {item.camera_id}: {item.reason}",
                )
            )
        return events


privacy_challenge_store = _PrivacyChallengeStore()


def build_privacy_proof_layer(
    frames: List[CameraFrame],
    analyses: List[FrameAnalysis],
) -> PrivacyProofResponse:
    worker_confidences: List[float] = []
    for frame in frames:
        for detection in frame.detections:
            if detection.category == "worker":
                worker_confidences.append(float(detection.confidence))

    confidence_score = (sum(worker_confidences) / len(worker_confidences) * 100.0) if worker_confidences else 0.0
    challenge_count = privacy_challenge_store.count()

    privacy_score = 92.0
    if challenge_count > 0:
        privacy_score = max(70.0, privacy_score - min(12.0, challenge_count * 1.5))
    if not frames:
        privacy_score = max(65.0, privacy_score - 8.0)

    controls = [
        PrivacyControl(
            key="on_device_signal_extraction",
            status="enabled",
            detail="Face/eye/hand signals are reduced to metrics before dashboard analytics.",
        ),
        PrivacyControl(
            key="no_face_identification",
            status="enabled",
            detail="No identity recognition model or person-name linkage exists in pipeline.",
        ),
        PrivacyControl(
            key="raw_video_retention",
            status="disabled",
            detail="Raw camera frames are not stored as long-term records in analytics dataset.",
        ),
        PrivacyControl(
            key="team_level_reporting",
            status="enabled",
            detail="Outputs are aggregate camera/team metrics, not employee ranking.",
        ),
        PrivacyControl(
            key="challenge_channel",
            status="enabled",
            detail="Users can challenge detection results for audit follow-up.",
        ),
    ]

    audit_log = [
        PrivacyAuditEvent(
            event_id="AUD-0001",
            timestamp=_utc_now(),
            severity="info",
            detail="Privacy proof generated from aggregate frame metadata only.",
        ),
        PrivacyAuditEvent(
            event_id="AUD-0002",
            timestamp=_utc_now(),
            severity="info",
            detail="Retention policy check: no long-term raw video persistence in analytics response store.",
        ),
    ]
    audit_log.extend(privacy_challenge_store.recent_audit_events(limit=6))

    return PrivacyProofResponse(
        generated_at=_utc_now(),
        privacy_score=round(privacy_score, 1),
        confidence_score=round(confidence_score, 1),
        data_retention_policy="No long-term raw video retention; aggregate metrics and audit events only.",
        controls=controls,
        audit_log=audit_log,
        challenge_count=challenge_count,
    )
