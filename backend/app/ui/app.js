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
  flowRecovery: null,
  bottleneckGraph: null,
  privacyProof: null,
  managerReport: null,
  managerChatHistory: [],
  managerReportTimer: null,
  managerApiFallbackNotified: false,
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

const IS_RENDER_HOST = window.location.hostname.includes("onrender.com");

const statusText = document.getElementById("statusText");
const cameraTableBody = document.getElementById("cameraTableBody");
const insightsList = document.getElementById("insightsList");
const portfolioList = document.getElementById("portfolioList");
const healthTableBody = document.getElementById("healthTableBody");
const eventFeedList = document.getElementById("eventFeedList");
const trendCameraSelect = document.getElementById("trendCameraSelect");
const trendChartCanvas = document.getElementById("trendChartCanvas");
const flowRecoveryBox = document.getElementById("flowRecoveryBox");
const bottleneckGraphBox = document.getElementById("bottleneckGraphBox");
const privacyProofBox = document.getElementById("privacyProofBox");
const managerReportBox = document.getElementById("managerReportBox");
const managerChatLog = document.getElementById("managerChatLog");
const privacyChallengeReason = document.getElementById("privacyChallengeReason");
const submitPrivacyChallengeBtn = document.getElementById("submitPrivacyChallengeBtn");
const managerCameraIdInput = document.getElementById("managerCameraIdInput");
const managerQuestionInput = document.getElementById("managerQuestionInput");
const askManagerBtn = document.getElementById("askManagerBtn");
const managerQuickAskButtons = Array.from(document.querySelectorAll(".quick-ask-btn"));

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
const managerReportBtn = document.getElementById("managerReportBtn");
const reportBtn = document.getElementById("reportBtn");
const startCameraBtn = document.getElementById("startCameraBtn");
const stopCameraBtn = document.getElementById("stopCameraBtn");

const cameraVideo = document.getElementById("cameraVideo");
const trackingOverlay = document.getElementById("trackingOverlay");
const faceTrackingCanvas = document.getElementById("faceTrackingCanvas");
const faceTrackingStatus = document.getElementById("faceTrackingStatus");
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

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithRetry(url, options, retries = 2) {
  let attempt = 0;
  let lastError = null;

  while (attempt <= retries) {
    try {
      const response = await fetch(url, options);
      if (response.ok) {
        return response;
      }

      const retryable = response.status === 502 || response.status === 503 || response.status === 504;
      if (!retryable || attempt >= retries) {
        return response;
      }
    } catch (error) {
      lastError = error;
      if (attempt >= retries) {
        throw error;
      }
    }

    attempt += 1;
    await delay(700 * attempt);
  }

  if (lastError) {
    throw lastError;
  }

  throw new Error("request failed after retries");
}

function lockButtons(locked) {
  loadSeedBtn.disabled = locked;
  runMockBtn.disabled = locked;
  analyzeBtn.disabled = locked;
  advancedAnalyticsBtn.disabled = locked;
  managerReportBtn.disabled = locked;
  reportBtn.disabled = locked;
}

function ensureManagerInputReady() {
  if (managerCameraIdInput) {
    managerCameraIdInput.disabled = false;
    managerCameraIdInput.readOnly = false;
  }
  if (managerQuestionInput) {
    managerQuestionInput.disabled = false;
    managerQuestionInput.readOnly = false;
    managerQuestionInput.setAttribute("tabindex", "0");
    managerQuestionInput.removeAttribute("readonly");
    managerQuestionInput.removeAttribute("disabled");
    managerQuestionInput.style.pointerEvents = "auto";
    managerQuestionInput.style.userSelect = "text";
    managerQuestionInput.style.caretColor = "auto";
  }
  if (askManagerBtn) {
    askManagerBtn.disabled = false;
  }
}

