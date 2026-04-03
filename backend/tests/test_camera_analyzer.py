import base64

import cv2
import numpy as np

from app.schemas import CameraImageRequest
from app.services.camera_analyzer import analyze_camera_image


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

    frame, detector, motion_score = analyze_camera_image(request)

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
        "hog-people-detector",
        "contour-fallback",
        "motion-fallback",
    }
    assert 0.0 <= motion_score <= 1.0


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

    _, _, motion_score = analyze_camera_image(request)

    assert motion_score > 0.0
