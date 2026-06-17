import logging
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import requests
from dotenv import load_dotenv
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")

MATCH_THRESHOLD = 80

CALL_WINDOW_START_HOUR = 14
CALL_WINDOW_END_HOUR = 2


def _vapi_config():
    return {
        "api_key": os.getenv("VAPI_API_KEY"),
        "assistant_id": os.getenv("VAPI_ASSISTANT_ID"),
        "phone_number_id": os.getenv("VAPI_PHONE_NUMBER_ID"),
    }


def _call_timezone():
    return ZoneInfo(os.getenv("BATCH_CALL_TIMEZONE", "Asia/Karachi"))


def _call_window_bounds(now: datetime) -> tuple[datetime, datetime]:
    """
    Return (start, end) for the current 2 PM → 2 AM call window.
    If now is between midnight and 2 AM, the window started yesterday at 2 PM.
    """
    tz = _call_timezone()
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    today = now.date()

    if now.hour < CALL_WINDOW_END_HOUR:
        # Still inside last night's window (midnight → 2 AM)
        start = datetime.combine(today - timedelta(days=1), time(CALL_WINDOW_START_HOUR, 0), tzinfo=tz)
        end = datetime.combine(today, time(CALL_WINDOW_END_HOUR, 0), tzinfo=tz)
    else:
        # Window starts today (or later today) at 2 PM, ends tomorrow at 2 AM
        start = datetime.combine(today, time(CALL_WINDOW_START_HOUR, 0), tzinfo=tz)
        end = datetime.combine(today + timedelta(days=1), time(CALL_WINDOW_END_HOUR, 0), tzinfo=tz)

    return start, end


def call_user(job: dict, user_phone: str) -> dict:
    """Place an immediate outbound Vapi call."""
    config = _vapi_config()
    missing = [k for k, v in config.items() if not v]
    if missing:
        raise ValueError(f"Missing Vapi env vars: {', '.join(missing)}")
    if not user_phone:
        raise ValueError("USER_PHONE_NUMBER is not set")

    url = "https://api.vapi.ai/call"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "assistantId": config["assistant_id"],
        "phoneNumberId": config["phone_number_id"],
        "customer": {"number": user_phone},
        "metadata": {
            "job_title": job.get("job_title"),
            "summary": job.get("summary"),
            "project_description": job.get("project_description"),
            "budget": job.get("budget"),
            "skills": job.get("skills"),
        },
    }

    logger.info(
        "Vapi call → job='%s' phone='%s' assistant=%s",
        job.get("job_title"),
        user_phone[:4] + "****",  # redact most of phone number
        config["assistant_id"],
    )
    logger.debug("Vapi payload metadata: %s", payload["metadata"])

    response = requests.post(url, json=payload, headers=headers, timeout=30)

    if not response.ok:
        logger.error(
            "Vapi HTTP %s for job '%s': %s",
            response.status_code,
            job.get("job_title"),
            response.text,
        )
        response.raise_for_status()

    result = response.json()
    logger.info("Vapi call placed — id=%s job='%s'", result.get("id"), job.get("job_title"))
    return result


def schedule_job_calls(job_matches) -> dict:
    qualifying = [
        m for m in job_matches
        if not m.call_triggered and m.match_score > MATCH_THRESHOLD
    ]

    if not qualifying:
        logger.info("No matches above %s — nothing to schedule", MATCH_THRESHOLD)
        return {"scheduled": 0, "qualifying": 0, "interval_minutes": None, "window": None}

    now = datetime.now(_call_timezone())
    start, end = _call_window_bounds(now)
    window_seconds = (end - start).total_seconds()
    interval_seconds = window_seconds / len(qualifying)

    schedule = []
    for i, match in enumerate(qualifying):
        scheduled_at = start + timedelta(seconds=interval_seconds * i)
        match.scheduled_call_at = scheduled_at
        match.save(update_fields=["scheduled_call_at"])
        schedule.append({
            "match_id": match.id,
            "job_title": match.job.job_title,
            "match_score": match.match_score,
            "scheduled_call_at": scheduled_at.isoformat(),
        })
        logger.info(
            "Scheduled call #%d — job='%s' score=%.1f at %s",
            i + 1,
            match.job.job_title,
            match.match_score,
            scheduled_at.isoformat(),
        )

    return {
        "scheduled": len(schedule),
        "qualifying": len(qualifying),
        "interval_minutes": round(interval_seconds / 60, 1),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "calls": schedule,
    }


def dispatch_job_calls(job_matches, user_phone: str, only_due: bool = False) -> dict:
    """
    Place Vapi calls for qualifying matches.

    only_due=False  → call immediately (legacy / manual trigger)
    only_due=True   → only call matches whose scheduled_call_at <= now
    """
    summary = {
        "considered": 0,
        "skipped_already_triggered": 0,
        "skipped_below_threshold": 0,
        "skipped_not_due": 0,
        "dispatched": 0,
        "failed": 0,
        "calls": [],
        "errors": [],
    }

    now = datetime.now(_call_timezone())

    for match in job_matches:
        summary["considered"] += 1

        if match.call_triggered:
            summary["skipped_already_triggered"] += 1
            continue

        if match.match_score <= MATCH_THRESHOLD:
            summary["skipped_below_threshold"] += 1
            logger.debug(
                "Skip job '%s' — score %.1f <= %d",
                match.job.job_title,
                match.match_score,
                MATCH_THRESHOLD,
            )
            continue

        if only_due:
            if not match.scheduled_call_at:
                summary["skipped_not_due"] += 1
                logger.debug("Skip job '%s' — no scheduled_call_at set", match.job.job_title)
                continue
            scheduled = match.scheduled_call_at
            if scheduled.tzinfo is None:
                scheduled = scheduled.replace(tzinfo=_call_timezone())
            if scheduled > now:
                summary["skipped_not_due"] += 1
                logger.debug(
                    "Skip job '%s' — scheduled at %s, now %s",
                    match.job.job_title,
                    scheduled.isoformat(),
                    now.isoformat(),
                )
                continue

        job = match.job
        job_data = {
            "job_title": job.job_title,
            "summary": job.summary,
            "project_description": job.project_description,
            "budget": job.budget,
            "skills": job.skills,
        }

        try:
            response = call_user(job_data, user_phone)
            match.call_triggered = True
            match.vapi_call_id = response.get("id")
            match.save(update_fields=["call_triggered", "vapi_call_id"])
            summary["dispatched"] += 1
            summary["calls"].append({
                "match_id": match.id,
                "job_title": job.job_title,
                "vapi_call_id": response.get("id"),
            })
        except requests.HTTPError as e:
            summary["failed"] += 1
            body = e.response.text if e.response is not None else str(e)
            summary["errors"].append({"job_title": job.job_title, "error": body})
            logger.error("Vapi HTTP error for '%s': %s", job.job_title, body)
        except Exception as e:
            summary["failed"] += 1
            summary["errors"].append({"job_title": job.job_title, "error": str(e)})
            logger.exception("Failed to dispatch call for '%s'", job.job_title)

    logger.info(
        "dispatch_job_calls done — dispatched=%d failed=%d skipped_threshold=%d skipped_not_due=%d",
        summary["dispatched"],
        summary["failed"],
        summary["skipped_below_threshold"],
        summary["skipped_not_due"],
    )
    return summary
