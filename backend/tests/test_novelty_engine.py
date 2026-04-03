from datetime import datetime, timedelta, timezone

from app.schemas import BoundingBox, CameraFrame, Detection, PrivacyChallengeRequest
from app.services.novelty_engine import (
    build_flow_recovery_copilot,
    build_privacy_proof_layer,
    build_team_bottleneck_graph,
    privacy_challenge_store,
)
from app.services.progress_engine import analyze_frame


def _frame(
    camera_id: str,
    minutes_offset: int,
    worker_count: int,
    moving_workers: int,
    tasks_planned: int,
    tasks_completed: int,
) -> CameraFrame:
    detections = []
    for index in range(worker_count):
        detections.append(
            Detection(
                category="worker",
                confidence=0.7,
                bbox=BoundingBox(x=0.1 + (index * 0.02), y=0.2, w=0.15, h=0.3),
                moving=index < moving_workers,
            )
        )

    return CameraFrame(
        camera_id=camera_id,
        timestamp=datetime.now(timezone.utc) + timedelta(minutes=minutes_offset),
        site_area="dev-floor",
        expected_workers=max(worker_count, 1),
        tasks_planned=tasks_planned,
        tasks_completed=tasks_completed,
        detections=detections,
    )


def test_flow_recovery_returns_ranked_issues() -> None:
    frames = [
        _frame("CAM-A", 0, worker_count=4, moving_workers=1, tasks_planned=10, tasks_completed=2),
        _frame("CAM-B", 1, worker_count=4, moving_workers=3, tasks_planned=10, tasks_completed=8),
    ]
    analyses = [analyze_frame(frame) for frame in frames]

    response = build_flow_recovery_copilot(analyses)

    assert response.issues
    assert response.issues[0].blocked_score >= response.issues[-1].blocked_score
    assert response.projected_utilization_gain_pct >= 0


def test_bottleneck_graph_contains_nodes_edges_and_interventions() -> None:
    frames = [
        _frame("CAM-A", 0, worker_count=3, moving_workers=1, tasks_planned=8, tasks_completed=2),
        _frame("CAM-B", 1, worker_count=5, moving_workers=2, tasks_planned=10, tasks_completed=3),
    ]
    analyses = [analyze_frame(frame) for frame in frames]

    graph = build_team_bottleneck_graph(frames, analyses)

    assert graph.nodes
    assert graph.edges
    assert graph.interventions
    assert graph.bottleneck_index_pct >= 0


def test_privacy_proof_reflects_challenges() -> None:
    frames = [_frame("CAM-A", 0, worker_count=2, moving_workers=1, tasks_planned=6, tasks_completed=2)]
    analyses = [analyze_frame(frame) for frame in frames]

    before = build_privacy_proof_layer(frames, analyses)
    initial_count = before.challenge_count

    challenge = privacy_challenge_store.create(
        request=PrivacyChallengeRequest(
            camera_id="CAM-A",
            reason="False positive on idle state during code review.",
        )
    )
    assert challenge.status == "accepted"

    after = build_privacy_proof_layer(frames, analyses)
    assert after.challenge_count >= initial_count + 1
    assert after.audit_log
