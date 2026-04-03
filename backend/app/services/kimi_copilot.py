from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request

from app.schemas import AnalysisSummary, CameraFrame, FrameAnalysis, JudgeWowResponse


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _latest_by_camera(
    frames: List[CameraFrame],
    analyses: List[FrameAnalysis],
) -> Dict[str, Tuple[CameraFrame, FrameAnalysis]]:
    latest: Dict[str, Tuple[CameraFrame, FrameAnalysis]] = {}
    for frame, analysis in sorted(zip(frames, analyses), key=lambda item: item[0].timestamp):
        latest[frame.camera_id] = (frame, analysis)
    return latest


def _fallback_response(
    summary: AnalysisSummary,
    latest: Dict[str, Tuple[CameraFrame, FrameAnalysis]],
    judge_focus: str,
    demo_context: str,
    model: str,
    provider: str,
) -> JudgeWowResponse:
    camera_count = len(latest)
    avg_util = summary.avg_utilization_pct
    avg_progress = summary.avg_progress_pct
    interruptions = summary.safety_violations

    strongest = None
    weakest = None
    if latest:
        analyses = [item[1] for item in latest.values()]
        strongest = max(analyses, key=lambda item: item.utilization_pct)
        weakest = min(analyses, key=lambda item: item.progress_pct)

    one_liner = (
        f"{camera_count} team lanes are live, {summary.total_active_workers}/{summary.total_workers} contributors are active, "
        f"and WorkSight surfaced {interruptions} interruption signals in real time."
    )

    pitch = (
        f"This is not a generic dashboard. For {demo_context}, WorkSight converts raw camera activity into sprint-grade "
        f"decision intelligence: utilization {avg_util:.1f}%, progress {avg_progress:.1f}%, and interruption pressure "
        f"ranked per lane so leads can unblock delivery instantly. Judge focus: {judge_focus}."
    )

    wow_moments = [
        (
            f"Live flow delta: when one lane drops below 55% utilization, the copilot immediately explains likely causes "
            f"and recovery actions."
        ),
        (
            f"Privacy-by-design proof: team-level metrics only, no face identity, and a challenge workflow visible to judges."
        ),
        (
            f"Operational surprise: advanced analytics auto-refresh after base analysis, so insights appear without extra clicks."
        ),
    ]

    if strongest is not None:
        wow_moments.append(
            f"Top lane now: {strongest.camera_id} at {strongest.utilization_pct:.1f}% utilization with {strongest.active_workers} active contributors."
        )
    if weakest is not None:
        wow_moments.append(
            f"Biggest recovery target: {weakest.camera_id} at {weakest.progress_pct:.1f}% progress with actionable alert signals."
        )

    live_script = [
        "Start camera analysis and show evidence score + data mode badges.",
        "Trigger Analyze Progress and pause while interruption counts and utilization update.",
        "Open advanced analytics to display flow recovery, bottleneck graph, and privacy proof in one sequence.",
        "Read the one-liner aloud, then show the weakest lane recommendation to prove immediate decision support.",
    ]

    risk_watchouts = [
        "Lighting and camera angle impact evidence confidence; keep frame stable before judge walkthrough.",
        "If API connectivity drops, local fallback still returns a complete demo narrative.",
        "Use real task plan values to make progress percentages judge-credible.",
    ]

    return JudgeWowResponse(
        generated_at=_utc_now(),
        provider=provider,
        model=model,
        data_mode="local-fallback",
        one_liner=one_liner,
        pitch=pitch,
        wow_moments=wow_moments[:5],
        live_script=live_script,
        risk_watchouts=risk_watchouts,
    )


def _build_prompt(
    summary: AnalysisSummary,
    latest: Dict[str, Tuple[CameraFrame, FrameAnalysis]],
    judge_focus: str,
    demo_context: str,
) -> str:
    camera_summaries: List[str] = []
    for camera_id, (frame, analysis) in latest.items():
        camera_summaries.append(
            (
                f"{camera_id} in {frame.site_area}: workers={analysis.worker_count}, active={analysis.active_workers}, "
                f"util={analysis.utilization_pct:.1f}, progress={analysis.progress_pct:.1f}, interruptions={analysis.safety_violations}, "
                f"alerts={'; '.join(analysis.alerts[:3]) if analysis.alerts else 'none'}"
            )
        )

    joined = "\n".join(camera_summaries) if camera_summaries else "No camera summaries available"

    return (
        "Create a judge-facing hackathon demo brief from these analytics.\n"
        f"Context: {demo_context}\n"
        f"Judge focus: {judge_focus}\n"
        "Return strict JSON with keys: one_liner (string), pitch (string), wow_moments (array of 3-5 strings), "
        "live_script (array of exactly 4 strings), risk_watchouts (array of 3 strings).\n"
        f"Summary: frames={summary.frames_processed}, total_workers={summary.total_workers}, "
        f"active={summary.total_active_workers}, avg_util={summary.avg_utilization_pct:.1f}, "
        f"avg_progress={summary.avg_progress_pct:.1f}, interruptions={summary.safety_violations}\n"
        f"Per camera:\n{joined}"
    )


