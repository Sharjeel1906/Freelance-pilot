from django.db import models


class Job(models.Model):
    job_title = models.CharField(max_length=255)
    job_type = models.CharField(max_length=100, blank=True, null=True)
    summary = models.TextField()
    project_description = models.TextField()
    skills = models.JSONField(default=list, blank=True)
    technologies = models.JSONField(default=list, blank=True)
    budget = models.CharField(max_length=100, blank=True, null=True)
    duration = models.CharField(max_length=100, blank=True, null=True)
    experience_required = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    company_name = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )
    contact_email = models.EmailField(
        blank=True,
        null=True
    )
    deadline = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.job_title

class JobMatchResult(models.Model):

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name='match_results'
    )
    match_score = models.FloatField()
    decision = models.CharField(max_length=50)
    breakdown = models.JSONField()
    strengths = models.JSONField(default=list)
    missing_skills = models.JSONField(default=list)
    risk_factors = models.JSONField(default=list)
    suggested_improvements = models.JSONField(default=list)
    recommendation_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    call_triggered = models.BooleanField(default=False)
    vapi_call_id = models.CharField(max_length=255, null=True, blank=True)
    # When the Vapi call should fire (set by schedule_job_calls during daily batch)
    scheduled_call_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.job.job_title} - {self.match_score}"