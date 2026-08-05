#!/usr/bin/env bash
set -euo pipefail

# Stable RTX-backed rendering for the RealVNC desktop.  Strict synchronization
# and disabled frame spoiling prevent the alternating black/stale frames that
# VirtualGL's latency-oriented defaults can produce over VNC.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${DC3PA_PYTHON:-/root/miniconda3/envs/MP5_agent/bin/python}"

export DISPLAY="${DISPLAY:-:3}"
export DC3PA_IMAGE_WIDTH="${DC3PA_IMAGE_WIDTH:-1640}"
export DC3PA_IMAGE_HEIGHT="${DC3PA_IMAGE_HEIGHT:-1024}"

if command -v xset >/dev/null 2>&1; then
    xset s off >/dev/null 2>&1 || true
    xset -dpms >/dev/null 2>&1 || true
fi

cd "$repo_root"
exec vglrun -d egl -c proxy +sync -sp -fps 30 \
    "$python_bin" -m dc3pa_stage_a.run_stage_a_episode "$@"
