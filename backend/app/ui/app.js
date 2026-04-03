const state = {
  seed: null,
  frames: [],
  analyses: [],
  maxFrameHistory: 300,
  maxAnalysisHistory: 300,
  summary: null,
  portfolio: null,
  cameraHealth: null,
  eventFeed: null,
  trends: null,
  trendChart: null,
  selectedTrendCameraId: null,
  cameraDevices: [],
  cameraStream: null,
  cameraTimer: null,
  previousFrameBase64: null,
  evidenceSnapshots: [],
  maxEvidenceSnapshots: 9,
  lastEvidenceAt: 0,
};

const statusText = document.getElementById("statusText");
const cameraTableBody = document.getElementById("cameraTableBody");
const insightsList = document.getElementById("insightsList");
const portfolioList = document.getElementById("portfolioList");
const healthTableBody = document.getElementById("healthTableBody");
const eventFeedList = document.getElementById("eventFeedList");
const trendCameraSelect = document.getElementById("trendCameraSelect");
const trendChartCanvas = document.getElementById("trendChartCanvas");

const framesProcessed = document.getElementById("framesProcessed");
const totalWorkers = document.getElementById("totalWorkers");
const avgUtilization = document.getElementById("avgUtilization");
const avgProgress = document.getElementById("avgProgress");
const safetyViolations = document.getElementById("safetyViolations");
const activeWorkers = document.getElementById("activeWorkers");

const loadSeedBtn = document.getElementById("loadSeedBtn");
const runMockBtn = document.getElementById("runMockBtn");
const analyzeBtn = document.getElementById("analyzeBtn");
const advancedAnalyticsBtn = document.getElementById("advancedAnalyticsBtn");
const reportBtn = document.getElementById("reportBtn");
const startCameraBtn = document.getElementById("startCameraBtn");
const stopCameraBtn = document.getElementById("stopCameraBtn");

const cameraVideo = document.getElementById("cameraVideo");
const trackingOverlay = document.getElementById("trackingOverlay");
const captureCanvas = document.getElementById("captureCanvas");
const cameraIdInput = document.getElementById("cameraIdInput");
const siteAreaInput = document.getElementById("siteAreaInput");
const expectedWorkersInput = document.getElementById("expectedWorkersInput");
const tasksPlannedInput = document.getElementById("tasksPlannedInput");
const tasksCompletedInput = document.getElementById("tasksCompletedInput");
const captureIntervalInput = document.getElementById("captureIntervalInput");
const cameraDeviceSelect = document.getElementById("cameraDeviceSelect");
const singlePersonModeInput = document.getElementById("singlePersonModeInput");
const refreshDevicesBtn = document.getElementById("refreshDevicesBtn");
const resetLiveBtn = document.getElementById("resetLiveBtn");
const uploadFrameInput = document.getElementById("uploadFrameInput");
const analyzeUploadBtn = document.getElementById("analyzeUploadBtn");
const cameraDebugText = document.getElementById("cameraDebugText");
const evidenceStrip = document.getElementById("evidenceStrip");
const motionStatePill = document.getElementById("motionStatePill");
const motionScoreLabel = document.getElementById("motionScoreLabel");
const trackedWorkersLabel = document.getElementById("trackedWorkersLabel");
const eyeIdleLabel = document.getElementById("eyeIdleLabel");
const handBreakLabel = document.getElementById("handBreakLabel");
const dataModeLabel = document.getElementById("dataModeLabel");
const dataSourceLabel = document.getElementById("dataSourceLabel");
const mockFlagLabel = document.getElementById("mockFlagLabel");
const activityIndexLabel = document.getElementById("activityIndexLabel");
const evidenceScoreLabel = document.getElementById("evidenceScoreLabel");
const calibrationLabel = document.getElementById("calibrationLabel");

function setStatus(text, tone = "ok") {
  statusText.textContent = text;
  statusText.dataset.tone = tone === "warn" ? "warn" : "ok";
}

function lockButtons(locked) {
  loadSeedBtn.disabled = locked;
  runMockBtn.disabled = locked;
  analyzeBtn.disabled = locked;
  advancedAnalyticsBtn.disabled = locked;
  reportBtn.disabled = locked;
}

function lockCameraButtons(running) {
  startCameraBtn.disabled = running;
  stopCameraBtn.disabled = !running;
  refreshDevicesBtn.disabled = running;
}

function setCameraDebug(text) {
  cameraDebugText.textContent = text;
}

function setMotionPillState(isActive) {
  if (!motionStatePill) {
    return;
  }

  motionStatePill.classList.remove("is-active", "is-idle");
  motionStatePill.classList.add(isActive ? "is-active" : "is-idle");
}

function updateLiveMovement(analysis, motionScore) {
  if (!motionStatePill || !motionScoreLabel || !trackedWorkersLabel) {
    return;
  }

  if (!analysis) {
    motionStatePill.textContent = "Motion: idle";
    motionScoreLabel.textContent = "Motion score: 0.0%";
    trackedWorkersLabel.textContent = "Tracked workers: 0/0 moving";
    setMotionPillState(false);
    return;
  }

  const normalizedMotion = Number.isFinite(motionScore) ? Math.max(0, Math.min(1, motionScore)) : 0;
  const motionPct = (normalizedMotion * 100).toFixed(1);
  const movingWorkers = Number(analysis.active_workers || 0);
  const totalWorkers = Number(analysis.worker_count || 0);
  const hasMovement = movingWorkers > 0 || normalizedMotion >= 0.02;

  motionStatePill.textContent = hasMovement ? "Motion: active" : "Motion: idle";
  motionScoreLabel.textContent = `Motion score: ${motionPct}%`;
  trackedWorkersLabel.textContent = `Tracked workers: ${movingWorkers}/${totalWorkers} moving`;
  setMotionPillState(hasMovement);
}

