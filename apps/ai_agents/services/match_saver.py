from ..models import JobMatchResult

class MatchResultSaver:

    def save(self, data: dict) -> JobMatchResult:
        return JobMatchResult.objects.create(
            job_id=data.get("job_id"),
            # removed job_title — now accessed via job.job_title (ForeignKey)
            match_score=data.get("match_score", 0),
            decision=data.get("decision", ""),
            breakdown=data.get("breakdown", {}),
            strengths=data.get("strengths", []),
            missing_skills=data.get("missing_skills", []),
            risk_factors=data.get("risk_factors", []),
            suggested_improvements=data.get("suggested_improvements", []),
            recommendation_reason=data.get("recommendation_reason"),
        )