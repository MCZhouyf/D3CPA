import importlib.util
from pathlib import Path


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts_dc3pa" / "stage0_freeze_environment.py"
    spec = importlib.util.spec_from_file_location("stage0_freeze_environment", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_freeze_redacts_url_credentials():
    module = _load_script()
    raw = "pkg @ git+https://user:token@example.com/repo.git\nplain==1.0\n"
    redacted = module._redact_credentials(raw)
    assert "user:token" not in redacted
    assert "https://<redacted>@example.com" in redacted
    assert "plain==1.0" in redacted
