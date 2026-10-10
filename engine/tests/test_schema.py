import json
from pathlib import Path

import jsonschema

SCHEMA = Path(__file__).parents[2] / "schema"


def test_fixture_matches_schema():
    schema = json.loads((SCHEMA / "constant.schema.json").read_text())
    fixture = json.loads((SCHEMA / "fixtures" / "case_study.json").read_text())
    jsonschema.validate(fixture, schema)
