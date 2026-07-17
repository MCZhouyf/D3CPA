from dc3pa.experiments.development_records import audit_development_collection
from tests_dc3pa.round511_test_utils import make_record


def test_development_collection_uses_one_readonly_v5_and_no_holdout():
    records = [
        make_record("train", role="dev_train"),
        make_record("tune", role="dev_tune", correct=False),
    ]
    report = audit_development_collection(
        records,
        collection_id="collection",
        development_input_release_id="dev-input",
        development_protocol_id="protocol",
        paper_memory_v5_release_id="memory-v5",
        source_commit="a" * 40,
    )
    assert report.eligible
    assert report.memory_write_count == 0
    assert report.holdout_record_count == 0
