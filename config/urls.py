from django.contrib import admin
from django.urls import path
from apps.gmail_integration.views import (
    sync_emails,
    list_jobs,
    process_emails_with_ai,
    match_all_jobs,
    list_match_results,
    list_emails,
    run_daily_batch,
    dispatch_scheduled_calls,
)

urlpatterns = [
    path("sync-emails/", sync_emails),
    path("process-emails/", process_emails_with_ai),
    path("emails/", list_emails),
    path("jobs/", list_jobs),
    path("match-all-jobs/", match_all_jobs, name="match_all_jobs"),
    path("match-results/", list_match_results, name="list_match_results"),
    # Daily batch — single cron trigger for the full pipeline
    path("run-daily-batch/", run_daily_batch, name="run_daily_batch"),
    # Fires due Vapi calls during the 2 PM → 2 AM window (cron every ~10 min)
    path("dispatch-scheduled-calls/", dispatch_scheduled_calls, name="dispatch_scheduled_calls"),
]
