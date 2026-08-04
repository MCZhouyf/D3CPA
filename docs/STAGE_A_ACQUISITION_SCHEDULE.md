# Stage A acquisition-schedule decision

## Inspected source

`/root/autodl-tmp/dc3pa-round510-pressure-plate/formal_acquisition_schedule.json`
was inspected only. Its campaign metadata identifies it as
`dc3pa-round510-pressure-plate-formal-acquisition-v1`, method
`single_chain_reactive_acquisition`, scope `formal_acquisition`, source commit
`b84252c4cc51a8599ee88449dc36ac66d7c9fef5`, with 100 scheduled episodes.

## Relationship to the formal 50-task registry

| Measure | Result |
| --- | ---: |
| Schedule entries / distinct scheduled tasks | 100 / 25 |
| Current formal catalog tasks | 50 |
| Name overlap | 22 |
| Schedule-only names | 3 (`craft diamond axe`, `craft fence`, `craft shears`) |
| Current-catalog-only names | 28 |
| Old schedule seeds / proposed diagnostic seeds | 100 / 6 |
| Seed overlap | 0 |

The overlap means this is not an automatically compatible acquisition state for
the current 50-task evaluation. The seeds are separate, and the source is
explicitly an acquisition campaign, so it is a **candidate for human approval
only**. It has not been adopted, executed, copied into a snapshot, or used by
any Stage A run. No acquisition run may begin without approval of an exact
snapshot manifest/root bound to the current task registry.
