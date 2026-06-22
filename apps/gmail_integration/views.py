import logging
import traceback

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db.models import Count
from dotenv import load_dotenv
import os
from pathlib import Path

from .gmail_services import (
    connect_mail,
    fetch_email_ids,
    read_email,
    save_email,
    get_last_sync_date,
)
from .models import GmailEmail
from apps.ai_agents.services.profile_matching_agent import ProfileMatchingAgent
from apps.ai_agents.models import Job, JobMatchResult
from apps.ai_agents.services.analyzer import EmailAnalyzer
from apps.ai_agents.services.job_saver import JobSaver
from apps.ai_agents.services.gemini_throttle import wait_for_slot
from apps.ai_agents.services import clarification_service
from apps.ai_agents.services.voice_agent import (
    dispatch_job_calls,
    schedule_job_calls,
    MATCH_THRESHOLD,
)

# Load .env from project root before reading any credentials
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

analyzer = EmailAnalyzer(api_key=GEMINI_API_KEY)
saver = JobSaver()


def _sync_new_emails():
    since_date = get_last_sync_date()
    mail = connect_mail()
    email_ids = fetch_email_ids(mail, since_date=since_date)

    existing_ids = set(GmailEmail.objects.values_list("gmail_id", flat=True))

    saved_count = 0
    skipped_count = 0

    for e_id in email_ids:
        data = read_email(mail, e_id)
        if data["gmail_id"] in existing_ids:
            skipped_count += 1
            continue
        if save_email(data):
            saved_count += 1

    logger.info(
        "Email sync — fetched=%d saved=%d skipped=%d since=%s",
        len(email_ids), saved_count, skipped_count, since_date,
    )
    return {
        "total_fetched": len(email_ids),
        "saved": saved_count,
        "skipped_duplicates": skipped_count,
        "since_date": since_date.isoformat() if since_date else None,
    }


def _process_unprocessed_emails():
    emails = GmailEmail.objects.filter(processed=False)
    processed_count = 0
    skipped_count = 0
    errors = []
    skipped_details = []

    for email in emails:
        try:
            wait_for_slot()  # shared RPM gate — also used by ProfileMatchingAgent
            ai_result = analyzer.analyze(email.body)

            if not ai_result.get("job_title"):
                reason = (
                    ai_result.get("error")
                    or ai_result.get("reason")
                    or ai_result.get("skip_reason")
                    or "AI analysis did not return a job_title for this email "
                       "(either not a job posting, or the Gemini call failed silently)"
                )
                skipped_details.append({
                    "email_id": email.gmail_id,
                    "subject": getattr(email, "subject", None),
                    "reason": reason,
                })
                skipped_count += 1
                logger.warning("Skipped email %s — %s", email.gmail_id, reason)
                # Deliberately NOT marking processed=True here, so this email
                # gets retried on the next run instead of being skipped forever.
                continue

            saver.save(ai_result)
            email.processed = True
            email.save(update_fields=["processed"])
            processed_count += 1
        except Exception as e:
            errors.append({"email_id": email.gmail_id, "error": str(e)})
            logger.exception("Failed to process email %s", email.gmail_id)
            # Also not marked processed — exceptions should always be retried.

    logger.info(
        "Email processing — processed=%d skipped=%d errors=%d",
        processed_count, skipped_count, len(errors),
    )
    return {
        "processed": processed_count,
        "skipped": skipped_count,
        "skipped_details": skipped_details,
        "errors": errors,
        "remaining_unprocessed": GmailEmail.objects.filter(processed=False).count(),
    }


def _match_new_jobs():
    already_matched_ids = JobMatchResult.objects.values_list("job_id", flat=True)
    jobs = list(Job.objects.exclude(id__in=already_matched_ids).values())

    if not jobs:
        logger.info("No new jobs to match")
        return []

    agent = ProfileMatchingAgent(api_key=GEMINI_API_KEY)
    results = agent.match_batch(jobs)
    logger.info("Matched %d new jobs", len(results))

    queued = clarification_service.queue_low_completeness_jobs(results)
    if queued:
        logger.info("Queued %d job(s) for Telegram clarification", queued)

    return results


def _schedule_and_dispatch_calls():
    user_phone = os.getenv("USER_PHONE_NUMBER")
    pending = JobMatchResult.objects.filter(call_triggered=False).select_related("job")

    schedule_summary = schedule_job_calls(pending)
    dispatch_summary = dispatch_job_calls(pending, user_phone, only_due=True)

    return {
        "match_threshold": MATCH_THRESHOLD,
        "schedule": schedule_summary,
        "dispatch": dispatch_summary,
    }