function updateEyeIdleBadge(result) {
  if (!eyeIdleLabel) {
    return;
  }

  const eyeIdleWorkers = result && Number.isFinite(result.eye_idle_workers)
    ? Number(result.eye_idle_workers)
    : 0;

  eyeIdleLabel.textContent = `Eye idle workers: ${eyeIdleWorkers}`;
  setPillTone(eyeIdleLabel, eyeIdleWorkers > 0 ? "is-warn" : "is-idle");
}

function updateHandBreakBadge(result) {
  if (!handBreakLabel) {
    return;
  }

  const breakWorkers = result && Number.isFinite(result.hand_break_workers)
    ? Number(result.hand_break_workers)
    : 0;

  handBreakLabel.textContent = `Keyboard break workers: ${breakWorkers}`;
  setPillTone(handBreakLabel, breakWorkers > 0 ? "is-warn" : "is-idle");
}

function setPillTone(pill, tone) {
  if (!pill) {
    return;
  }

  pill.classList.remove("is-active", "is-idle", "is-warn");
  pill.classList.add(tone);
}

function updateEvidenceBadges(result) {
  if (
    !dataModeLabel
    || !dataSourceLabel
    || !mockFlagLabel
    || !activityIndexLabel
    || !evidenceScoreLabel
    || !calibrationLabel
  ) {
    return;
  }

  if (!result) {
    dataModeLabel.textContent = "Data mode: live-calibrated";
    dataSourceLabel.textContent = "Source: live-camera";
    mockFlagLabel.textContent = "Mock: no";
    activityIndexLabel.textContent = "Activity index: 0.0%";
    evidenceScoreLabel.textContent = "Evidence score: 0.0%";
    calibrationLabel.textContent = "Calibration: warming up";
    setPillTone(dataModeLabel, "is-idle");
    setPillTone(dataSourceLabel, "is-active");
    setPillTone(mockFlagLabel, "is-active");
    setPillTone(activityIndexLabel, "is-idle");
    setPillTone(evidenceScoreLabel, "is-idle");
    setPillTone(calibrationLabel, "is-idle");
    return;
  }

  const mode = String(result.data_mode || "live-calibrated");
  const source = String(result.data_source || "live-camera");
  const isMock = Boolean(result.is_mock);
  const activityIndex = Number.isFinite(result.activity_index_pct) ? result.activity_index_pct : 0;
  const evidence = Number.isFinite(result.evidence_score) ? result.evidence_score : 0;
  const calibrationReady = Boolean(result.calibration_ready);
  const remainingFrames = Number(result.calibration_frames_remaining || 0);

  dataModeLabel.textContent = `Data mode: ${mode}`;
  dataSourceLabel.textContent = `Source: ${source}`;
  mockFlagLabel.textContent = `Mock: ${isMock ? "yes" : "no"}`;
  activityIndexLabel.textContent = `Activity index: ${activityIndex.toFixed(1)}%`;
  evidenceScoreLabel.textContent = `Evidence score: ${evidence.toFixed(1)}%`;
  calibrationLabel.textContent = calibrationReady
    ? "Calibration: ready"
    : `Calibration: ${remainingFrames} frame(s) left`;

  setPillTone(dataModeLabel, mode === "manual-assisted" ? "is-warn" : "is-active");
  setPillTone(dataSourceLabel, source === "live-camera" ? "is-active" : "is-warn");
  setPillTone(mockFlagLabel, isMock ? "is-warn" : "is-active");
  setPillTone(activityIndexLabel, activityIndex >= 35 ? "is-active" : "is-idle");
  setPillTone(evidenceScoreLabel, evidence >= 65 ? "is-active" : evidence >= 45 ? "is-idle" : "is-warn");
  setPillTone(calibrationLabel, calibrationReady ? "is-active" : "is-idle");
}

function renderEvidenceStrip() {
  if (!evidenceStrip) {
    return;
  }

  if (!state.evidenceSnapshots.length) {
    evidenceStrip.innerHTML = '<div class="placeholder">No evidence yet. Start camera to collect snapshots.</div>';
    return;
  }

  evidenceStrip.innerHTML = state.evidenceSnapshots
    .map((item) => `<article class="evidence-card">
      <img src="${item.image}" alt="Evidence snapshot" />
      <div class="evidence-meta">
        <strong>${item.cameraId}</strong>
        <span>${item.timeLabel}</span>
        <span>Source: ${item.source} | Mock: ${item.mock}</span>
        <span>Evidence: ${item.evidence}% | Activity: ${item.activity}%</span>
        <span>Detector: ${item.detector}</span>
      </div>
    </article>`)
    .join("");
}

