import json
import re
import time
import logging
import google.generativeai as genai
from .prompts import PROFILE_MATCHING_PROMPT
from .match_saver import MatchResultSaver
from .gemini_throttle import wait_for_slot

logger = logging.getLogger(__name__)
DEFAULT_PROFILE = {
    "identity": {
        "name": "Sharjeel Ahmed",
        "role": "Full-Stack & Digital Marketing Developer (Flutter • Django • GTM • Meta Pixel • AI)",
        "level": "Fresher (0–1 year)",
        "focus": [
            "Full-stack application development",
            "AI-powered automation systems",
            "Digital marketing & analytics setup",
            "Google Tag Manager and tracking pixel configuration",
            "Backend architecture & APIs",
        ]
    },

    "core_expertise": {
        "frontend": ["Flutter", "Dart", "UI/UX implementation", "Cross-platform apps"],
        "backend": ["Django", "REST APIs", "Django Channels", "Authentication systems"],
        "ai_integration": ["LLMs (Gemini/OpenAI)", "Prompt engineering", "AI agents", "Text extraction pipelines"],
        "digital_marketing": [
            "Google Tag Manager (GTM)",
            "Meta Pixel Installation",
            "Meta Business Manager",
            "Microsoft Clarity Analytics",
            "Web Analytics",
            "Conversion tracking setup",
            "Tag deployment & event tracking",
        ],
        "data_handling": ["IMAP email parsing", "SQLite", "structured data modeling", "Analytics data collection"],
        "system_design": ["Event-driven workflows", "Automation pipelines", "Real-time systems"],
        "tools": ["Git", "Postman", "Vercel", "Firebase", "Google Tag Manager", "Meta Business Manager", "Clarity"]
    },

    "engineering_profile": {
        "strengths": [
            "Builds full-stack systems independently from scratch",
            "Sets up and configures web analytics and marketing tracking tools end-to-end",
            "Experienced with GTM access, Meta Pixel installation via Meta Business Manager, and Clarity admin setup",
            "Transforms unstructured data (emails) into structured systems using AI",
            "Integrates backend + AI workflows into production-like pipelines",
            "Focuses on automation, analytics, and productivity systems",
        ],

        "thinking_style": (
            "Systems-oriented developer who thinks in pipelines: "
            "input → processing (AI/logic/analytics) → structured output → measurable results."
        )
    },

    "projects": [
        {
            "name": "Digital Marketing & Analytics Setup — momagroupllc",
            "type": "Digital marketing & web analytics project",

            "architecture": {
                "tracking": "Google Tag Manager (GTM) container management",
                "advertising": "Meta Pixel via Meta Business Manager",
                "analytics": "Microsoft Clarity admin & session analytics",
            },

            "features": [
                "Gained access to and configured Google Tag Manager",
                "Accepted Meta Business Manager invitation and installed Meta Pixel",
                "Accepted admin invitation to Clarity account for analytics management",
                "End-to-end tracking setup for client digital properties",
            ],

            "engineering_value": (
                "Direct hands-on experience with the exact stack required for digital marketing "
                "and analytics setup projects: GTM, Meta Pixel, Meta Business Manager, and Clarity."
            )
        },

        {
            "name": "dEVPartner — Real-Time Developer Collaboration System",
            "type": "Full-stack real-time platform",

            "architecture": {
                "frontend": "Flutter mobile application",
                "backend": "Django REST + Django Channels",
                "communication": "WebSocket-based real-time messaging",
                "auth": "JWT-based authentication system"
            },

            "features": [
                "Real-time chat system (WebSockets)",
                "User authentication & session management",
                "Team-based collaboration structure",
                "Cross-platform mobile UI",
                "Backend API integration"
            ],

            "engineering_value": (
                "Demonstrates ability to design real-time systems, manage stateful connections, "
                "and integrate mobile frontend with scalable backend architecture."
            )
        },

        {
            "name": "Freelance Pilot — AI Job Intelligence Engine",
            "type": "AI + backend automation system",

            "architecture": {
                "data_source": "Gmail (IMAP email ingestion)",
                "processing_layer": "Python backend + AI agents",
                "ai_layer": "Gemini/OpenAI-based text understanding",
                "storage": "SQLite structured job database",
                "output": "Parsed job listings + profile matching results"
            },

            "pipeline": [
                "Fetch emails from Gmail via IMAP",
                "Extract raw job descriptions",
                "Clean + normalize text",
                "Send to AI agent for structuring",
                "Convert into structured job object",
                "Match against user profile",
                "Store + mark processed emails"
            ],

            "features": [
                "Automated job extraction from emails",
                "AI-based job structuring",
                "Profile-job matching logic",
                "Duplicate handling",
                "End-to-end automation pipeline"
            ],

            "engineering_value": (
                "Full data pipeline combining email ingestion, NLP processing, "
                "AI transformation, and structured storage."
            )
        },

        {
            "name": "3D Portfolio System",
            "type": "Frontend experience engineering",

            "stack": ["Next.js", "Three.js", "Vercel"],

            "features": [
                "3D interactive UI",
                "Smooth animations and transitions",
                "Project showcase system",
                "Responsive design optimized for recruiters"
            ],

            "engineering_value": (
                "Ability to build non-traditional UI systems and focus on user engagement "
                "through interactive 3D web experiences."
            )
        }
    ],

    "system_design_level": {
        "understanding": [
            "Event-driven architectures (WebSockets, email triggers)",
            "Pipeline-based processing systems",
            "AI-assisted backend workflows",
            "Analytics & tracking instrumentation (GTM, pixels, Clarity)",
            "Client-server separation (Flutter ↔ Django)"
        ],

        "current_level": "Junior system builder with production-oriented mindset"
    },

    "career_positioning": {
        "title_variation_suggestion": [
            "Full-Stack Developer",
            "Digital Marketing & Analytics Developer",
            "AI Automation Developer",
            "Backend Engineer (Django + AI)",
        ],

        "best_fit_roles": [
            "Digital marketing & analytics setup freelancer",
            "Full-stack developer (startup)",
            "AI integration developer",
            "Automation engineer",
            "Junior software engineer",
        ]
    },

    "portfolio": "https://sharjeelahmed3d.vercel.app/",
    "linkedin": "https://www.linkedin.com/in/sharjeel-ahmed-7b2300380",

    "highlights": [
        "Configured GTM, Meta Pixel, Meta Business Manager, and Clarity for client analytics",
        "Built AI-powered job extraction system from Gmail",
        "Designed real-time chat system using WebSockets",
        "Created full-stack Flutter + Django applications",
        "Built end-to-end automation pipelines using AI",
    ],

    "availability": "Open to Full-time / Freelance / Internship roles"
}