async function postManagerApi(path, payload) {
  const origins = [window.location.origin];
  const fallbackOrigin = "http://127.0.0.1:8010";
  if (!origins.includes(fallbackOrigin)) {
    origins.push(fallbackOrigin);
  }

  let lastResponse = null;
  let lastError = null;

  for (let index = 0; index < origins.length; index += 1) {
    const origin = origins[index];
    try {
      const response = await fetch(`${origin}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        if (origin !== window.location.origin && !state.managerApiFallbackNotified) {
          state.managerApiFallbackNotified = true;
          setStatus("Manager API auto-switched to port 8010 fallback.", "ok");
        }
        return response;
      }

      lastResponse = response;
      const canRetryFallback = index < origins.length - 1 && (response.status === 404 || response.status === 405);
      if (canRetryFallback) {
        continue;
      }
      return response;
    } catch (error) {
      lastError = error;
      if (index === origins.length - 1) {
        throw error;
      }
    }
  }

  if (lastResponse) {
    return lastResponse;
  }

  throw lastError || new Error("manager API is unreachable");
}

function bindManagerQuickAsks() {
  if (!managerQuickAskButtons.length) {
    return;
  }

  managerQuickAskButtons.forEach((button) => {
    button.addEventListener("click", () => {
      ensureManagerInputReady();
      const presetQuestion = button.dataset.question || "";
      if (managerQuestionInput && presetQuestion) {
        managerQuestionInput.value = presetQuestion;
      }
      void askManagerAssistant();
    });
  });
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

function syncFaceTrackingCanvasSize() {
  if (!faceTrackingCanvas) {
    return;
  }

  const rect = faceTrackingCanvas.getBoundingClientRect();
  if (!rect.width || !rect.height) {
    return;
  }

  const dpr = window.devicePixelRatio || 1;
  const targetWidth = Math.max(1, Math.round(rect.width * dpr));
  const targetHeight = Math.max(1, Math.round(rect.height * dpr));

  if (faceTrackingCanvas.width !== targetWidth || faceTrackingCanvas.height !== targetHeight) {
    faceTrackingCanvas.width = targetWidth;
    faceTrackingCanvas.height = targetHeight;
  }
}

function clearTrackingOverlay() {
  if (!trackingOverlay) {
    return;
  }

  const context = trackingOverlay.getContext("2d");
  context.clearRect(0, 0, trackingOverlay.width, trackingOverlay.height);
}

function clearFaceTrackingScreen(message = "Face tracker idle. Start camera to lock face.") {
  if (!faceTrackingCanvas) {
    return;
  }

  syncFaceTrackingCanvasSize();
  const context = faceTrackingCanvas.getContext("2d");
  const width = faceTrackingCanvas.width;
  const height = faceTrackingCanvas.height;

  context.fillStyle = "#0a1114";
  context.fillRect(0, 0, width, height);

  context.strokeStyle = "rgba(64, 208, 180, 0.55)";
  context.lineWidth = Math.max(2, Math.round(2 * (window.devicePixelRatio || 1)));
  const guideW = Math.round(width * 0.46);
  const guideH = Math.round(height * 0.54);
  const guideX = Math.round((width - guideW) / 2);
  const guideY = Math.round((height - guideH) / 2);
  context.strokeRect(guideX, guideY, guideW, guideH);

  context.fillStyle = "#9fb7c4";
  context.font = `${Math.max(13, Math.round(11 * (window.devicePixelRatio || 1)))}px \"IBM Plex Mono\", monospace`;
  context.fillText("face-lock target", guideX + 8, guideY + 22);

  if (faceTrackingStatus) {
    faceTrackingStatus.textContent = message;
  }
}

function renderFaceTrackingScreen(frame) {
  if (!faceTrackingCanvas || !frame || !Array.isArray(frame.detections)) {
    clearFaceTrackingScreen();
    return;
  }

  const workers = frame.detections.filter((detection) => detection.category === "worker");
  const faceWorkers = workers.filter((detection) => detection.face_detected === true);
  if (!faceWorkers.length) {
    clearFaceTrackingScreen("Face lost. Keep face visible and centered.");
    return;
  }

  const target = faceWorkers
    .slice()
    .sort((a, b) => {
      const aArea = Number(a.face_bbox?.w || 0) * Number(a.face_bbox?.h || 0);
      const bArea = Number(b.face_bbox?.w || 0) * Number(b.face_bbox?.h || 0);
      return (Number(b.confidence || 0) + bArea) - (Number(a.confidence || 0) + aArea);
    })[0];

  const workerBox = target.bbox || {};
  const fallbackFaceBox = {
    x: Number(workerBox.x || 0) + (Number(workerBox.w || 0) * 0.22),
    y: Number(workerBox.y || 0) + (Number(workerBox.h || 0) * 0.04),
    w: Number(workerBox.w || 0) * 0.56,
    h: Number(workerBox.h || 0) * 0.36,
  };
  const faceBox = target.face_bbox || fallbackFaceBox;

  const source = cameraVideo;
  const sourceWidth = source && source.videoWidth ? source.videoWidth : 0;
  const sourceHeight = source && source.videoHeight ? source.videoHeight : 0;
  if (!sourceWidth || !sourceHeight) {
    clearFaceTrackingScreen("Face detected. Start live camera to render face screen.");
    return;
  }

  syncFaceTrackingCanvasSize();
  const context = faceTrackingCanvas.getContext("2d");
  const canvasWidth = faceTrackingCanvas.width;
  const canvasHeight = faceTrackingCanvas.height;
  context.clearRect(0, 0, canvasWidth, canvasHeight);

  const fx = Math.max(0, Math.min(sourceWidth - 1, Math.round(Number(faceBox.x || 0) * sourceWidth)));
  const fy = Math.max(0, Math.min(sourceHeight - 1, Math.round(Number(faceBox.y || 0) * sourceHeight)));
  const fw = Math.max(2, Math.min(sourceWidth - fx, Math.round(Number(faceBox.w || 0.1) * sourceWidth)));
  const fh = Math.max(2, Math.min(sourceHeight - fy, Math.round(Number(faceBox.h || 0.1) * sourceHeight)));

  const padX = Math.round(fw * 1.05);
  const padY = Math.round(fh * 1.28);
  const cropX = Math.max(0, fx - padX);
  const cropY = Math.max(0, fy - padY);
  const cropW = Math.max(2, Math.min(sourceWidth - cropX, fw + (padX * 2)));
  const cropH = Math.max(2, Math.min(sourceHeight - cropY, fh + (padY * 2)));

  context.drawImage(source, cropX, cropY, cropW, cropH, 0, 0, canvasWidth, canvasHeight);

  const scaleX = canvasWidth / cropW;
  const scaleY = canvasHeight / cropH;
  const faceLeft = (fx - cropX) * scaleX;
  const faceTop = (fy - cropY) * scaleY;
  const faceWidth = fw * scaleX;
  const faceHeight = fh * scaleY;

  context.strokeStyle = "#40d0b4";
  context.lineWidth = Math.max(2, Math.round(2 * (window.devicePixelRatio || 1)));
  context.strokeRect(faceLeft, faceTop, faceWidth, faceHeight);

  const eyeText = target.eyes_closed === true
    ? `eyes closed ${Number(target.eyes_closed_seconds || 0).toFixed(1)}s`
    : target.eyes_closed === false
      ? "eyes open"
      : "eyes unknown";
  const keyboardText = target.hand_on_keyboard === true
    ? "keyboard on"
    : target.hand_on_keyboard === false
      ? `keyboard off ${Number(target.hand_off_keyboard_seconds || 0).toFixed(1)}s`
      : "keyboard unknown";

  if (faceTrackingStatus) {
    faceTrackingStatus.textContent = `Face lock ${target.track_id || "W-001"} | ${eyeText} | ${keyboardText}`;
  }
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
          label: "Interruptions",
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
          title: { display: true, text: "Interruptions" },
        },
      },
      plugins: {
        legend: { position: "top" },
      },
    },
  });
}

