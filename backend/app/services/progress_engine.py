from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from app.schemas import (
    CameraHealthItem,
    CameraHealthResponse,
    CameraPortfolioCard,
    CameraTrend,
    AnalysisSummary,
    CameraFrame,
    EventFeedItem,
    EventFeedResponse,
    FrameAnalysis,
    PortfolioResponse,
    ReportInsight,
    TrendPoint,
    TrendResponse,
)


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(100.0, (numerator / denominator) * 100.0))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _trend_direction(start_value: float, end_value: float, threshold: float = 6.0) -> str:
    delta = end_value - start_value
    if delta >= threshold:
        return "up"
    if delta <= -threshold:
        return "down"
    return "stable"


def analyze_frames(frames: List[CameraFrame]) -> List[FrameAnalysis]:
    return [analyze_frame(frame) for frame in frames]


def _group_by_camera(
    frames: List[CameraFrame],
    analyses: List[FrameAnalysis],
) -> Dict[str, List[Tuple[CameraFrame, FrameAnalysis]]]:
    grouped: Dict[str, List[Tuple[CameraFrame, FrameAnalysis]]] = defaultdict(list)

    for frame, analysis in zip(frames, analyses):
        grouped[frame.camera_id].append((frame, analysis))

    for camera_id in grouped:
        grouped[camera_id].sort(key=lambda item: item[0].timestamp)

    return grouped


def analyze_frame(frame: CameraFrame) -> FrameAnalysis:
    workers = [detection for detection in frame.detections if detection.category == "worker"]
    worker_count = len(workers)
    idle_workers = sum(1 for worker in workers if not worker.moving)
    active_workers = max(0, worker_count - idle_workers)

    no_helmet = sum(1 for detection in frame.detections if detection.category == "no_helmet")
    restricted_entries = sum(
        1 for detection in frame.detections if detection.category == "restricted_zone_entry"
    )
    phone_use = sum(1 for detection in frame.detections if detection.category == "phone_use")

    expected_workers = frame.expected_workers if frame.expected_workers > 0 else max(worker_count, 1)
    utilization_pct = _pct(active_workers, expected_workers)

    if frame.tasks_planned > 0:
        progress_pct = _pct(frame.tasks_completed, frame.tasks_planned)
    else:
        progress_pct = min(100.0, utilization_pct * 0.9)

    safety_violations = no_helmet + restricted_entries

    alerts: List[str] = []
    if no_helmet > 0:
        alerts.append(f"{no_helmet} helmet compliance violations")
    if restricted_entries > 0:
        alerts.append(f"{restricted_entries} restricted zone intrusions")
    if phone_use >= 3:
        alerts.append("high distraction pattern detected")
    if utilization_pct < 55:
        alerts.append("low workforce utilization")
    if frame.tasks_planned >= 6 and progress_pct < 45:
        alerts.append("task completion lagging plan")

    return FrameAnalysis(
        camera_id=frame.camera_id,
        timestamp=frame.timestamp,
        worker_count=worker_count,
        active_workers=active_workers,
        idle_workers=idle_workers,
        utilization_pct=round(utilization_pct, 1),
        progress_pct=round(progress_pct, 1),
        safety_violations=safety_violations,
        alerts=alerts,
    )


def aggregate_analyses(analyses: List[FrameAnalysis]) -> AnalysisSummary:
    if not analyses:
        return AnalysisSummary()

    frames_processed = len(analyses)
    total_workers = sum(analysis.worker_count for analysis in analyses)
    total_active_workers = sum(analysis.active_workers for analysis in analyses)
    safety_violations = sum(analysis.safety_violations for analysis in analyses)

    avg_utilization_pct = sum(analysis.utilization_pct for analysis in analyses) / frames_processed
    avg_progress_pct = sum(analysis.progress_pct for analysis in analyses) / frames_processed

    return AnalysisSummary(
        frames_processed=frames_processed,
        total_workers=total_workers,
        total_active_workers=total_active_workers,
        avg_utilization_pct=round(avg_utilization_pct, 1),
        avg_progress_pct=round(avg_progress_pct, 1),
        safety_violations=safety_violations,
    )