class ProfileMatchingAgent:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", profile: dict = None):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
        self.profile = profile or DEFAULT_PROFILE
        self.saver = MatchResultSaver()

        self.generation_config = {
            "temperature": 0.2,
            "response_mime_type": "application/json"
        }

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
JOB POSTING:
Title              : {job.get('job_title', 'N/A')}
Type               : {job.get('job_type', 'N/A')}
Summary            : {job.get('summary', 'N/A')}
Description        : {job.get('project_description', 'N/A')}
Required Skills    : {', '.join(skills) or 'Not specified'}
Technologies       : {', '.join(technologies) or 'Not specified'}
Experience Required: {job.get('experience_required') or 'Not specified'}
Budget             : {job.get('budget') or 'Not specified'}
Duration           : {job.get('duration') or 'Not specified'}
Company            : {job.get('company_name') or 'Not specified'}
""".strip()

    def build_input(self, job: dict) -> str:
        profile_text = self.build_profile_text()
        job_text = self.build_job_text(job)
        return f"{PROFILE_MATCHING_PROMPT}\n\n{profile_text}\n\n{job_text}"

    def _extract_retry_delay(self, error_str: str) -> float | None:
        m = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", error_str)
        if m:
            return float(m.group(1)) + 1  # small buffer
        m = re.search(r"retry in ([\d.]+)s", error_str)
        if m:
            return float(m.group(1)) + 1
        return None

    def match(self, job: dict, max_retries: int = 2) -> dict:
        final_input = self.build_input(job)
        last_error = None
        for attempt in range(max_retries):
            try:
                wait_for_slot()
                response = self.model.generate_content(
                    final_input,
                    generation_config=self.generation_config
                )

                result = self._safe_json_parse(response.text)
                result["job_id"] = job.get("id")
                result["job_title"] = job.get("job_title")
                self.saver.save(result)
                return result

            except Exception as e:
                last_error = e
                error_str = str(e)

                if "PerDay" in error_str:
                    logger.error(
                        f"Gemini DAILY quota exhausted (job_id={job.get('id')}) — "
                        f"no retry will help until it resets. Stopping immediately."
                    )
                    break

                is_transient = any(code in error_str for code in ("429", "500", "503"))
                if is_transient and attempt < max_retries - 1:
                    wait_time = self._extract_retry_delay(error_str) or 2
                    logger.warning(
                        f"Transient Gemini error for job_id={job.get('id')}, "
                        f"retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    continue

                break

        logger.error(
            f"Match failed for job_id={job.get('id')} after {max_retries} attempt(s): {last_error}"
        )
        return {
            "error": str(last_error),
            "job_id": job.get("id"),
            "job_title": job.get("job_title"),
            "match_score": None,
            "decision": None,
            "match_failed": True,
            "data_completeness": {
                "profile_completeness": None,
                "job_completeness": None,
            },
            "breakdown": {
                "skill_match": 0,
                "portfolio_match": 0,
                "experience_match": 0,
                "tech_stack_match": 0,
                "domain_relevance": 0,
            },
            "strengths": [],
            "missing_skills": [],
            "risk_factors": [],
            "recommendation_reason": None,
            "suggested_improvements": [],
        }

    def match_batch(self, jobs: list) -> list:
        results = []
        for job in jobs:
            results.append(self.match(job))
        results.sort(key=lambda x: x.get("match_score") or 0, reverse=True)
        return results

    def _safe_json_parse(self, content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError("Invalid JSON from Gemini")