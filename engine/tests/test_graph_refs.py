import pytest

from graph.refs import expand_range, make_key, parse_ref, ref_cells, split_key

# (min_row, min_col, max_row, max_col)
BOUNDS = {"Model": (1, 1, 5, 4), "Assumptions": (2, 2, 4, 3), "My Sheet": (1, 1, 2, 2)}


def keys(sheet: str, *coords: str) -> list[str]:
    return [f"{sheet}!{coord}" for coord in coords]


def test_make_and_split_key_round_trip():
    assert make_key("Assumptions", "$c$14") == "Assumptions!C14"
    assert split_key("Assumptions!C14") == ("Assumptions", "C14")


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("B5", ("Model", "B5")),
        ("$B$5", ("Model", "B5")),
        ("b5", ("Model", "B5")),
        ("B$5", ("Model", "B5")),
        ("XFD1048576", ("Model", "XFD1048576")),
        ("TAX1", ("Model", "TAX1")),
        ("A1:C3", ("Model", "A1:C3")),
        ("$A$1:$C$3", ("Model", "A1:C3")),
        ("a1:c3", ("Model", "A1:C3")),
        ("A:A", ("Model", "A:A")),
        ("A:C", ("Model", "A:C")),
        ("$A:$C", ("Model", "A:C")),
        ("1:3", ("Model", "1:3")),
        ("$1:$3", ("Model", "1:3")),
    ],
)
def test_parse_ref_without_sheet_uses_current_sheet(ref, expected):
    assert parse_ref(ref, "Model") == expected


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("Assumptions!C14", ("Assumptions", "C14")),
        ("assumptions!c14", ("assumptions", "C14")),
        ("Sheet1!A1:B2", ("Sheet1", "A1:B2")),
        ("Sheet2!B:B", ("Sheet2", "B:B")),
        ("Sheet2!$2:$4", ("Sheet2", "2:4")),
        ("FY24.Q1_v2!A1", ("FY24.Q1_v2", "A1")),
        ("'My Sheet'!$B$4", ("My Sheet", "B4")),
        ("'My Sheet'!$A$1:$C$3", ("My Sheet", "A1:C3")),
        ("'Bob''s Sheet'!A1", ("Bob's Sheet", "A1")),
        ("'P&L (2024)'!D7", ("P&L (2024)", "D7")),
        ("'Assumptions'!C14", ("Assumptions", "C14")),
    ],
)
def test_parse_ref_with_sheet(ref, expected):
    assert parse_ref(ref, "Model") == expected


@pytest.mark.parametrize(
    "ref",
    [
        "[Book2.xlsx]Sheet1!A1",
        "'[Book2.xlsx]Sheet1'!A1",
        "'[Book2.xlsx]My Sheet'!$A$1:$B$2",
        r"'C:\path\[Book2.xlsx]Sheet1'!A1",
        "[1]Sheet1!A1",
        "'[1]Sheet1'!A:A",
    ],
)
def test_parse_ref_external_workbook_is_none(ref):
    assert parse_ref(ref, "Model") is None


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "TaxRate",
        "TRUE",
        "#REF!",
        "#REF!A1",
        "Sheet1!#REF!",
        "Sheet1!TaxRate",
        "A",
        "5",
        "A0",
        "A01",
        "ABCD1",
        "A1:B",
        "A:1",
        "A1:B2:C3",
        "A1 ",
        "Sheet1!",
        "!A1",
        "''!A1",
        "'My Sheet!A1",
        "My Sheet!A1",
        "Sheet1:Sheet3!A1",
        "'Sheet1:Sheet3'!A1",
        "Sheet1!A1:Sheet1!B2",
    ],
)
def test_parse_ref_non_reference_is_none(ref):
    assert parse_ref(ref, "Model") is None


def test_parse_ref_never_raises_on_non_string():
    assert parse_ref(None, "Model") is None
    assert parse_ref(42, "Model") is None


def test_expand_single_coord():
    assert expand_range("Model", "B5") == ["Model!B5"]


def test_expand_range_is_row_major():
    expected = keys("Model", "A1", "B1", "C1", "A2", "B2", "C2", "A3", "B3", "C3")
    assert expand_range("Model", "A1:C3") == expected


@pytest.mark.parametrize("rng", ["C3:A1", "A3:C1", "C1:A3"])
def test_expand_range_normalises_reversed_corners(rng):
    assert expand_range("Model", rng) == expand_range("Model", "A1:C3")


def test_expand_range_crosses_single_to_double_letter_columns():
    assert expand_range("Model", "Z1:AB1") == keys("Model", "Z1", "AA1", "AB1")


def test_expand_range_keeps_sheet_name_verbatim():
    assert expand_range("Bob's Sheet", "A1:A2") == ["Bob's Sheet!A1", "Bob's Sheet!A2"]


def test_expand_range_clips_to_bounds():
    assert expand_range("S", "A1:D4", (2, 2, 3, 3)) == keys("S", "B2", "C2", "B3", "C3")
    assert expand_range("S", "A1:Z1000", (1, 1, 2, 2)) == keys("S", "A1", "B1", "A2", "B2")
    assert expand_range("S", "B2:C3", (1, 1, 10, 10)) == keys("S", "B2", "C2", "B3", "C3")


