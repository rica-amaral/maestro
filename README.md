# Maestro

**One orchestrator, one context, one way of working, across every device and every project.**

Maestro is how I run my own SaaS products and a small 3D-printing e-commerce operation with AI
agents. It is a single Claude Code session on a server that turns what I ask for into task cards,
routes them to a fleet of stateless Claude agents through
[Mission Control](https://github.com/builderz-labs/mission-control) (open source, run from
[my fork](https://github.com/rica-amaral/mission-control)), and gets the results back to me as
pull requests I approve from my phone.

This repository is the part I built: the orchestrator's rules, the agent prompts and access
policy, the operations scripts around the fleet, a cost report, and the changes I made to Mission
Control. It is small on purpose. Everything here runs in production today.

## The problem

- My agents ran on my laptop, so work stopped whenever it slept or closed.
- I used Claude on a Mac, a work PC, a phone and a server. Each had its own context, permissions
  and output format, so the same request could be done four different ways.
- Nothing was documented: which agent did what, with which access, and how results came back.

## What I built

```
request (text or voice, any device)
   -> Maestro writes the card (objective, context, fences, proof of done) + dispatchCwd
   -> Mission Control dispatches it to the right agent (claude --print, in the project folder)
   -> the agent builds, runs the project's build/lint, opens a PR
   -> Aegis reviews; a rejection goes back with the reason
   -> Vercel builds a preview; I review and merge from the GitHub app
   -> production; progress and failures reach me on WhatsApp or Telegram
```

A human approves every change before it ships. Agents do the work; the pull request is the gate.

## What is in here

| Path | What it is |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Diagram, components (what is mine and what is upstream), one request step by step, design decisions. |
| [AGENTS.md](AGENTS.md) | Every agent's role, model, write access and budget cap, and the guardrails. |
| [agents/](agents/) | Production prompts (SOULs) of `dev`, `qa` and `creator`, with their tool allowlists. Translated from Portuguese. |
| [skills/writing-agent-cards/](skills/writing-agent-cards/SKILL.md) | The Maestro's rules for writing a card a stateless agent can finish, packaged as a skill. |
| [specs/example-feature.md](specs/example-feature.md) | A real card the fleet executed, end to end: a spec-driven feature in three parts. |
| [ops/](ops/) | `dispatch.sh` (trigger), `failure_watch.py` (diagnosis that only speaks on change), `token_governor.py` (subscription quota policy). |
| [tools/cost_report.py](tools/cost_report.py) | Usage by model and week, delivery outcomes, read-only from Mission Control's SQLite. |
| [mcp/](mcp/README.md) | MCP servers the Maestro uses and the changes I made to Mission Control's. |
| [infra/](infra/) | systemd units for the Maestro and the timers; a compose example for n8n and the WhatsApp gateway. |
| [docs/fork-changes.md](docs/fork-changes.md) | What I changed in Mission Control, grouped by the problem it solved. |

## Numbers

From Mission Control's database, 2026-08-14 to 2026-11-16, generated with
`tools/cost_report.py`. They cover the dispatched agents, not the Maestro session itself.

| | |
|---|---|
| Tasks | 303 (231 done, 67 failed, 5 open) |
| Completion rate on finished tasks | 78% |
| Distinct pull request URLs reported by agents | 157 |
| Reviewer verdicts | 235 approved, 113 rejected (32% sent back) |
| Agent runs | 662 |

Model mix by runs: Opus 4.6 46%, Sonnet 5.5 31%, Sonnet 4.6 20%, Haiku 4.5 1%, others 2%.
The case study I wrote earlier says routine work defaults to Haiku. The logs do not support that:
the fleet's default is Sonnet for building and Opus for scope and orchestration. I am leaving the
measured number here rather than the intended policy.

**On cost.** The fleet runs on a Claude subscription, so the real constraint is quota, not
dollars; [ops/token_governor.py](ops/token_governor.py) is the control for that. The report can
price runs at API list prices from [tools/pricing.json](tools/pricing.json), and leaves models
without a configured price as n/a instead of guessing.

**Known gap.** Mission Control's `token_usage` table has `agent_name` and `task_id` columns, but
the dispatcher does not fill them yet, so cost per agent and per task is not available. That is
the next change to the dispatcher.

## What runs on it today

- **SaaS products**: practice management for independent health professionals (piloted with a
  real user), household finance, event and guest-list management (used at a real event), a
  business-management panel for small local businesses, and a RAG study companion
  (Postgres/pgvector, Claude, Next.js).
- **A 3D-printing e-commerce operation**: daily briefings, product listings and pricing, with
  agents connected to the ERP and marketplaces.

At my day job I applied the same pattern to an engineering squad (an orchestrator bundling skills, agents, MCP servers and hooks); none of that code is here.

## What I learned

- **Standardize before you scale.** One context and one execution path mattered more than adding
  agents. Most of my changes to Mission Control are about the fleet doing the same thing the same
  way, not about new capabilities.
- **Keep a human gate where it is cheap.** Approving a PR with a live preview from a phone takes a
  minute and keeps production in human hands.
- **Make failure loud and specific.** A third of deliveries get sent back by the reviewer and a
  fifth of tasks fail. That is fine as long as I hear about it, grouped by cause, once.
- **Adoption is the product.** Tooling only counts when people run it every day, the way they
  already work. For me that meant the phone, not a dashboard.

## Not here, on purpose

Credentials, server addresses, the WhatsApp allowlist, chat IDs, client data, and anything from
my employer. Configuration is shown with placeholders.

## License

[MIT](LICENSE)
