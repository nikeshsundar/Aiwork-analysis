from datetime import datetime, timezone

from app.schemas import BoundingBox, CameraFrame, Detection, MockVisionRequest


def _bbox_for_index(index: int, total: int) -> BoundingBox:
    # Distribute detections across frame for a stable demo layout.
    columns = max(1, min(4, total))
    row = index // columns
    col = index % columns

    x = 0.08 + (col * 0.22)
    y = 0.12 + (row * 0.22)

    return BoundingBox(x=min(x, 0.86), y=min(y, 0.86), w=0.1, h=0.12)


def mock_infer_frame(request: MockVisionRequest) -> CameraFrame:
    detections = []

    idle_workers = int(round(request.people_count * request.idle_ratio))
    for index in range(request.people_count):
        detections.append(
            Detection(
                category="worker",
                confidence=0.9,
                bbox=_bbox_for_index(index, request.people_count),
                zone=request.site_area,
                moving=index >= idle_workers,
            )
        )

    # Legacy field kept for compatibility; map it to generic interruption detections.
    for index in range(request.no_helmet_count):
        detections.append(
            Detection(
                category="phone_use",
                confidence=0.92,
                bbox=_bbox_for_index(index, max(1, request.no_helmet_count)),
                zone=request.site_area,
                moving=False,
            )
        )

    for index in range(request.phone_use_count):
        detections.append(
            Detection(
                category="phone_use",
                confidence=0.86,
                bbox=_bbox_for_index(index, max(1, request.phone_use_count)),
                zone=request.site_area,
                moving=False,
            )
        )

    # Legacy field kept for compatibility; treat these as interruption events in office mode.
    for index in range(request.restricted_entry_count):
        detections.append(
            Detection(
                category="phone_use",
                confidence=0.88,
                bbox=_bbox_for_index(index, max(1, request.restricted_entry_count)),
                zone=request.site_area,
                moving=False,
            )
        )

    return CameraFrame(
        camera_id=request.camera_id,
        timestamp=datetime.now(timezone.utc),
        site_area=request.site_area,
        expected_workers=request.expected_workers,
        tasks_planned=request.tasks_planned,
        tasks_completed=request.tasks_completed,
        detections=detections,
    )
