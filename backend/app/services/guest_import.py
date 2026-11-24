"""Parse and validate a bounded Excel contact-bank import."""

from io import BytesIO

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from app.services.guests import normalize_phone
from app.services.import_files import MAX_ROWS, checked_workbook

HEADERS = ("نام", "نام خانوادگی", "شماره موبایل", "سن", "جنسیت", "تحصیلات", "یادداشت")
HEADER_KEYS = ("first_name", "last_name", "phone", "age", "gender", "education",
               "internal_note")
REQUIRED = set(HEADER_KEYS[:3])


def template_bytes() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "مخاطبان"
    sheet.sheet_view.rightToLeft = True
    sheet.sheet_view.showGridLines = False
    sheet.append(list(HEADERS))
    sheet.freeze_panes = "A2"
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="173650")
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")
    for index, width in enumerate((18, 22, 20, 10, 14, 24, 40), 1):
        sheet.column_dimensions[chr(64 + index)].width = width
    sheet.column_dimensions["C"].number_format = "@"
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def _header(value: object) -> str:
    return " ".join(str(value or "").strip().replace("ي", "ی").replace("ك", "ک").split())


def _text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if len(value) > limit:
        raise ValueError("طول متن بیش از حد مجاز است")
    return value or None


def parse_workbook(content: bytes) -> tuple[list[dict], list[dict], int]:
    book = checked_workbook(content)
    try:
        sheet = book.active
        if sheet is None:
            raise HTTPException(422, "invalid_import_file")
        iterator = sheet.iter_rows(values_only=False)
        header_row = next(iterator, None)
        if header_row is None:
            raise HTTPException(422, "invalid_import_columns")
        names = [_header(cell.value) for cell in header_row]
        if len(names) != len(set(name for name in names if name)):
            raise HTTPException(422, "invalid_import_columns")
        unknown = [name for name in names if name and name not in HEADERS]
        if unknown or not REQUIRED.issubset({HEADER_KEYS[HEADERS.index(name)]
                                             for name in names if name}):
            raise HTTPException(422, "invalid_import_columns")
        index = {HEADER_KEYS[HEADERS.index(name)]: position
                 for position, name in enumerate(names) if name}
        unnamed_columns = [position for position, name in enumerate(names) if not name]
        candidates, errors = [], []
        count = 0
        seen: dict[str, int] = {}
        for row_number, cells in enumerate(iterator, 2):
            if all(cell.value is None or str(cell.value).strip() == "" for cell in cells):
                continue
            count += 1
            if count > MAX_ROWS:
                raise HTTPException(422, "invalid_import_size")
            try:
                if any(cell.data_type == "f" for cell in cells):
                    raise ValueError("فرمول در فایل ورودی مجاز نیست")
                if any(position < len(cells) and cells[position].value is not None
                       for position in unnamed_columns):
                    raise ValueError("ستون بدون عنوان داده دارد")
                values = {key: cells[position].value if position < len(cells) else None
                          for key, position in index.items()}
                first = _text(values.get("first_name"), 100)
                last = _text(values.get("last_name"), 100)
                if not first or not last:
                    raise ValueError("نام و نام خانوادگی الزامی است")
                raw_phone = values.get("phone")
                if raw_phone is None:
                    raise ValueError("شماره موبایل الزامی است")
                try:
                    phone = normalize_phone(str(raw_phone))
                except ValueError:
                    raise ValueError(
                        "شماره موبایل نامعتبر است؛ ستون را به‌صورت متن وارد کنید"
                    ) from None
                if phone in seen:
                    raise ValueError(f"شماره موبایل در ردیف {seen[phone]} تکرار شده است")
                age_raw = values.get("age")
                age = None
                if age_raw is not None and str(age_raw).strip():
                    if isinstance(age_raw, bool) or not str(age_raw).strip().isdigit():
                        raise ValueError("سن باید عدد صحیح باشد")
                    age = int(age_raw)
                    if age > 130:
                        raise ValueError("سن باید بین ۰ تا ۱۳۰ باشد")
                candidates.append({"row": row_number, "first_name": first, "last_name": last,
                                   "phone": phone, "age": age,
                                   "gender": _text(values.get("gender"), 30),
                                   "education": _text(values.get("education"), 200),
                                   "internal_note": _text(values.get("internal_note"), 10000)})
                seen[phone] = row_number
            except ValueError as error:
                errors.append({"row": row_number, "reason": str(error)})
        return candidates, errors, count
    finally:
        book.close()
