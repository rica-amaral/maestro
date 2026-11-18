#!/usr/bin/env python3
"""failure_watch: reads Mission Control, works out why tasks stopped, and reports it by message.

Why it exists: a task dies and nobody notices. The `failed` status sits in the database, the
error sits in a column, and the fleet keeps retrying. By the time someone looks, there are 28
failures and 13 stuck tasks. That is exactly what happened on 2026-10-09.

What it does NOT do, on purpose:

- **It does not fix anything.** Diagnosis and action are separate: a watcher that also changes
  things becomes the thing nobody checks. It describes and points at what to do; a human decides.
- **It does not report every run.** It speaks when something CHANGES. A watcher that repeats
  the same alert every 30 minutes stops being read in week two, and then it is useless.

De-duplication has two layers, because one is not enough: a local state file (lost if the server
is rebuilt) and the `key` sent with each message, which the message queue never delivers twice.
The key carries the date, so a problem that is still unresolved alerts again tomorrow, once.

Runs every 30 minutes from a systemd timer. Flags: --dry-run (print, don't send), --force
(ignore previous state). Environment: MC_DB, NOTIFY_WEBHOOK_URL, NOTIFY_WEBHOOK_KEY, STATE_FILE.
"""
import collections
import datetime
import json
import os
import re
import sqlite3
import sys
import urllib.request

DB = os.environ.get("MC_DB", "/opt/mission-control/.data/mission-control.db")
STATE_FILE = os.environ.get("STATE_FILE", "/var/lib/failure-watch/state.json")
BRT = datetime.timezone(datetime.timedelta(hours=-3))

DRY_RUN = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv

# Hours a task may sit in `assigned` before it is news. The worker on the office PC polls every
# 10 minutes while the machine is on; 6 h covers a whole night without false alarms.
STUCK_HOURS = 6
# How many times the same title must appear in 24 h to be a loop, not normal repetition.
LOOP_COUNT = 3


def now():
    return datetime.datetime.now(BRT)


def local(ts):
    # Mission Control stores epoch SECONDS as integers. SQLite's datetime(updated_at) returns
    # NULL on them without complaining; that is how I once read "1970" in a diagnosis.
    return datetime.datetime.fromtimestamp(int(ts), BRT).strftime("%d/%m %H:%M")


def family(msg):
    """Group error messages by CAUSE, not by text. Otherwise 18 identical failures become
    18 lines and the message on the phone is unreadable."""
    m = (msg or "").strip()
    if not m:
        return "no error message"
    for pattern, name in [
        (r"tags\.join is not a function", "dispatcher bug (tags.join)"),
        (r"No conversation found with session ID", "Claude session disappeared"),
        (r"Aegis rejected", "reviewer rejected the delivery"),
        (r"received a task from project", "task went to another project's agent"),
        (r"runs on another machine", "agent runs on another machine"),
        (r"permission|not allowed|allowedTools", "missing tool permission"),
        (r"ENOENT|no such file|dispatch cwd", "invalid working directory"),
        (r"budget|max-budget", "budget exceeded"),
        (r"timeout|timed out|ETIMEDOUT", "timed out"),
        (r"ECONNREFUSED|ENOTFOUND|socket|EAI_AGAIN", "network"),
    ]:
        if re.search(pattern, m, re.I):
            return name
    return m.split("\n")[0][:60]


def read_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def write_state(d):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, STATE_FILE)  # atomic swap: a timer killed mid-write never leaves half a state


