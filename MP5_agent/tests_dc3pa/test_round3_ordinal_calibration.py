from dc3pa.reliability.ordinal_calibration import (
    OrdinalCalibrationArtifact,
    OrdinalCalibrationSample,
    fit_ordinal_calibration,
)


def test_pav_fixes_non_monotone_empirical_rates_and_roundtrips(tmp_path):
    samples = []
    # Deliberately non-monotone: unlikely > uncertain before PAV.
    for index, (level, positives, total) in enumerate(
        [
            ("very_unlikely", 0, 4),
            ("unlikely", 4, 5),
            ("uncertain", 1, 5),
            ("likely", 4, 5),
            ("very_likely", 5, 5),
        ]
    ):
        samples.extend(
            OrdinalCalibrationSample(level, 1 if item < positives else 0, f"{index}-{item}")
            for item in range(total)
        )
    artifact = fit_ordinal_calibration(
        samples,
        model_id="model",
        prompt_version="v1",
        prompt_sha256="prompt",
        created_from_commit="commit",
        min_total_samples=1,
        min_observed_levels=1,
    )
    values = list(artifact.calibrated_mapping.values())
    assert values == sorted(values)
    assert artifact.metrics["calibrated_brier"] >= 0
    path = artifact.save(tmp_path / "artifact.json")
    loaded = OrdinalCalibrationArtifact.load(path)
    assert loaded.to_dict() == artifact.to_dict()
    loaded.validate_compatibility(
        model_id="model", prompt_version="v1", prompt_sha256="prompt"
    )


def test_missing_levels_are_filled_monotonically():
    artifact = fit_ordinal_calibration(
        [
            OrdinalCalibrationSample("unlikely", 0, "a"),
            OrdinalCalibrationSample("likely", 1, "b"),
        ],
        model_id="model",
        prompt_version="v1",
        prompt_sha256="prompt",
        created_from_commit="commit",
    )
    values = list(artifact.calibrated_mapping.values())
    assert values == sorted(values)
    assert artifact.sample_counts["uncertain"]["total"] == 0
