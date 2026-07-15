import pytest

from dc3pa.reliability.ordinal_confidence import parse_ordinal_confidence
from dc3pa.reliability.ordinal_levels import normalize_ordinal_level


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"confidence_level":"very_unlikely","reason":"x"}', "very_unlikely"),
        ('```json\n{"confidence_level":"Likely","reason":"x"}\n```', "likely"),
        ({"confidence_level": "Very likely", "reason": "x"}, "very_likely"),
    ],
)
def test_parse_valid_ordinal_confidence(raw, expected):
    level, reason, metadata = parse_ordinal_confidence(raw)
    assert level == expected
    assert reason == "x"
    assert metadata["protocol"] == "ordinal_v2"


@pytest.mark.parametrize(
    "raw",
    [0.82, "0.82", {"confidence": 0.8}, {"confidence_level": "mostly_likely"}],
)
def test_parse_rejects_numeric_or_unknown_protocol(raw):
    with pytest.raises(ValueError):
        parse_ordinal_confidence(raw)


def test_normalizer_accepts_formatting_not_synonyms():
    assert normalize_ordinal_level("VERY-LIKELY") == "very_likely"
    with pytest.raises(ValueError):
        normalize_ordinal_level("high")