def send(text, key):
    req = urllib.request.Request(
        os.environ["NOTIFY_WEBHOOK_URL"], data=json.dumps({"text": text, "key": key}).encode(),
        headers={"Content-Type": "application/json", "X-Notify-Key": os.environ.get("NOTIFY_WEBHOOK_KEY", "")},
        method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode()[:200]


def diagnose(db):
    """Return a list of (key, line_for_the_phone). Each item is a conclusion, not raw data."""
    today = now().strftime("%Y-%m-%d")
    t_now = now().timestamp()
    findings = []

    # 1. loop: the same card turning into a new task again and again
    by_title = collections.Counter()
    seen = {}
    for r in db.execute("SELECT title, id, created_at, status FROM tasks WHERE created_at >= ? ORDER BY id",
                        (t_now - 24 * 3600,)):
        by_title[r["title"]] += 1
        seen.setdefault(r["title"], []).append((r["id"], r["created_at"], r["status"]))
    loops = []
    for title, n in by_title.most_common():
        if n < LOOP_COUNT:
            continue
        ids = seen[title]
        gap = (int(ids[-1][1]) - int(ids[0][1])) / (len(ids) - 1) / 60 if len(ids) >= 2 else 0
        loops.append((title, n, gap, sum(1 for i in ids if i[2] == "assigned")))
    if loops:
        # One block: three cards stuck by the SAME mechanism are one problem, not three.
        total = sum(n for _, n, _, _ in loops)
        waiting = sum(w for *_, w in loops)
        pace = sum(g for _, _, g, _ in loops) / len(loops)
        lines = "\n".join(f"   - {n}x \"{t[:46]}\"" for t, n, _, _ in loops)
        findings.append((f"loop:{today}:{len(loops)}cards:{total}",
                         f"*{total} repeated tasks* from {len(loops)} card(s), one every ~{pace:.0f} min\n{lines}\n"
                         f"   {waiting} still waiting. The card returns to the queue while the task does not\n"
                         f"   finish, and becomes a new task. Unblock execution for all {total}."))

    # 2. stuck: assigned for too long, nobody picked it up
    stuck = list(db.execute(
        "SELECT id, assigned_to, updated_at, dispatch_attempts FROM tasks "
        "WHERE status='assigned' AND updated_at < ? ORDER BY updated_at", (t_now - STUCK_HOURS * 3600,)))
    if stuck:
        per_agent = collections.Counter(s["assigned_to"] or "?" for s in stuck)
        never = sum(1 for s in stuck if not s["dispatch_attempts"])
        findings.append((f"stuck:{today}:{len(stuck)}",
                         f"*{len(stuck)} tasks stuck* for more than {STUCK_HOURS}h\n"
                         f"   {', '.join(f'{a} ({n})' for a, n in per_agent.most_common())}\n"
                         f"   oldest since {local(stuck[0]['updated_at'])}"
                         + (f"; {never} were never attempted." if never else ".")))

    # 3. new failures since the last look
    previous = read_state()
    cutoff = 0 if FORCE else previous.get("last_failed_id", 0)
    new = list(db.execute("SELECT id, error_message FROM tasks WHERE status='failed' AND id > ? ORDER BY id",
                          (cutoff,)))
    if new:
        causes = collections.Counter(family(r["error_message"]) for r in new)
        lines = "\n".join(f"   - {n}x {c}" for c, n in causes.most_common(4))
        # On the first run there is no "last alert"; claiming one would be a false statement
        # in the very message that should earn trust in the watcher.
        when = "since the last alert" if previous.get("last_look") else "in total (first look)"
        findings.append((f"failed:{today}:{new[-1]['id']}", f"*{len(new)} tasks failed* {when}\n{lines}"))

    top = max([r["id"] for r in db.execute("SELECT id FROM tasks WHERE status='failed'")] or [0])
    return findings, top


def main():
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    findings, top_failed = diagnose(db)

    state = read_state()
    already = set(state.get("alerted", []))
    fresh = [(k, t) for k, t in findings if FORCE or k not in already]
    if not fresh:
        print(f"{now():%H:%M} nothing new ({len(findings)} known conditions)")
        state.update(last_failed_id=top_failed, last_look=now().isoformat())
        if not DRY_RUN:
            write_state(state)
        return 0

    text = f"*Mission Control: what got stuck*\n_{now():%d/%m %H:%M}_\n\n" + "\n\n".join(t for _, t in fresh)
    if DRY_RUN:
        print(text, "\n--- keys:", [k for k, _ in fresh])
        return 0
    try:
        print(f"{now():%H:%M} sent {len(fresh)} condition(s): {send(text, 'watch:' + '|'.join(k for k, _ in fresh)[:120])}")
    except Exception as e:
        # A network error must not mark anything as alerted: the next run tries again.
        # Silence caused by a send error is worse than a repeated alert.
        print(f"{now():%H:%M} could NOT send: {e}", file=sys.stderr)
        return 1
    state.update(alerted=list(already | {k for k, _ in fresh})[-200:], last_failed_id=top_failed,
                 last_look=now().isoformat())
    write_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
