"""Small, read-only Excel projections of management reports."""

from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def _safe(value: object) -> object:
    """Never let user-controlled text become an Excel formula."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return value


def workbook_bytes(title: str, columns: list[tuple[str, str]], rows: list[dict],
                   *, total_keys: tuple[str, ...] = ()) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "گزارش"
    sheet.sheet_view.rightToLeft = True
    sheet.sheet_view.showGridLines = False
    sheet.append([title])
    sheet.cell(1, 1).font = Font(name="Arial", size=14, bold=True, color="173650")
    sheet.append([header for header, _ in columns])
    for cell in sheet[2]:
        cell.fill = PatternFill("solid", fgColor="173650")
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")
    for row in rows:
        sheet.append([_safe(row.get(key)) for _, key in columns])
    footer = len(rows) + 3
    sheet.cell(footer, 1, "تعداد")
    if len(columns) > 1:
        sheet.cell(footer, 2, len(rows))
    for index, (_, key) in enumerate(columns, 1):
        if key in total_keys:
            sheet.cell(footer, index, sum(int(row.get(key) or 0) for row in rows))
    for cell in sheet[footer]:
        cell.font = Font(name="Arial", bold=True)
    for index, (header, key) in enumerate(columns, 1):
        width = min(45, max(16, len(header) * 2 + 4))
        sheet.column_dimensions[get_column_letter(index)].width = width
        if key.endswith("_at") or key.endswith("_date"):
            for cells in sheet.iter_cols(min_col=index, max_col=index, min_row=3,
                                         max_row=footer - 1):
                for cell in cells:
                    if isinstance(cell.value, (date, datetime)):
                        cell.number_format = "yyyy-mm-dd hh:mm" if isinstance(
                            cell.value, datetime) else "yyyy-mm-dd"
        elif key in total_keys or key.endswith(("_balance", "_debt", "_count")) or key in {
            "debt", "charges", "settled", "entry", "orders",
        }:
            for cells in sheet.iter_cols(min_col=index, max_col=index, min_row=3,
                                         max_row=footer):
                for cell in cells:
                    if isinstance(cell.value, int):
                        cell.number_format = "#,##0"
    sheet.freeze_panes = "A3"
    sheet.auto_filter.ref = f"A2:{get_column_letter(len(columns))}{footer - 1}"
    output = BytesIO()
    book.save(output)
    return output.getvalue()
