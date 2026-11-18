# Agents: roles and access

Every agent has a documented role, a working directory rule, a tool allowlist, a budget cap and a
model. Access is enforced by the dispatcher (`dispatchAllowedTools` is passed to `claude --print`),
not by asking the agent nicely. Agent names are translated from Portuguese.

## Layer 0: the orchestrator

| Agent | Runs as | Does | Does not |
|---|---|---|---|
| **Maestro** | One long-lived Claude Code session on the server, reachable from every device via Remote Control | Talks to me, decides scope with me, writes task cards, routes them, applies database migrations after I merge, reports PR URLs | Receive tasks. Write product code. Merge. |

The Maestro is the only agent with a conversation. Everything below it is stateless: one task in,
one report out.

## Layer 1: development (work on any project)

The task, not the agent, decides the project: every code card carries `metadata.dispatchCwd`.

| Agent | Model | Edit/Write tools | Budget cap | Role |
|---|---|---|---|---|
| **coordinator** | Opus | no | $2 | Owns all code work; splits it across dev, qa and analyst. |
| **dev** | Sonnet | **yes** | $20 | The only agent that writes product code. Delivers a branch and a PR, never main. [Prompt](agents/dev.md) |
| **qa** | Sonnet | no | $8 | Runs lint/build/tests, returns APPROVED / REJECTED / NOT VERIFIED with evidence. [Prompt](agents/qa.md) |
| **analyst** | Opus | Write only (scope docs) + web | $8 | Maps scope and documents it before a build. |
| **designer** | Fable | **yes** | $20 | Takes a product intent, returns the feature designed and built. |
| **n8n-dev** | Sonnet | no | $6 | Builds n8n automations through the n8n API. |
| **root-cause** | default | **yes** | $8 | Finds why something failed and fixes it through a PR. |
| **creator** | Opus | no | $8 | Creates and configures other agents through the API. [Prompt](agents/creator.md) |

Model policy (decided 2026-10-20): Sonnet builds, Opus manages and reviews scope, Fable designs.
What the logs show is in [README.md](README.md#numbers).

## Layer 2: product and content (any SaaS)

| Agent | Role |
|---|---|
| **sales** | Sales and marketing copy. |
| **docs-writer** | PDF manuals and in-app help for each SaaS. |
| **social-content** | Instagram content for the SaaS products. |
| **image-generator** | Text-free product images. |
| **legal** | Legal opinions. Read-only. |

## Layer 3: operations (3D printing e-commerce)

An orchestrator with two sub-orchestrators ("make" and "sell") and specialist agents for model
sourcing and license checks, quoting, pricing, stock reconciliation with the ERP, customer
WhatsApp, and Instagram. Two of them run on an office PC that **pulls** work from Mission Control
every 5 minutes outside business hours; nothing can push into that machine.

## Review

**Aegis**, Mission Control's built-in reviewer, checks every delivery before it moves to done.
A rejection sends the task back with the reason, and the agent continues on the same PR instead of
starting over (one of my changes to the dispatcher).

## Not agents, on purpose

| Component | Why it is a script and not an LLM |
|---|---|
| [`ops/failure_watch.py`](ops/failure_watch.py) | Diagnosis must be deterministic and cheap. It reads, groups failures by cause, and alerts only on change. It never fixes. |
| [`ops/token_governor.py`](ops/token_governor.py) | Quota policy is arithmetic. Pauses development tasks, never operations. |
| [`ops/dispatch.sh`](ops/dispatch.sh) | A timer that triggers dispatch, because the built-in scheduler never starts. |

## Guardrails, summarised

1. **Project lock.** No `dispatchCwd` -> the agent aborts at the workspace root; the dispatcher
   also refuses a card with no repository owner.
2. **Write access is granted per role.** Full `Edit`/`Write` only where the job is producing
   files (dev, designer, root-cause, docs and content agents). Reviewers and orchestrators get
   none, so they cannot fix their own findings. Most agents keep `Bash` to run builds and tests,
   so this is a tool allowlist plus prompt discipline, not a sandbox; the hard gate is the PR.
3. **main is untouchable.** Agents deliver branches and PRs. I merge from the GitHub app; Vercel
   deploys on merge.
4. **Migrations are never applied by agents.** The Maestro applies them after the merge.
5. **Budget caps per agent** (`dispatchMaxBudgetUsd`) plus the quota governor across the fleet.
6. **One repository, one task at a time**, and every task starts from the current main.
