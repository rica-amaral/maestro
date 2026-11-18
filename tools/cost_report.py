#!/usr/bin/env python3
"""Fleet cost and outcome report, read straight from the Mission Control SQLite database.

Usage:
    cost_report.py /path/to/mission-control.db [--pricing pricing.json] [--weeks 12]

Read-only: the database is opened with mode=ro, so this can run next to the live server.

What it answers:
  1. How many tokens each model consumed, and what that would cost at API list prices.
  2. How usage moves week by week.
  3. What the fleet delivered: task outcomes, reviewer verdicts, pull requests opened.

What it deliberately does NOT print: task titles or descriptions. They carry client and
business context, and a cost report should be safe to paste anywhere.

Known gap: `token_usage.agent_name` and `token_usage.task_id` exist in the schema but the
dispatcher does not fill them yet, so cost per agent and per task is not available. The report
says so instead of guessing.
"""
import argparse
import collections
import datetime as dt
import json
import re
import sqlite3
import sys

PR_URL = re.compile(r"github\.com/[\w.-]+/[\w.-]+/pull/\d+")


def load_pricing(path):
    if not path:
        return {}
    with open(path) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def price_for(model, pricing):
    """Exact match first, then the longest known prefix. Unknown model -> None (not a guess)."""
    if model in pricing:
        return pricing[model]
    hits = [k for k in pricing if model.startswith(k)]
    return pricing[max(hits, key=len)] if hits else None


def usd(p, tin, tout):
    if p is None or p.get("input") is None or p.get("output") is None:
        return None
    return tin / 1e6 * p["input"] + tout / 1e6 * p["output"]


def fmt_usd(v):
    return "n/a" if v is None else f"${v:,.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--pricing")
    ap.add_argument("--weeks", type=int, default=12)
    a = ap.parse_args()

    db = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    pricing = load_pricing(a.pricing)

    rows = db.execute(
        "SELECT model, input_tokens, output_tokens, created_at, agent_name, task_id FROM token_usage"
    ).fetchall()
    if not rows:
        sys.exit("token_usage is empty")

    first = dt.datetime.fromtimestamp(min(r[3] for r in rows), dt.timezone.utc).date()
    last = dt.datetime.fromtimestamp(max(r[3] for r in rows), dt.timezone.utc).date()
    print(f"# Fleet report ({first} to {last})\n")

    # 1. by model
    by_model = collections.defaultdict(lambda: [0, 0, 0])
    for model, tin, tout, *_ in rows:
        m = by_model[model]
        m[0] += 1
        m[1] += tin or 0
        m[2] += tout or 0
    total_runs = sum(v[0] for v in by_model.values())
    print("## Usage by model\n")
    print("| Model | Runs | Share of runs | Output tokens | Est. cost at API list price |")
    print("|---|---:|---:|---:|---:|")
    total_cost, unpriced = 0.0, []
    for model, (n, tin, tout) in sorted(by_model.items(), key=lambda kv: -kv[1][0]):
        c = usd(price_for(model, pricing), tin, tout)
        if c is None:
            unpriced.append(model)
        else:
            total_cost += c
        print(f"| {model} | {n} | {n / total_runs:.0%} | {tout:,} | {fmt_usd(c)} |")
    print(f"\nTotal runs: {total_runs}. Priced subtotal: {fmt_usd(total_cost)}.")
    if unpriced:
        print(f"No list price configured for: {', '.join(unpriced)} (shown as n/a, not estimated).")

    # 2. by ISO week
    by_week = collections.Counter()
    tok_week = collections.Counter()
    for _, tin, tout, ts, *_ in rows:
        w = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%G-W%V")
        by_week[w] += 1
        tok_week[w] += (tin or 0) + (tout or 0)
    print(f"\n## Last {a.weeks} active weeks\n")
    print("| ISO week | Runs | Tokens |")
    print("|---|---:|---:|")
    for w in sorted(by_week)[-a.weeks:]:
        print(f"| {w} | {by_week[w]} | {tok_week[w]:,} |")

    # 3. outcomes
    print("\n## What the fleet delivered\n")
    status = dict(db.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall())
    total = sum(status.values())
    done, failed = status.get("done", 0), status.get("failed", 0)
    print(f"- Tasks: {total} (done {done}, failed {failed}, other {total - done - failed})")
    if done + failed:
        print(f"- Completion rate on finished tasks: {done / (done + failed):.0%}")
    prs = set()
    for (text,) in db.execute("SELECT COALESCE(resolution,'') || ' ' || COALESCE(outcome,'') FROM tasks"):
        prs.update(PR_URL.findall(text))
    print(f"- Distinct pull request URLs reported by agents: {len(prs)}")
    qr = dict(db.execute("SELECT status, COUNT(*) FROM quality_reviews GROUP BY status").fetchall())
    if qr:
        ok, ko = qr.get("approved", 0), qr.get("rejected", 0)
        print(f"- Reviewer verdicts: {ok} approved, {ko} rejected ({ko / max(ok + ko, 1):.0%} sent back)")

    # 4. the honest gap
    attributed = sum(1 for r in rows if r[4] or r[5])
    print("\n## Attribution\n")
    print(f"- Runs tagged with an agent or task: {attributed} of {total_runs}.")
    if attributed == 0:
        print("- Cost per agent / per task is not available yet: the dispatcher does not write "
              "`agent_name` / `task_id` into `token_usage`. Next step, not a guess.")


if __name__ == "__main__":
    main()
