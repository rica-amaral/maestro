#!/usr/bin/env python3
"""Token governance for the agent fleet (runs every 10 minutes on the server).

The fleet runs on a Claude subscription, so the constraint is not dollars, it is quota:
a 5-hour session window and a 7-day weekly window. The rules I set:

  - At 90% of the session window, pause DEVELOPMENT work and keep the remaining quota for
    OPERATIONS (customer-facing agents keep running).
  - The weekly quota is split across the 5 working days: each working day that has started
    releases 1/5, cumulative, with one day of advance. Weekends release nothing new.
  - Near the end of a window, allow spending more so quota is not left unused.

How it measures: a minimal API call with the agents' token returns, in the response headers,
the session and weekly utilization and when each resets.

How it pauses: development tasks in `assigned` move to `backlog` with
`metadata.paused_by = "token-governor"`. When quota frees up, only those tasks go back to
`assigned`. A task already running is never interrupted. Operations agents are never paused.

Usage: token_governor.py           (apply)
       token_governor.py --dry-run (only print what it would do)

Environment: MC_URL, MC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN, NOTIFY_WEBHOOK_URL, NOTIFY_WEBHOOK_KEY,
STATE_DIR.
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

STATE_DIR = os.environ.get("STATE_DIR", "/var/lib/token-governor")
DRY_RUN = "--dry-run" in sys.argv
DEVELOPMENT = {"dev", "qa", "analyst", "creator", "n8n-dev", "root-cause", "docs-writer", "social-content", "legal"}
SESSION_LIMIT = 0.90
WEEK_SLACK = 0.02               # tolerance above the cumulative daily allowance
WEEK_FINAL_STRETCH_H = 24       # in the last 24 h of the week, only pause above 97%
SESSION_FINAL_STRETCH_MIN = 45  # in the last 45 min of the session, the 90% limit rises to 97%
ADVANCE_DAYS = 1                # always release the next working day's share early
MARK = "token-governor"
BRT = -3 * 3600                 # working days are counted in Brasilia time


def usage():
    # Subscription (OAuth) tokens only accept requests that identify as Claude Code.
    body = {"model": "claude-haiku-4-5", "max_tokens": 1,
            "system": "You are Claude Code, Anthropic's official CLI for Claude.",
            "messages": [{"role": "user", "content": "ok"}]}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": "Bearer " + os.environ["CLAUDE_CODE_OAUTH_TOKEN"],
                 "anthropic-beta": "oauth-2025-04-20", "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        h = urllib.request.urlopen(req, timeout=30).headers
    except urllib.error.HTTPError as e:  # a 429 carries the same headers
        h = e.headers
    g = lambda k: h.get("anthropic-ratelimit-unified-" + k)
    if g("5h-utilization") is None:
        raise SystemExit("the API did not return utilization headers")
    return {"session": float(g("5h-utilization")), "session_reset": int(g("5h-reset")),
            "week": float(g("7d-utilization")), "week_reset": int(g("7d-reset"))}


def mc(method, path, body=None):
    req = urllib.request.Request(
        os.environ["MC_URL"] + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"x-api-key": os.environ["MC_API_KEY"], "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def notify(text, key):
    url = os.environ.get("NOTIFY_WEBHOOK_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(url, method="POST",
            data=json.dumps({"text": text, "key": key}).encode(),
            headers={"X-Notify-Key": os.environ.get("NOTIFY_WEBHOOK_KEY", ""),
                     "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:
        print("notify failed:", e)


def week_allowance(week_reset, now):
    """Fraction of the weekly quota released so far: 1/5 per started working day, +1 day early."""
    to_date = lambda ts: datetime.datetime.fromtimestamp(ts + BRT, datetime.timezone.utc).date()
    week_start = week_reset - 7 * 86400
    d, end, workdays = to_date(week_start), to_date(now), 0
    # The reset day is not a full day if the week restarts in the afternoon.
    if datetime.datetime.fromtimestamp(week_start + BRT, datetime.timezone.utc).hour >= 12:
        d += datetime.timedelta(days=1)
    while d <= end:
        workdays += d.weekday() < 5
        d += datetime.timedelta(days=1)
    return min((workdays + ADVANCE_DAYS) / 5, 1)


def main():
    u = usage()
    now = time.time()
    allowance = week_allowance(u["week_reset"], now)
    min_to_session_reset = (u["session_reset"] - now) / 60
    h_to_week_reset = (u["week_reset"] - now) / 3600

    session_limit = 0.97 if min_to_session_reset <= SESSION_FINAL_STRETCH_MIN else SESSION_LIMIT
    session_full = u["session"] >= session_limit
    if h_to_week_reset <= WEEK_FINAL_STRETCH_H:
        week_over = u["week"] >= 0.97
    else:
        week_over = u["week"] > allowance + WEEK_SLACK

    pause = session_full or week_over
    reason = (f"session at {u['session']:.0%}" if session_full else
              f"week at {u['week']:.0%}, above the {allowance:.0%} allowance" if week_over else "")

    state_file = os.path.join(STATE_DIR, "state.json")
    before = json.load(open(state_file)) if os.path.exists(state_file) else {"paused": False}
    tasks = mc("GET", "/api/tasks?limit=500").get("tasks", [])
    moved = []
    for t in tasks:
        meta = dict(t.get("metadata") or {})
        if pause and t.get("status") == "assigned" and t.get("assigned_to") in DEVELOPMENT:
            meta.update(paused_by=MARK, paused_at=int(now))
            moved.append(t["id"])
            if not DRY_RUN:
                mc("PUT", f"/api/tasks/{t['id']}", {"status": "backlog", "metadata": meta})
        elif not pause and t.get("status") == "backlog" and meta.get("paused_by") == MARK:
            meta.pop("paused_by", None)
            meta.pop("paused_at", None)
            moved.append(t["id"])
            if not DRY_RUN:
                mc("PUT", f"/api/tasks/{t['id']}", {"status": "assigned", "metadata": meta})

    line = {"at": int(now), "session": u["session"], "week": u["week"], "allowance": round(allowance, 3),
            "paused": pause, "reason": reason, "moved": moved}
    print(json.dumps(line))
    if DRY_RUN:
        return
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, "history.jsonl"), "a") as f:
        f.write(json.dumps(line) + "\n")
    json.dump({"paused": pause}, open(state_file, "w"))

    if pause != before.get("paused"):  # only speak when the state changes
        if pause:
            notify(f"Token governor: development paused ({reason}). {len(moved)} task(s) back to backlog. "
                   "Operations keep running.", f"pause-{int(now)}")
        else:
            notify(f"Token governor: development resumed (session {u['session']:.0%}, week {u['week']:.0%} "
                   f"for a {allowance:.0%} allowance). {len(moved)} task(s) back in the queue.", f"resume-{int(now)}")


if __name__ == "__main__":
    main()
