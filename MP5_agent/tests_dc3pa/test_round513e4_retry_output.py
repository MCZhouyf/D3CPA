from pathlib import Path

import pytest

from scripts_dc3pa.stage6_run_minecraft import (
    _ROUND513_DISPOSITION_DIRECTORIES,
    _round513_output_root_is_logically_empty,
)


def test_round513_retry_accepts_only_empty_disposition_skeleton(tmp_path: Path):
    output_root = tmp_path / "output"

    assert _round513_output_root_is_logically_empty(output_root)
    output_root.mkdir()
    assert _round513_output_root_is_logically_empty(output_root)

    for name in _ROUND513_DISPOSITION_DIRECTORIES:
        (output_root / name).mkdir()
    assert _round513_output_root_is_logically_empty(output_root)


@pytest.mark.parametrize("entry_kind", ["record", "unknown_dir", "nested_dir"])
def test_round513_retry_rejects_nonempty_or_unknown_output(tmp_path: Path, entry_kind: str):
    output_root = tmp_path / "output"
    accepted = output_root / "accepted_scientific"
    accepted.mkdir(parents=True)

    if entry_kind == "record":
        (accepted / "record.json").write_text("{}", encoding="utf-8")
    elif entry_kind == "unknown_dir":
        (output_root / "unexpected").mkdir()
    else:
        (accepted / "nested").mkdir()

    assert not _round513_output_root_is_logically_empty(output_root)


def test_round513_retry_rejects_files_and_symlinks(tmp_path: Path):
    output_file = tmp_path / "output"
    output_file.write_text("not a directory", encoding="utf-8")
    assert not _round513_output_root_is_logically_empty(output_file)

    output_file.unlink()
    target = tmp_path / "target"
    target.mkdir()
    output_file.symlink_to(target, target_is_directory=True)
    assert not _round513_output_root_is_logically_empty(output_file)
