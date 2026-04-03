from datetime import datetime, timedelta, timezone

from app.schemas import BoundingBox, CameraFrame, Detection
from app.services.progress_engine import (
    analyze_frames,
    build_camera_health,
    build_event_feed,
    build_portfolio_analytics,
    build_trend_response,
)


def _worker(moving: bool) -> Detection:
    return Detection(
        category="worker",
        confidence=0.9,
        bbox=BoundingBox(x=0.1, y=0.1, w=0.1, h=0.1),
        zone="zone",
        moving=moving,
    )


def _frame(
    camera_id: str,
    timestamp: datetime,
    expected_workers: int,
    planned: int,
    completed: int,
    moving_workers: int,
    idle_workers: int,
    no_helmet: int = 0,
) -> CameraFrame:
    detections = [_worker(True) for _ in range(moving_workers)]
    detections.extend(_worker(False) for _ in range(idle_workers))
    detections.extend(
        Detection(
            category="no_helmet",
            confidence=0.95,
            bbox=BoundingBox(x=0.3, y=0.1, w=0.1, h=0.1),
            zone="zone",
            moving=True,
        )
        for _ in range(no_helmet)
    )

    return CameraFrame(
        camera_id=camera_id,
        timestamp=timestamp,
        site_area=f"site-{camera_id.lower()}",
        expected_workers=expected_workers,
        tasks_planned=planned,
        tasks_completed=completed,
        detections=detections,
    )


def test_portfolio_analytics_returns_ranked_cards() -> None:
    now = datetime.now(timezone.utc)
    frames = [
        _frame("CAM-A", now, 10, 10, 8, moving_workers=8, idle_workers=1),
        _frame("CAM-B", now, 10, 10, 4, moving_workers=4, idle_workers=3, no_helmet=1),
    ]

    analyses = analyze_frames(frames)
    portfolio = build_portfolio_analytics(frames, analyses)

    assert len(portfolio.cameras) == 2
    assert portfolio.cameras[0].camera_id == "CAM-A"
    assert portfolio.cameras[0].performance_score >= portfolio.cameras[1].performance_score


def test_camera_health_marks_delayed_camera() -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(minutes=8)

    frames = [
        _frame("CAM-NEW", now, 8, 8, 6, moving_workers=5, idle_workers=1),
        _frame("CAM-OLD", old, 8, 8, 6, moving_workers=5, idle_workers=1),
    ]

    analyses = analyze_frames(frames)
    health = build_camera_health(frames, analyses)

    status_map = {camera.camera_id: camera.status for camera in health.cameras}
    assert status_map["CAM-NEW"] == "online"
    assert status_map["CAM-OLD"] == "offline"


def test_event_feed_and_trends_have_expected_signals() -> None:
    now = datetime.now(timezone.utc)
    frames = [
        _frame("CAM-T", now - timedelta(minutes=2), 10, 10, 3, moving_workers=3, idle_workers=4, no_helmet=1),
        _frame("CAM-T", now, 10, 10, 7, moving_workers=7, idle_workers=1, no_helmet=0),
    ]

    analyses = analyze_frames(frames)
    event_feed = build_event_feed(analyses)
    trends = build_trend_response(frames, analyses)

    assert len(event_feed.events) >= 1
    assert any(event.severity in {"warn", "critical"} for event in event_feed.events)
    assert len(trends.cameras) == 1
    assert len(trends.cameras[0].points) == 2