function renderFlowRecovery(flowRecovery) {
  if (!flowRecoveryBox) {
    return;
  }

  if (!flowRecovery || !Array.isArray(flowRecovery.issues) || flowRecovery.issues.length === 0) {
    flowRecoveryBox.innerHTML = '<p class="placeholder">Run advanced analytics to generate flow recovery guidance.</p>';
    return;
  }

  flowRecoveryBox.innerHTML = `
    <div class="novelty-header-row">
      <strong>Projected Utilization Gain: ${Number(flowRecovery.projected_utilization_gain_pct || 0).toFixed(1)}%</strong>
      <span>${escapeHtml(flowRecovery.top_recommendation || "")}</span>
    </div>
    ${flowRecovery.issues.slice(0, 4).map((issue) => `
      <article class="novelty-card">
        <div class="novelty-topline">
          <strong>${escapeHtml(issue.camera_id)}</strong>
          <span class="severity-pill ${escapeHtml(issue.severity)}">${escapeHtml(issue.severity)}</span>
        </div>
        <div class="novelty-topline">
          <span>Blocked score: ${Number(issue.blocked_score || 0).toFixed(1)}%</span>
          <span>Recovery ETA: ${Number(issue.estimated_recovery_minutes || 0)} min</span>
        </div>
        <div class="novelty-subtext">Cause: ${escapeHtml(issue.likely_cause || "")}</div>
        <div class="novelty-subtext">Signals: ${(issue.signals || []).map((item) => escapeHtml(item)).join(" | ") || "none"}</div>
        <ul class="novelty-actions">
          ${(issue.recommended_actions || []).slice(0, 3).map((action) => `<li>${escapeHtml(action)}</li>`).join("")}
        </ul>
      </article>
    `).join("")}
  `;
}