def test_expand_range_outside_bounds_is_empty():
    assert expand_range("S", "F10:G12", (1, 1, 5, 4)) == []
    assert expand_range("S", "A10:B12", (1, 1, 5, 4)) == []
    assert expand_range("S", "F1:G2", (1, 1, 5, 4)) == []


def test_expand_single_coord_outside_bounds_is_kept():
    assert expand_range("S", "Z99", (1, 1, 5, 4)) == ["S!Z99"]


def test_expand_whole_columns_span_bounds_rows():
    assert expand_range("S", "A:A", (2, 1, 4, 3)) == keys("S", "A2", "A3", "A4")
    assert expand_range("S", "C:B", (2, 1, 3, 3)) == keys("S", "B2", "C2", "B3", "C3")
    assert expand_range("S", "C:F", (1, 1, 2, 4)) == keys("S", "C1", "D1", "C2", "D2")
    assert expand_range("S", "F:G", (1, 1, 2, 4)) == []


def test_expand_whole_rows_span_bounds_columns():
    assert expand_range("S", "2:2", (1, 2, 5, 4)) == keys("S", "B2", "C2", "D2")
    assert expand_range("S", "3:2", (1, 1, 5, 2)) == keys("S", "A2", "B2", "A3", "B3")
    assert expand_range("S", "4:9", (1, 1, 5, 2)) == keys("S", "A4", "B4", "A5", "B5")
    assert expand_range("S", "8:9", (1, 1, 5, 2)) == []


@pytest.mark.parametrize("rng", ["A:C", "A:A", "1:3", "2:2"])
def test_expand_whole_row_or_column_without_bounds_raises(rng):
    with pytest.raises(ValueError):
        expand_range("S", rng)


@pytest.mark.parametrize("rng", ["A1:B", "A:1", "A1:", ":", "A1:B2:C3"])
def test_expand_malformed_range_raises(rng):
    with pytest.raises(ValueError):
        expand_range("S", rng, (1, 1, 5, 5))


def test_ref_cells_on_current_sheet():
    assert ref_cells("$B$2", "Model", BOUNDS) == ["Model!B2"]
    assert ref_cells("A1:B2", "Model", BOUNDS) == keys("Model", "A1", "B1", "A2", "B2")


def test_ref_cells_cross_sheet_range_is_clipped_to_that_sheet():
    assert ref_cells("Assumptions!A1:C3", "Model", BOUNDS) == keys(
        "Assumptions", "B2", "C2", "B3", "C3"
    )
    assert ref_cells("'My Sheet'!$A$1:$C$3", "Model", BOUNDS) == keys(
        "My Sheet", "A1", "B1", "A2", "B2"
    )


def test_ref_cells_whole_column_and_row_use_sheet_bounds():
    assert ref_cells("Assumptions!B:B", "Model", BOUNDS) == keys("Assumptions", "B2", "B3", "B4")
    assert ref_cells("3:3", "Model", BOUNDS) == keys("Model", "A3", "B3", "C3", "D3")


def test_ref_cells_single_cell_outside_bounds_is_kept():
    assert ref_cells("Assumptions!Z99", "Model", BOUNDS) == ["Assumptions!Z99"]


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("assumptions!c3", ["Assumptions!C3"]),
        ("ASSUMPTIONS!$C$3", ["Assumptions!C3"]),
        ("'my sheet'!A1", ["My Sheet!A1"]),
        ("'MY SHEET'!a1:b1", ["My Sheet!A1", "My Sheet!B1"]),
    ],
)
def test_ref_cells_resolves_sheet_case_insensitively(ref, expected):
    assert ref_cells(ref, "Model", BOUNDS) == expected


def test_ref_cells_resolves_current_sheet_case_insensitively():
    assert ref_cells("A1", "model", BOUNDS) == ["Model!A1"]


def test_ref_cells_prefers_exact_sheet_spelling():
    bounds = {"data": (1, 1, 1, 1), "Data": (1, 1, 1, 1)}
    assert ref_cells("Data!A1", "data", bounds) == ["Data!A1"]
    assert ref_cells("data!A1", "Data", bounds) == ["data!A1"]


@pytest.mark.parametrize(
    "ref",
    [
        "Missing!A1",
        "'No Such Sheet'!A1:B2",
        "[Book2.xlsx]Model!A1",
        "'[Book2.xlsx]Model'!A1",
        r"'C:\path\[Book2.xlsx]Model'!A1",
        "Model:Assumptions!A1",
        "TaxRate",
        "TRUE",
        "#REF!",
        "",
    ],
)
def test_ref_cells_unresolvable_is_empty(ref):
    assert ref_cells(ref, "Model", BOUNDS) == []


def test_ref_cells_unknown_current_sheet_is_empty():
    assert ref_cells("A1", "Missing", BOUNDS) == []
    assert ref_cells("A1", "Model", {}) == []
