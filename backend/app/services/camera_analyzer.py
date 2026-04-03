import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.schemas import BoundingBox, CameraFrame, CameraImageRequest, Detection


_HOG = cv2.HOGDescriptor()
_HOG.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
YOLO_MODEL_PATH = MODEL_DIR / "safety_yolov8.onnx"
YOLO_CLASSES_PATH = MODEL_DIR / "safety_classes.txt"
YOLO_PERSON_MODEL_PATH = MODEL_DIR / "person_yolov8.onnx"
YOLO_PERSON_CLASSES_PATH = MODEL_DIR / "person_classes.txt"
YOLO_INPUT_SIZE = 640
YOLO_CONF_THRESHOLD = 0.35
YOLO_NMS_THRESHOLD = 0.45
TRACK_MATCH_IOU = 0.12
TRACK_MAX_MISSES = 1
TRACK_STALE_SECONDS = 18
TRACK_SMOOTH_ALPHA = 0.58
TRACK_OVERFLOW_MARGIN = 3
MIN_TRACK_CONFIDENCE = 0.36
MAX_FALLBACK_WORKERS_AUTO = 1
MIN_FALLBACK_BBOX_AREA = 0.06
MIN_FALLBACK_BBOX_HEIGHT = 0.24
TRACK_CENTER_MATCH_DISTANCE = 0.16
EYES_IDLE_THRESHOLD_SEC = 10.0
MAX_EYE_CLOSED_SECONDS = 120.0
KEYBOARD_BREAK_THRESHOLD_SEC = 10.0
MAX_HAND_OFF_SECONDS = 600.0
FACE_ANCHOR_CONFIDENCE = 0.9
SINGLE_PERSON_FACE_BLEND = 0.86

_YOLO_NET: Optional[cv2.dnn.Net] = None
_YOLO_LABELS: List[str] = []
_YOLO_LOAD_ATTEMPTED = False
_YOLO_LOCK = Lock()

_PERSON_YOLO_NET: Optional[cv2.dnn.Net] = None
_PERSON_YOLO_LABELS: List[str] = []
_PERSON_YOLO_LOAD_ATTEMPTED = False
_PERSON_YOLO_LOCK = Lock()

_FACE_CASCADE = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
_FACE_CASCADE_ALT = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_alt2.xml"))
_FACE_PROFILE_CASCADE = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_profileface.xml"))
_EYE_CASCADE = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_eye_tree_eyeglasses.xml"))


@dataclass
class _TrackedWorker:
    track_id: int
    bbox: BoundingBox
    confidence: float
    zone: str
    moving: bool
    face_bbox: Optional[BoundingBox] = None
    face_detected: bool = False
    eyes_closed: bool = False
    eyes_closed_seconds: float = 0.0
    hand_on_keyboard: Optional[bool] = None
    hand_off_keyboard_seconds: float = 0.0
    missed_frames: int = 0
    age_frames: int = 1


@dataclass
class _CameraTrackerState:
    next_track_id: int = 1
    workers: List[_TrackedWorker] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_CAMERA_TRACKERS: Dict[str, _CameraTrackerState] = {}
_TRACKER_LOCK = Lock()


def _safe_detect_multiscale(
    cascade: cv2.CascadeClassifier,
    source: np.ndarray,
    scale_factor: float,
    min_neighbors: int,
    min_size: Tuple[int, int],
) -> List[Tuple[int, int, int, int]]:
    if cascade.empty() or source.size == 0:
        return []

    height, width = source.shape[:2]
    if width < min_size[0] or height < min_size[1]:
        return []

    try:
        raw = cascade.detectMultiScale(
            source,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=min_size,
        )
    except cv2.error:
        return []

    if raw is None or len(raw) == 0:
        return []

    return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in raw]


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


