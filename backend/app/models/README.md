# Safety YOLO Model Setup

To enable true YOLO safety detection classes in live camera analysis, place these files here:

- `safety_yolov8.onnx`: YOLO ONNX model trained for worker safety classes
- `safety_classes.txt`: one class label per line (matching model output order)

Optional worker-localization model (recommended):

- `person_yolov8.onnx`: YOLO ONNX model with person class
- `person_classes.txt`: class labels for person model (COCO-compatible labels supported)

Recommended labels include:

- `person`
- `helmet`
- `no_helmet`
- `cell phone`
- `restricted_zone_entry`
- `vehicle`

If model files are not present, the app falls back to HOG/face-body/contour worker detection and still runs.
