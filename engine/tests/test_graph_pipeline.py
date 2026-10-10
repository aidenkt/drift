"""pipeline.run end to end, with the checks half absent and with it stubbed."""

import json
from pathlib import Path

import jsonschema
import openpyxl
import pytest

import pipeline
from checks import label, series

SCHEMA = json.loads((Path(__file__).parents[2] / "schema" / "constant.schema.json").read_text())


@pytest.fixture
def model(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Model"
    ws["A1"], ws["B1"] = "EUR/USD rate", 1.25
    ws["A2"], ws["B2"] = "Units", 100
    ws["A3"], ws["B3"] = "EBITDA", "=B2*B1*0.5"
    path = tmp_path / "model.xlsx"
    wb.save(path)
    return path


def _run(path):
    return pipeline.run(path, model_id="m1", filename="model.xlsx", built_on="2026-08-01")


def test_report_is_valid_when_the_checks_half_is_not_implemented(model, monkeypatch):
    def missing(*args):
        raise NotImplementedError

    monkeypatch.setattr(label, "apply", missing)
    report = _run(model)
    jsonschema.validate(report, SCHEMA)
    assert [c["cell"] for c in report["constants"]] == ["Model!B1", "Model!B2", "Model!B3"]
    assert all(c["check"] is None and c["impact"] == [] for c in report["constants"])
    # never calculated by Excel, so the value comes from the recalculation
    assert report["outputs"] == [{"cell": "Model!B3", "label": "EBITDA", "value": 62.5}]
    assert report["combined"] == []


def test_a_live_value_flows_through_to_impact(model, monkeypatch):
    def apply(c, wb):
        c["label"] = wb.context(c["cell"])["row_label"] or ""
        c["driver"] = "eurusd" if c["cell"] == "Model!B1" else None

    def check(c, built_on):
        return {"kind": "series", "status": "stale", "live": 1.5, "evidence": []}

    monkeypatch.setattr(label, "apply", apply)
    monkeypatch.setattr(series, "check", check)
    report = _run(model)
    jsonschema.validate(report, SCHEMA)

    fx = report["constants"][0]  # sorted by impact, so the only constant with one comes first
    assert fx["cell"] == "Model!B1"
    assert fx["impact"] == [{"output": "Model!B3", "delta": pytest.approx(12.5)}]
    assert report["combined"] == [{"output": "Model!B3", "delta": pytest.approx(12.5)}]
    assert [c["check"] for c in report["constants"][1:]] == [None, None]