function renderBottleneckGraph(graph) {
  if (!bottleneckGraphBox) {
    return;
  }

  if (!graph || !Array.isArray(graph.nodes) || graph.nodes.length === 0) {
    bottleneckGraphBox.innerHTML = '<p class="placeholder">Run advanced analytics to build the bottleneck graph.</p>';
    return;
  }

  const cameraNodes = graph.nodes.filter((node) => node.node_type === "camera");
  const strongEdges = (graph.edges || []).slice().sort((a, b) => Number(b.weight || 0) - Number(a.weight || 0)).slice(0, 6);

  bottleneckGraphBox.innerHTML = `
    <div class="novelty-header-row">
      <strong>Bottleneck Index: ${Number(graph.bottleneck_index_pct || 0).toFixed(1)}%</strong>
      <span>${cameraNodes.length} camera nodes, ${Number((graph.edges || []).length)} dependency edges</span>
    </div>
    <div class="bottleneck-grid">
      ${cameraNodes.map((node) => `
        <article class="novelty-card">
          <div class="novelty-topline">
            <strong>${escapeHtml(node.label)}</strong>
            <span>Load ${Number(node.load_pct || 0).toFixed(1)}%</span>
          </div>
          <div class="bottleneck-bar-wrap">
            <div class="bottleneck-bar" style="width: ${Math.max(0, Math.min(100, Number(node.load_pct || 0)))}%"></div>
          </div>
        </article>
      `).join("")}
    </div>
    <div class="novelty-subtext">Top dependency edges</div>
    <ul class="novelty-actions">
      ${strongEdges.map((edge) => `<li>${escapeHtml(edge.source)} -> ${escapeHtml(edge.target)} (${Number(edge.weight || 0).toFixed(1)}%): ${escapeHtml(edge.reason || "")}</li>`).join("")}
    </ul>
    <div class="novelty-subtext">Recommended interventions</div>
    <ul class="novelty-actions">
      ${(graph.interventions || []).slice(0, 4).map((item) => `<li>${escapeHtml(item.title)}: ${escapeHtml(item.detail)} (expected +${Number(item.expected_gain_pct || 0).toFixed(1)}%)</li>`).join("")}
    </ul>
  `;
}

