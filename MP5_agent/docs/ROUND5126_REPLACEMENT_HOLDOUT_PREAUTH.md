# DC3PA Round 5.12.6 Replacement Holdout Pre-Authorization

## Scope

Round 5.12.6 currently contains engineering contracts and tests only. No fresh
assignment was generated, no assignment bundle was read, no ledger was opened,
and no MineDojo campaign or locked evaluation was started. Final evaluation and
Round 6 remain closed.

The supplied startup SHA `db72ed2` was not the repository HEAD. Review began
from `104e5f1b3f561e260eddbcea0b478adc37d1fd10`, which contains the later
preflight, provider-transport classification, and observational report commits.
This discrepancy was handled fail-closed rather than silently rewriting history.

## Review Pass 1

Repository reconnaissance covered the frozen candidate and activation policy,
component releases, Paper Memory V5, pressure-plate taskset, Controller,
evaluator, prompts, execution budget, Log Bootstrap, prior holdout ledgers,
replacement generator, and historical gates. The candidate remains
`8e5376a7aa0aefd7b4f3fe6ece78c9148b108f7705d746824651848e0e4b82e1`.
The complete budget remains 30-second action steps, 3,600-second episodes, four
execution attempts, 120 exploration steps, four replans, two technical retries,
three provider retries, and a 180-second provider timeout.

The review found that `35472b9` changed structured provider-transport failure
classification after `db72ed2`. The author approved treating that exact change
as the engineering retry baseline. The external amendment SHA-256 is
`eb08d433d98e90084f8736cb7763deb6ea6049cfa17f4345eb9d2d994e6bc6db`.
The approval does not authorize assignment generation. All other protected
scientific artifacts must remain byte- and identity-equal; the binding rejects
any other exception.

## Review Pass 2

The prior replacement generator was not safe for confirmatory reuse because it
accepted free-form authorization and did not prove exclusions against every
historical and reserved set. The new generator has no outcome/label input,
requires a hash-bound ZYF authorization, uses a prospectively committed disjoint
seed namespace, preserves 15 assignments with three per frozen stratum, and
rejects collisions without outcome-dependent resampling.

The observational set remains `observational_only`; its 15 outcomes cannot be
used for fitting, activation, task selection, seed selection, or budget changes.
The failed-prelaunch set remains `permanently_retired`. Neither assignment set
may be copied, rerun, or reopened.

The new ledger persists `claimed` under an OS lock before invoking the bundle
reader. Concurrent or repeated claims fail, scientific outcomes cannot retry,
attempt 3 is rejected before environment launch, unclassified technical failures
block the campaign, and only accepted scientific rows can enter evaluation.

## Authorization Boundary

The three repository contracts are deliberately DRAFTs. A complete external,
hash-bound ReplacementHoldoutAuthorization must bind the final source SHA,
preflight binding, runtime release, exclusion registry, protected artifact IDs
and hashes, frozen design, and fresh namespace commitment. Until that artifact
exists, assignment generation and ledger creation are forbidden.
