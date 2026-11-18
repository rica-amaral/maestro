---
name: writing-agent-cards
description: Turn a request from Ricardo into Mission Control task cards that a stateless, non-interactive agent can finish in one short run and deliver as a pull request. Use whenever the Maestro is about to call mc_create_task for code work.
---

# Writing agent cards

In production these rules live in the Maestro's `CLAUDE.md` (translated and condensed here into
the SKILL.md format). They exist because every rule below was learned from a task that failed.

## Why cards need this much care

The executing agent:
- has **no memory** between tasks and does not read the Maestro's memory;
- runs **non-interactively** with a hard time limit; nobody answers its questions;
- works on **any** project, so it only knows which repo to touch if the card says so.

Everything the agent needs goes in the card text. A good card is an agent that gets it right.

## The rule that cannot be broken: `dispatchCwd`

Every code task carries `metadata.dispatchCwd` with the project folder name.

```
mc_create_task({
  title: "...",
  description: "...",
  assigned_to: "dev",
  project_id: <id>,
  metadata: { dispatchCwd: "<project-slug>" }
})
```

- Get it from `mc_list_projects`. The project `slug` is exactly the folder name on disk.
  Never infer it from how the project was named in conversation.
- It is **relative** to the workspace root: never an absolute path, never `../`. A path outside
  the root is ignored silently and the agent runs in the wrong place.
- If nothing matches what was asked, ask instead of guessing.
- Without it the agent lands at the workspace root. Its prompt tells it to abort there, so the
  cycle is wasted, but no wrong repo is touched. The dispatcher also refuses a card without a
  repo owner.

## Card structure

```
# <what will exist when this is done>

## Objective          why this matters, in two or three sentences
## Context            what the agent cannot know: files to use as a model, schema quirks,
                      decisions already made, links to the previous part
## What to do         numbered, concrete, with file paths
## Do NOT do          scope fences (no migrations applied, no real data, no unrelated modules)
## Proof of done      the exact commands that must pass, real screenshots, the PR URL
```

## Sizing

- One card fits one short run. Bigger work becomes a chain of cards (part 1/3, 2/3, 3/3).
- If part B depends on part A, write in B the context from A. The agent will not remember A.
- Ask for the first coherent slice plus a precise "what is left" when unsure.

## Things that are never delegated

- Applying database migrations: the Maestro applies them after the human merges the PR.
- Merging: only the human merges. `main` deploys to production.
- Test, draft or example tasks: some projects sync every new task to a real GitHub issue.

## After creating

Tell the human what was created, for which agent, in which project. When a task finishes,
report the PR URL from the agent's result, never "it is live". Production happens at merge.
