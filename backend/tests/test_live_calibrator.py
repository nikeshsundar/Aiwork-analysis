from datetime import datetime, timedelta, timezone

from app.services.live_calibrator import LiveCalibrationStore


def test_live_calibration_auto_expected_and_progress_increase() -> None:
    store = LiveCalibrationStore()
    camera_id = "CAM-LIVE-CAL"
    start = datetime.now(timezone.utc)

    first = store.calibrate(
        camera_id=camera_id,
        timestamp=start,
        worker_count=3,
        active_workers=2,
        average_worker_confidence=0.72,
        detector="contour-fallback",
        expected_workers_input=0,
        tasks_planned_input=0,
        tasks_completed_input=0,
    )

    second = store.calibrate(
        camera_id=camera_id,
        timestamp=start + timedelta(seconds=2),
        worker_count=4,
        active_workers=3,
        average_worker_confidence=0.82,
        detector="hog-people-detector",
        expected_workers_input=0,
        tasks_planned_input=0,
        tasks_completed_input=0,
    )

    assert first.data_mode == "live-calibrated"
    assert first.calibrated_expected_workers >= 1
    assert first.progress_pct == 0.0
    assert second.progress_pct == 0.0
    assert second.activity_index_pct >= first.activity_index_pct
    assert second.utilization_pct >= 0
    assert 0 <= second.evidence_score <= 100


def test_live_calibration_manual_mode_uses_task_progress() -> None:
    store = LiveCalibrationStore()

    result = store.calibrate(
        camera_id="CAM-MANUAL",
        timestamp=datetime.now(timezone.utc),
        worker_count=5,
        active_workers=4,
        average_worker_confidence=0.88,
        detector="yolo-safety",
        expected_workers_input=6,
        tasks_planned_input=10,
        tasks_completed_input=4,
    )

    assert result.data_mode == "manual-assisted"
    assert result.calibrated_expected_workers == 6
    assert result.progress_pct == 40.0


def test_live_calibration_reset_clears_state() -> None:
    store = LiveCalibrationStore()
    camera_id = "CAM-RESET"
    now = datetime.now(timezone.utc)

    store.calibrate(
        camera_id=camera_id,
        timestamp=now,
        worker_count=2,
        active_workers=1,
        average_worker_confidence=0.5,
        detector="motion-fallback",
        expected_workers_input=0,
        tasks_planned_input=0,
        tasks_completed_input=0,
    )
    removed = store.reset(camera_id)

    assert removed == 1

    fresh = store.calibrate(
        camera_id=camera_id,
        timestamp=now + timedelta(seconds=1),
        worker_count=1,
        active_workers=1,
        average_worker_confidence=0.6,
        detector="contour-fallback",
        expected_workers_input=0,
        tasks_planned_input=0,
        tasks_completed_input=0,
    )

    assert fresh.calibration_frames_remaining >= 7
