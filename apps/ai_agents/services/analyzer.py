import json
import re
import google.generativeai as genai
from .prompts import SYSTEM_EMAIL_ANALYZER_PROMPT


class EmailAnalyzer:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

        self.generation_config = {
            "temperature": 0.2,
            "response_mime_type": "application/json"
        }

    def clean_email(self, raw_email: str) -> str:
        clean = re.sub(r"<[^>]+>", " ", raw_email)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    def build_input(self, email: str) -> str:
        return f"{SYSTEM_EMAIL_ANALYZER_PROMPT}\n\nEMAIL:\n{email}"

    def analyze(self, raw_email: str) -> dict:

        cleaned_email = self.clean_email(raw_email)
        final_input = self.build_input(cleaned_email)

        try:
            response = self.model.generate_content(
                final_input,
                generation_config=self.generation_config
            )
            return self._safe_json_parse(response.text)

        except Exception as e:
            return {
                "error": str(e),
                "job_title": None,
                "job_type": None,
                "summary": None,
                "project_description": None,
                "skills": [],
                "technologies": [],
                "budget": None,
                "duration": None,
                "experience_required": None,
                "company_name": None,
                "contact_email": None,
                "deadline": None
            }

    def _safe_json_parse(self, content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError("Invalid JSON from Gemini")