function renderPrivacyProof(proof) {
  if (!privacyProofBox) {
    return;
  }

  if (!proof) {
    privacyProofBox.innerHTML = '<p class="placeholder">Run advanced analytics to generate privacy proof and audit logs.</p>';
    return;
  }

  privacyProofBox.innerHTML = `
    <div class="novelty-header-row">
      <strong>Privacy Score: ${Number(proof.privacy_score || 0).toFixed(1)}%</strong>
      <span>Model Confidence: ${Number(proof.confidence_score || 0).toFixed(1)}% | Challenges: ${Number(proof.challenge_count || 0)}</span>
    </div>
    <div class="novelty-subtext">Retention: ${escapeHtml(proof.data_retention_policy || "")}</div>
    <div class="novelty-subtext">Controls</div>
    <ul class="novelty-actions">
      ${(proof.controls || []).map((control) => `<li><strong>${escapeHtml(control.key)}</strong> [${escapeHtml(control.status)}]: ${escapeHtml(control.detail)}</li>`).join("")}
    </ul>
    <div class="novelty-subtext">Recent Audit Log</div>
    <ul class="novelty-actions">
      ${(proof.audit_log || []).slice(0, 6).map((event) => `<li>${escapeHtml(event.event_id)} (${escapeHtml(event.severity)}): ${escapeHtml(event.detail)}</li>`).join("")}
    </ul>
  `;
}

function renderManagerReport(report) {
  if (!managerReportBox) {
    return;
  }

  if (!report) {
    managerReportBox.innerHTML = '<p class="placeholder">Live 2-minute manager report will appear here when worker camera frames are analyzed.</p>';
    return;
  }

  const start = report.window_start ? new Date(report.window_start) : null;
  const end = report.window_end ? new Date(report.window_end) : null;
  const windowLabel = start && end
    ? `${start.toLocaleTimeString()} - ${end.toLocaleTimeString()}`
    : "window unavailable";

  managerReportBox.innerHTML = `
    <div class="novelty-header-row">
      <strong>2-Minute Worker Report</strong>
      <span class="manager-report-window">${escapeHtml(report.camera_id || "")}: ${escapeHtml(windowLabel)}</span>
    </div>
    <div class="manager-report-lead">${escapeHtml(String(report.summary || ""))}</div>
    <div class="manager-report-meta">Source mode: ${escapeHtml(String(report.source_mode || "local-fallback"))} | Utilization ${Number(report.avg_utilization_pct || 0).toFixed(1)}% | Progress ${Number(report.avg_progress_pct || 0).toFixed(1)}% | Interruptions ${Number(report.interruptions || 0)}</div>
    <div class="novelty-subtext">Manager highlights</div>
    <ul class="novelty-actions">
      ${(report.highlights || []).map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}
    </ul>
  `;
}

function renderManagerChatLog() {
  if (!managerChatLog) {
    return;
  }

  if (!state.managerChatHistory.length) {
    managerChatLog.innerHTML = '<li class="placeholder">No manager chat yet.</li>';
    return;
  }

  managerChatLog.innerHTML = state.managerChatHistory
    .slice(-8)
    .reverse()
    .map((item) => {
      const start = item.window_start ? new Date(item.window_start) : null;
      const end = item.window_end ? new Date(item.window_end) : null;
      const windowText = start && end
        ? `${start.toLocaleTimeString()} - ${end.toLocaleTimeString()}`
        : "window unavailable";

      return `<li class="manager-chat-item">
        <strong>Q: ${escapeHtml(item.question || "")}</strong>
        <div>${escapeHtml(item.answer || "")}</div>
        <div class="novelty-subtext">${escapeHtml(item.camera_id || "")} | ${escapeHtml(windowText)} | ${escapeHtml(item.source_mode || "local-fallback")}</div>
        <ul class="novelty-actions">
          ${(item.supporting_points || []).map((point) => `<li>${escapeHtml(String(point))}</li>`).join("")}
        </ul>
      </li>`;
    })
    .join("");
}

