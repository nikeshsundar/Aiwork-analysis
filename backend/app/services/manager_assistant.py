from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request

from app.schemas import ManagerChatResponse, ManagerReportResponse


@dataclass
class TimelineEvent:
    timestamp: datetime
    camera_id: str
    site_area: str
    worker_count: int
    active_workers: int
    utilization_pct: float
    progress_pct: float
    interruptions: int
    alerts: List[str]
    eye_idle_workers: int
    hand_break_workers: int
    activity_index_pct: float
    evidence_score: float


class ManagerTimelineStore:
    def __init__(self) -> None:
        self._events: List[TimelineEvent] = []
        self._lock = Lock()

    def ingest(self, event: TimelineEvent) -> None:
        with self._lock:
            self._events.append(event)
            self._events.sort(key=lambda item: item.timestamp)

            cutoff = _utc_now() - timedelta(hours=12)
            self._events = [item for item in self._events if item.timestamp >= cutoff]

    def range(self, camera_id: str, start_time: datetime, end_time: datetime) -> List[TimelineEvent]:
        with self._lock:
            return [
                item
                for item in self._events
                if item.camera_id == camera_id and start_time <= item.timestamp <= end_time
            ]

    def latest_timestamp(self, camera_id: str) -> Optional[datetime]:
        with self._lock:
            filtered = [item.timestamp for item in self._events if item.camera_id == camera_id]
        if not filtered:
            return None
        return max(filtered)


