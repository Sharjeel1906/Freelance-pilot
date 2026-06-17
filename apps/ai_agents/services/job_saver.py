from ..models import Job


class JobSaver:

    REQUIRED_FIELDS = [
        "job_title",
        "summary",
        "project_description",
    ]

    def validate(self, data: dict):

        if not isinstance(data, dict):
            raise ValueError("AI response must be a dictionary")

        # Ensure required fields exist (even if null)
        for field in self.REQUIRED_FIELDS:
            if field not in data:
                data[field] = None

        return data

    def save(self, data: dict) -> Job:
        data = self.validate(data)
        job = Job.objects.create(
            job_title=data.get("job_title"),
            job_type=data.get("job_type"),
            summary=data.get("summary"),
            project_description=data.get("project_description"),
            skills=data.get("skills", []),
            technologies=data.get("technologies", []),
            budget=data.get("budget"),
            duration=data.get("duration"),
            experience_required=data.get("experience_required"),
            company_name=data.get("company_name"),
            contact_email=data.get("contact_email"),
            deadline=data.get("deadline"),
        )

        return job