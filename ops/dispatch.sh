#!/bin/bash
# Triggers Mission Control's task dispatcher. Runs from a systemd timer every 10 minutes.
#
# WHY A SYSTEMD TIMER AND NOT THE BUILT-IN SCHEDULER: Mission Control ships an `initScheduler()`
# with `task_dispatch` registered and `enabled: true`, but nothing ever calls it. There is no
# `instrumentation.ts`, so the periodic loop never starts. That is why the fleet went weeks
# without dispatching anything while the UI said scheduling was on.
#
# It could be fixed by calling `initScheduler()` at Next.js startup. I chose the timer instead:
# it survives restarts and rebuilds, it shows up in the same cron mirror as every other routine,
# and the cadence changes without recompiling.
set -euo pipefail
: "${MC_URL:?set MC_URL}"
: "${MC_API_KEY:?set MC_API_KEY}"

R=$(curl -s -m 600 -X POST -H "x-api-key: $MC_API_KEY" -H 'Content-Type: application/json' \
      -d '{"task_id":"task_dispatch"}' "$MC_URL/api/scheduler")
echo "$R"
# "No tasks" is the normal case: don't fill the journal with empty successes.
echo "$R" | grep -q '"ok":true' || exit 1
