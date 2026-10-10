from pathlib import Path

import pytest

DATA = Path(__file__).parents[2] / "data"
CASES = [
    (DATA / "case_study_aug2026.xlsx", DATA / "ground_truth.md"),
    (DATA / "case_study_aug2025.xlsx", DATA / "ground_truth_aug2025.md"),
    (DATA / "case_study_airline.xlsx", DATA / "ground_truth_airline.md"),
    (DATA / "case_study_homebuilder.xlsx", DATA / "ground_truth_homebuilder.md"),
    (DATA / "case_study_coffee.xlsx", DATA / "ground_truth_coffee.md"),
    (DATA / "case_study_trucking.xlsx", DATA / "ground_truth_trucking.md"),
]


@pytest.mark.parametrize("xlsx,truth", CASES, ids=lambda p: p.stem)
def test_flags_planted_constants(xlsx, truth):
    if not xlsx.exists():
        pytest.skip("case study workbook not added yet")
    # TODO: run pipeline on xlsx, compare stale flags to truth
    pytest.skip("pipeline not implemented")
