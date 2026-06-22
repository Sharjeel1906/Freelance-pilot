import logging

from django.utils import timezone

from apps.ai_agents.models import Job, PendingClarification

logger = logging.getLogger(__name__)


def queue_low_completeness_jobs(match_results: list) -> int:
    queued = 0
    for result in match_results:
        job_id = result.get("job_id")
        if not job_id:
            continue

        completeness = (
            (result.get("data_completeness") or {}).get("job_completeness") or ""
        ).strip().upper()

        if completeness != "LOW":
            continue

        if PendingClarification.objects.filter(job_id=job_id).exists():
            continue  # already queued, sent, or resolved previously

        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            continue

        PendingClarification.objects.create(job=job)
        queued += 1
        logger.info("Queued clarification for job_id=%s (%s)", job_id, job.job_title)

    return queued


def get_next_waiting():
    return (
        PendingClarification.objects.filter(status=PendingClarification.STATUS_WAITING)
        .order_by("created_at")
        .first()
    )


def get_active_sent():
    return (
        PendingClarification.objects.filter(status=PendingClarification.STATUS_SENT)
        .order_by("sent_at")
        .first()
    )


def get_active_described():
    return (
        PendingClarification.objects.filter(status=PendingClarification.STATUS_DESCRIBED)
        .order_by("created_at")
        .first()
    )


def get_active_in_flight():
    return (
        PendingClarification.objects.filter(
            status__in=[PendingClarification.STATUS_SENT, PendingClarification.STATUS_DESCRIBED]
        )
        .order_by("created_at")
        .first()
    )


def mark_sent(pending: PendingClarification, telegram_chat_id: str):
    pending.status = PendingClarification.STATUS_SENT
    pending.telegram_chat_id = telegram_chat_id
    pending.sent_at = timezone.now()
    pending.save(update_fields=["status", "telegram_chat_id", "sent_at"])


def mark_described(pending: PendingClarification, full_description: str):
    pending.full_description = full_description
    pending.status = PendingClarification.STATUS_DESCRIBED
    pending.save(update_fields=["full_description", "status"])


def append_description(pending: PendingClarification, extra_text: str):
    pending.full_description = f"{pending.full_description or ''}\n\n{extra_text}".strip()
    pending.save(update_fields=["full_description"])


def resolve_clarification(pending: PendingClarification, full_description: str, proposal_text: str):
    pending.full_description = full_description
    pending.proposal_text = proposal_text
    pending.status = PendingClarification.STATUS_RESOLVED
    pending.resolved_at = timezone.now()
    pending.save(update_fields=["full_description", "proposal_text", "status", "resolved_at"])