function maybeCaptureEvidenceSnapshot(result, frameImageDataUrl) {
  if (!result || !frameImageDataUrl) {
    return;
  }

  const workerCount = Number(result.analysis?.worker_count || 0);
  const evidence = Number.isFinite(result.evidence_score) ? result.evidence_score : 0;
  const now = Date.now();
  if (workerCount <= 0 || evidence < 40) {
    return;
  }
  if ((now - state.lastEvidenceAt) < 2200) {
    return;
  }

  state.lastEvidenceAt = now;
  state.evidenceSnapshots.unshift({
    image: frameImageDataUrl,
    cameraId: result.frame?.camera_id || "CAM-LIVE",
    timeLabel: new Date(result.frame?.timestamp || now).toLocaleTimeString(),
    source: String(result.data_source || "live-camera"),
    mock: result.is_mock ? "yes" : "no",
    evidence: evidence.toFixed(1),
    activity: (Number(result.activity_index_pct || 0)).toFixed(1),
    detector: String(result.detector || "unknown"),
  });

  if (state.evidenceSnapshots.length > state.maxEvidenceSnapshots) {
    state.evidenceSnapshots.splice(state.maxEvidenceSnapshots);
  }

  renderEvidenceStrip();
}

function syncTrackingOverlaySize() {
  if (!trackingOverlay) {
    return;
  }

  const rect = cameraVideo.getBoundingClientRect();
  if (!rect.width || !rect.height) {
    return;
  }

  const dpr = window.devicePixelRatio || 1;
  const targetWidth = Math.max(1, Math.round(rect.width * dpr));
  const targetHeight = Math.max(1, Math.round(rect.height * dpr));

  if (trackingOverlay.width !== targetWidth || trackingOverlay.height !== targetHeight) {
    trackingOverlay.width = targetWidth;
    trackingOverlay.height = targetHeight;
  }
}

function clearTrackingOverlay() {
  if (!trackingOverlay) {
    return;
  }

  const context = trackingOverlay.getContext("2d");
  context.clearRect(0, 0, trackingOverlay.width, trackingOverlay.height);
}

function detectionColor(detection) {
  if (detection.category === "worker") {
    return detection.moving ? "#21b594" : "#c68625";
  }
  if (detection.category === "no_helmet") {
    return "#d04d26";
  }
  if (detection.category === "phone_use") {
    return "#8d4bc9";
  }
  if (detection.category === "restricted_zone_entry") {
    return "#b43863";
  }
  if (detection.category === "helmet") {
    return "#2e73c3";
  }
  if (detection.category === "vehicle") {
    return "#475661";
  }

  return "#2e73c3";
}

function drawTrackingOverlay(frame) {
  if (!trackingOverlay || !frame || !Array.isArray(frame.detections)) {
    clearTrackingOverlay();
    return;
  }

  syncTrackingOverlaySize();

  const context = trackingOverlay.getContext("2d");
  const overlayWidth = trackingOverlay.width;
  const overlayHeight = trackingOverlay.height;
  context.clearRect(0, 0, overlayWidth, overlayHeight);

  if (!overlayWidth || !overlayHeight) {
    return;
  }

  const sourceWidth = cameraVideo.videoWidth || overlayWidth;
  const sourceHeight = cameraVideo.videoHeight || overlayHeight;
  if (!sourceWidth || !sourceHeight) {
    return;
  }

  const scale = Math.min(overlayWidth / sourceWidth, overlayHeight / sourceHeight);
  const drawWidth = sourceWidth * scale;
  const drawHeight = sourceHeight * scale;
  const offsetX = (overlayWidth - drawWidth) / 2;
  const offsetY = (overlayHeight - drawHeight) / 2;
  const fontSize = Math.max(14, Math.round(12 * (window.devicePixelRatio || 1)));

  frame.detections.forEach((detection, index) => {
    const bbox = detection.bbox || {};
    const x = Number(bbox.x || 0);
    const y = Number(bbox.y || 0);
    const w = Number(bbox.w || 0);
    const h = Number(bbox.h || 0);
    if (w <= 0 || h <= 0) {
      return;
    }

    const left = offsetX + x * drawWidth;
    const top = offsetY + y * drawHeight;
    const boxWidth = w * drawWidth;
    const boxHeight = h * drawHeight;
    const color = detectionColor(detection);

    context.strokeStyle = color;
    context.lineWidth = Math.max(2, Math.round(2 * (window.devicePixelRatio || 1)));
    context.strokeRect(left, top, boxWidth, boxHeight);

    const workerToken = detection.track_id || `W-${index + 1}`;
    let tag = detection.category === "worker"
      ? `${detection.moving ? "moving" : "idle"} ${workerToken}`
      : detection.category.replaceAll("_", " ");

    if (detection.category === "worker") {
      if (detection.face_detected === true) {
        if (detection.eyes_closed === true) {
          const seconds = Number.isFinite(detection.eyes_closed_seconds)
            ? Number(detection.eyes_closed_seconds).toFixed(1)
            : "0.0";
          tag += ` eyes-closed ${seconds}s`;
        } else if (detection.eyes_closed === false) {
          tag += " eyes-open";
        }
      } else {
        tag += " face-unseen";
      }

      if (detection.hand_on_keyboard === true) {
        tag += " kb-on";
      } else if (detection.hand_on_keyboard === false) {
        const breakSeconds = Number.isFinite(detection.hand_off_keyboard_seconds)
          ? Number(detection.hand_off_keyboard_seconds).toFixed(1)
          : "0.0";
        tag += ` kb-off ${breakSeconds}s`;
      }
    }
    const confidence = Number.isFinite(detection.confidence)
      ? `${Math.round(detection.confidence * 100)}%`
      : "";
    const label = confidence ? `${tag} ${confidence}` : tag;

    context.font = `${fontSize}px "IBM Plex Mono", monospace`;
    const textWidth = context.measureText(label).width;
    const labelHeight = Math.max(18, Math.round(16 * (window.devicePixelRatio || 1)));
    const labelTop = Math.max(0, top - labelHeight - 2);

    context.fillStyle = color;
    context.fillRect(left, labelTop, textWidth + 10, labelHeight);
    context.fillStyle = "#ffffff";
    context.fillText(label, left + 5, labelTop + labelHeight - 6);
  });
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function isLocalHost() {
  return ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
}

function cameraErrorMessage(error) {
  if (!error || !error.name) {
    return "unknown camera error";
  }

  if (error.name === "NotAllowedError" || error.name === "SecurityError") {
    return "camera permission denied. Allow camera access in browser site permissions";
  }
  if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
    return "no camera device found. Connect a webcam and retry";
  }
  if (error.name === "NotReadableError" || error.name === "TrackStartError") {
    return "camera is in use by another app. Close other apps using camera and retry";
  }
  if (error.name === "OverconstrainedError" || error.name === "ConstraintNotSatisfiedError") {
    return "requested camera mode not supported on this device";
  }
  if (error.name === "AbortError") {
    return "camera initialization was interrupted. Retry start camera";
  }

  return `${error.name}: ${error.message || "camera access failed"}`;
}