manager_timeline_store = ManagerTimelineStore()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _first_non_empty(*values: Optional[str]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _is_local_base_url(base_url: str) -> bool:
    lowered = base_url.lower()
    return "127.0.0.1" in lowered or "localhost" in lowered


def _parse_time_range(question: str, reference_day: datetime) -> Optional[Tuple[datetime, datetime]]:
    # Supports patterns like "4:01 to 4:05" and "4 01 to 4 05".
    pattern = re.compile(r"(\d{1,2})\s*[:.\s]\s*(\d{2})\s*(?:to|-|until)\s*(\d{1,2})\s*[:.\s]\s*(\d{2})", re.IGNORECASE)
    match = pattern.search(question)
    if not match:
        return None

    sh, sm, eh, em = [int(item) for item in match.groups()]

    def _align_hour(hour_value: int, reference_hour: int) -> int:
        bounded = max(0, min(hour_value, 23))
        candidates = [bounded]
        if bounded < 12:
            candidates.append(bounded + 12)
        elif bounded == 12:
            candidates.append(0)

        return min(candidates, key=lambda candidate: abs(candidate - reference_hour))

    sh = _align_hour(sh, reference_day.hour)
    eh = _align_hour(eh, reference_day.hour)
    sm = max(0, min(sm, 59))
    em = max(0, min(em, 59))

    start = reference_day.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = reference_day.replace(hour=eh, minute=em, second=59, microsecond=0)

    if end < start:
        end = end + timedelta(days=1)

    return start, end


def _report_stats(events: List[TimelineEvent]) -> Tuple[float, float, int, float]:
    if not events:
        return 0.0, 0.0, 0, 0.0

    avg_util = sum(item.utilization_pct for item in events) / len(events)
    avg_progress = sum(item.progress_pct for item in events) / len(events)
    interruptions = sum(item.interruptions for item in events)
    avg_activity = sum(item.activity_index_pct for item in events) / len(events)
    return avg_util, avg_progress, interruptions, avg_activity


def _local_report_summary(camera_id: str, events: List[TimelineEvent], start: datetime, end: datetime) -> ManagerReportResponse:
    avg_util, avg_progress, interruptions, avg_activity = _report_stats(events)

    if not events:
        return ManagerReportResponse(
            generated_at=_utc_now(),
            camera_id=camera_id,
            window_start=start,
            window_end=end,
            source_mode="local-fallback",
            summary="No worker activity captured in this 2-minute window yet.",
            highlights=[
                "Camera is connected but no analyzed frames were received in this interval.",
                "Keep live capture running to build report continuity.",
            ],
            avg_utilization_pct=0.0,
            avg_progress_pct=0.0,
            interruptions=0,
        )

    eye_idle = sum(item.eye_idle_workers for item in events)
    hand_break = sum(item.hand_break_workers for item in events)

    if interruptions > 0:
        mode = "interruption-heavy"
    elif avg_util >= 60:
        mode = "focused"
    else:
        mode = "low-focus"

    summary = (
        f"From {start.strftime('%H:%M')} to {end.strftime('%H:%M')}, worker lane {camera_id} was {mode}. "
        f"Utilization averaged {avg_util:.1f}% and progress averaged {avg_progress:.1f}% with {interruptions} interruption signals."
    )

    highlights = [
        f"Average activity index: {avg_activity:.1f}%.",
        f"Eye-idle triggers: {eye_idle}; keyboard-break triggers: {hand_break}.",
    ]
    if interruptions > 0:
        highlights.append("Manager action: check blocker context and restore a focused 20-minute execution block.")
    else:
        highlights.append("Manager action: maintain current flow cadence and avoid unnecessary context switches.")

    return ManagerReportResponse(
        generated_at=_utc_now(),
        camera_id=camera_id,
        window_start=start,
        window_end=end,
        source_mode="local-fallback",
        summary=summary,
        highlights=highlights,
        avg_utilization_pct=round(avg_util, 1),
        avg_progress_pct=round(avg_progress, 1),
        interruptions=interruptions,
    )


def _events_for_window(camera_id: str, start: datetime, end: datetime) -> List[TimelineEvent]:
    return manager_timeline_store.range(camera_id, start, end)


def _call_llm(api_key: Optional[str], model: str, base_url: str, prompt: str) -> Dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.25,
        "messages": [
            {
                "role": "system",
                "content": "You are a manager-side workforce analytics assistant. Be precise, concise, and actionable.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(
        endpoint,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )

    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _report_prompt(camera_id: str, start: datetime, end: datetime, events: List[TimelineEvent]) -> str:
    rows = [
        (
            f"{item.timestamp.strftime('%H:%M:%S')} util={item.utilization_pct:.1f} progress={item.progress_pct:.1f} "
            f"active={item.active_workers}/{item.worker_count} interrupts={item.interruptions} "
            f"eye_idle={item.eye_idle_workers} hand_break={item.hand_break_workers} alerts={'; '.join(item.alerts[:2]) if item.alerts else 'none'}"
        )
        for item in events[-12:]
    ]

    return (
        "Generate a strict JSON manager report for the 2-minute worker monitoring window. "
        "Return keys: summary (string), highlights (array of 2-4 strings).\n"
        f"Camera: {camera_id}\n"
        f"Window: {start.isoformat()} to {end.isoformat()}\n"
        "Event samples:\n"
        + "\n".join(rows)
    )


def _chat_prompt(question: str, camera_id: str, start: datetime, end: datetime, events: List[TimelineEvent]) -> str:
    rows = [
        (
            f"{item.timestamp.strftime('%H:%M:%S')} util={item.utilization_pct:.1f} progress={item.progress_pct:.1f} "
            f"active={item.active_workers}/{item.worker_count} interruptions={item.interruptions} "
            f"alerts={'; '.join(item.alerts[:3]) if item.alerts else 'none'}"
        )
        for item in events[-25:]
    ]

    return (
        "Answer the manager question using ONLY the supplied timeline. "
        "Keep answer concise and factual in 4-6 lines plus 2 supporting points. "
        "Return strict JSON keys: answer (string), supporting_points (array of 2-4 strings).\n"
        f"Camera: {camera_id}\n"
        f"Window: {start.isoformat()} to {end.isoformat()}\n"
        f"Question: {question}\n"
        "Timeline:\n"
        + "\n".join(rows)
    )


def _resolve_manager_llm_config() -> Tuple[str, str, str]:
    resolved_model = _first_non_empty(
        os.getenv("OPENROUTER_MODEL"),
        os.getenv("KIMI_MODEL"),
        os.getenv("NIM_MODEL"),
        "qwen/qwen3.6-plus:free",
    )
    resolved_base_url = _first_non_empty(
        os.getenv("OPENROUTER_BASE_URL"),
        os.getenv("KIMI_BASE_URL"),
        os.getenv("NIM_BASE_URL"),
        "https://openrouter.ai/api/v1",
    )
    resolved_key = _first_non_empty(
        os.getenv("OPENROUTER_API_KEY"),
        os.getenv("KIMI_API_KEY"),
        os.getenv("NVCF_RUN_KEY"),
        os.getenv("NVIDIA_API_KEY"),
    )
    return resolved_model, resolved_base_url, resolved_key


def build_manager_two_minute_report(
    camera_id: str,
) -> ManagerReportResponse:
    latest = manager_timeline_store.latest_timestamp(camera_id)
    if latest is None:
        now = _utc_now()
        return _local_report_summary(camera_id, [], now - timedelta(minutes=2), now)

    end = latest
    start = end - timedelta(minutes=2)
    events = _events_for_window(camera_id, start, end)

    resolved_model, resolved_base_url, resolved_key = _resolve_manager_llm_config()

    key_required = not _is_local_base_url(resolved_base_url)
    if key_required and not resolved_key:
        return _local_report_summary(camera_id, events, start, end)

    local = _local_report_summary(camera_id, events, start, end)

    try:
        raw = _call_llm(resolved_key if resolved_key else None, resolved_model, resolved_base_url, _report_prompt(camera_id, start, end, events))
        choices = raw.get("choices", [])
        content = str(choices[0].get("message", {}).get("content", "")).strip() if choices else ""
        if not content:
            return local

        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx < 0 or end_idx <= start_idx:
            return local

        parsed = json.loads(content[start_idx : end_idx + 1])
        summary = str(parsed.get("summary", "")).strip() or local.summary
        highlights = parsed.get("highlights", local.highlights)
        if not isinstance(highlights, list):
            highlights = local.highlights
        highlights = [str(item).strip() for item in highlights if str(item).strip()][:4] or local.highlights

        return ManagerReportResponse(
            generated_at=_utc_now(),
            camera_id=camera_id,
            window_start=start,
            window_end=end,
            source_mode="live-llm",
            summary=summary,
            highlights=highlights,
            avg_utilization_pct=local.avg_utilization_pct,
            avg_progress_pct=local.avg_progress_pct,
            interruptions=local.interruptions,
        )
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return local


def build_manager_chat_answer(
    question: str,
    camera_id: str,
) -> ManagerChatResponse:
    latest = manager_timeline_store.latest_timestamp(camera_id)
    if latest is None:
        now = _utc_now()
        return ManagerChatResponse(
            generated_at=now,
            camera_id=camera_id,
            source_mode="local-fallback",
            answer="No monitored activity is available yet for this worker camera.",
            supporting_points=[
                "Start live camera analysis to capture timeline events.",
                "Ask again after at least 2 minutes of monitoring.",
            ],
            window_start=now - timedelta(minutes=5),
            window_end=now,
        )

    parsed = _parse_time_range(question, latest)
    if parsed:
        start, end = parsed
    else:
        end = latest
        start = end - timedelta(minutes=5)

    events = _events_for_window(camera_id, start, end)

    avg_util, avg_progress, interruptions, avg_activity = _report_stats(events)
    local_answer = (
        f"Between {start.strftime('%H:%M')} and {end.strftime('%H:%M')}, worker lane {camera_id} "
        f"had average utilization {avg_util:.1f}% and progress {avg_progress:.1f}% with {interruptions} interruption signals."
    )
    local_points = [
        f"Average activity index in window: {avg_activity:.1f}%.",
        f"Records analyzed in window: {len(events)}.",
    ]

    resolved_model, resolved_base_url, resolved_key = _resolve_manager_llm_config()
    key_required = not _is_local_base_url(resolved_base_url)

    if key_required and not resolved_key:
        return ManagerChatResponse(
            generated_at=_utc_now(),
            camera_id=camera_id,
            source_mode="local-fallback",
            answer=local_answer,
            supporting_points=local_points,
            window_start=start,
            window_end=end,
        )

    try:
        raw = _call_llm(resolved_key if resolved_key else None, resolved_model, resolved_base_url, _chat_prompt(question, camera_id, start, end, events))
        choices = raw.get("choices", [])
        content = str(choices[0].get("message", {}).get("content", "")).strip() if choices else ""
        if not content:
            raise ValueError("empty model content")

        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx < 0 or end_idx <= start_idx:
            raise ValueError("json not found")

        parsed_json = json.loads(content[start_idx : end_idx + 1])
        answer = str(parsed_json.get("answer", "")).strip() or local_answer
        supporting = parsed_json.get("supporting_points", local_points)
        if not isinstance(supporting, list):
            supporting = local_points
        supporting = [str(item).strip() for item in supporting if str(item).strip()][:4] or local_points

        return ManagerChatResponse(
            generated_at=_utc_now(),
            camera_id=camera_id,
            source_mode="live-llm",
            answer=answer,
            supporting_points=supporting,
            window_start=start,
            window_end=end,
        )
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return ManagerChatResponse(
            generated_at=_utc_now(),
            camera_id=camera_id,
            source_mode="local-fallback",
            answer=local_answer,
            supporting_points=local_points,
            window_start=start,
            window_end=end,
        )
