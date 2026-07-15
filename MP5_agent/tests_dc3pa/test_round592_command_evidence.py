import sys

from dc3pa.experiments.command_evidence import run_command_evidence


def test_command_evidence_captures_hashes_and_pass_count(tmp_path):
    result = run_command_evidence(
        evidence_name="synthetic-marker",
        source_commit="commit",
        command=[sys.executable, "-c", "print('3 passed')"],
        cwd=tmp_path,
        output_root=tmp_path / "evidence",
    )
    assert result.passed
    assert result.parsed_passed_count == 3
    assert result.stdout_sha256
    assert result.stderr_sha256