def build_report_insights(analyses: List[FrameAnalysis], summary: AnalysisSummary) -> List[ReportInsight]:
    insights: List[ReportInsight] = []

    if summary.avg_utilization_pct < 60:
        insights.append(
            ReportInsight(
                title="Utilization Risk",
                detail="Average utilization is below 60%. Rebalance crew allocation between camera zones.",
            )
        )
    else:
        insights.append(
            ReportInsight(
                title="Utilization Healthy",
                detail="Utilization trend is acceptable. Maintain current staffing cadence.",
            )
        )

    if summary.safety_violations > 0:
        insights.append(
            ReportInsight(
                title="Safety Action Needed",
                detail=f"{summary.safety_violations} safety events observed. Trigger toolbox talk and zone supervisor checks.",
            )
        )

    if analyses:
        weakest = min(analyses, key=lambda analysis: analysis.progress_pct)
        insights.append(
            ReportInsight(
                title="Lowest Progress Camera",
                detail=f"{weakest.camera_id} is at {weakest.progress_pct:.1f}% progress. Prioritize this zone in next shift.",
            )
        )

    insights.append(
        ReportInsight(
            title="Privacy Guardrail",
            detail="Metrics are team-level only. No face recognition, no individual ranking, no automatic payroll actions.",
        )
    )

    return insights


def build_portfolio_analytics(
    frames: List[CameraFrame],
    analyses: List[FrameAnalysis],
) -> PortfolioResponse:
    grouped = _group_by_camera(frames, analyses)
    cards: List[CameraPortfolioCard] = []

    for camera_id, entries in grouped.items():
        frame_list = [entry[0] for entry in entries]
        analysis_list = [entry[1] for entry in entries]

        site_area = frame_list[-1].site_area if frame_list else "general"
        avg_util = sum(item.utilization_pct for item in analysis_list) / len(analysis_list)
        avg_progress = sum(item.progress_pct for item in analysis_list) / len(analysis_list)
        total_safety = sum(item.safety_violations for item in analysis_list)
        avg_safety = total_safety / len(analysis_list)
        safety_score = max(0.0, 100.0 - (avg_safety * 35.0))

        performance_score = (
            (avg_progress * 0.50)
            + (avg_util * 0.35)
            + (safety_score * 0.15)
        )

        trend = _trend_direction(
            analysis_list[0].progress_pct + analysis_list[0].utilization_pct,
            analysis_list[-1].progress_pct + analysis_list[-1].utilization_pct,
            threshold=8.0,
        )

        if performance_score >= 75:
            status = "excellent"
        elif performance_score >= 55:
            status = "watch"
        else:
            status = "critical"

        cards.append(
            CameraPortfolioCard(
                camera_id=camera_id,
                site_area=site_area,
                utilization_pct=round(avg_util, 1),
                progress_pct=round(avg_progress, 1),
                safety_violations=total_safety,
                performance_score=round(performance_score, 1),
                trend=trend,
                status=status,
            )
        )

    cards.sort(key=lambda item: item.performance_score, reverse=True)
    fleet_score = sum(item.performance_score for item in cards) / len(cards) if cards else 0.0

    return PortfolioResponse(
        generated_at=_utc_now(),
        fleet_score=round(fleet_score, 1),
        cameras=cards,
    )


