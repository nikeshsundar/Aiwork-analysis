# Safety YOLO Model Setup

To enable true YOLO safety detection classes in live camera analysis, place these files here:

- `safety_yolov8.onnx`: YOLO ONNX model trained for worker safety classes
- `safety_classes.txt`: one class label per line (matching model output order)

Recommended labels include:

- `person`
- `helmet`
- `no_helmet`
- `cell phone`
- `restricted_zone_entry`
- `vehicle`

If model files are not present, the app falls back to HOG/contour worker detection and still runs.
