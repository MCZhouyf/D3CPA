# Stage A analysis

## A. Low-level substitute scope

- tasks in run: 7
- tasks touched by the substitute: 2 (28.6%)
- affected: diamond, redstone

| tier | tasks | affected |
| --- | ---: | ---: |
| basic | 2 | 0 |
| complex | 2 | 2 |
| easy | 1 | 0 |
| hard | 1 | 0 |
| medium | 1 | 0 |

| task | calls | granted items |
| --- | ---: | --- |
| diamond | 27 | coal×27, cobblestone×27, iron ore×27 |
| redstone | 27 | coal×27, cobblestone×27, iron ore×27 |

## B. Per-mode symmetry

| runtime mode | episodes | calls | calls/episode | episodes touched |
| --- | ---: | ---: | ---: | ---: |
| dc3pa | 84 | 18 | 0.214 | 6 (7.1%) |
| mp5_legacy | 84 | 18 | 0.214 | 6 (7.1%) |
| reasoning_only | 84 | 18 | 0.214 | 6 (7.1%) |

- calls/episode relative spread: 0.0%
- within 10%: True

## C. Order invariance

| memory mode | compared pairs | agreed | agreement |
| --- | ---: | ---: | ---: |
| acquire | 63 | 23 | 36.5% |
| evaluate_readonly | 63 | 63 | 100.0% |

## D. Dual population success rate

| runtime mode | all tasks | substitute-free tasks |
| --- | ---: | ---: |
| dc3pa | 61.9% (52/84) | 61.7% (37/60) |
| mp5_legacy | 45.2% (38/84) | 46.7% (28/60) |
| reasoning_only | 59.5% (50/84) | 61.7% (37/60) |
