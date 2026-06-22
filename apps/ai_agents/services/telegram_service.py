import os
import requests


def _api_base() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set — check your .env file")
    return f"https://api.telegram.org/bot{token}"


def send_message(chat_id: str, text: str) -> dict:
    resp = requests.post(
        f"{_api_base()}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_updates(offset: int = None, timeout: int = 30) -> list:
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset

    resp = requests.get(
        f"{_api_base()}/getUpdates",
        params=params,
        timeout=timeout + 10,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])