def _extract_json_object(content: str) -> Dict[str, Any]:
    text = content.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("no JSON object found in model output")


def _coerce_string_list(value: Any, fallback: List[str]) -> List[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or fallback


def _is_local_base_url(base_url: str) -> bool:
    lowered = base_url.lower()
    return "127.0.0.1" in lowered or "localhost" in lowered


def _resolve_provider(base_url: str) -> str:
    lowered = base_url.lower()
    if _is_local_base_url(base_url):
        return "nvidia-nim-local"
    if "nvidia" in lowered or "nim" in lowered:
        return "nvidia-nim-kimi"
    return "moonshot-kimi"


def _first_non_empty(*values: Optional[str]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _call_kimi_chat(
    api_key: Optional[str],
    model: str,
    prompt: str,
    base_url: str,
) -> Dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.35,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a world-class hackathon demo copilot. Always produce concise, specific, judge-impressive output "
                    "with measurable impact language."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(
        endpoint,
        method="POST",
        data=body,
        headers=headers,
    )

    with request.urlopen(req, timeout=20) as response:
        response_body = response.read().decode("utf-8")
        return json.loads(response_body)


def build_judge_wow_response(
    frames: List[CameraFrame],
    analyses: List[FrameAnalysis],
    summary: AnalysisSummary,
    judge_focus: str,
    demo_context: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> JudgeWowResponse:
    resolved_model = _first_non_empty(model, os.getenv("KIMI_MODEL"), os.getenv("NIM_MODEL"), "moonshot-v1-8k")
    resolved_base_url = _first_non_empty(base_url, os.getenv("KIMI_BASE_URL"), os.getenv("NIM_BASE_URL"), "https://api.moonshot.cn/v1")
    provider = _resolve_provider(resolved_base_url)

    latest = _latest_by_camera(frames, analyses)

    key = _first_non_empty(
        api_key,
        os.getenv("KIMI_API_KEY"),
        os.getenv("NVCF_RUN_KEY"),
        os.getenv("NVIDIA_API_KEY"),
    )
    key_required = not _is_local_base_url(resolved_base_url)

    if key_required and not key:
        return _fallback_response(summary, latest, judge_focus, demo_context, resolved_model, provider)

    prompt = _build_prompt(summary, latest, judge_focus, demo_context)

    try:
        raw = _call_kimi_chat(key if key else None, resolved_model, prompt, resolved_base_url)
        choices = raw.get("choices", [])
        content = ""
        if choices:
            content = str(choices[0].get("message", {}).get("content", "")).strip()

        if not content:
            raise ValueError("empty model content")

        parsed = _extract_json_object(content)

        one_liner = str(parsed.get("one_liner", "")).strip() or "WorkSight turns live team behavior into instant delivery decisions."
        pitch = str(parsed.get("pitch", "")).strip() or "Live metrics, actionable insights, and privacy proof in one workflow."
        wow_moments = _coerce_string_list(
            parsed.get("wow_moments"),
            [
                "Live interruption detection with instant recovery guidance.",
                "Bottleneck graph pinpoints where delivery is blocked.",
                "Privacy challenge workflow provides transparent trust signals.",
            ],
        )
        live_script = _coerce_string_list(
            parsed.get("live_script"),
            [
                "Start live analysis and show evidence/provenance badges.",
                "Run analysis and highlight interruption trends.",
                "Open advanced analytics and show flow recovery + bottleneck graph.",
                "Close with privacy proof and the top recommendation.",
            ],
        )
        risk_watchouts = _coerce_string_list(
            parsed.get("risk_watchouts"),
            [
                "Camera placement and lighting affect confidence.",
                "Task planning inputs are needed for realistic progress metrics.",
                "Network/API instability should degrade gracefully to fallback output.",
            ],
        )

        return JudgeWowResponse(
            generated_at=_utc_now(),
            provider=provider,
            model=resolved_model,
            data_mode="live-kimi",
            one_liner=one_liner,
            pitch=pitch,
            wow_moments=wow_moments[:5],
            live_script=live_script[:4],
            risk_watchouts=risk_watchouts[:4],
        )
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return _fallback_response(summary, latest, judge_focus, demo_context, resolved_model, provider)
