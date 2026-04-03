from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.services.manager_assistant import TimelineEvent, manager_timeline_store


def test_manager_report_and_chat_endpoints() -> None:
    manager_timeline_store._events = []
    now = datetime.now(timezone.utc)
    manager_timeline_store.ingest(
        TimelineEvent(
            timestamp=now,
            camera_id="CAM-LIVE-01",
            site_area="worker-desk",
            worker_count=1,
            active_workers=1,
            utilization_pct=75.0,
            progress_pct=62.0,
            interruptions=1,
            alerts=["phone distraction"],
            eye_idle_workers=0,
            hand_break_workers=0,
            activity_index_pct=70.0,
            evidence_score=80.0,
        )
    )

    client = TestClient(app)

    report_response = client.post(
        "/manager/report/latest",
        json={"camera_id": "CAM-LIVE-01"},
    )
    assert report_response.status_code == 200
    report_body = report_response.json()
    assert report_body["camera_id"] == "CAM-LIVE-01"
    assert "summary" in report_body

    chat_response = client.post(
        "/manager/chat",
        json={"camera_id": "CAM-LIVE-01", "question": "from 4:01 to 4:05 what he did"},
    )
    assert chat_response.status_code == 200
    chat_body = chat_response.json()
    assert "answer" in chat_body
    assert isinstance(chat_body["supporting_points"], list)