async function requestCameraStream(selectedDeviceId) {
  const attempts = [];
  if (selectedDeviceId && selectedDeviceId !== "__auto__") {
    attempts.push({
      video: {
        deviceId: { exact: selectedDeviceId },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    });
  }

  attempts.push(
    {
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    },
    {
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    },
    { video: true, audio: false },
  );

  let lastError = null;
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints);
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error("camera unavailable");
}

async function refreshCameraDevices() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
    setCameraDebug("Device enumeration unsupported in this browser.");
    return;
  }

  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter((device) => device.kind === "videoinput");
    state.cameraDevices = videoDevices;

    const currentSelection = cameraDeviceSelect.value || "__auto__";
    const options = [
      '<option value="__auto__">Auto-select</option>',
      ...videoDevices.map((device, index) => {
        const label = device.label || `Camera ${index + 1}`;
        return `<option value="${escapeHtml(device.deviceId)}">${escapeHtml(label)}</option>`;
      }),
    ];
    cameraDeviceSelect.innerHTML = options.join("");

    const hasCurrent = videoDevices.some((device) => device.deviceId === currentSelection);
    cameraDeviceSelect.value = hasCurrent ? currentSelection : "__auto__";

    const secureLabel = window.isSecureContext || isLocalHost() ? "secure context ok" : "not secure";
    setCameraDebug(`Detected ${videoDevices.length} camera device(s); ${secureLabel}.`);
  } catch (error) {
    setCameraDebug(`Could not enumerate devices: ${cameraErrorMessage(error)}`);
  }
}

function summarizeAnalyses(analyses) {
  if (!analyses || analyses.length === 0) {
    return null;
  }

  const framesCount = analyses.length;
  const totalWorkerCount = analyses.reduce((acc, item) => acc + item.worker_count, 0);
  const totalActive = analyses.reduce((acc, item) => acc + item.active_workers, 0);
  const safety = analyses.reduce((acc, item) => acc + item.safety_violations, 0);
  const avgUtilizationPct = analyses.reduce((acc, item) => acc + item.utilization_pct, 0) / framesCount;
  const avgProgressPct = analyses.reduce((acc, item) => acc + item.progress_pct, 0) / framesCount;

  return {
    frames_processed: framesCount,
    total_workers: totalWorkerCount,
    total_active_workers: totalActive,
    avg_utilization_pct: avgUtilizationPct,
    avg_progress_pct: avgProgressPct,
    safety_violations: safety,
  };
}

function latestAnalysesByCamera(analyses) {
  if (!analyses || analyses.length === 0) {
    return [];
  }

  const latestMap = new Map();
  analyses.forEach((analysis) => {
    latestMap.set(analysis.camera_id, analysis);
  });

  return [...latestMap.values()].sort((a, b) => a.camera_id.localeCompare(b.camera_id));
}

function renderSummary(summary) {
  if (!summary) {
    framesProcessed.textContent = "-";
    totalWorkers.textContent = "-";
    avgUtilization.textContent = "-";
    avgProgress.textContent = "-";
    safetyViolations.textContent = "-";
    activeWorkers.textContent = "-";
    return;
  }

  framesProcessed.textContent = `${summary.frames_processed}`;
  totalWorkers.textContent = `${summary.total_workers}`;
  avgUtilization.textContent = `${summary.avg_utilization_pct.toFixed(1)}%`;
  avgProgress.textContent = `${summary.avg_progress_pct.toFixed(1)}%`;
  safetyViolations.textContent = `${summary.safety_violations}`;
  activeWorkers.textContent = `${summary.total_active_workers}`;
}

function renderAnalyses(analyses) {
  if (!analyses || analyses.length === 0) {
    cameraTableBody.innerHTML = '<tr><td colspan="6" class="placeholder">No analysis yet.</td></tr>';
    return;
  }

  const rows = latestAnalysesByCamera(analyses);

  cameraTableBody.innerHTML = rows
    .map((analysis) => {
      const alerts = analysis.alerts.length
        ? analysis.alerts.map((alert) => `<span class="alert-pill">${alert}</span>`).join("")
        : "None";

      return `<tr>
        <td>${analysis.camera_id}</td>
        <td>${analysis.worker_count} (active ${analysis.active_workers})</td>
        <td>${analysis.utilization_pct.toFixed(1)}%</td>
        <td>${analysis.progress_pct.toFixed(1)}%</td>
        <td>${analysis.safety_violations}</td>
        <td>${alerts}</td>
      </tr>`;
    })
    .join("");
}

