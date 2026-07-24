# Round 5.13E3 formal-50 smoke alignment

The successor Engineering Smoke retains nine assignments across all five
difficulty levels, but every task must resolve to an entry in the formal
50-task catalog. The historical E1R generator and artifacts remain unchanged.

The formal catalog has no combat goal. The successor therefore replaces the
find-only `creature` proxy with the Hard, experience-covered task `smelt iron
ingot`, represented by `agent/tasks/creative/iron_ingot.json`. Furnace
processing uses the legacy `craft` action contract. The smoke deliberately
omits `fight` rather than claiming unsupported semantic coverage.

The successor uses a new deterministic namespace so its task-seed assignments
cannot overlap the historical smoke namespace. It remains engineering-only,
fitting-ineligible, outcome-independent, and no-write. Freeze it explicitly
with `--formal-50-task-smoke`; the default freeze path still reproduces E1R.

## Planner compatibility hardening

Track-E requests OpenAI-compatible JSON object mode for its one Planner call.
The bound Planner output schema now declares the exact legacy Controller
argument names for all nine action families, and OneCallPlanner formats the
prompt with that bound schema rather than a global fallback. The strict JSON
parser, same-generation confidence, one-call limit, and no-retry malformed
policy remain unchanged.

A credentialed provider probe against `glm-5.2` returned strict JSON and a
Controller-compatible `find` action with the required `obj` argument in one
call. Provider response content and credentials are not retained. Because the
output schema changes, its schema ID and parser ID must be regenerated and
explicitly rebound before another source-frozen campaign is authorized.