def build_camera_health(
    frames: List[CameraFrame],
    analyses: List[FrameAnalysis],
) -> CameraHealthResponse:
    grouped = _group_by_camera(frames, analyses)
    health_rows: List[CameraHealthItem] = []

    if not frames:
        return CameraHealthResponse(generated_at=_utc_now(), online=0, delayed=0, offline=0, cameras=[])

    latest_timestamp = max(frame.timestamp for frame in frames)

    online = 0
    delayed = 0
    offline = 0

    for camera_id, entries in grouped.items():
        frame_list = [entry[0] for entry in entries]
        analysis_list = [entry[1] for entry in entries]
        last_frame = frame_list[-1]

        lag_seconds = max(0, int((latest_timestamp - last_frame.timestamp).total_seconds()))
        avg_worker_density = sum(item.worker_count for item in analysis_list) / len(analysis_list)

        if lag_seconds <= 90:
            status = "online"
            uptime_score = 100.0
            online += 1
        elif lag_seconds <= 300:
            status = "delayed"
            uptime_score = 70.0
            delayed += 1
        else:
            status = "offline"
            uptime_score = 35.0
            offline += 1

        reliability_score = min(100.0, (uptime_score * 0.6) + ((avg_worker_density * 12.0 + 20.0) * 0.4))

        health_rows.append(
            CameraHealthItem(
                camera_id=camera_id,
                site_area=last_frame.site_area,
                status=status,
                last_seen_seconds=lag_seconds,
                detection_density=round(avg_worker_density, 2),
                reliability_score=round(reliability_score, 1),
            )
        )

    health_rows.sort(key=lambda item: (item.status, item.last_seen_seconds))

    return CameraHealthResponse(
        generated_at=_utc_now(),
        online=online,
        delayed=delayed,
        offline=offline,
        cameras=health_rows,
    )


def build_event_feed(analyses: List[FrameAnalysis], limit: int = 50) -> EventFeedResponse:
    events: List[EventFeedItem] = []

    for analysis in analyses:
        if analysis.safety_violations > 0:
            events.append(
                EventFeedItem(
                    timestamp=analysis.timestamp,
                    camera_id=analysis.camera_id,
                    severity="critical",
                    event_type="safety",
                    message=f"{analysis.safety_violations} safety violations detected",
                    action="Dispatch supervisor and enforce PPE/restricted-zone protocol.",
                )
            )

        if analysis.utilization_pct < 50:
            events.append(
                EventFeedItem(
                    timestamp=analysis.timestamp,
                    camera_id=analysis.camera_id,
                    severity="warn",
                    event_type="productivity",
                    message=f"Low utilization at {analysis.utilization_pct:.1f}%",
                    action="Rebalance crews or unblock workfront dependencies.",
                )
            )

        if analysis.progress_pct < 45:
            events.append(
                EventFeedItem(
                    timestamp=analysis.timestamp,
                    camera_id=analysis.camera_id,
                    severity="warn",
                    event_type="progress",
                    message=f"Progress lag at {analysis.progress_pct:.1f}%",
                    action="Review daily plan and add short-interval recovery actions.",
                )
            )

        if (
            analysis.safety_violations == 0
            and analysis.utilization_pct >= 70
            and analysis.progress_pct >= 65
        ):
            events.append(
                EventFeedItem(
                    timestamp=analysis.timestamp,
                    camera_id=analysis.camera_id,
                    severity="info",
                    event_type="milestone",
                    message="Strong performance window observed",
                    action="Capture this crew setup as repeatable best practice.",
                )
            )

    events.sort(key=lambda item: item.timestamp, reverse=True)
    return EventFeedResponse(generated_at=_utc_now(), events=events[:limit])


def build_trend_response(
    frames: List[CameraFrame],
    analyses: List[FrameAnalysis],
) -> TrendResponse:
    grouped = _group_by_camera(frames, analyses)
    camera_trends: List[CameraTrend] = []

    for camera_id, entries in grouped.items():
        frame_list = [entry[0] for entry in entries]
        analysis_list = [entry[1] for entry in entries]

        points = [
            TrendPoint(
                timestamp=analysis.timestamp,
                utilization_pct=analysis.utilization_pct,
                progress_pct=analysis.progress_pct,
                safety_violations=analysis.safety_violations,
            )
            for analysis in analysis_list
        ]

        direction = _trend_direction(
            analysis_list[0].progress_pct + analysis_list[0].utilization_pct,
            analysis_list[-1].progress_pct + analysis_list[-1].utilization_pct,
            threshold=8.0,
        )

        camera_trends.append(
            CameraTrend(
                camera_id=camera_id,
                site_area=frame_list[-1].site_area,
                direction=direction,
                points=points,
            )
        )

    camera_trends.sort(key=lambda item: item.camera_id)
    return TrendResponse(generated_at=_utc_now(), cameras=camera_trends)
