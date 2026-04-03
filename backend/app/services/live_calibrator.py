from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Literal, Optional

DataMode = Literal["live-calibrated", "manual-assisted"]

CALIBRATION_WARMUP_FRAMES = 8


@dataclass
class _CameraCalibrationState:
    frames_seen: int = 0
    ema_workers: float = 0.0
    progress_units: float = 0.0
    last_timestamp: Optional[datetime] = None


@dataclass
class LiveCalibrationResult:
    calibrated_expected_workers: int
    utilization_pct: float
    progress_pct: float
    activity_index_pct: float
    evidence_score: float
    data_mode: DataMode
    calibration_ready: bool
    calibration_frames_remaining: int


class LiveCalibrationStore:
    def __init__(self) -> None:
        self._states: Dict[str, _CameraCalibrationState] = {}
        self._lock = Lock()

    def reset(self, camera_id: Optional[str] = None) -> int:
        with self._lock:
            if camera_id:
                return 1 if self._states.pop(camera_id, None) is not None else 0
            removed = len(self._states)
            self._states.clear()
            return removed

    def calibrate(
        self,
        camera_id: str,
        timestamp: datetime,
        worker_count: int,
        active_workers: int,
        average_worker_confidence: float,
        detector: str,
        expected_workers_input: int,
        tasks_planned_input: int,
        tasks_completed_input: int,
    ) -> LiveCalibrationResult:
        with self._lock:
            state = self._states.get(camera_id)
            if state is None:
                state = _CameraCalibrationState()
                self._states[camera_id] = state

            state.frames_seen += 1
            if state.frames_seen == 1:
                state.ema_workers = float(worker_count)
            else:
                state.ema_workers = (state.ema_workers * 0.75) + (worker_count * 0.25)

            calibrated_expected_workers = (
                expected_workers_input if expected_workers_input > 0 else max(1, int(round(max(state.ema_workers, worker_count))))
            )

            utilization_pct = _pct(active_workers, calibrated_expected_workers)

            if state.last_timestamp is None:
                dt_seconds = 1.0
            else:
                dt_seconds = max(0.5, min(3.0, (timestamp - state.last_timestamp).total_seconds()))
            state.last_timestamp = timestamp

            active_signal = max(0.0, float(active_workers))
            state.progress_units += active_signal * dt_seconds

            target_units = max(16.0, calibrated_expected_workers * 85.0)
            activity_index_pct = min(100.0, max(0.0, (state.progress_units / target_units) * 100.0))

            if tasks_planned_input > 0:
                progress_pct = _pct(tasks_completed_input, tasks_planned_input)
                data_mode: DataMode = "manual-assisted"
            else:
                progress_pct = 0.0
                data_mode = "live-calibrated"

            evidence_score = _evidence_score(
                detector=detector,
                worker_count=worker_count,
                average_worker_confidence=average_worker_confidence,
                active_workers=active_workers,
                ema_workers=state.ema_workers,
                frames_seen=state.frames_seen,
            )

            calibration_ready = state.frames_seen >= CALIBRATION_WARMUP_FRAMES
            calibration_frames_remaining = max(0, CALIBRATION_WARMUP_FRAMES - state.frames_seen)

            return LiveCalibrationResult(
                calibrated_expected_workers=calibrated_expected_workers,
                utilization_pct=round(utilization_pct, 1),
                progress_pct=round(progress_pct, 1),
                activity_index_pct=round(activity_index_pct, 1),
                evidence_score=round(evidence_score, 1),
                data_mode=data_mode,
                calibration_ready=calibration_ready,
                calibration_frames_remaining=calibration_frames_remaining,
            )


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(100.0, (numerator / denominator) * 100.0))


def _detector_score(detector: str) -> float:
    detector_name = (detector or "").lower()
    if detector_name.startswith("yolo-safety"):
        return 0.96
    if detector_name == "hog-people-detector" or detector_name.endswith("+hog-people-detector"):
        return 0.78
    if detector_name == "contour-fallback" or detector_name.endswith("+contour-fallback"):
        return 0.62
    if detector_name == "motion-fallback":
        return 0.45
    if detector_name == "yolo-unavailable":
        return 0.4
    return 0.55


def _evidence_score(
    detector: str,
    worker_count: int,
    average_worker_confidence: float,
    active_workers: int,
    ema_workers: float,
    frames_seen: int,
) -> float:
    detector_component = _detector_score(detector)
    confidence_component = max(0.0, min(1.0, average_worker_confidence))

    if worker_count <= 0:
        activity_component = 0.2
    else:
        activity_component = max(0.0, min(1.0, active_workers / float(worker_count)))

    if ema_workers <= 0:
        stability_component = 0.4
    else:
        drift = abs(worker_count - ema_workers) / max(1.0, ema_workers)
        stability_component = max(0.0, min(1.0, 1.0 - drift))

    maturity_component = max(0.0, min(1.0, frames_seen / 12.0))

    weighted = (
        (detector_component * 0.33)
        + (confidence_component * 0.25)
        + (stability_component * 0.18)
        + (activity_component * 0.12)
        + (maturity_component * 0.12)
    )

    return max(0.0, min(100.0, weighted * 100.0))


live_calibration_store = LiveCalibrationStore()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