function renderInsights(insights) {
  if (!insights || !insights.length) {
    insightsList.innerHTML = '<li class="placeholder">Generate a report to see insights.</li>';
    return;
  }

  insightsList.innerHTML = insights
    .map(
      (insight) => `<li class="insight-item">
        <span class="insight-title">${insight.title}</span>
        <span>${insight.detail}</span>
      </li>`,
    )
    .join("");
}

function renderPortfolio(portfolio) {
  if (!portfolio || !portfolio.cameras || !portfolio.cameras.length) {
    portfolioList.innerHTML = '<li class="placeholder">Run advanced analytics to view ranking.</li>';
    return;
  }

  portfolioList.innerHTML = portfolio.cameras
    .map((camera) => `<li class="portfolio-item">
      <div class="portfolio-topline">
        <strong>${camera.camera_id}</strong>
        <span class="score-pill">Score ${camera.performance_score.toFixed(1)}</span>
      </div>
      <div class="portfolio-topline">
        <span>${camera.site_area}</span>
        <span class="status-pill ${camera.status}">${camera.status}</span>
      </div>
      <div class="portfolio-topline">
        <span>Util ${camera.utilization_pct.toFixed(1)}% | Prog ${camera.progress_pct.toFixed(1)}%</span>
        <span class="trend-pill ${camera.trend}">${camera.trend}</span>
      </div>
    </li>`)
    .join("");
}

function renderCameraHealth(cameraHealth) {
  if (!cameraHealth || !cameraHealth.cameras || !cameraHealth.cameras.length) {
    healthTableBody.innerHTML = '<tr><td colspan="5" class="placeholder">Run advanced analytics to view health.</td></tr>';
    return;
  }

  healthTableBody.innerHTML = cameraHealth.cameras
    .map((camera) => `<tr>
      <td>${camera.camera_id}</td>
      <td><span class="health-status ${camera.status}">${camera.status}</span></td>
      <td>${camera.last_seen_seconds}s</td>
      <td>${camera.detection_density.toFixed(2)}</td>
      <td>${camera.reliability_score.toFixed(1)}%</td>
    </tr>`)
    .join("");
}

function renderEventFeed(eventFeed) {
  if (!eventFeed || !eventFeed.events || !eventFeed.events.length) {
    eventFeedList.innerHTML = '<li class="placeholder">Run advanced analytics to load event feed.</li>';
    return;
  }

  eventFeedList.innerHTML = eventFeed.events
    .slice(0, 12)
    .map((event) => {
      const timestamp = new Date(event.timestamp).toLocaleTimeString();
      return `<li class="event-item">
        <div class="event-head">
          <strong>${event.camera_id}</strong>
          <span class="severity-pill ${event.severity}">${event.severity}</span>
        </div>
        <div>${event.message}</div>
        <span class="event-time">${event.event_type} | ${timestamp}</span>
        <span class="event-action">Action: ${event.action}</span>
      </li>`;
    })
    .join("");
}

function destroyTrendChart() {
  if (state.trendChart) {
    state.trendChart.destroy();
    state.trendChart = null;
  }
}

function renderTrendTimeline(trends) {
  if (!trends || !trends.cameras || !trends.cameras.length) {
    trendCameraSelect.innerHTML = "";
    destroyTrendChart();
    return;
  }

  trendCameraSelect.innerHTML = trends.cameras
    .map((camera) => `<option value="${camera.camera_id}">${camera.camera_id} (${camera.site_area})</option>`)
    .join("");

  const validSelection = trends.cameras.some((camera) => camera.camera_id === state.selectedTrendCameraId);
  if (!validSelection) {
    state.selectedTrendCameraId = trends.cameras[0].camera_id;
  }

  trendCameraSelect.value = state.selectedTrendCameraId;
  renderTrendTimelineForCamera(state.selectedTrendCameraId);
}

function renderTrendTimelineForCamera(cameraId) {
  if (!state.trends || !state.trends.cameras || !state.trends.cameras.length) {
    destroyTrendChart();
    return;
  }

  const cameraTrend = state.trends.cameras.find((camera) => camera.camera_id === cameraId);
  if (!cameraTrend || !cameraTrend.points.length || typeof Chart === "undefined") {
    destroyTrendChart();
    return;
  }

  const labels = cameraTrend.points.map((point) => new Date(point.timestamp).toLocaleTimeString());
  const utilization = cameraTrend.points.map((point) => point.utilization_pct);
  const progress = cameraTrend.points.map((point) => point.progress_pct);
  const safety = cameraTrend.points.map((point) => point.safety_violations);

  destroyTrendChart();
  const context = trendChartCanvas.getContext("2d");

  state.trendChart = new Chart(context, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Utilization %",
          data: utilization,
          borderColor: "#0f8f7e",
          backgroundColor: "rgba(15, 143, 126, 0.15)",
          tension: 0.3,
        },
        {
          label: "Progress %",
          data: progress,
          borderColor: "#3d6fb3",
          backgroundColor: "rgba(61, 111, 179, 0.15)",
          tension: 0.3,
        },
        {
          label: "Safety Violations",
          data: safety,
          borderColor: "#c85127",
          backgroundColor: "rgba(200, 81, 39, 0.15)",
          tension: 0.3,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          title: { display: true, text: "%" },
        },
        y1: {
          beginAtZero: true,
          position: "right",
          grid: { drawOnChartArea: false },
          title: { display: true, text: "Safety" },
        },
      },
      plugins: {
        legend: { position: "top" },
      },
    },
  });
}

