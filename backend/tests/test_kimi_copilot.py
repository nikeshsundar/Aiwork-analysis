from datetime import datetime, timezone
import json

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import AnalysisSummary, BoundingBox, CameraFrame, Detection
from app.services.kimi_copilot import build_judge_wow_response
from app.services.progress_engine import analyze_frame, aggregate_analyses


def _frame() -> CameraFrame:
    return CameraFrame(
        camera_id="CAM-DEMO-1",
        timestamp=datetime.now(timezone.utc),
        site_area="engineering-floor",
        expected_workers=5,
        tasks_planned=10,
        tasks_completed=6,
        detections=[
            Detection(
                category="worker",
                confidence=0.93,
                bbox=BoundingBox(x=0.1, y=0.1, w=0.2, h=0.3),
                moving=True,
            ),
            Detection(
                category="worker",
                confidence=0.91,
                bbox=BoundingBox(x=0.4, y=0.1, w=0.2, h=0.3),
                moving=False,
            ),
            Detection(
                category="phone_use",
                confidence=0.84,
                bbox=BoundingBox(x=0.3, y=0.2, w=0.1, h=0.1),
                moving=False,
            ),
        ],
    )


def test_build_judge_wow_response_uses_fallback_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("KIMI_API_KEY", raising=False)

    frames = [_frame()]
    analyses = [analyze_frame(frames[0])]
    summary: AnalysisSummary = aggregate_analyses(analyses)

    response = build_judge_wow_response(
        frames=frames,
        analyses=analyses,
        summary=summary,
        judge_focus="impact",
        demo_context="software engineering floor",
    )

    assert response.data_mode == "local-fallback"
    assert response.one_liner
    assert len(response.wow_moments) >= 3
    assert len(response.live_script) == 4


def test_copilot_judge_wow_endpoint_returns_payload() -> None:
    client = TestClient(app)
    frame = _frame()

    response = client.post(
        "/copilot/judge-wow",
        json={
            "frames": [frame.model_dump(mode="json")],
            "judge_focus": "novelty",
            "demo_context": "engineering sprint room",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "moonshot-kimi"
    assert "one_liner" in body
    assert "pitch" in body
    assert isinstance(body["wow_moments"], list)


def test_build_judge_wow_response_supports_local_nim_without_key(monkeypatch) -> None:
    monkeypatch.delenv("KIMI_API_KEY", raising=False)

    captured = {}

    def _fake_call(api_key, model, prompt, base_url):
        captured["api_key"] = api_key
        captured["model"] = model
        captured["base_url"] = base_url
        captured["prompt"] = prompt
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "one_liner": "Live NIM brief is ready.",
                                "pitch": "NIM-backed demo pitch.",
                                "wow_moments": ["moment 1", "moment 2", "moment 3"],
                                "live_script": ["step 1", "step 2", "step 3", "step 4"],
                                "risk_watchouts": ["risk 1", "risk 2", "risk 3"],
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("app.services.kimi_copilot._call_kimi_chat", _fake_call)

    frames = [_frame()]
    analyses = [analyze_frame(frames[0])]
    summary: AnalysisSummary = aggregate_analyses(analyses)

    response = build_judge_wow_response(
        frames=frames,
        analyses=analyses,
        summary=summary,
        judge_focus="novelty",
        demo_context="nim local demo",
        base_url="http://127.0.0.1:8000/v1",
        model="moonshotai/kimi-k2.5",
    )

    assert response.data_mode == "live-kimi"
    assert response.provider == "nvidia-nim-local"
    assert captured["api_key"] is None
    assert captured["base_url"] == "http://127.0.0.1:8000/v1"