function captureFrameBase64() {
  const width = cameraVideo.videoWidth || 640;
  const height = cameraVideo.videoHeight || 360;

  captureCanvas.width = width;
  captureCanvas.height = height;

  const context = captureCanvas.getContext("2d");
  context.drawImage(cameraVideo, 0, 0, width, height);

  const quality = IS_RENDER_HOST ? 0.58 : 0.72;
  return captureCanvas.toDataURL("image/jpeg", quality);
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
      previous_image_base64: IS_RENDER_HOST ? null : state.previousFrameBase64,
      site_area: siteAreaInput.value.trim() || "live-zone",
      expected_workers: Number(expectedWorkersInput.value || 0),
      tasks_planned: Number(tasksPlannedInput.value || 0),
      tasks_completed: Number(tasksCompletedInput.value || 0),
      single_person_mode: Boolean(singlePersonModeInput && singlePersonModeInput.checked),
    };

    const response = await fetchWithRetry("/vision/analyze-camera-frame", {
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
    renderFaceTrackingScreen(result.frame);
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
      `Live ${result.frame.camera_id}: source ${result.data_source}, mock ${result.is_mock ? "yes" : "no"}, single-mode ${result.single_person_mode_applied ? "on" : "off"}, eye-idle ${result.eye_idle_workers}, hand-break ${result.hand_break_workers}, ${result.analysis.worker_count} workers, util ${result.analysis.utilization_pct.toFixed(1)}%, task progress ${result.analysis.progress_pct.toFixed(1)}%, activity ${result.activity_index_pct.toFixed(1)}%, mode ${result.data_mode}, evidence ${result.evidence_score.toFixed(1)}%, calibration ${calibrationLabel}, detector ${result.detector}, interruptions ${result.safety_detections}, classes ${classesLabel}, motion ${(result.motion_score * 100).toFixed(1)}%.`,
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

    const response = await fetchWithRetry("/vision/analyze-camera-frame", {
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
    renderFaceTrackingScreen(result.frame);
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
    clearFaceTrackingScreen();

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
    syncFaceTrackingCanvasSize();
    clearFaceTrackingScreen("Searching for face lock...");

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
    await refreshManagerReport(true);

    const minimumInterval = IS_RENDER_HOST ? 2 : 1;
    const intervalSec = Math.max(minimumInterval, Math.min(10, Number(captureIntervalInput.value || 3)));
    if (IS_RENDER_HOST && Number(captureIntervalInput.value || 0) < minimumInterval) {
      captureIntervalInput.value = String(minimumInterval);
      setStatus("Render mode: using safer 2s capture interval for stable analysis.", "ok");
    }
    state.cameraTimer = setInterval(analyzeSingleCameraFrame, intervalSec * 1000);

    if (state.managerReportTimer) {
      clearInterval(state.managerReportTimer);
    }
    state.managerReportTimer = setInterval(() => {
      void refreshManagerReport(true);
    }, 120000);
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

  if (state.managerReportTimer) {
    clearInterval(state.managerReportTimer);
    state.managerReportTimer = null;
  }

  if (state.cameraStream) {
    state.cameraStream.getTracks().forEach((track) => track.stop());
    state.cameraStream = null;
  }

  cameraVideo.srcObject = null;
  state.previousFrameBase64 = null;
  clearTrackingOverlay();
  clearFaceTrackingScreen();
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
    state.flowRecovery = null;
    state.bottleneckGraph = null;
    state.privacyProof = null;
    state.managerReport = null;
    state.managerChatHistory = [];
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
    renderFlowRecovery(null);
    renderBottleneckGraph(null);
    renderPrivacyProof(null);
    renderManagerReport(null);
    renderManagerChatLog();
    updateEvidenceBadges(null);
    updateEyeIdleBadge(null);
    updateHandBreakBadge(null);
    renderEvidenceStrip();
    clearFaceTrackingScreen();

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

  setStatus("Analyzing worker progress and flow interruptions...");
  lockButtons(true);
  let shouldRefreshAdvanced = false;

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
      `Analysis complete. Avg utilization ${state.summary.avg_utilization_pct.toFixed(1)}%, interruption events ${state.summary.safety_violations}.`,
      state.summary.safety_violations > 0 ? "warn" : "ok",
    );
    shouldRefreshAdvanced = true;
  } catch (error) {
    setStatus(`Analysis failed: ${error.message}`, "warn");
  } finally {
    lockButtons(false);
  }

  if (shouldRefreshAdvanced) {
    await runAdvancedAnalytics();
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
    return false;
  }

  setStatus("Running portfolio analytics, camera health, events, and trends...");
  lockButtons(true);

  try {
    const payload = JSON.stringify({ frames: state.frames });
    const [portfolioRes, healthRes, eventsRes, trendsRes, flowRes, bottleneckRes, privacyRes] = await Promise.all([
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
      fetch("/copilot/flow-recovery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      }),
      fetch("/copilot/bottleneck-graph", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      }),
      fetch("/trust/privacy-proof", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      }),
    ]);

    if (
      !portfolioRes.ok
      || !healthRes.ok
      || !eventsRes.ok
      || !trendsRes.ok
      || !flowRes.ok
      || !bottleneckRes.ok
      || !privacyRes.ok
    ) {
      throw new Error("one or more advanced analytics requests failed");
    }

    state.portfolio = await portfolioRes.json();
    state.cameraHealth = await healthRes.json();
    state.eventFeed = await eventsRes.json();
    state.trends = await trendsRes.json();
    state.flowRecovery = await flowRes.json();
    state.bottleneckGraph = await bottleneckRes.json();
    state.privacyProof = await privacyRes.json();

    renderPortfolio(state.portfolio);
    renderCameraHealth(state.cameraHealth);
    renderEventFeed(state.eventFeed);
    renderTrendTimeline(state.trends);
    renderFlowRecovery(state.flowRecovery);
    renderBottleneckGraph(state.bottleneckGraph);
    renderPrivacyProof(state.privacyProof);

    const trendSummary = state.trends.cameras
      .map((camera) => `${camera.camera_id}:${camera.direction}`)
      .join(", ");
    setStatus(
      `Advanced analytics ready. Fleet score ${state.portfolio.fleet_score.toFixed(1)}. Trends ${trendSummary}. Flow gain ${Number(state.flowRecovery.projected_utilization_gain_pct || 0).toFixed(1)}%, bottleneck index ${Number(state.bottleneckGraph.bottleneck_index_pct || 0).toFixed(1)}%, privacy ${Number(state.privacyProof.privacy_score || 0).toFixed(1)}%.`,
      "ok",
    );
    return true;
  } catch (error) {
    setStatus(`Advanced analytics failed: ${error.message}`, "warn");
    return false;
  } finally {
    lockButtons(false);
  }
}