function captureFrameBase64() {
  const width = cameraVideo.videoWidth || 640;
  const height = cameraVideo.videoHeight || 360;

  captureCanvas.width = width;
  captureCanvas.height = height;

  const context = captureCanvas.getContext("2d");
  context.drawImage(cameraVideo, 0, 0, width, height);

  return captureCanvas.toDataURL("image/jpeg", 0.72);
}

function upsertFrameAndAnalysis(frame, analysis) {
  state.frames.push(frame);
  if (state.frames.length > state.maxFrameHistory) {
    state.frames.splice(0, state.frames.length - state.maxFrameHistory);
  }

  state.analyses.push(analysis);
  if (state.analyses.length > state.maxAnalysisHistory) {
    state.analyses.splice(0, state.analyses.length - state.maxAnalysisHistory);
  }

  const summaryWindow = state.analyses.slice(-90);
  state.summary = summarizeAnalyses(summaryWindow);
}

async function analyzeSingleCameraFrame() {
  if (!state.cameraStream) {
    return;
  }

  try {
    const imageBase64 = captureFrameBase64();
    const payload = {
      camera_id: cameraIdInput.value.trim() || "CAM-LIVE-01",
      image_base64: imageBase64,
      previous_image_base64: state.previousFrameBase64,
      site_area: siteAreaInput.value.trim() || "live-zone",
      expected_workers: Number(expectedWorkersInput.value || 0),
      tasks_planned: Number(tasksPlannedInput.value || 0),
      tasks_completed: Number(tasksCompletedInput.value || 0),
      single_person_mode: Boolean(singlePersonModeInput && singlePersonModeInput.checked),
    };

    const response = await fetch("/vision/analyze-camera-frame", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`camera analysis failed (${response.status})`);
    }

    const result = await response.json();
    state.previousFrameBase64 = imageBase64;

    upsertFrameAndAnalysis(result.frame, result.analysis);
    drawTrackingOverlay(result.frame);
    updateLiveMovement(result.analysis, result.motion_score);
    updateEvidenceBadges(result);
    updateEyeIdleBadge(result);
    updateHandBreakBadge(result);
    maybeCaptureEvidenceSnapshot(result, imageBase64);
    renderAnalyses(state.analyses);
    renderSummary(state.summary);

    const tone = result.analysis.safety_violations > 0 ? "warn" : "ok";
    const classesLabel = result.classes_detected && result.classes_detected.length
      ? result.classes_detected.join(",")
      : "none";
    const calibrationLabel = result.calibration_ready
      ? "ready"
      : `${result.calibration_frames_remaining}f`;
    setStatus(
      `Live ${result.frame.camera_id}: source ${result.data_source}, mock ${result.is_mock ? "yes" : "no"}, single-mode ${result.single_person_mode_applied ? "on" : "off"}, eye-idle ${result.eye_idle_workers}, hand-break ${result.hand_break_workers}, ${result.analysis.worker_count} workers, util ${result.analysis.utilization_pct.toFixed(1)}%, task progress ${result.analysis.progress_pct.toFixed(1)}%, activity ${result.activity_index_pct.toFixed(1)}%, mode ${result.data_mode}, evidence ${result.evidence_score.toFixed(1)}%, calibration ${calibrationLabel}, detector ${result.detector}, safety ${result.safety_detections}, classes ${classesLabel}, motion ${(result.motion_score * 100).toFixed(1)}%.`,
      tone,
    );
  } catch (error) {
    setStatus(`Live camera analysis error: ${error.message}`, "warn");
  }
}

async function analyzeUploadedFrame() {
  if (!uploadFrameInput.files || uploadFrameInput.files.length === 0) {
    setStatus("Select an image file first.", "warn");
    return;
  }

  const file = uploadFrameInput.files[0];
  const reader = new FileReader();

  const dataUrl = await new Promise((resolve, reject) => {
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("file read failed"));
    reader.readAsDataURL(file);
  });

  try {
    const payload = {
      camera_id: cameraIdInput.value.trim() || "CAM-UPLOAD-01",
      image_base64: String(dataUrl),
      site_area: siteAreaInput.value.trim() || "upload-zone",
      expected_workers: Number(expectedWorkersInput.value || 0),
      tasks_planned: Number(tasksPlannedInput.value || 0),
      tasks_completed: Number(tasksCompletedInput.value || 0),
      single_person_mode: Boolean(singlePersonModeInput && singlePersonModeInput.checked),
    };

    const response = await fetch("/vision/analyze-camera-frame", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`upload analysis failed (${response.status})`);
    }

    const result = await response.json();
    upsertFrameAndAnalysis(result.frame, result.analysis);
    drawTrackingOverlay(result.frame);
    updateLiveMovement(result.analysis, result.motion_score);
    updateEvidenceBadges(result);
    updateEyeIdleBadge(result);
    updateHandBreakBadge(result);
    maybeCaptureEvidenceSnapshot(result, String(dataUrl));
    renderAnalyses(state.analyses);
    renderSummary(state.summary);

    const classesLabel = result.classes_detected && result.classes_detected.length
      ? result.classes_detected.join(",")
      : "none";
    setStatus(
      `Uploaded frame analyzed: source ${result.data_source}, mock ${result.is_mock ? "yes" : "no"}, single-mode ${result.single_person_mode_applied ? "on" : "off"}, eye-idle ${result.eye_idle_workers}, hand-break ${result.hand_break_workers}, ${result.analysis.worker_count} workers, activity ${result.activity_index_pct.toFixed(1)}%, mode ${result.data_mode}, evidence ${result.evidence_score.toFixed(1)}%, detector ${result.detector}, classes ${classesLabel}.`,
      result.analysis.safety_violations > 0 ? "warn" : "ok",
    );
  } catch (error) {
    setStatus(`Uploaded frame analysis failed: ${error.message}`, "warn");
  }
}

