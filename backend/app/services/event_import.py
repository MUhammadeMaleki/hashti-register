"""Parse historical events from the public Excel template."""

from datetime import date, datetime, time
from io import BytesIO

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from app.services.import_files import MAX_ROWS, checked_workbook

HEADERS = ("شماره رویداد", "عنوان", "تاریخ", "ساعت", "توضیحات", "نام مکان",
           "آدرس مکان", "هزینه ورودی", "یادداشت عمومی", "وضعیت ثبت‌نام")
KEYS = ("event_number", "title", "event_date", "start_time", "description",
        "location_name", "location_address", "entry_fee", "public_note",
        "registration_status")


def template_bytes() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "آرشیو رویدادها"
    sheet.sheet_view.rightToLeft = True
    sheet.sheet_view.showGridLines = False
    sheet.append(list(HEADERS))
    sheet.freeze_panes = "A2"
    widths = (17, 32, 19, 13, 40, 24, 40, 18, 40, 19)
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[chr(64 + index)].width = width
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="173650")
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")
    sheet.column_dimensions["C"].number_format = "yyyy-mm-dd"
    sheet.column_dimensions["D"].number_format = "hh:mm"
    result = BytesIO()
    book.save(result)
    return result.getvalue()


def _header(value: object) -> str:
    return " ".join(str(value or "").strip().replace("ي", "ی").replace("ك", "ک").split())


def _text(value: object, limit: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if limit is not None and len(text) > limit:
        raise ValueError("طول متن بیش از حد مجاز است")
    return text or None


def _integer(value: object, label: str, *, default: int | None = None) -> int:
    if value is None or str(value).strip() == "":
        if default is not None:
            return default
        raise ValueError(f"{label} الزامی است")
    if isinstance(value, bool) or not str(value).strip().isdigit():
        raise ValueError(f"{label} باید عدد صحیح باشد")
    number = int(value)
    if number < (1 if label == "شماره رویداد" else 0):
        raise ValueError(f"{label} نامعتبر است")
    return number


def _date(value: object) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        result = value.date()
    elif isinstance(value, date):
        result = value
    elif isinstance(value, str):
        try:
            result = date.fromisoformat(value.strip())
        except ValueError:
            raise ValueError("تاریخ باید میلادی و به‌شکل YYYY-MM-DD باشد") from None
    else:
        raise ValueError("تاریخ نامعتبر است")
    if result.year < 1900 or result.year > 2200:
        raise ValueError("تاریخ باید میلادی و به‌شکل YYYY-MM-DD باشد")
    return result


def _time(value: object) -> time | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, time):
        return value.replace(microsecond=0)
    if isinstance(value, str):
        try:
            return time.fromisoformat(value.strip())
        except ValueError:
            pass
    raise ValueError("ساعت باید به‌شکل HH:MM باشد")


def _status(value: object) -> str:
    text = _text(value)
    if text in {None, "بسته", "closed"}:
        return "closed"
    if text in {"باز", "open"}:
        return "open"
    raise ValueError("وضعیت ثبت‌نام باید باز یا بسته باشد")


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
        if ("شماره رویداد" not in names or
                len([name for name in names if name]) != len(set(name for name in names if name)) or
                any(name and name not in HEADERS for name in names)):
            raise HTTPException(422, "invalid_import_columns")
        positions = {KEYS[HEADERS.index(name)]: index
                     for index, name in enumerate(names) if name}
        unnamed = [index for index, name in enumerate(names) if not name]
        candidates, errors, seen = [], [], {}
        count = 0
        for row_number, cells in enumerate(iterator, 2):
            if all(cell.value is None or str(cell.value).strip() == "" for cell in cells):
                continue
            count += 1
            if count > MAX_ROWS:
                raise HTTPException(422, "invalid_import_size")
            try:
                if any(cell.data_type == "f" for cell in cells):
                    raise ValueError("فرمول در فایل ورودی مجاز نیست")
                if any(index < len(cells) and cells[index].value is not None for index in unnamed):
                    raise ValueError("ستون بدون عنوان داده دارد")
                values = {key: cells[index].value if index < len(cells) else None
                          for key, index in positions.items()}
                number = _integer(values.get("event_number"), "شماره رویداد")
                if number in seen:
                    raise ValueError(f"شماره رویداد در ردیف {seen[number]} تکرار شده است")
                title = _text(values.get("title"), 255) or f"هشتی {number}"
                event_date = _date(values.get("event_date"))
                start_time = _time(values.get("start_time"))
                location_name = _text(values.get("location_name"), 200)
                location_address = _text(values.get("location_address"))
                candidate = {"row": row_number, "event_number": number, "title": title,
                             "event_date": event_date, "start_time": start_time,
                             "description": _text(values.get("description")),
                             "location_name": location_name,
                             "location_address": location_address,
                             "entry_fee": _integer(values.get("entry_fee"), "هزینه ورودی",
                                                   default=0),
                             "public_note": _text(values.get("public_note")),
                             "registration_status": _status(values.get("registration_status"))}
                candidates.append(candidate)
                seen[number] = row_number
            except ValueError as error:
                errors.append({"row": row_number, "reason": str(error)})
        return candidates, errors, count
    finally:
        book.close()