async function refreshManagerReport(silent = false) {
  ensureManagerInputReady();

  const cameraId = managerCameraIdInput && managerCameraIdInput.value
    ? managerCameraIdInput.value.trim()
    : "CAM-LIVE-01";

  if (!cameraId) {
    if (!silent) {
      setStatus("Provide worker camera ID for manager report.", "warn");
    }
    return;
  }

  if (!silent) {
    setStatus("Refreshing manager 2-minute report...");
  }
  lockButtons(true);

  try {
    const payload = {
      camera_id: cameraId,
    };

    const response = await postManagerApi("/manager/report/latest", payload);

    if (!response.ok) {
      throw new Error(`manager report failed (${response.status})`);
    }

    state.managerReport = await response.json();
    renderManagerReport(state.managerReport);

    if (!silent) {
      setStatus("Manager 2-minute report updated.", "ok");
    }
  } catch (error) {
    if (!silent) {
      setStatus(`Manager report failed: ${error.message}`, "warn");
    }
  } finally {
    lockButtons(false);
  }
}

async function askManagerAssistant() {
  ensureManagerInputReady();

  const question = managerQuestionInput && managerQuestionInput.value
    ? managerQuestionInput.value.trim()
    : "";
  const cameraId = managerCameraIdInput && managerCameraIdInput.value
    ? managerCameraIdInput.value.trim()
    : "CAM-LIVE-01";

  const safeQuestion = question && question.length >= 4
    ? question
    : "In the last 5 minutes, what did the worker do and where were the interruptions?";

  setStatus("Manager assistant is analyzing requested time window...");
  lockButtons(true);

  try {
    const payload = {
      question: safeQuestion,
      camera_id: cameraId,
    };

    const response = await postManagerApi("/manager/chat", payload);

    if (!response.ok) {
      throw new Error(`manager chat failed (${response.status})`);
    }

    const result = await response.json();
    state.managerChatHistory.push({
      question: safeQuestion,
      ...result,
    });
    if (state.managerChatHistory.length > 40) {
      state.managerChatHistory.splice(0, state.managerChatHistory.length - 40);
    }

    renderManagerChatLog();
    if (managerQuestionInput) {
      managerQuestionInput.value = "";
    }

    setStatus("Manager assistant response ready.", "ok");
  } catch (error) {
    setStatus(`Manager assistant failed: ${error.message}`, "warn");
  } finally {
    lockButtons(false);
  }
}

