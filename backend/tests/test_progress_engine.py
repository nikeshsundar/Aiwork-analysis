from datetime import datetime, timezone

from app.schemas import BoundingBox, CameraFrame, Detection
from app.services.progress_engine import aggregate_analyses, analyze_frame


def _worker(moving: bool) -> Detection:
    return Detection(
        category="worker",
        confidence=0.9,
        bbox=BoundingBox(x=0.1, y=0.1, w=0.1, h=0.1),
        zone="zone-a",
        moving=moving,
    )


def test_analyze_frame_computes_utilization_and_progress() -> None:
    frame = CameraFrame(
        camera_id="CAM-1",
        timestamp=datetime.now(timezone.utc),
        site_area="zone-a",
        expected_workers=10,
        tasks_planned=20,
        tasks_completed=10,
        detections=[_worker(True), _worker(True), _worker(False), _worker(True)],
    )

    analysis = analyze_frame(frame)

    assert analysis.worker_count == 4
    assert analysis.active_workers == 3
    assert analysis.idle_workers == 1
    assert analysis.utilization_pct == 30.0
    assert analysis.progress_pct == 50.0


def test_analyze_frame_counts_safety_violations() -> None:
    frame = CameraFrame(
        camera_id="CAM-2",
        timestamp=datetime.now(timezone.utc),
        site_area="zone-b",
        expected_workers=5,
        tasks_planned=8,
        tasks_completed=3,
        detections=[
            _worker(True),
            Detection(
                category="no_helmet",
                confidence=0.95,
                bbox=BoundingBox(x=0.3, y=0.1, w=0.1, h=0.1),
                zone="zone-b",
                moving=True,
            ),
            Detection(
                category="restricted_zone_entry",
                confidence=0.91,
                bbox=BoundingBox(x=0.5, y=0.2, w=0.1, h=0.1),
                zone="restricted",
                moving=True,
            ),
        ],
    )

    analysis = analyze_frame(frame)

    assert analysis.safety_violations == 2
    assert any("helmet" in alert for alert in analysis.alerts)
    assert any("restricted" in alert for alert in analysis.alerts)


def test_aggregate_analyses_returns_averages() -> None:
    frame_a = CameraFrame(
        camera_id="CAM-A",
        timestamp=datetime.now(timezone.utc),
        site_area="a",
        expected_workers=4,
        tasks_planned=4,
        tasks_completed=2,
        detections=[_worker(True), _worker(True), _worker(False), _worker(False)],
    )
    frame_b = CameraFrame(
        camera_id="CAM-B",
        timestamp=datetime.now(timezone.utc),
        site_area="b",
        expected_workers=4,
        tasks_planned=4,
        tasks_completed=4,
        detections=[_worker(True), _worker(True), _worker(True), _worker(True)],
    )

    analyses = [analyze_frame(frame_a), analyze_frame(frame_b)]
    summary = aggregate_analyses(analyses)

    assert summary.frames_processed == 2
    assert summary.total_workers == 8
    assert summary.total_active_workers == 6
    assert summary.avg_utilization_pct == 75.0
    assert summary.avg_progress_pct == 75.0