# Individual endpoints (kept for manual/debug use)

@require_GET
def sync_emails(request):
    try:
        result = _sync_new_emails()

        breakdown = GmailEmail.objects.values("sender").annotate(
            total=Count("id")
        ).order_by("-total")

        return JsonResponse({
            "status": "success",
            **result,
            "total_in_db": GmailEmail.objects.count(),
            "breakdown_by_sender": list(breakdown),
        })
    except Exception as e:
        logger.exception("sync_emails failed")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_GET
def process_emails_with_ai(request):
    try:
        result = _process_unprocessed_emails()
        if result["errors"]:
            return JsonResponse({"status": "partial_error", **result}, status=500)
        return JsonResponse({"status": "success", **result})
    except Exception as e:
        logger.exception("process_emails_with_ai failed")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_GET
def list_emails(request):
    emails = GmailEmail.objects.all().order_by("-created_at").values(
        "gmail_id", "sender", "subject", "body", "created_at"
    )
    return JsonResponse({"status": "success", "emails": list(emails)})


@require_GET
def list_jobs(request):
    jobs = Job.objects.all().order_by("-created_at").values(
        "id", "job_title", "job_type", "summary", "project_description",
        "skills", "technologies", "budget", "duration", "experience_required",
        "company_name", "contact_email", "deadline", "created_at",
    )
    return JsonResponse({
        "status": "success",
        "count": Job.objects.count(),
        "jobs": list(jobs),
    })


def get_agent() -> ProfileMatchingAgent:
    return ProfileMatchingAgent(api_key=GEMINI_API_KEY)


@require_GET
def match_all_jobs(request):
    """
    Match new jobs AND always attempt call scheduling/dispatch afterward.
    (Previously returned early when all jobs were already matched, skipping Vapi entirely.)
    """
    try:
        results = _match_new_jobs()

        call_summary = _schedule_and_dispatch_calls()

        return JsonResponse({
            "status": "success",
            "count": len(results),
            "results": results,
            "calls": call_summary,
        })
    except Exception as e:
        traceback.print_exc()
        logger.exception("match_all_jobs failed")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@require_GET
def dispatch_scheduled_calls(request):
    try:
        user_phone = os.getenv("USER_PHONE_NUMBER")
        pending = JobMatchResult.objects.filter(
            call_triggered=False,
            scheduled_call_at__isnull=False,
        ).select_related("job")

        dispatch_summary = dispatch_job_calls(pending, user_phone, only_due=True)

        return JsonResponse({"status": "success", "dispatch": dispatch_summary})
    except Exception as e:
        logger.exception("dispatch_scheduled_calls failed")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@require_GET
def run_daily_batch(request):
    """
    Single daily batch job — runs the full pipeline in order:
      1. Fetch all new emails since last run
      2. Analyze with Gemini → save jobs
      3. Match against profile
      4. Schedule Vapi calls (score > 80) across 2 PM → 2 AM window
      5. Dispatch any calls already due

    Schedule this endpoint once per day via cron / Task Scheduler:
      GET http://localhost:8000/run-daily-batch/

    During the call window, also schedule periodic hits to:
      GET http://localhost:8000/dispatch-scheduled-calls/
    """
    try:
        logger.info("=== Daily batch started ===")

        sync_result = _sync_new_emails()
        process_result = _process_unprocessed_emails()
        match_results = _match_new_jobs()
        call_summary = _schedule_and_dispatch_calls()

        logger.info("=== Daily batch completed ===")

        return JsonResponse({
            "status": "success",
            "sync": sync_result,
            "process": process_result,
            "match": {
                "count": len(match_results),
                "results": match_results,
            },
            "calls": call_summary,
        })
    except Exception as e:
        traceback.print_exc()
        logger.exception("run_daily_batch failed")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@require_GET
def list_match_results(request):
    results = JobMatchResult.objects.all().order_by("-created_at").values(
        "id", "job_id", "job__job_title", "match_score", "decision",
        "breakdown", "strengths", "missing_skills", "risk_factors",
        "recommendation_reason", "suggested_improvements",
        "call_triggered", "vapi_call_id", "scheduled_call_at", "created_at",
    )
    return JsonResponse({
        "status": "success",
        "count": JobMatchResult.objects.count(),
        "results": list(results),
    })