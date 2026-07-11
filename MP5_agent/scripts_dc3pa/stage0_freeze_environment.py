#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from pathlib import Path


def _command(command):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=30,
        )
        return {"return_code": result.returncode, "output": result.stdout}
    except Exception as exc:
        return {"return_code": None, "output": f"{type(exc).__name__}: {exc}"}


_CREDENTIAL_IN_URL = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)[^/@\s]+@")


def _redact_credentials(text: str) -> str:
    return _CREDENTIAL_IN_URL.sub(r"\g<scheme><redacted>@", text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze the active MP5 environment")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    freeze = _command([sys.executable, "-m", "pip", "freeze"])
    (output / "pip-freeze.txt").write_text(
        _redact_credentials(freeze["output"]), encoding="utf-8"
    )
    system = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "java_version": _command(["java", "-version"]),
        "nvidia_smi": _command(["nvidia-smi"]),
        "pip_freeze_return_code": freeze["return_code"],
    }
    (output / "system.json").write_text(
        json.dumps(system, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote environment snapshot to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
