from __future__ import annotations

from dc3pa.experiments.author_decisions import prompt_hashes


def test_prompt_hash_changes_when_content_changes(tmp_path):
    path = tmp_path / "planner.txt"
    path.write_text("first", encoding="utf-8")
    first = prompt_hashes({"planner": path})
    path.write_text("second", encoding="utf-8")
    second = prompt_hashes({"planner": path})
    assert first["planner"] != second["planner"]
