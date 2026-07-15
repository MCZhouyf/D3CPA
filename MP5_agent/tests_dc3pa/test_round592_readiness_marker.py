from scripts_dc3pa.audit_acquisition_readiness import (
    marker_evidence_passed,
)


def marker(**changes):
    value = {
        "passed": True,
        "exit_code": 0,
        "parsed_passed_count": 18,
        "source_commit": "commit",
        "stdout_sha256": "stdout",
        "stderr_sha256": "stderr",
        "started_at": "start",
        "finished_at": "finish",
    }
    value.update(changes)
    return value


def test_command_evidence_pass_count_is_accepted():
    assert marker_evidence_passed(marker(), "commit")


def test_zero_command_evidence_pass_count_fails_closed():
    assert not marker_evidence_passed(
        marker(parsed_passed_count=0), "commit"
    )
