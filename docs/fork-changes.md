# What I changed in Mission Control

Mission Control is open source ([builderz-labs/mission-control](https://github.com/builderz-labs/mission-control)).
I run it from [a fork](https://github.com/rica-amaral/mission-control). These are my changes,
grouped by the problem each one solved. Every change went in through a branch and a PR, merged
by me.

## The fleet sat idle while the UI said it was working

- **Three causes that left the fleet stopped**: tasks for a non-existent agent silently
  disappeared; without `MC_WORKSPACE_ROOT` the working-directory guard sent agents *into the
  Mission Control folder itself*; the internal scheduler never started (worked around with
  [a systemd timer](../ops/dispatch.sh)).
- **Status summary shows what is running even when the fleet is reported offline.**
- **Agents no longer inherit the server's environment** (`NODE_ENV=production`, Next.js internal
  config), which broke builds inside the spawned `claude --print`.

## Agents worked in the wrong repository

- **Project scope enforced at dispatch**, and **every card must have a repository owner, or the
  dispatcher refuses it.**
- **MCP server exposes `project_id` and `metadata`, adds `mc_list_projects`**, so the orchestrator
  can route by project slug ([mcp/README.md](../mcp/README.md)).
- **Each task starts from the current main, and one repository serves one task at a time**, so two
  agents never collide in the same clone.

## Rework was expensive

- **A rejected task receives the reviewer's reason and continues, instead of redoing everything
  from scratch.**
- **The agent's final report becomes the task comment**, instead of a second write that could fail.
- **Long agent responses are no longer cut at 10,000 characters** (they were being truncated, then
  rejected by the reviewer for being incomplete).
- **Task descriptions up to 50,000 characters**, because good cards are long.

## Operator experience

- **Timeout and retries configurable per environment.**
- **Org chart with hierarchy, scope, budget ceiling and notes per agent.**
- **Board shows the project ticket number** instead of a global ID.
- **Images in task descriptions and comments**, so creative work arrives visible.
- **A "Products" view** showing which step each product is at, what is waiting on the owner, and
  its indicators.
- **`PUT /soul` refuses an empty SOUL** instead of erasing it and answering 200.
- **Owner comments go back to the queue**: replying on a task re-dispatches it with the answer.
- **The failure watch is versioned in the repo** and detects when a task has no executor at all.

## Housekeeping

Dependency bumps that conflicted with each other resolved together, CI contract-parity fixes for
new routes, a pinned security-scanner SHA updated, and a vendor name removed from the tagline in
all 10 languages.
