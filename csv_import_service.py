"""Bulk import of goods from a CSV file.

Improvements over the original version:
  * Friendlier header handling: any column order, upper/lower case and
    stray spaces are accepted, and "description" is optional. Missing,
    unknown and duplicated columns are named in the error message.
  * Semicolon- or tab-separated files (common in Excel for many locales)
    are detected automatically.
  * Duplicate goods codes inside the same file are reported clearly,
    pointing at the first line that used the code.
  * Unknown categories get a "Did you mean ...?" suggestion.
  * Row errors report how many columns were found.
  * `sample_csv()` returns a ready-to-download template file.

The return value of import_goods_csv() is unchanged
({"imported", "failed", "rows"}); it only gains an extra "skipped" count
for blank lines.
"""

import csv
import difflib
import io

from category_repository import get_all_categories
from goods_repository import add_goods

REQUIRED_COLUMNS = [
    "code",
    "name",
    "category",
    "unit",
    "weight",
    "description",
]

# "description" may be left out of the file entirely.
OPTIONAL_COLUMNS = {"description"}

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 500
DELIMITERS = ",;\t"


def sample_csv():
    """Return a small example file users can download and fill in."""
    return (
        "code,name,category,unit,weight,description\r\n"
        "USB-001,USB cable,Electronics,Piece,0.05,1 m USB-C cable\r\n"
        "PEN-010,Blue pen,Office Supplies,Box,0.30,Box of 10 pens\r\n"
    )


def _detect_delimiter(text):
    """Pick , ; or tab by looking at the header line only."""
    first_line = text.splitlines()[0] if text.strip() else ""

    counts = {d: first_line.count(d) for d in DELIMITERS}
    best = max(counts, key=counts.get)

    return best if counts[best] > 0 else ","


def _read_rows(text):
    """Parse and structurally validate the CSV text.

    Returns [(line_number, {column: value}), ...] with blank lines removed
    and the number of skipped blank lines. Raises ValueError for any
    problem with the file itself, before anything is saved.
    """
    try:
        reader = csv.reader(
            io.StringIO(text, newline=""),
            delimiter=_detect_delimiter(text),
            strict=True,
        )

        try:
            raw_header = next(reader)
        except StopIteration:
            raise ValueError("The CSV file is empty.") from None

        header = [cell.strip().casefold() for cell in raw_header]

        duplicates = sorted({h for h in header if header.count(h) > 1})
        if duplicates:
            raise ValueError(
                "Duplicate column(s) in the header: "
                + ", ".join(duplicates) + "."
            )

        unknown = [h for h in header if h not in REQUIRED_COLUMNS]
        if unknown:
            raise ValueError(
                "Unknown column(s): " + ", ".join(unknown)
                + ". Expected: " + ",".join(REQUIRED_COLUMNS) + "."
            )

        missing = [
            c for c in REQUIRED_COLUMNS
            if c not in header and c not in OPTIONAL_COLUMNS
        ]
        if missing:
            raise ValueError(
                "Missing column(s): " + ", ".join(missing)
                + ". The header must contain: "
                + ",".join(REQUIRED_COLUMNS) + "."
            )

        rows = []
        skipped = 0

        for cells in reader:
            line_number = reader.line_num

            if not any(cell.strip() for cell in cells):
                skipped += 1
                continue

            if len(cells) != len(header):
                raise ValueError(
                    f"Line {line_number}: expected {len(header)} columns "
                    f"but found {len(cells)}."
                )

            row = {c: "" for c in REQUIRED_COLUMNS}
            row.update(zip(header, (cell.strip() for cell in cells)))
            rows.append((line_number, row))

            if len(rows) > MAX_ROWS:
                raise ValueError(
                    f"Import a maximum of {MAX_ROWS} goods at a time."
                )

    except csv.Error as error:
        raise ValueError(f"Invalid CSV format: {error}") from error

    if not rows:
        raise ValueError("The CSV file contains no goods.")

    return rows, skipped


def _category_error(name, categories):
    """Build a helpful message for an unknown category."""
    message = f"Category '{name}' does not exist."

    close = difflib.get_close_matches(
        name.casefold(), list(categories), n=1, cutoff=0.6
    )
    if close:
        message += f" Did you mean '{categories[close[0]][1]}'?"

    return message + " Create it on the Categories page first."


def import_goods_csv(upload):
    """Import new goods and return a result for each row."""
    if upload is None or not upload.filename:
        raise ValueError("Please select a CSV file.")

    if not upload.filename.lower().endswith(".csv"):
        raise ValueError("Please select a file ending in .csv.")

    data = upload.stream.read(MAX_FILE_BYTES + 1)

    if len(data) > MAX_FILE_BYTES:
        raise ValueError("The CSV file must be smaller than 2 MB.")

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(
            "Please save the file using CSV UTF-8 encoding."
        ) from error

    # Check the whole file structure before saving any goods.
    rows, skipped = _read_rows(text)

    # casefolded name -> (id, original name)
    categories = {
        category["name"].strip().casefold(): (
            category["id"], category["name"].strip()
        )
        for category in get_all_categories()
    }

    results = []
    imported = 0
    first_seen = {}  # casefolded code -> first line number

    for line_number, values in rows:
        code_key = values["code"].casefold()

        try:
            if code_key and code_key in first_seen:
                raise ValueError(
                    f"Duplicate code in this file (first used on line "
                    f"{first_seen[code_key]})."
                )

            match = categories.get(values["category"].casefold())

            if match is None:
                raise ValueError(
                    _category_error(values["category"], categories)
                )

            goods_id = add_goods(
                code=values["code"],
                name=values["name"],
                category_id=match[0],
                unit=values["unit"],
                weight=values["weight"],
                description=values["description"],
            )

        except ValueError as error:
            results.append({
                "line": line_number,
                "code": values["code"],
                "success": False,
                "message": str(error),
            })

        else:
            imported += 1
            first_seen.setdefault(code_key, line_number)
            results.append({
                "line": line_number,
                "code": values["code"],
                "success": True,
                "message": f"Created goods record #{goods_id}.",
            })

    return {
        "imported": imported,
        "failed": len(results) - imported,
        "skipped": skipped,
        "rows": results,
    }
