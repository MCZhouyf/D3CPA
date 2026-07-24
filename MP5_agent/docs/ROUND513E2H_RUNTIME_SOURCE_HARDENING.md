# Round 5.13E2H runtime source hardening

E2H keeps the V4.1.2 scientific method and Candidate B unchanged. It adds a
versioned, fail-closed contract adapter, separates contract authoring commits
from the execution source, expands the Track E binding, makes every smoke-data
eligibility field explicit, and separates scientific records from technical
quarantine.

The previously valid smoke authorization is preserved but superseded before
execution. No environment was started and no outcome was observed under it.

The repository contains no unique, complete, prospectively authorized E2
technical-retry and process-cleanup policy. Existing retry evidence is scoped
to earlier Acquisition/Holdout work, and the legacy cleanup helper does not
provide campaign-owned process, port, lock, or display-session guarantees.
ZYF subsequently selected the prospective T1 one-retry and C1 scoped-cleanup
policies. Technical retries are restricted to four enumerated pre-action
failures, one retry, and isolated output; scientific outcomes remain final.
Cleanup is restricted to resources recorded in the campaign launch-ownership
ledger and may not kill unrelated processes.

The external freeze tool can now create the runtime release, re-seal the same
nine scientific assignment payloads under the R1 schema, and create a new
pending Smoke Authorization Input. This source-hardening round still cannot
start MineDojo; execution requires a subsequent source-frozen authorization.

The pre-execution execution amendment also binds each assignment's numeric seed
in both the R1 Run Binding and Execution Manifest. The runner requires the same
`PYTHONHASHSEED` at process start, applies the world and simulator seed before
environment construction, and verifies the effective simulator values. Track-E
state snapshots derive their pre-action image vector only through the injected
frozen MineCLIP image encoder; malformed vectors fail closed.

Planner identity uses the canonical definitions exposed by
`CHRMLitePlannerOutputSchemaV4_1`: Prompt ID hashes the object containing
`prompt_template`; Parser ID hashes `parser_policy`, `malformed_policy`, and
`output_schema`. Freeze, R1 preflight, and OneCallPlanner metadata use these
same properties. Hashing only the raw prompt or parser-policy string is
rejected before environment construction.
