# Round 5.10 taskset amendment

The author replaces `mine sand` with `craft wooden pressure plate` after the
first Round 5.10 campaign exposed unbounded resource search for sand. The
replacement occupies the same Basic task slot and reuses the four frozen
acquisition seeds. This preserves 50 total tasks, ten tasks per difficulty and
the acquisition execution order.

The runtime creative payload is the previously supplied ZYF asset:

```json
[
  {
    "task": "wooden pressure plate",
    "quantity": 1,
    "material": {
      "planks": 2
    },
    "tool": null,
    "platform": "crafting table"
  }
]
```

The prior campaign, Blueprint, schedule, authorization and acquisition records
remain immutable and superseded. They cannot be combined with results produced
under the amended taskset. Controller, Evaluator, prompts, model policy, Log
Bootstrap policy, execution budgets and all non-task seeds remain unchanged.
