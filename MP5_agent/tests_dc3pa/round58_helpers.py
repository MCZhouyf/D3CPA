from __future__ import annotations

from dc3pa.experiments.reference_design import (
    DIFFICULTIES,
    ReferenceDesignConfig,
    TaskCatalogEntry,
    build_reference_design,
)


def catalog():
    entries = []
    for difficulty_index, difficulty in enumerate(DIFFICULTIES):
        for index in range(10):
            entries.append(
                TaskCatalogEntry(
                    task=f"{difficulty}-task-{index}",
                    difficulty=difficulty,
                    minimum_subgoals=1 + difficulty_index * 3 + index // 2,
                )
            )
    return tuple(entries)


def design():
    return build_reference_design(
        catalog(),
        config=ReferenceDesignConfig(source_commit="commit"),
    )
