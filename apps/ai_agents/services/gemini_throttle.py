import os
import threading
import time
from collections import deque

# How many Gemini requests/minute you're allowed across this whole process
# (EmailAnalyzer + ProfileMatchingAgent share this — it's one quota bucket).
# Free tier gemini-2.5-flash = 5 RPM. Once your paid tier is confirmed active,
# check https://ai.google.dev/gemini-api/docs/rate-limits for the real number
# and either change the default below or set GEMINI_RPM_LIMIT in your .env.
MAX_REQUESTS_PER_MINUTE = int(os.getenv("GEMINI_RPM_LIMIT", "5"))

_lock = threading.Lock()
_call_times = deque()  # monotonic timestamps of recent calls, oldest first


def wait_for_slot():
    """
    Blocks ONLY when necessary to stay under MAX_REQUESTS_PER_MINUTE in any
    rolling 60-second window. Unlike a fixed per-call sleep, this lets calls
    run back-to-back at full speed as long as you're under the limit, and
    only pauses the exact amount of time needed once you hit it.

    Call this immediately before every generate_content() call.
    """
    with _lock:
        now = time.monotonic()

        # Drop timestamps older than 60s — they no longer count against the limit.
        while _call_times and now - _call_times[0] >= 60:
            _call_times.popleft()

        if len(_call_times) >= MAX_REQUESTS_PER_MINUTE:
            wait_time = 60 - (now - _call_times[0])
            if wait_time > 0:
                time.sleep(wait_time)
            now = time.monotonic()
            while _call_times and now - _call_times[0] >= 60:
                _call_times.popleft()

        _call_times.append(time.monotonic())
