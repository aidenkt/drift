from pathlib import Path

import pytest

XLSX = Path(__file__).parents[2] / "data" / "Drift_Hertz_Mock_Fleet_Model.xlsx"


@pytest.mark.skipif(not XLSX.exists(), reason="case study workbook not added yet")
def test_flags_planted_constants():
    # TODO: run pipeline on XLSX, compare stale flags to data/ground_truth.md
    pytest.skip("pipeline not implemented")