async function submitPrivacyChallenge() {
  const reason = privacyChallengeReason ? privacyChallengeReason.value.trim() : "";
  if (!reason || reason.length < 3) {
    setStatus("Provide a clearer challenge reason (minimum 3 characters).", "warn");
    return;
  }

  const latestCamera = state.frames.length ? state.frames[state.frames.length - 1].camera_id : "CAM-LIVE-01";

  try {
    const response = await fetch("/trust/privacy-proof/challenge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        camera_id: latestCamera,
        reason,
      }),
    });

    if (!response.ok) {
      throw new Error(`challenge failed (${response.status})`);
    }

    const result = await response.json();
    if (privacyChallengeReason) {
      privacyChallengeReason.value = "";
    }

    const refreshed = await runAdvancedAnalytics();
    if (refreshed) {
      setStatus(`Privacy challenge ${result.challenge_id} accepted and privacy proof refreshed.`, "ok");
    } else {
      setStatus(`Privacy challenge ${result.challenge_id} accepted. Advanced analytics refresh failed.`, "warn");
    }
  } catch (error) {
    setStatus(`Privacy challenge failed: ${error.message}`, "warn");
  }
}

loadSeedBtn.addEventListener("click", loadSeedFrames);
runMockBtn.addEventListener("click", runMockInference);
analyzeBtn.addEventListener("click", analyzeProgress);
advancedAnalyticsBtn.addEventListener("click", runAdvancedAnalytics);
managerReportBtn.addEventListener("click", () => {
  void refreshManagerReport(false);
});
reportBtn.addEventListener("click", generateReport);
startCameraBtn.addEventListener("click", startCameraAnalysis);
stopCameraBtn.addEventListener("click", stopCameraAnalysis);
refreshDevicesBtn.addEventListener("click", refreshCameraDevices);
resetLiveBtn.addEventListener("click", () => {
  void resetLiveBaseline(false);
});
analyzeUploadBtn.addEventListener("click", analyzeUploadedFrame);
if (askManagerBtn) {
  askManagerBtn.addEventListener("click", askManagerAssistant);
}
if (managerQuestionInput) {
  managerQuestionInput.addEventListener("focus", ensureManagerInputReady);
  managerQuestionInput.addEventListener("pointerdown", ensureManagerInputReady, true);
  managerQuestionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void askManagerAssistant();
    }
  });
}
bindManagerQuickAsks();
if (submitPrivacyChallengeBtn) {
  submitPrivacyChallengeBtn.addEventListener("click", submitPrivacyChallenge);
}
trendCameraSelect.addEventListener("change", () => {
  state.selectedTrendCameraId = trendCameraSelect.value;
  renderTrendTimelineForCamera(state.selectedTrendCameraId);
});

window.addEventListener("beforeunload", stopCameraAnalysis);
window.addEventListener("resize", () => {
  syncTrackingOverlaySize();
  syncFaceTrackingCanvasSize();

  const latestFrame = state.frames[state.frames.length - 1];
  if (latestFrame) {
    drawTrackingOverlay(latestFrame);
    renderFaceTrackingScreen(latestFrame);
  }
});
cameraVideo.addEventListener("loadedmetadata", () => {
  syncTrackingOverlaySize();
  syncFaceTrackingCanvasSize();

  const latestFrame = state.frames[state.frames.length - 1];
  if (latestFrame) {
    drawTrackingOverlay(latestFrame);
    renderFaceTrackingScreen(latestFrame);
  }
});

setStatus("Ready. Start camera to run live evidence mode.");
ensureManagerInputReady();
setInterval(ensureManagerInputReady, 4000);
updateLiveMovement(null, 0);
updateEvidenceBadges(null);
updateEyeIdleBadge(null);
updateHandBreakBadge(null);
renderFlowRecovery(null);
renderBottleneckGraph(null);
renderPrivacyProof(null);
renderManagerReport(null);
renderManagerChatLog();
clearFaceTrackingScreen();
renderEvidenceStrip();
refreshCameraDevices();
