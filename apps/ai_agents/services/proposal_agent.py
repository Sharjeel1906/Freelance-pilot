import logging
import time

import google.generativeai as genai

from .prompts import PROPOSAL_WRITER_PROMPT
from .profile_matching_agent import DEFAULT_PROFILE
from .gemini_throttle import wait_for_slot

logger = logging.getLogger(__name__)


class ProposalWriterAgent:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", profile: dict = None):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
        self.profile = profile or DEFAULT_PROFILE
        self.generation_config = {"temperature": 0.4}

    def build_profile_text(self) -> str:
        p = self.profile
        identity = p.get("identity", {})
        expertise = p.get("core_expertise", {})

        all_skills = []
        for skill_list in expertise.values():
            all_skills.extend(skill_list)

        projects_str = "\n".join(
            f"  - {proj['name']}: {proj.get('engineering_value', '')}"
            for proj in p.get("projects", [])
        )

        return f"""
    CANDIDATE PROFILE:
    Name             : {identity.get('name', 'N/A')}
    Title            : {identity.get('role', 'N/A')}
    Experience Level : {identity.get('level', 'N/A')}
    Skills           : {', '.join(all_skills)}
    Availability     : {p.get('availability', 'N/A')}

    Projects:
    {projects_str}

    Portfolio : {p.get('portfolio', 'N/A')}
    LinkedIn  : {p.get('linkedin', 'N/A')}
    """.strip()

    def build_job_text(self, job: dict) -> str:
        skills = job.get("skills") or []
        technologies = job.get("technologies") or []

        if isinstance(skills, str):
            skills = [skills]
        if isinstance(technologies, str):
            technologies = [technologies]

        return f"""
JOB POSTING (full description provided directly by the candidate):
Title              : {job.get('job_title', 'N/A')}
Type               : {job.get('job_type', 'N/A')}
Summary            : {job.get('summary', 'N/A')}
Full Description   : {job.get('project_description', 'N/A')}
Required Skills    : {', '.join(skills) or 'Not specified'}
Technologies       : {', '.join(technologies) or 'Not specified'}
Experience Required: {job.get('experience_required') or 'Not specified'}
Budget             : {job.get('budget') or 'Not specified'}
Duration           : {job.get('duration') or 'Not specified'}
Company            : {job.get('company_name') or 'Not specified'}
""".strip()

    def build_input(self, job: dict) -> str:
        return f"{PROPOSAL_WRITER_PROMPT}\n\n{self.build_profile_text()}\n\n{self.build_job_text(job)}"

    def write_proposal(self, job: dict, max_retries: int = 2) -> str:
        final_input = self.build_input(job)
        last_error = None

        for attempt in range(max_retries):
            try:
                wait_for_slot()
                response = self.model.generate_content(
                    final_input,
                    generation_config=self.generation_config,
                )
                return response.text.strip()

            except Exception as e:
                last_error = e
                error_str = str(e)

                if "PerDay" in error_str:
                    logger.error("Daily Gemini quota exhausted while writing proposal — stopping.")
                    break

                is_transient = any(code in error_str for code in ("429", "500", "503"))
                if is_transient and attempt < max_retries - 1:
                    logger.warning(
                        f"Transient Gemini error writing proposal, "
                        f"retrying (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(5)
                    continue
                break

        logger.error(f"Failed to generate proposal: {last_error}")
        return (
            "Sorry — I couldn't generate the proposal due to an error "
            f"({last_error}). The full description has been saved, so this can be retried later."
        )
