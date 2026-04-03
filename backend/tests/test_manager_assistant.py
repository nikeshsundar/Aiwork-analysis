from datetime import datetime, timedelta, timezone

from app.schemas import ManagerChatResponse, ManagerReportResponse
from app.services.manager_assistant import (
    TimelineEvent,
    build_manager_chat_answer,
    build_manager_two_minute_report,
    manager_timeline_store,
)


def _event(ts: datetime, interruptions: int = 0) -> TimelineEvent:
    return TimelineEvent(
        timestamp=ts,
        camera_id="CAM-LIVE-01",
        site_area="worker-desk",
        worker_count=1,
        active_workers=1,
        utilization_pct=78.0,
        progress_pct=66.0,
        interruptions=interruptions,
        alerts=["focus steady"] if interruptions == 0 else ["phone distraction"],
        eye_idle_workers=0,
        hand_break_workers=0,
        activity_index_pct=72.0,
        evidence_score=82.0,
    )


def test_manager_report_returns_local_window_summary(monkeypatch) -> None:
    manager_timeline_store._events = []

    now = datetime.now(timezone.utc)
    manager_timeline_store.ingest(_event(now - timedelta(seconds=90), interruptions=0))
    manager_timeline_store.ingest(_event(now - timedelta(seconds=30), interruptions=1))

    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    response: ManagerReportResponse = build_manager_two_minute_report(camera_id="CAM-LIVE-01")

    assert response.camera_id == "CAM-LIVE-01"
    assert response.window_end >= response.window_start
    assert response.avg_utilization_pct >= 0
    assert response.interruptions >= 1
    assert response.summary


def test_manager_chat_answers_explicit_time_range(monkeypatch) -> None:
    manager_timeline_store._events = []

    ref = datetime.now(timezone.utc).replace(hour=16, minute=5, second=0, microsecond=0)
    manager_timeline_store.ingest(_event(ref.replace(minute=1), interruptions=0))
    manager_timeline_store.ingest(_event(ref.replace(minute=3), interruptions=1))
    manager_timeline_store.ingest(_event(ref.replace(minute=5), interruptions=0))

    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    response: ManagerChatResponse = build_manager_chat_answer(
        question="At 4:01 to 4:05 what he did?",
        camera_id="CAM-LIVE-01",
    )

    assert response.answer
    assert response.window_start is not None
    assert response.window_end is not None
    assert response.window_start.hour == 16
    assert response.window_start.minute == 1
    assert response.window_end.minute == 5
