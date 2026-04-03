import base64
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.schemas import BoundingBox, CameraFrame, CameraImageRequest, Detection


_HOG = cv2.HOGDescriptor()
_HOG.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
YOLO_MODEL_PATH = MODEL_DIR / "safety_yolov8.onnx"
YOLO_CLASSES_PATH = MODEL_DIR / "safety_classes.txt"
YOLO_INPUT_SIZE = 640
YOLO_CONF_THRESHOLD = 0.35
YOLO_NMS_THRESHOLD = 0.45

_YOLO_NET: Optional[cv2.dnn.Net] = None
_YOLO_LABELS: List[str] = []
_YOLO_LOAD_ATTEMPTED = False
_YOLO_LOCK = Lock()


def _strip_data_url_prefix(image_base64: str) -> str:
    if "," in image_base64 and image_base64.strip().lower().startswith("data:image"):
        return image_base64.split(",", 1)[1]
    return image_base64


def _decode_base64_image(image_base64: str) -> np.ndarray:
    cleaned = _strip_data_url_prefix(image_base64)
    image_bytes = base64.b64decode(cleaned)
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if frame is None:
        raise ValueError("Could not decode image")

    return frame


def _to_bbox(x: int, y: int, w: int, h: int, width: int, height: int) -> BoundingBox:
    width = max(1, width)
    height = max(1, height)

    return BoundingBox(
        x=max(0.0, min(1.0, x / width)),
        y=max(0.0, min(1.0, y / height)),
        w=max(0.01, min(1.0, w / width)),
        h=max(0.01, min(1.0, h / height)),
    )


def _load_yolo_labels() -> List[str]:
    if YOLO_CLASSES_PATH.exists():
        lines = YOLO_CLASSES_PATH.read_text(encoding="utf-8").splitlines()
        labels = [line.strip() for line in lines if line.strip()]
        if labels:
            return labels

    # Fallback labels for common safety use-cases and COCO-like models.
    return [
        "person",
        "helmet",
        "no_helmet",
        "cell phone",
        "restricted_zone_entry",
        "vehicle",
    ]


def _load_yolo_model() -> Tuple[Optional[cv2.dnn.Net], List[str]]:
    global _YOLO_NET, _YOLO_LABELS, _YOLO_LOAD_ATTEMPTED

    with _YOLO_LOCK:
        if _YOLO_NET is not None:
            return _YOLO_NET, _YOLO_LABELS

        if _YOLO_LOAD_ATTEMPTED:
            return None, _YOLO_LABELS

        _YOLO_LOAD_ATTEMPTED = True
        _YOLO_LABELS = _load_yolo_labels()

        if not YOLO_MODEL_PATH.exists():
            return None, _YOLO_LABELS

        try:
            _YOLO_NET = cv2.dnn.readNetFromONNX(str(YOLO_MODEL_PATH))
        except Exception:
            _YOLO_NET = None

        return _YOLO_NET, _YOLO_LABELS


def _map_label_to_category(label: str) -> Optional[str]:
    normalized = label.lower().replace("_", " ").replace("-", " ").strip()

    if normalized in {"person", "worker", "construction worker"}:
        return "worker"
    if "helmet" in normalized or "hardhat" in normalized:
        if "no" in normalized or "without" in normalized:
            return "no_helmet"
        return "helmet"
    if normalized in {"phone", "cell phone", "mobile phone"} or "phone" in normalized:
        return "phone_use"
    if "restricted" in normalized:
        return "restricted_zone_entry"
    if normalized in {"vehicle", "car", "truck", "bus", "forklift", "excavator"}:
        return "vehicle"

    return None


def _parse_yolo_rows(output: np.ndarray) -> np.ndarray:
    if output.ndim == 3:
        squeezed = np.squeeze(output, axis=0)
        if squeezed.ndim != 2:
            return np.empty((0, 0), dtype=np.float32)
        if squeezed.shape[0] < squeezed.shape[1]:
            return squeezed.T
        return squeezed

    if output.ndim == 2:
        return output

    return np.empty((0, 0), dtype=np.float32)


def _yolo_safety_detections(frame: np.ndarray, site_area: str) -> Tuple[List[Detection], str]:
    net, labels = _load_yolo_model()
    if net is None:
        return [], "yolo-unavailable"

    height, width = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(
        frame,
        scalefactor=1.0 / 255.0,
        size=(YOLO_INPUT_SIZE, YOLO_INPUT_SIZE),
        swapRB=True,
        crop=False,
    )

    try:
        net.setInput(blob)
        output = net.forward()
    except Exception:
        return [], "yolo-error"

    rows = _parse_yolo_rows(output)
    if rows.size == 0:
        return [], "yolo-empty"

    boxes: List[List[int]] = []
    confidences: List[float] = []
    categories: List[str] = []

    for row in rows:
        if row.shape[0] < 6:
            continue

        cx, cy, bw, bh = float(row[0]), float(row[1]), float(row[2]), float(row[3])
        class_scores = row[4:]
        class_id = int(np.argmax(class_scores))
        confidence = float(class_scores[class_id])

        if confidence < YOLO_CONF_THRESHOLD:
            continue

        label = labels[class_id] if class_id < len(labels) else f"class-{class_id}"
        category = _map_label_to_category(label)
        if category is None:
            continue

        scale = YOLO_INPUT_SIZE if max(cx, cy, bw, bh) > 2.0 else 1.0
        x = int(((cx - (bw / 2.0)) / scale) * width)
        y = int(((cy - (bh / 2.0)) / scale) * height)
        w_box = int((bw / scale) * width)
        h_box = int((bh / scale) * height)

        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        w_box = max(2, min(width - x, w_box))
        h_box = max(2, min(height - y, h_box))

        boxes.append([x, y, w_box, h_box])
        confidences.append(confidence)
        categories.append(category)

    if not boxes:
        return [], "yolo-no-safety-match"

    raw_indices = cv2.dnn.NMSBoxes(boxes, confidences, YOLO_CONF_THRESHOLD, YOLO_NMS_THRESHOLD)
    if len(raw_indices) == 0:
        return [], "yolo-nms-empty"

    if isinstance(raw_indices, np.ndarray):
        indices = raw_indices.flatten().tolist()
    else:
        indices = [int(idx[0]) if isinstance(idx, (list, tuple, np.ndarray)) else int(idx) for idx in raw_indices]

    detections: List[Detection] = []
    for idx in indices:
        x, y, w_box, h_box = boxes[idx]
        detections.append(
            Detection(
                category=categories[idx],
                confidence=min(0.99, max(0.35, float(confidences[idx]))),
                bbox=_to_bbox(x, y, w_box, h_box, width, height),
                zone="restricted" if categories[idx] == "restricted_zone_entry" else site_area,
                moving=True,
            )
        )

    return detections, "yolo-safety"


