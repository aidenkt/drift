"""Load a workbook and build the cell dependency graph."""


def load(path):
    """openpyxl twice: formulas (data_only=False) and cached values (data_only=True)."""
    raise NotImplementedError


def build_graph(wb):
    """Cell -> cells it references, from formula refs (A1, ranges, cross-sheet)."""
    raise NotImplementedError
