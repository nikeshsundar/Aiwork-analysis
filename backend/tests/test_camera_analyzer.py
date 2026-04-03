import base64

import cv2
import numpy as np

from app.schemas import BoundingBox, CameraImageRequest, Detection
from app.services.camera_analyzer import _apply_eye_idle_override, _apply_keyboard_break_override, analyze_camera_image


def _encode_image(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return base64.b64encode(encoded.tobytes()).decode("utf-8")


def test_analyze_camera_image_returns_frame_and_detector() -> None:
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.rectangle(image, (120, 60), (190, 220), (255, 255, 255), -1)

    request = CameraImageRequest(
        camera_id="CAM-LIVE-TEST",
        image_base64=_encode_image(image),
        site_area="lab",
        expected_workers=5,
        tasks_planned=8,
        tasks_completed=3,
    )

    frame, detector, motion_score, single_person_mode_applied = analyze_camera_image(request)

    assert frame.camera_id == "CAM-LIVE-TEST"
    assert frame.site_area == "lab"
    assert detector in {
        "yolo-safety",
        "yolo-safety+hog-people-detector",
        "yolo-safety+contour-fallback",
        "yolo-unavailable",
        "yolo-error",
        "yolo-empty",
        "yolo-no-safety-match",
        "yolo-nms-empty",
        "person-yolo",
        "person-yolo-unavailable",
        "person-yolo-error",
        "person-yolo-empty",
        "person-yolo-no-person",
        "person-yolo-nms-empty",
        "hog-people-detector",
        "yolo-safety+person-yolo",
        "yolo-safety+face-body-fallback",
        "yolo-safety+contour-fallback",
        "face-body-fallback",
        "contour-fallback",
        "motion-fallback",
    }
    assert 0.0 <= motion_score <= 1.0
    assert single_person_mode_applied is False


def test_analyze_camera_image_uses_previous_frame_for_motion_score() -> None:
    image_a = np.zeros((180, 320, 3), dtype=np.uint8)
    image_b = np.zeros((180, 320, 3), dtype=np.uint8)
    cv2.circle(image_b, (120, 90), 28, (255, 255, 255), -1)

    request = CameraImageRequest(
        camera_id="CAM-LIVE-TEST",
        image_base64=_encode_image(image_b),
        previous_image_base64=_encode_image(image_a),
        expected_workers=4,
        tasks_planned=6,
        tasks_completed=2,
    )

    _, _, motion_score, _ = analyze_camera_image(request)

    assert motion_score > 0.0


def test_analyze_camera_image_generates_stable_track_ids() -> None:
    base = np.zeros((240, 320, 3), dtype=np.uint8)
    moved_a = base.copy()
    moved_b = base.copy()
    cv2.rectangle(moved_a, (110, 60), (190, 220), (255, 255, 255), -1)
    cv2.rectangle(moved_b, (118, 64), (198, 224), (255, 255, 255), -1)

    first_request = CameraImageRequest(
        camera_id="CAM-TRACK-TEST",
        image_base64=_encode_image(moved_a),
        previous_image_base64=_encode_image(base),
        site_area="track-zone",
        expected_workers=0,
    )
    second_request = CameraImageRequest(
        camera_id="CAM-TRACK-TEST",
        image_base64=_encode_image(moved_b),
        previous_image_base64=_encode_image(moved_a),
        site_area="track-zone",
        expected_workers=0,
    )

    frame_a, _, _, _ = analyze_camera_image(first_request)
    frame_b, _, _, _ = analyze_camera_image(second_request)

    ids_a = {
        detection.track_id
        for detection in frame_a.detections
        if detection.category == "worker" and detection.track_id
    }
    ids_b = {
        detection.track_id
        for detection in frame_b.detections
        if detection.category == "worker" and detection.track_id
    }

    assert ids_a
    assert ids_b
    assert ids_a.intersection(ids_b)


def test_analyze_camera_image_single_person_mode_caps_workers() -> None:
    image = np.zeros((320, 240, 3), dtype=np.uint8)
    cv2.rectangle(image, (20, 60), (90, 260), (255, 255, 255), -1)
    cv2.rectangle(image, (130, 70), (200, 280), (255, 255, 255), -1)

    request = CameraImageRequest(
        camera_id="CAM-SINGLE-PERSON",
        image_base64=_encode_image(image),
        previous_image_base64=_encode_image(np.zeros((320, 240, 3), dtype=np.uint8)),
        site_area="single-zone",
        single_person_mode=True,
    )

    frame, _, _, single_person_mode_applied = analyze_camera_image(request)
    workers = [detection for detection in frame.detections if detection.category == "worker"]

    assert single_person_mode_applied is True
    assert len(workers) <= 1


def test_analyze_camera_image_single_person_mode_requires_face() -> None:
    current = np.zeros((240, 320, 3), dtype=np.uint8)
    previous = np.full((240, 320, 3), 255, dtype=np.uint8)

    request = CameraImageRequest(
        camera_id="CAM-SINGLE-PERSON-NOFACE",
        image_base64=_encode_image(current),
        previous_image_base64=_encode_image(previous),
        site_area="single-zone",
        single_person_mode=True,
    )

    frame, detector, _, single_person_mode_applied = analyze_camera_image(request)
    workers = [detection for detection in frame.detections if detection.category == "worker"]

    assert single_person_mode_applied is True
    assert detector == "single-person-no-face"
    assert workers == []


def test_apply_eye_idle_override_marks_worker_idle_after_threshold() -> None:
    detection = Detection(
        category="worker",
        confidence=0.9,
        bbox=BoundingBox(x=0.2, y=0.2, w=0.2, h=0.4),
        moving=True,
        face_detected=True,
        eyes_closed=True,
        eyes_closed_seconds=10.4,
    )

    _apply_eye_idle_override(detection)

    assert detection.moving is False


def test_apply_keyboard_break_override_marks_worker_idle_after_threshold() -> None:
    detection = Detection(
        category="worker",
        confidence=0.9,
        bbox=BoundingBox(x=0.2, y=0.2, w=0.2, h=0.4),
        moving=True,
        hand_on_keyboard=False,
        hand_off_keyboard_seconds=10.2,
    )

    _apply_keyboard_break_override(detection)

    assert detection.moving is False