def _bbox_iou(a: BoundingBox, b: BoundingBox) -> float:
    ax1, ay1 = a.x, a.y
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx1, by1 = b.x, b.y
    bx2, by2 = b.x + b.w, b.y + b.h

    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0

    area_a = max(0.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(0.0, (bx2 - bx1) * (by2 - by1))
    union = area_a + area_b - inter_area
    if union <= 0.0:
        return 0.0

    return max(0.0, min(1.0, inter_area / union))


def _bbox_area(bbox: BoundingBox) -> float:
    return max(0.0, bbox.w * bbox.h)


def _bbox_center_distance(a: BoundingBox, b: BoundingBox) -> float:
    ax = a.x + (a.w / 2.0)
    ay = a.y + (a.h / 2.0)
    bx = b.x + (b.w / 2.0)
    by = b.y + (b.h / 2.0)
    return float(np.hypot(ax - bx, ay - by))


def _nms_worker_detections(detections: List[Detection], iou_threshold: float = 0.42) -> List[Detection]:
    if len(detections) <= 1:
        return detections

    sorted_detections = sorted(detections, key=lambda detection: detection.confidence, reverse=True)
    kept: List[Detection] = []

    for candidate in sorted_detections:
        if any(_bbox_iou(candidate.bbox, current.bbox) >= iou_threshold for current in kept):
            continue
        kept.append(candidate)

    return kept


def _intersection_over_smaller(a: BoundingBox, b: BoundingBox) -> float:
    ax1, ay1 = a.x, a.y
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx1, by1 = b.x, b.y
    bx2, by2 = b.x + b.w, b.y + b.h

    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0

    area_a = max(0.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(0.0, (bx2 - bx1) * (by2 - by1))
    smaller = max(1e-6, min(area_a, area_b))

    return max(0.0, min(1.0, inter_area / smaller))


def _suppress_contained_worker_detections(
    detections: List[Detection],
    containment_threshold: float = 0.72,
) -> List[Detection]:
    if len(detections) <= 1:
        return detections

    ordered = sorted(detections, key=lambda detection: detection.confidence, reverse=True)
    kept: List[Detection] = []

    for candidate in ordered:
        if any(
            _intersection_over_smaller(candidate.bbox, current.bbox) >= containment_threshold
            for current in kept
        ):
            continue
        kept.append(candidate)

    return kept


def _face_body_fallback_detections(frame: np.ndarray, site_area: str) -> List[Detection]:
    if _FACE_CASCADE.empty():
        return []

    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    faces = _safe_detect_multiscale(
        _FACE_CASCADE,
        gray,
        scale_factor=1.1,
        min_neighbors=5,
        min_size=(28, 28),
    )

    detections: List[Detection] = []
    for (x, y, w, h) in faces:
        body_x = x - int(0.9 * w)
        body_y = y - int(0.45 * h)
        body_w = int(2.8 * w)
        body_h = int(4.8 * h)

        body_x = max(0, body_x)
        body_y = max(0, body_y)
        body_w = max(16, min(width - body_x, body_w))
        body_h = max(16, min(height - body_y, body_h))

        if body_w * body_h < 2600:
            continue

        detections.append(
            Detection(
                category="worker",
                confidence=0.72,
                bbox=_to_bbox(body_x, body_y, body_w, body_h, width, height),
                zone=site_area,
                moving=False,
            )
        )

    detections = _nms_worker_detections(detections, iou_threshold=0.3)
    detections = _suppress_contained_worker_detections(detections, containment_threshold=0.75)
    return detections[:4]


def _smooth_bbox(previous: BoundingBox, current: BoundingBox, alpha: float = TRACK_SMOOTH_ALPHA) -> BoundingBox:
    blended_x = (alpha * current.x) + ((1.0 - alpha) * previous.x)
    blended_y = (alpha * current.y) + ((1.0 - alpha) * previous.y)
    blended_w = (alpha * current.w) + ((1.0 - alpha) * previous.w)
    blended_h = (alpha * current.h) + ((1.0 - alpha) * previous.h)

    return BoundingBox(
        x=max(0.0, min(1.0, blended_x)),
        y=max(0.0, min(1.0, blended_y)),
        w=max(0.01, min(1.0, blended_w)),
        h=max(0.01, min(1.0, blended_h)),
    )


def _load_labels_file(labels_path: Path, fallback_labels: List[str]) -> List[str]:
    if labels_path.exists():
        lines = labels_path.read_text(encoding="utf-8").splitlines()
        labels = [line.strip() for line in lines if line.strip()]
        if labels:
            return labels

    return fallback_labels


def _load_safety_yolo_labels() -> List[str]:
    return _load_labels_file(
        YOLO_CLASSES_PATH,
        [
            "person",
            "helmet",
            "no_helmet",
            "cell phone",
            "restricted_zone_entry",
            "vehicle",
        ],
    )


def _load_person_yolo_labels() -> List[str]:
    return _load_labels_file(
        YOLO_PERSON_CLASSES_PATH,
        [
            "person",
            "bicycle",
            "car",
            "motorcycle",
            "airplane",
            "bus",
            "train",
            "truck",
            "boat",
            "traffic light",
        ],
    )


def _load_safety_yolo_model() -> Tuple[Optional[cv2.dnn.Net], List[str]]:
    global _YOLO_NET, _YOLO_LABELS, _YOLO_LOAD_ATTEMPTED

    with _YOLO_LOCK:
        if _YOLO_NET is not None:
            return _YOLO_NET, _YOLO_LABELS

        if _YOLO_LOAD_ATTEMPTED:
            return None, _YOLO_LABELS

        _YOLO_LOAD_ATTEMPTED = True
        _YOLO_LABELS = _load_safety_yolo_labels()

        if not YOLO_MODEL_PATH.exists():
            return None, _YOLO_LABELS

        try:
            _YOLO_NET = cv2.dnn.readNetFromONNX(str(YOLO_MODEL_PATH))
        except Exception:
            _YOLO_NET = None

        return _YOLO_NET, _YOLO_LABELS


def _load_person_yolo_model() -> Tuple[Optional[cv2.dnn.Net], List[str]]:
    global _PERSON_YOLO_NET, _PERSON_YOLO_LABELS, _PERSON_YOLO_LOAD_ATTEMPTED

    with _PERSON_YOLO_LOCK:
        if _PERSON_YOLO_NET is not None:
            return _PERSON_YOLO_NET, _PERSON_YOLO_LABELS

        if _PERSON_YOLO_LOAD_ATTEMPTED:
            return None, _PERSON_YOLO_LABELS

        _PERSON_YOLO_LOAD_ATTEMPTED = True
        _PERSON_YOLO_LABELS = _load_person_yolo_labels()

        if not YOLO_PERSON_MODEL_PATH.exists():
            return None, _PERSON_YOLO_LABELS

        try:
            _PERSON_YOLO_NET = cv2.dnn.readNetFromONNX(str(YOLO_PERSON_MODEL_PATH))
        except Exception:
            _PERSON_YOLO_NET = None

        return _PERSON_YOLO_NET, _PERSON_YOLO_LABELS


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
    net, labels = _load_safety_yolo_model()
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


def _yolo_person_detections(frame: np.ndarray, site_area: str) -> Tuple[List[Detection], str]:
    net, labels = _load_person_yolo_model()
    if net is None:
        return [], "person-yolo-unavailable"

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
        return [], "person-yolo-error"

    rows = _parse_yolo_rows(output)
    if rows.size == 0:
        return [], "person-yolo-empty"

    boxes: List[List[int]] = []
    confidences: List[float] = []

    for row in rows:
        if row.shape[0] < 6:
            continue

        cx, cy, bw, bh = float(row[0]), float(row[1]), float(row[2]), float(row[3])
        class_scores = row[4:]
        class_id = int(np.argmax(class_scores))
        confidence = float(class_scores[class_id])

        if confidence < 0.3:
            continue

        label = labels[class_id] if class_id < len(labels) else f"class-{class_id}"
        category = _map_label_to_category(label)
        if category != "worker":
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

    if not boxes:
        return [], "person-yolo-no-person"

    raw_indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.3, YOLO_NMS_THRESHOLD)
    if len(raw_indices) == 0:
        return [], "person-yolo-nms-empty"

    if isinstance(raw_indices, np.ndarray):
        indices = raw_indices.flatten().tolist()
    else:
        indices = [int(idx[0]) if isinstance(idx, (list, tuple, np.ndarray)) else int(idx) for idx in raw_indices]

    detections: List[Detection] = []
    for idx in indices:
        x, y, w_box, h_box = boxes[idx]
        detections.append(
            Detection(
                category="worker",
                confidence=min(0.99, max(0.35, float(confidences[idx]))),
                bbox=_to_bbox(x, y, w_box, h_box, width, height),
                zone=site_area,
                moving=True,
            )
        )

    detections = _nms_worker_detections(detections, iou_threshold=0.3)
    detections = _suppress_contained_worker_detections(detections, containment_threshold=0.74)
    detections.sort(key=lambda detection: detection.confidence, reverse=True)
    return detections[:6], "person-yolo"


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


def _contour_fallback_detections(
    frame: np.ndarray,
    previous_frame: Optional[np.ndarray],
    site_area: str,
) -> List[Detection]:
    height, width = frame.shape[:2]
    frame_area = float(max(1, width * height))

    if previous_frame is None or previous_frame.shape[:2] != frame.shape[:2]:
        return []

    current_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    previous_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.GaussianBlur(current_gray, (7, 7), 0)
    previous_gray = cv2.GaussianBlur(previous_gray, (7, 7), 0)

    diff = cv2.absdiff(current_gray, previous_gray)
    _, motion_mask = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
    motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    motion_mask = cv2.dilate(motion_mask, np.ones((5, 5), np.uint8), iterations=1)

    motion_contours, _ = cv2.findContours(motion_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections: List[Detection] = []
    for contour in motion_contours:
        area = cv2.contourArea(contour)
        if area < 1300 or area > (frame_area * 0.5):
            continue

        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = w / max(1, h)
        fill_ratio = area / float(max(1, w * h))
        if aspect_ratio < 0.2 or aspect_ratio > 1.25:
            continue
        if fill_ratio < 0.28:
            continue

        confidence = min(0.7, max(0.42, 0.42 + ((area / frame_area) * 8.0)))
        detections.append(
            Detection(
                category="worker",
                confidence=confidence,
                bbox=_to_bbox(x, y, w, h, width, height),
                zone=site_area,
                moving=True,
            )
        )

    detections = _nms_worker_detections(detections, iou_threshold=0.32)
    detections = _suppress_contained_worker_detections(detections, containment_threshold=0.7)
    detections.sort(key=lambda detection: detection.confidence, reverse=True)
    return detections[:3]


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


def _keyboard_zone_from_worker_bbox(
    bbox: BoundingBox,
    width: int,
    height: int,
) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = _bbox_to_pixels(bbox, width, height)
    worker_w = max(1, x2 - x1)
    worker_h = max(1, y2 - y1)

    keyboard_x1 = x1 + int(worker_w * 0.08)
    keyboard_x2 = x2 - int(worker_w * 0.08)
    keyboard_y1 = y1 + int(worker_h * 0.56)
    keyboard_y2 = y1 + int(worker_h * 0.98)

    keyboard_x1 = max(0, min(width - 1, keyboard_x1))
    keyboard_y1 = max(0, min(height - 1, keyboard_y1))
    keyboard_x2 = max(keyboard_x1 + 1, min(width, keyboard_x2))
    keyboard_y2 = max(keyboard_y1 + 1, min(height, keyboard_y2))

    return keyboard_x1, keyboard_y1, keyboard_x2, keyboard_y2


def _detect_hand_on_keyboard(
    current_frame: np.ndarray,
    previous_frame: Optional[np.ndarray],
    bbox: BoundingBox,
) -> Optional[bool]:
    height, width = current_frame.shape[:2]
    x1, y1, x2, y2 = _keyboard_zone_from_worker_bbox(bbox, width, height)

    keyboard_roi = current_frame[y1:y2, x1:x2]
    if keyboard_roi.size == 0:
        return None

    if keyboard_roi.shape[0] < 16 or keyboard_roi.shape[1] < 16:
        return None

    hsv = cv2.cvtColor(keyboard_roi, cv2.COLOR_BGR2HSV)
    ycrcb = cv2.cvtColor(keyboard_roi, cv2.COLOR_BGR2YCrCb)

    skin_hsv_mask = cv2.inRange(hsv, (0, 30, 30), (25, 210, 255))
    skin_ycrcb_mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    skin_mask = cv2.bitwise_or(skin_hsv_mask, skin_ycrcb_mask)
    skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    skin_ratio = float(np.count_nonzero(skin_mask)) / float(skin_mask.size)

    motion_ratio = 0.0
    if previous_frame is not None and previous_frame.shape[:2] == current_frame.shape[:2]:
        previous_roi = previous_frame[y1:y2, x1:x2]
        if previous_roi.size > 0:
            current_gray = cv2.cvtColor(keyboard_roi, cv2.COLOR_BGR2GRAY)
            previous_gray = cv2.cvtColor(previous_roi, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(current_gray, previous_gray)
            _, thresh = cv2.threshold(diff, 16, 255, cv2.THRESH_BINARY)
            motion_ratio = float(np.count_nonzero(thresh)) / float(thresh.size)

    brightness = float(np.mean(cv2.cvtColor(keyboard_roi, cv2.COLOR_BGR2GRAY)))
    if brightness < 22.0 and motion_ratio < 0.015 and skin_ratio < 0.01:
        return None

    hand_presence_score = max(
        skin_ratio * 3.2,
        motion_ratio * 2.6,
        (skin_ratio + motion_ratio) * 1.8,
    )

    if skin_ratio >= 0.022:
        return True

    return hand_presence_score >= 0.064


def _bbox_to_pixels(
    bbox: BoundingBox,
    width: int,
    height: int,
    padding_ratio: float = 0.0,
) -> Tuple[int, int, int, int]:
    x1 = int((bbox.x - padding_ratio) * width)
    y1 = int((bbox.y - padding_ratio) * height)
    x2 = int((bbox.x + bbox.w + padding_ratio) * width)
    y2 = int((bbox.y + bbox.h + padding_ratio) * height)

    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(x1 + 1, min(width, x2))
    y2 = max(y1 + 1, min(height, y2))

    return x1, y1, x2, y2


def _detect_face_eye_state(
    frame: np.ndarray,
    bbox: BoundingBox,
) -> Tuple[bool, Optional[bool], Optional[BoundingBox]]:
    if _FACE_CASCADE.empty() and _FACE_CASCADE_ALT.empty() and _FACE_PROFILE_CASCADE.empty():
        return False, None, None

    height, width = frame.shape[:2]
    x1, y1, x2, y2 = _bbox_to_pixels(bbox, width, height, padding_ratio=0.02)
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return False, None, None

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    face = _detect_primary_face(gray)
    if face is None:
        return False, None, None

    fx, fy, fw, fh = face
    face_bbox = _to_bbox(x1 + fx, y1 + fy, fw, fh, width, height)
    face_roi = gray[fy:fy + fh, fx:fx + fw]
    if face_roi.size == 0:
        return True, None, face_bbox

    if _EYE_CASCADE.empty():
        return True, None, face_bbox

    upper_face = face_roi[: max(1, int(face_roi.shape[0] * 0.72)), :]
    eyes = _safe_detect_multiscale(
        _EYE_CASCADE,
        upper_face,
        scale_factor=1.1,
        min_neighbors=3,
        min_size=(8, 8),
    )

    eyes_open = len(eyes) >= 1
    return True, not eyes_open, face_bbox


def _detect_primary_face(gray: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    if _FACE_CASCADE.empty() and _FACE_CASCADE_ALT.empty() and _FACE_PROFILE_CASCADE.empty():
        return None

    height, width = gray.shape[:2]
    candidates: List[Tuple[int, int, int, int, float]] = []

    frontal_search_profiles = [
        (1.08, 5, (34, 34)),
        (1.06, 4, (26, 26)),
        (1.12, 6, (42, 42)),
    ]
    profile_search_profiles = [
        (1.08, 4, (28, 28)),
        (1.06, 3, (22, 22)),
    ]

    def _collect_candidates(
        cascade: cv2.CascadeClassifier,
        search_profiles: List[Tuple[float, int, Tuple[int, int]]],
        source_bonus: float,
        mirrored: bool = False,
    ) -> None:
        if cascade.empty():
            return

        source = cv2.flip(gray, 1) if mirrored else gray
        source_width = source.shape[1]
        for scale_factor, min_neighbors, min_size in search_profiles:
            faces = _safe_detect_multiscale(
                cascade,
                source,
                scale_factor=scale_factor,
                min_neighbors=min_neighbors,
                min_size=min_size,
            )
            if len(faces) == 0:
                continue

            for (x, y, w, h) in faces:
                x_px = int(source_width - x - w) if mirrored else int(x)
                y_px = int(y)
                w_px = int(w)
                h_px = int(h)

                if w_px <= 0 or h_px <= 0:
                    continue

                if x_px < 0 or y_px < 0 or (x_px + w_px) > width or (y_px + h_px) > height:
                    continue

                candidates.append((x_px, y_px, w_px, h_px, source_bonus))

    _collect_candidates(_FACE_CASCADE, frontal_search_profiles, source_bonus=0.12)
    _collect_candidates(_FACE_CASCADE_ALT, frontal_search_profiles, source_bonus=0.09)
    _collect_candidates(_FACE_PROFILE_CASCADE, profile_search_profiles, source_bonus=-0.02, mirrored=False)
    _collect_candidates(_FACE_PROFILE_CASCADE, profile_search_profiles, source_bonus=-0.02, mirrored=True)

    if not candidates:
        return None

    def _pixel_iou(a: Tuple[int, int, int, int, float], b: Tuple[int, int, int, int, float]) -> float:
        ax1, ay1, aw, ah, _ = a
        bx1, by1, bw, bh, _ = b
        ax2, ay2 = ax1 + aw, ay1 + ah
        bx2, by2 = bx1 + bw, by1 + bh

        inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
        inter_h = max(0, min(ay2, by2) - max(ay1, by1))
        inter_area = inter_w * inter_h
        if inter_area <= 0:
            return 0.0

        area_a = max(1, aw * ah)
        area_b = max(1, bw * bh)
        union = area_a + area_b - inter_area
        if union <= 0:
            return 0.0

        return inter_area / float(union)

    deduped: List[Tuple[int, int, int, int, float]] = []
    for candidate in sorted(candidates, key=lambda item: item[2] * item[3], reverse=True):
        if any(_pixel_iou(candidate, existing) >= 0.42 for existing in deduped):
            continue
        deduped.append(candidate)

    image_cx = width / 2.0
    image_cy = height / 2.0

    def _face_score(face: Tuple[int, int, int, int, float]) -> float:
        x, y, w, h, source_bonus = face
        area = float(w * h)
        cx = x + (w / 2.0)
        cy = y + (h / 2.0)

        center_dist = np.hypot((cx - image_cx) / max(1.0, width), (cy - image_cy) / max(1.0, height))
        aspect_ratio = w / max(1.0, h)
        aspect_penalty = abs(aspect_ratio - 0.78)
        low_face_penalty = max(0.0, ((y / max(1.0, height)) - 0.72))

        return (
            area
            - (center_dist * area * 0.5)
            - (aspect_penalty * area * 0.3)
            - (low_face_penalty * area * 0.8)
            + (source_bonus * area)
        )

    best = max(deduped, key=_face_score)
    return int(best[0]), int(best[1]), int(best[2]), int(best[3])


def _eyes_closed_from_face_roi(face_gray: np.ndarray) -> Optional[bool]:
    if _EYE_CASCADE.empty() or face_gray.size == 0:
        return None

    upper_face = face_gray[: max(1, int(face_gray.shape[0] * 0.72)), :]
    if upper_face.size == 0:
        return None

    eyes = _safe_detect_multiscale(
        _EYE_CASCADE,
        upper_face,
        scale_factor=1.1,
        min_neighbors=3,
        min_size=(8, 8),
    )
    if len(eyes) >= 1:
        return False

    brightness = float(np.mean(upper_face))
    if brightness < 42.0:
        return None

    return True


def _face_anchor_worker_detection(frame: np.ndarray, site_area: str) -> Optional[Detection]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    face = _detect_primary_face(gray)
    if face is None:
        return None

    x, y, w, h = face
    height, width = frame.shape[:2]
    face_area_ratio = float(w * h) / float(max(1, width * height))

    if face_area_ratio >= 0.16:
        body_x = x - int(0.56 * w)
        body_y = y - int(0.14 * h)
        body_w = int(2.15 * w)
        body_h = int(3.25 * h)
    else:
        body_x = x - int(0.82 * w)
        body_y = y - int(0.32 * h)
        body_w = int(2.65 * w)
        body_h = int(4.45 * h)

    body_x = max(0, body_x)
    body_y = max(0, body_y)
    body_w = max(20, min(width - body_x, body_w))
    body_h = max(20, min(height - body_y, body_h))

    face_roi = gray[y:y + h, x:x + w]
    eyes_closed = _eyes_closed_from_face_roi(face_roi)

    return Detection(
        category="worker",
        confidence=FACE_ANCHOR_CONFIDENCE,
        bbox=_to_bbox(body_x, body_y, body_w, body_h, width, height),
        face_bbox=_to_bbox(x, y, w, h, width, height),
        zone=site_area,
        moving=True,
        face_detected=True,
        eyes_closed=eyes_closed,
        eyes_closed_seconds=0.0,
        hand_on_keyboard=None,
        hand_off_keyboard_seconds=0.0,
    )


def _apply_eye_idle_override(detection: Detection) -> None:
    if detection.category != "worker":
        return

    if detection.eyes_closed and (detection.eyes_closed_seconds or 0.0) >= EYES_IDLE_THRESHOLD_SEC:
        detection.moving = False


def _apply_keyboard_break_override(detection: Detection) -> None:
    if detection.category != "worker":
        return

    if detection.hand_on_keyboard is False and (detection.hand_off_keyboard_seconds or 0.0) >= KEYBOARD_BREAK_THRESHOLD_SEC:
        detection.moving = False


def _region_motion_score(
    current_frame: np.ndarray,
    previous_frame: Optional[np.ndarray],
    bbox: BoundingBox,
) -> float:
    if previous_frame is None:
        return 0.0

    height, width = current_frame.shape[:2]
    x1, y1, x2, y2 = _bbox_to_pixels(bbox, width, height, padding_ratio=0.03)

    current_roi = current_frame[y1:y2, x1:x2]
    previous_roi = previous_frame[y1:y2, x1:x2]

    if current_roi.size == 0 or previous_roi.size == 0:
        return 0.0

    current_gray = cv2.cvtColor(current_roi, cv2.COLOR_BGR2GRAY)
    previous_gray = cv2.cvtColor(previous_roi, cv2.COLOR_BGR2GRAY)

    current_gray = cv2.GaussianBlur(current_gray, (5, 5), 0)
    previous_gray = cv2.GaussianBlur(previous_gray, (5, 5), 0)

    diff = cv2.absdiff(current_gray, previous_gray)
    _, thresh = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
    motion_ratio = float(np.count_nonzero(thresh)) / float(thresh.size)

    return min(1.0, max(0.0, motion_ratio))


def _match_tracks(
    tracks: List[_TrackedWorker],
    detections: List[Detection],
) -> Tuple[List[Tuple[int, int]], set[int], set[int]]:
    if not tracks or not detections:
        return [], set(), set()

    candidates: List[Tuple[float, int, int]] = []
    for track_index, track in enumerate(tracks):
        for detection_index, detection in enumerate(detections):
            iou = _bbox_iou(track.bbox, detection.bbox)
            distance = _bbox_center_distance(track.bbox, detection.bbox)
            area_ratio = _bbox_area(detection.bbox) / max(1e-6, _bbox_area(track.bbox))
            size_compatible = 0.45 <= area_ratio <= 2.2

            if iou >= TRACK_MATCH_IOU or (distance <= TRACK_CENTER_MATCH_DISTANCE and size_compatible):
                score = max(iou, 1.0 - distance)
                candidates.append((score, track_index, detection_index))

    candidates.sort(reverse=True)
    matched_tracks: set[int] = set()
    matched_detections: set[int] = set()
    pairs: List[Tuple[int, int]] = []

    for _, track_index, detection_index in candidates:
        if track_index in matched_tracks or detection_index in matched_detections:
            continue
        matched_tracks.add(track_index)
        matched_detections.add(detection_index)
        pairs.append((track_index, detection_index))

    return pairs, matched_tracks, matched_detections


def _stabilize_worker_detections(
    camera_id: str,
    worker_detections: List[Detection],
    site_area: str,
    motion_score: float,
    expected_workers: int,
) -> List[Detection]:
    now = datetime.now(timezone.utc)

    with _TRACKER_LOCK:
        stale_camera_ids = [
            key
            for key, tracker_state in _CAMERA_TRACKERS.items()
            if (now - tracker_state.last_updated).total_seconds() > (TRACK_STALE_SECONDS * 2)
        ]
        for stale_camera_id in stale_camera_ids:
            _CAMERA_TRACKERS.pop(stale_camera_id, None)

        state = _CAMERA_TRACKERS.get(camera_id)
        if state is None:
            state = _CameraTrackerState()
            _CAMERA_TRACKERS[camera_id] = state
        elif (now - state.last_updated).total_seconds() > TRACK_STALE_SECONDS:
            state.workers.clear()
            state.next_track_id = 1

        if state.workers:
            dt_seconds = max(0.3, min(3.0, (now - state.last_updated).total_seconds()))
        else:
            dt_seconds = 1.0

        state.last_updated = now

        pairs, matched_tracks, matched_detections = _match_tracks(state.workers, worker_detections)

        for track_index, detection_index in pairs:
            track = state.workers[track_index]
            detection = worker_detections[detection_index]

            track.bbox = _smooth_bbox(track.bbox, detection.bbox)
            track.confidence = min(0.99, (track.confidence * 0.45) + (detection.confidence * 0.55))
            track.zone = detection.zone or site_area
            track.moving = detection.moving
            track.missed_frames = 0
            track.age_frames += 1

            if detection.face_detected is True:
                track.face_detected = True
                if detection.face_bbox is not None:
                    track.face_bbox = detection.face_bbox
                if detection.eyes_closed is True:
                    track.eyes_closed = True
                    track.eyes_closed_seconds = min(
                        MAX_EYE_CLOSED_SECONDS,
                        track.eyes_closed_seconds + dt_seconds,
                    )
                elif detection.eyes_closed is False:
                    track.eyes_closed = False
                    track.eyes_closed_seconds = 0.0
            elif detection.face_detected is False:
                track.face_detected = False
                track.face_bbox = None
                track.eyes_closed = False
                track.eyes_closed_seconds = max(0.0, track.eyes_closed_seconds - (dt_seconds * 0.8))

            if detection.hand_on_keyboard is True:
                track.hand_on_keyboard = True
                track.hand_off_keyboard_seconds = 0.0
            elif detection.hand_on_keyboard is False:
                track.hand_on_keyboard = False
                track.hand_off_keyboard_seconds = min(
                    MAX_HAND_OFF_SECONDS,
                    track.hand_off_keyboard_seconds + dt_seconds,
                )

        for track_index, track in enumerate(state.workers):
            if track_index in matched_tracks:
                continue
            track.missed_frames += 1
            if motion_score < 0.015:
                track.moving = False
            track.face_detected = False
            track.face_bbox = None
            track.eyes_closed = False
            track.eyes_closed_seconds = max(0.0, track.eyes_closed_seconds - (dt_seconds * 0.5))
            track.hand_on_keyboard = False
            track.hand_off_keyboard_seconds = min(
                MAX_HAND_OFF_SECONDS,
                track.hand_off_keyboard_seconds + (dt_seconds * 0.8),
            )

        for detection_index, detection in enumerate(worker_detections):
            if detection_index in matched_detections:
                continue

            state.workers.append(
                _TrackedWorker(
                    track_id=state.next_track_id,
                    bbox=detection.bbox,
                    confidence=detection.confidence,
                    zone=detection.zone or site_area,
                    moving=detection.moving,
                    face_bbox=detection.face_bbox if detection.face_detected else None,
                    face_detected=bool(detection.face_detected),
                    eyes_closed=bool(detection.eyes_closed),
                    eyes_closed_seconds=(
                        min(MAX_EYE_CLOSED_SECONDS, dt_seconds)
                        if detection.face_detected and detection.eyes_closed
                        else 0.0
                    ),
                    hand_on_keyboard=detection.hand_on_keyboard,
                    hand_off_keyboard_seconds=(
                        min(MAX_HAND_OFF_SECONDS, dt_seconds)
                        if detection.hand_on_keyboard is False
                        else 0.0
                    ),
                )
            )
            state.next_track_id += 1

        state.workers = [track for track in state.workers if track.missed_frames <= TRACK_MAX_MISSES]

        stabilized: List[Detection] = []
        for track in state.workers:
            confidence_decay = max(0.0, 1.0 - (0.22 * track.missed_frames))
            stabilized_confidence = max(0.25, min(0.99, track.confidence * confidence_decay))
            if stabilized_confidence < MIN_TRACK_CONFIDENCE:
                continue
            if track.missed_frames > 0 and motion_score < 0.02:
                continue

            stabilized.append(
                Detection(
                    category="worker",
                    confidence=round(stabilized_confidence, 3),
                    bbox=track.bbox,
                    zone=track.zone,
                    moving=track.moving,
                    track_id=f"W-{track.track_id:03d}",
                    face_bbox=track.face_bbox,
                    face_detected=track.face_detected,
                    eyes_closed=track.eyes_closed,
                    eyes_closed_seconds=round(track.eyes_closed_seconds, 1),
                    hand_on_keyboard=track.hand_on_keyboard,
                    hand_off_keyboard_seconds=round(track.hand_off_keyboard_seconds, 1),
                )
            )

        if expected_workers > 0:
            max_workers = max(1, expected_workers + TRACK_OVERFLOW_MARGIN)
            if len(stabilized) > max_workers:
                stabilized.sort(key=lambda detection: detection.confidence, reverse=True)
                stabilized = stabilized[:max_workers]

        for detection in stabilized:
            _apply_eye_idle_override(detection)
            _apply_keyboard_break_override(detection)

        stabilized.sort(key=lambda detection: detection.track_id or "")
        return stabilized


def _cap_fallback_worker_count(
    worker_detections: List[Detection],
    request: CameraImageRequest,
    fallback_detector: str,
) -> List[Detection]:
    if not worker_detections:
        return worker_detections

    if fallback_detector not in {"contour-fallback", "face-body-fallback"}:
        return worker_detections

    quality_filtered = [
        detection
        for detection in worker_detections
        if _bbox_area(detection.bbox) >= MIN_FALLBACK_BBOX_AREA
        and detection.bbox.h >= MIN_FALLBACK_BBOX_HEIGHT
    ]
    if quality_filtered:
        worker_detections = quality_filtered

    if request.expected_workers > 0:
        max_workers = max(1, min(request.expected_workers + 1, request.expected_workers + TRACK_OVERFLOW_MARGIN))
    else:
        max_workers = MAX_FALLBACK_WORKERS_AUTO

    if len(worker_detections) <= max_workers:
        return worker_detections

    ranked = sorted(
        worker_detections,
        key=lambda detection: detection.confidence * (0.65 + (_bbox_area(detection.bbox) * 0.8)),
        reverse=True,
    )
    return ranked[:max_workers]


def _apply_single_person_mode(worker_detections: List[Detection]) -> List[Detection]:
    if not worker_detections:
        return worker_detections

    ranked = sorted(
        worker_detections,
        key=lambda detection: (
            1 if detection.face_detected else 0,
            detection.confidence * (0.7 + (_bbox_area(detection.bbox) * 1.1)),
            1 if detection.moving else 0,
        ),
        reverse=True,
    )

    primary = ranked[0]
    primary.track_id = primary.track_id or "W-001"
    return [primary]


def analyze_camera_image(
    request: CameraImageRequest,
) -> Tuple[CameraFrame, str, float, bool]:
    current_frame = _decode_base64_image(request.image_base64)
    face_anchor_detection = (
        _face_anchor_worker_detection(current_frame, request.site_area)
        if request.single_person_mode
        else None
    )

    previous_frame = None
    if request.previous_image_base64:
        try:
            previous_frame = _decode_base64_image(request.previous_image_base64)
        except Exception:
            previous_frame = None

    yolo_detections, yolo_detector = _yolo_safety_detections(current_frame, request.site_area)

    worker_detections = [detection for detection in yolo_detections if detection.category == "worker"]
    worker_detector = "yolo-safety" if worker_detections else ""

    if not worker_detections:
        worker_detections, person_detector = _yolo_person_detections(current_frame, request.site_area)
        if worker_detections:
            worker_detector = person_detector

    if not worker_detections:
        worker_detections = _hog_worker_detections(current_frame, request.site_area)
        worker_detector = "hog-people-detector"

    if not worker_detections:
        worker_detections = _face_body_fallback_detections(current_frame, request.site_area)
        worker_detector = "face-body-fallback"

    if not worker_detections:
        worker_detections = _contour_fallback_detections(current_frame, previous_frame, request.site_area)
        worker_detector = "contour-fallback"

    if yolo_detector == "yolo-safety" and worker_detector and worker_detector != "yolo-safety":
        detector = f"yolo-safety+{worker_detector}"
    elif worker_detector:
        detector = worker_detector
    else:
        detector = yolo_detector

    if request.single_person_mode and face_anchor_detection is None:
        # In strict mode, do not trust generic detector fallbacks without a visible face.
        worker_detections = []
        detector = "single-person-no-face"

    motion_score = _motion_score(current_frame, previous_frame)
    for detection in worker_detections:
        if previous_frame is None:
            detection.moving = False
        else:
            local_motion_score = _region_motion_score(current_frame, previous_frame, detection.bbox)
            detection.moving = local_motion_score >= 0.012 or motion_score >= 0.03

        face_detected, eyes_closed, face_bbox = _detect_face_eye_state(current_frame, detection.bbox)
        detection.face_detected = face_detected
        detection.face_bbox = face_bbox if face_detected else None
        detection.eyes_closed = eyes_closed if face_detected else None
        detection.eyes_closed_seconds = 0.0

        hand_on_keyboard = _detect_hand_on_keyboard(current_frame, previous_frame, detection.bbox)
        detection.hand_on_keyboard = hand_on_keyboard
        if hand_on_keyboard is True:
            detection.hand_off_keyboard_seconds = 0.0
        elif hand_on_keyboard is False:
            detection.hand_off_keyboard_seconds = 1.0 if previous_frame is not None else 0.0
        else:
            detection.hand_off_keyboard_seconds = 0.0

    worker_detections = _nms_worker_detections(worker_detections)
    worker_detections = _suppress_contained_worker_detections(worker_detections)

    if request.single_person_mode and face_anchor_detection is not None:
        if worker_detections:
            best = max(
                worker_detections,
                key=lambda detection: (
                    _bbox_iou(detection.bbox, face_anchor_detection.bbox),
                    -_bbox_center_distance(detection.bbox, face_anchor_detection.bbox),
                    detection.confidence,
                ),
            )
            best.bbox = _smooth_bbox(best.bbox, face_anchor_detection.bbox, alpha=SINGLE_PERSON_FACE_BLEND)
            best.face_detected = True
            best.face_bbox = face_anchor_detection.face_bbox
            best.eyes_closed = face_anchor_detection.eyes_closed
            worker_detections = [best]
        else:
            worker_detections = [face_anchor_detection]

    worker_detections = _cap_fallback_worker_count(worker_detections, request, worker_detector)
    tracker_expected_workers = 1 if request.single_person_mode else request.expected_workers
    worker_detections = _stabilize_worker_detections(
        camera_id=request.camera_id,
        worker_detections=worker_detections,
        site_area=request.site_area,
        motion_score=motion_score,
        expected_workers=tracker_expected_workers,
    )

    if request.single_person_mode:
        if face_anchor_detection is not None and worker_detections:
            worker_detections[0].bbox = _smooth_bbox(
                worker_detections[0].bbox,
                face_anchor_detection.bbox,
                alpha=SINGLE_PERSON_FACE_BLEND,
            )
            worker_detections[0].face_detected = True
            worker_detections[0].face_bbox = face_anchor_detection.face_bbox
            worker_detections[0].eyes_closed = face_anchor_detection.eyes_closed
        elif face_anchor_detection is not None and not worker_detections:
            worker_detections = [face_anchor_detection]
        elif face_anchor_detection is None:
            worker_detections = [
                detection
                for detection in worker_detections
                if detection.face_detected
            ]

        worker_detections = _apply_single_person_mode(worker_detections)
        if worker_detections and face_anchor_detection is not None:
            worker_detections[0].face_detected = True
            worker_detections[0].face_bbox = face_anchor_detection.face_bbox
            worker_detections[0].eyes_closed = face_anchor_detection.eyes_closed
            worker_detections[0].eyes_closed_seconds = worker_detections[0].eyes_closed_seconds or 0.0
        if not worker_detections:
            detector = "single-person-no-face"

    safety_detections = [detection for detection in yolo_detections if detection.category != "worker"]
    detections = worker_detections + safety_detections

    for detection in detections:
        if detection.category != "worker":
            continue

        if previous_frame is None and not detection.moving:
            detection.moving = False

        _apply_eye_idle_override(detection)
        _apply_keyboard_break_override(detection)

    if not detections and motion_score > 0.025 and not request.single_person_mode:
        detections.append(
            Detection(
                category="worker",
                confidence=0.3,
                bbox=BoundingBox(x=0.4, y=0.3, w=0.2, h=0.35),
                zone=request.site_area,
                moving=True,
                track_id="W-MOTION",
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

    return frame, detector, round(motion_score, 3), request.single_person_mode
