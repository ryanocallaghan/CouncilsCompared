"""Reading spreadsheets (ODS, XLSX, XLS) and finding columns by their headings.

Column positions change between editions, so columns are found by what
their heading says, and rows by the ONS code in them.
"""

import io
import re

from python_calamine import CalamineWorkbook

CODE = re.compile(r"E0[6-9]\d{6}")


def workbook(data):
    return CalamineWorkbook.from_filelike(io.BytesIO(data))


def sheet(book, pattern):
    """The rows of the first sheet whose name matches pattern."""
    for name in book.sheet_names:
        if re.search(pattern, name, re.I):
            return book.get_sheet_by_name(name).to_python()
    raise KeyError(f"No sheet matching {pattern!r} in {book.sheet_names}")


def text(value):
    return re.sub(r"\s+", " ", str(value)).strip()


def header_row(rows, pattern, limit=40):
    """The index of the first row with a cell matching pattern."""
    for i, row in enumerate(rows[:limit]):
        if any(re.search(pattern, text(cell), re.I) for cell in row):
            return i
    raise KeyError(f"No header matching {pattern!r}")


def column(header, pattern, exclude=None, last=False):
    """The index of the column whose heading matches pattern."""
    found = [i for i, cell in enumerate(header)
             if re.search(pattern, text(cell), re.I) and not (exclude and re.search(exclude, text(cell), re.I))]
    if not found:
        raise KeyError(f"No column matching {pattern!r}")
    return found[-1] if last else found[0]


def code(value):
    match = CODE.fullmatch(text(value))
    return match.group(0) if match else None


def code_in(row):
    """The ONS code in a row, wherever it is."""
    for cell in row:
        c = code(cell)
        if c:
            return c
    return None


def num(value):
    """A number, or None for blanks and markers like [x], [c], "x", "-"."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    cleaned = text(value).replace(",", "").replace("%", "")
    try:
        return float(cleaned)
    except ValueError:
        return None