async function resetLiveBaseline(silent = false) {
  const cameraId = cameraIdInput.value.trim() || "CAM-LIVE-01";

  try {
    const response = await fetch("/vision/reset-live-session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ camera_id: cameraId }),
    });

    if (!response.ok) {
      throw new Error(`reset failed (${response.status})`);
    }

    state.previousFrameBase64 = null;
    state.evidenceSnapshots = [];
    state.lastEvidenceAt = 0;
    updateEvidenceBadges(null);
    updateEyeIdleBadge(null);
    updateHandBreakBadge(null);
    renderEvidenceStrip();

    if (!silent) {
      setStatus(`Live baseline reset for ${cameraId}.`, "ok");
    }
  } catch (error) {
    if (!silent) {
      setStatus(`Could not reset live baseline: ${error.message}`, "warn");
    }
  }
}

async function startCameraAnalysis() {
  if (state.cameraStream) {
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("Camera API is not available in this browser. Use Chrome/Edge desktop browser.", "warn");
    return;
  }

  if (!window.isSecureContext && !isLocalHost()) {
    setStatus("Camera access requires HTTPS or localhost. Open the app on localhost/HTTPS.", "warn");
    return;
  }

  try {
    setStatus("Requesting camera permission...");
    await resetLiveBaseline(true);
    const selectedDeviceId = cameraDeviceSelect.value;
    const stream = await requestCameraStream(selectedDeviceId);

    state.cameraStream = stream;
    state.previousFrameBase64 = null;
    cameraVideo.srcObject = stream;
    await cameraVideo.play();
    syncTrackingOverlaySize();

    const videoTrack = stream.getVideoTracks()[0];
    if (videoTrack) {
      const settings = videoTrack.getSettings();
      const label = videoTrack.label || settings.deviceId || "unknown";
      const size = settings.width && settings.height ? `${settings.width}x${settings.height}` : "auto";
      setCameraDebug(`Using ${label} (${size}).`);
    }

    await refreshCameraDevices();

    lockCameraButtons(true);
    setStatus("Camera started. Capturing live frames for analysis...");

    await analyzeSingleCameraFrame();

    const intervalSec = Math.max(1, Math.min(10, Number(captureIntervalInput.value || 3)));
    state.cameraTimer = setInterval(analyzeSingleCameraFrame, intervalSec * 1000);
  } catch (error) {
    setStatus(`Could not start camera: ${cameraErrorMessage(error)}`, "warn");
    setCameraDebug(`Start failed: ${cameraErrorMessage(error)}`);
    lockCameraButtons(false);
  }
}

function stopCameraAnalysis() {
  if (state.cameraTimer) {
    clearInterval(state.cameraTimer);
    state.cameraTimer = null;
  }

  if (state.cameraStream) {
    state.cameraStream.getTracks().forEach((track) => track.stop());
    state.cameraStream = null;
  }

  cameraVideo.srcObject = null;
  state.previousFrameBase64 = null;
  clearTrackingOverlay();
  updateLiveMovement(null, 0);
  updateEyeIdleBadge(null);
  updateHandBreakBadge(null);
  lockCameraButtons(false);
  setStatus("Camera stopped.");
  setCameraDebug("Camera stopped. You can refresh devices and retry.");
}

async function loadSeedFrames() {
  setStatus("Loading seed camera frames...");
  lockButtons(true);

  try {
    const response = await fetch("/demo/seed");
    if (!response.ok) {
      throw new Error(`seed load failed (${response.status})`);
    }

    state.seed = await response.json();
    state.frames = [...state.seed.frames];
    state.analyses = [];
    state.summary = null;
    state.portfolio = null;
    state.cameraHealth = null;
    state.eventFeed = null;
    state.trends = null;
    state.selectedTrendCameraId = null;
    state.evidenceSnapshots = [];
    state.lastEvidenceAt = 0;

    renderAnalyses([]);
    renderSummary(null);
    renderInsights([]);
    renderPortfolio(null);
    renderCameraHealth(null);
    renderEventFeed(null);
    renderTrendTimeline(null);
    updateEvidenceBadges(null);
    updateEyeIdleBadge(null);
    updateHandBreakBadge(null);
    renderEvidenceStrip();

    setStatus(`Loaded ${state.frames.length} seed frames. Ready for analysis.`);
  } catch (error) {
    setStatus(`Could not load seed: ${error.message}`, "warn");
  } finally {
    lockButtons(false);
  }
}

