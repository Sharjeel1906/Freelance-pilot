import json
import logging
import os
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from dotenv import load_dotenv

from apps.ai_agents.services import telegram_service as tg
from apps.ai_agents.services import clarification_service as cs
from apps.ai_agents.services.proposal_agent import ProposalWriterAgent

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_OFFSET_FILE = _PROJECT_ROOT / ".telegram_offset.json"


class Command(BaseCommand):
    help = "Long-polls Telegram for replies and drives the job-clarification queue."

    def handle(self, *args, **options):
        load_dotenv(_PROJECT_ROOT / ".env")

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not telegram_chat_id:
            self.stderr.write(
                "TELEGRAM_CHAT_ID is not set in .env — message your bot once, "
                "then fetch your chat_id from the getUpdates API and add it to .env."
            )
            return

        proposal_agent = ProposalWriterAgent(api_key=gemini_api_key)
        offset = self._load_offset()

        self.stdout.write(self.style.SUCCESS(
            "Telegram poller started. Waiting for clarification requests and replies..."
        ))

        while True:
            self._send_next_waiting_clarification(telegram_chat_id)

            try:
                updates = tg.get_updates(offset=offset, timeout=30)
            except Exception:
                logger.exception("Failed to poll Telegram updates")
                time.sleep(5)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                self._save_offset(offset)

                message = update.get("message") or {}
                chat_id = str(message.get("chat", {}).get("id", ""))
                text = message.get("text")

                if not text or chat_id != str(telegram_chat_id):
                    continue

                self._handle_reply(text, telegram_chat_id, proposal_agent)

    def _send_next_waiting_clarification(self, telegram_chat_id):
        print("1. Entered")

        active = cs.get_active_in_flight()
        print("2. Active:", active)

        from apps.ai_agents.models import PendingClarification
        from django.conf import settings

        print("DB:", settings.DATABASES["default"]["NAME"])

        print(
            "All rows:",
            list(
                PendingClarification.objects.values(
                    "id",
                    "status"
                )
            )
        )

        if active:
            print("3. Returning because active exists")
            return

        pending = cs.get_next_waiting()
        print("4. Pending:", pending)

        if not pending:
            print("5. No pending clarification")
            return

        job = pending.job
        print("6. Job:", job.job_title)

        msg = (
            f"Job needs more info: \"{job.job_title}\"\n\n"
            f"Type: {job.job_type or 'N/A'}\n"
            f"Budget: {job.budget or 'N/A'}\n"
            f"Summary: {job.summary or 'N/A'}\n\n"
            f"Paste the full job description below."
        )

        print("7. Sending Telegram message...")

        try:
            result = tg.send_message(telegram_chat_id, msg)
            print("8. Telegram result:", result)

            cs.mark_sent(pending, telegram_chat_id)
            print("9. Marked SENT")

        except Exception as e:
            print("ERROR:", repr(e))
            raise

    def _handle_reply(self, text, telegram_chat_id, proposal_agent: ProposalWriterAgent):
        waiting_for_description = cs.get_active_sent()
        if waiting_for_description:
            self._save_description(waiting_for_description, text, telegram_chat_id)
            return

        described = cs.get_active_described()
        if described:
            if self._is_proposal_request(text):
                self._generate_and_send_proposal(described, telegram_chat_id, proposal_agent)
            else:
                cs.append_description(described, text)
                tg.send_message(
                    telegram_chat_id,
                    "Added that to the description. Say something like "
                    "\"give me proposal\" whenever you're ready for it.",
                )
            return

        tg.send_message(
            telegram_chat_id,
            "I'm not currently waiting on anything for a job, so I'm not sure what to do with that.",
        )

    def _save_description(self, pending, text, telegram_chat_id):
        job = pending.job
        job.project_description = text
        job.save(update_fields=["project_description"])

        cs.mark_described(pending, text)

        tg.send_message(
            telegram_chat_id,
            f"Got the full description for \"{job.job_title}\". Send more details if you "
            f"want to add anything, or say \"give me proposal\" when you're ready for it.",
        )
        logger.info("Saved description for job_id=%s (awaiting proposal request)", job.id)

    def _generate_and_send_proposal(self, pending, telegram_chat_id, proposal_agent: ProposalWriterAgent):
        job = pending.job

        job.project_description = pending.full_description
        job.save(update_fields=["project_description"])

        tg.send_message(telegram_chat_id, "Writing the proposal now...")

        job_dict = {
            "id": job.id,
            "job_title": job.job_title,
            "job_type": job.job_type,
            "summary": job.summary,
            "project_description": job.project_description,
            "skills": job.skills,
            "technologies": job.technologies,
            "budget": job.budget,
            "duration": job.duration,
            "experience_required": job.experience_required,
            "company_name": job.company_name,
        }

        proposal_text = proposal_agent.write_proposal(job_dict)

        cs.resolve_clarification(pending, full_description=pending.full_description, proposal_text=proposal_text)

        tg.send_message(telegram_chat_id, proposal_text)
        logger.info("Resolved clarification and sent proposal for job_id=%s", job.id)

    @staticmethod
    def _is_proposal_request(text: str) -> bool:
        return "proposal" in text.lower()

    def _load_offset(self):
        if _OFFSET_FILE.exists():
            try:
                return json.loads(_OFFSET_FILE.read_text()).get("offset")
            except Exception:
                return None
        return None

    def _save_offset(self, offset):
        _OFFSET_FILE.write_text(json.dumps({"offset": offset}))