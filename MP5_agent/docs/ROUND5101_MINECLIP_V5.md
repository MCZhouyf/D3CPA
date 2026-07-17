# Round 5.10.1 pressure-plate taskset and MineCLIP Memory V5

Round 5.10.1 creates a superseding active taskset in which
`craft wooden pressure plate` is the sole active task for its Basic slot. The
historical migration contract and signed acquisition evidence remain immutable.
Future phases must use the eligible active taskset release produced by
`build_active_pressure_plate_taskset.py`,
`audit_active_pressure_plate_taskset.py`, and
`freeze_active_pressure_plate_release.py`.

Memory V5 is rebuilt offline from the unchanged 40 successful Round 5.10
acquisition records. It uses the official MineCLIP `attn` model at repository
commit `e6c06a0245fac63dceb38bc9bd4fecd033dae735`. One pre-action RGB image is
resized to 160 by 256, repeated as 16 identical frames, encoded as video, and
L2-normalized. Text is tokenized with the same model and L2-normalized in the
same 512-dimensional joint space.

The checkpoint, acquisition files, images, databases, manifests, releases,
comparison reports, and coverage reports stay outside Git. The V5 pipeline
fails closed rather than falling back to OpenAI CLIP, histogram, or hashing
encoders. V4 remains available as an engineering-only snapshot; V5 becomes the
paper-candidate pointer only after checkpoint probing, read-only smoke,
V4/V5 structural comparison, and coverage audit are all eligible.

This round starts no MineDojo episode and performs no development collection,
confidence calibration, environment tuning, fusion fitting, held-out test, or
Round 6 run.