async function runMockInference() {
  if (!state.seed || !state.seed.mock_requests) {
    setStatus("Load seed frames first.", "warn");
    return;
  }

  setStatus("Running mock computer-vision inference...");
  lockButtons(true);

  try {
    const calls = state.seed.mock_requests.map(async (request) => {
      const response = await fetch("/vision/mock-infer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`mock infer failed (${response.status})`);
      }

      return response.json();
    });

    const results = await Promise.all(calls);
    state.frames = [...state.frames, ...results.map((result) => result.frame)];
    setStatus(`Mock inference generated ${results.length} additional frames.`);
  } catch (error) {
    setStatus(`Mock inference failed: ${error.message}`, "warn");
  } finally {
    lockButtons(false);
  }
}

async function analyzeProgress() {
  if (!state.frames.length) {
    setStatus("No frames available. Load seed first.", "warn");
    return;
  }

  setStatus("Analyzing worker progress and safety...");
  lockButtons(true);

  try {
    const response = await fetch("/analysis/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frames: state.frames }),
    });

    if (!response.ok) {
      throw new Error(`analysis failed (${response.status})`);
    }

    const result = await response.json();
    state.analyses = result.analyses;
    state.summary = result.summary;

    renderAnalyses(state.analyses);
    renderSummary(state.summary);
    setStatus(
      `Analysis complete. Avg utilization ${state.summary.avg_utilization_pct.toFixed(1)}%, safety events ${state.summary.safety_violations}.`,
      state.summary.safety_violations > 0 ? "warn" : "ok",
    );
  } catch (error) {
    setStatus(`Analysis failed: ${error.message}`, "warn");
  } finally {
    lockButtons(false);
  }
}

async function generateReport() {
  if (!state.frames.length) {
    setStatus("No frames available. Load seed first.", "warn");
    return;
  }

  setStatus("Generating shift report with action insights...");
  lockButtons(true);

  try {
    const response = await fetch("/analysis/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frames: state.frames }),
    });

    if (!response.ok) {
      throw new Error(`report failed (${response.status})`);
    }

    const report = await response.json();
    state.summary = report.summary;

    renderSummary(state.summary);
    renderInsights(report.insights);
    setStatus("Shift report generated successfully.");
  } catch (error) {
    setStatus(`Report generation failed: ${error.message}`, "warn");
  } finally {
    lockButtons(false);
  }
}

async function runAdvancedAnalytics() {
  if (!state.frames.length) {
    setStatus("No frames available. Load seed or start camera first.", "warn");
    return;
  }

  setStatus("Running portfolio analytics, camera health, events, and trends...");
  lockButtons(true);

  try {
    const payload = JSON.stringify({ frames: state.frames });
    const [portfolioRes, healthRes, eventsRes, trendsRes] = await Promise.all([
      fetch("/analytics/portfolio", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      }),
      fetch("/analytics/camera-health", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      }),
      fetch("/analytics/event-feed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      }),
      fetch("/analytics/trends", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      }),
    ]);

    if (!portfolioRes.ok || !healthRes.ok || !eventsRes.ok || !trendsRes.ok) {
      throw new Error("one or more advanced analytics requests failed");
    }

    state.portfolio = await portfolioRes.json();
    state.cameraHealth = await healthRes.json();
    state.eventFeed = await eventsRes.json();
    state.trends = await trendsRes.json();

    renderPortfolio(state.portfolio);
    renderCameraHealth(state.cameraHealth);
    renderEventFeed(state.eventFeed);
    renderTrendTimeline(state.trends);

    const trendSummary = state.trends.cameras
      .map((camera) => `${camera.camera_id}:${camera.direction}`)
      .join(", ");
    setStatus(
      `Advanced analytics ready. Fleet score ${state.portfolio.fleet_score.toFixed(1)}. Trends ${trendSummary}.`,
      "ok",
    );
  } catch (error) {
    setStatus(`Advanced analytics failed: ${error.message}`, "warn");
  } finally {
    lockButtons(false);
  }
}

loadSeedBtn.addEventListener("click", loadSeedFrames);
runMockBtn.addEventListener("click", runMockInference);
analyzeBtn.addEventListener("click", analyzeProgress);
advancedAnalyticsBtn.addEventListener("click", runAdvancedAnalytics);
reportBtn.addEventListener("click", generateReport);
startCameraBtn.addEventListener("click", startCameraAnalysis);
stopCameraBtn.addEventListener("click", stopCameraAnalysis);
refreshDevicesBtn.addEventListener("click", refreshCameraDevices);
resetLiveBtn.addEventListener("click", () => {
  void resetLiveBaseline(false);
});
analyzeUploadBtn.addEventListener("click", analyzeUploadedFrame);
trendCameraSelect.addEventListener("change", () => {
  state.selectedTrendCameraId = trendCameraSelect.value;
  renderTrendTimelineForCamera(state.selectedTrendCameraId);
});

window.addEventListener("beforeunload", stopCameraAnalysis);
window.addEventListener("resize", syncTrackingOverlaySize);
cameraVideo.addEventListener("loadedmetadata", syncTrackingOverlaySize);

setStatus("Ready. Start camera to run live evidence mode.");
updateLiveMovement(null, 0);
updateEvidenceBadges(null);
updateEyeIdleBadge(null);
updateHandBreakBadge(null);
renderEvidenceStrip();
refreshCameraDevices();
