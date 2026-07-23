# Round 5.13E0R prospective authoritative re-baseline

Round 5.13E0R establishes a candidate provenance root over the actual immutable
Paper Memory V5 bytes. It does not repair or equate the invalid historical
MineCLIP, snapshot-manifest, acquisition-manifest, or Scene-release identities.

The closure distinguishes two acquisition manifests. The accepted source
manifest and the snapshot-local build-output manifest use different canonical
root algorithms and have different file identities, but contain the same 184
path-to-hash entries. The former is retained only as builder evidence; the
prospective candidate binds the actual snapshot-local manifest.

MineCLIP-to-embedding evidence uses path `P1`. The immutable rebuild contract
binds the verified policy, checkpoint, accepted source file map, builder source
commit, and encoder configuration. The actual snapshot metadata binds that
contract and policy to the database, while the snapshot manifest binds the
complete database hash. No re-encoding tolerance is needed and no vector is
re-encoded or replaced.

The 40 accepted episode receipts contain 144 frozen Scene candidates from 36
episodes. The four successful `mine log` receipts contain no valid Scene
candidate, matching the frozen lineage audit's `no_valid_scene_candidate`
retention reason. This is a retention-metadata explanation, not an inference
from task outcome.

All pre-approval releases are DRAFT candidates with `usable=false`.
Contract regeneration, V4.1.2 validation, smoke preparation, MineDojo,
formal Development, CHRM/CDT fitting, Holdout, final evaluation, and Round 6
remain prohibited until their respective author boundaries are satisfied.