def _hog_worker_detections(frame: np.ndarray, site_area: str) -> List[Detection]:
    height, width = frame.shape[:2]
    resized = cv2.resize(frame, (max(320, width), max(240, height)))

    boxes, weights = _HOG.detectMultiScale(
        resized,
        winStride=(8, 8),
        padding=(8, 8),
        scale=1.05,
    )

    scale_x = width / resized.shape[1]
    scale_y = height / resized.shape[0]

    detections: List[Detection] = []
    for index, (x, y, w, h) in enumerate(boxes):
        confidence = float(weights[index]) if len(weights) > index else 0.65
        if confidence < 0.3:
            continue

        x_scaled = int(x * scale_x)
        y_scaled = int(y * scale_y)
        w_scaled = int(w * scale_x)
        h_scaled = int(h * scale_y)

        detections.append(
            Detection(
                category="worker",
                confidence=min(0.99, max(0.35, confidence)),
                bbox=_to_bbox(x_scaled, y_scaled, w_scaled, h_scaled, width, height),
                zone=site_area,
                moving=True,
            )
        )

    return detections


def _contour_fallback_detections(frame: np.ndarray, site_area: str) -> List[Detection]:
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    edges = cv2.Canny(blurred, 60, 160)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    detections: List[Detection] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 2500 or area > 90000:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = w / max(1, h)
        if aspect_ratio > 1.8:
            continue

        detections.append(
            Detection(
                category="worker",
                confidence=0.42,
                bbox=_to_bbox(x, y, w, h, width, height),
                zone=site_area,
                moving=True,
            )
        )

    return detections[:8]


def _motion_score(current_frame: np.ndarray, previous_frame: Optional[np.ndarray]) -> float:
    if previous_frame is None:
        return 0.0

    current_small = cv2.resize(current_frame, (320, 180))
    previous_small = cv2.resize(previous_frame, (320, 180))

    current_gray = cv2.cvtColor(current_small, cv2.COLOR_BGR2GRAY)
    previous_gray = cv2.cvtColor(previous_small, cv2.COLOR_BGR2GRAY)

    diff = cv2.absdiff(current_gray, previous_gray)
    _, thresh = cv2.threshold(diff, 22, 255, cv2.THRESH_BINARY)
    motion_ratio = float(np.count_nonzero(thresh)) / float(thresh.size)

    return min(1.0, max(0.0, motion_ratio))


def analyze_camera_image(
    request: CameraImageRequest,
) -> Tuple[CameraFrame, str, float]:
    current_frame = _decode_base64_image(request.image_base64)

    previous_frame = None
    if request.previous_image_base64:
        try:
            previous_frame = _decode_base64_image(request.previous_image_base64)
        except Exception:
            previous_frame = None

    yolo_detections, yolo_detector = _yolo_safety_detections(current_frame, request.site_area)

    worker_detections = [detection for detection in yolo_detections if detection.category == "worker"]
    fallback_detector = ""

    if not worker_detections:
        worker_detections = _hog_worker_detections(current_frame, request.site_area)
        fallback_detector = "hog-people-detector"

    if not worker_detections:
        worker_detections = _contour_fallback_detections(current_frame, request.site_area)
        fallback_detector = "contour-fallback"

    safety_detections = [detection for detection in yolo_detections if detection.category != "worker"]
    detections = worker_detections + safety_detections

    if yolo_detector == "yolo-safety" and fallback_detector:
        detector = f"yolo-safety+{fallback_detector}"
    elif yolo_detector == "yolo-safety":
        detector = "yolo-safety"
    elif fallback_detector:
        detector = fallback_detector
    else:
        detector = yolo_detector

    motion_score = _motion_score(current_frame, previous_frame)
    moving = motion_score >= 0.02

    for detection in detections:
        if detection.category == "worker":
            detection.moving = moving

    if not detections and motion_score > 0.05:
        detections.append(
            Detection(
                category="worker",
                confidence=0.3,
                bbox=BoundingBox(x=0.4, y=0.3, w=0.2, h=0.35),
                zone=request.site_area,
                moving=True,
            )
        )
        detector = "motion-fallback"

    frame = CameraFrame(
        camera_id=request.camera_id,
        timestamp=datetime.now(timezone.utc),
        site_area=request.site_area,
        expected_workers=request.expected_workers,
        tasks_planned=request.tasks_planned,
        tasks_completed=request.tasks_completed,
        detections=detections,
    )

    return frame, detector, round(motion_score, 3)
