# DC3PA Round 5.9.1 author-approved readiness

Round 5.9.1 starts from commit
`57ab59d8cb99edb448fabc7cb74aea8d587e9341` and keeps ZYF-confirmed inputs
and all generated experiment evidence outside Git.

The repository adapters export the current MineDojo item registry, load each
candidate task through the existing Stage6 task loader, and construct the
unchanged Evaluator environment only after every referenced name has one exact
normalized match. Candidate descriptors never become runtime evidence through
fuzzy matching.

The supplied 50-task catalog has ten tasks in each of Basic, Easy, Medium,
Hard, and Complex and includes `craft bucket` once in Hard. Formal validation
is fail-closed if any target, material, tool, or platform is unresolved or
ambiguous.

Schema v1 may only be reconstructed from commit `15aa529` and must be labeled
`reconstructed schema-v1 consistency check`. It is not an official historical
artifact. Schema migration, ZYF approval, prompt and runtime identities, model
epoch, MineDojo marker receipt, six-entry dry run, and final readiness remain
immutable external artifacts.

Formal acquisition remains single-chain reactive. Round 5.9.1 does not
implement or activate Dual Chain, Fusion, Adaptive Trigger, or Trigger V2.
