from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ParsedSeat:
    number: int
    code: str
    x: int
    label: str | None = None

@dataclass(frozen=True, slots=True)
class ParsedRow:
    label: str
    section: str | None
    price_paise: int
    seats: list[ParsedSeat]
    @property
    def seat_count(self) -> int:
        return len(self.seats)

class LayoutParseError(ValueError):
    """Raised when text-grid syntax is malformed or seat count validation fails."""

def parse_text_grid(grid_text: str, default_price_paise: int = 29_000, section: str | None = None, expected_row_counts: dict[str, int] | None = None) -> list[ParsedRow]:
    lines = [line.strip() for line in grid_text.strip().splitlines() if line.strip()]
    parsed_rows = []
    for line_no, line in enumerate(lines, 1):
        if ":" not in line:
            raise LayoutParseError(f"Line {line_no}: Missing ':' separator in '{line}'")
        label_part, spec = line.split(":", 1)
        label_raw = label_part.strip()
        spec = spec.strip()
        declared_count = None
        match = re.search(r"[\(\[\{](\d+)[\)\]\}]", label_raw)
        if match:
            declared_count = int(match.group(1))
            row_label = re.sub(r"[\(\[\{]\d+[\)\]\}]", "", label_raw).strip().upper()
        else:
            row_label = label_raw.upper()
        if not row_label:
            raise LayoutParseError(f"Line {line_no}: Row label cannot be empty")
        if expected_row_counts and row_label in expected_row_counts:
            declared_count = expected_row_counts[row_label]
        seats = []
        seat_num = 1
        current_x = 0
        for char in spec:
            if char in ("1", "X", "x"):
                code = f"{row_label}{seat_num:02d}"
                seats.append(ParsedSeat(number=seat_num, code=code, x=current_x, label=code))
                seat_num += 1
                current_x += 1
            elif char in ("2", "3", "4", "5", "6", "7", "8", "9"):
                current_x += int(char)
            elif char == "-":
                current_x += 1
            elif char == " ":
                continue
            else:
                raise LayoutParseError(f"Line {line_no}: Invalid character '{char}'")
        parsed_count = len(seats)
        if parsed_count == 0:
            raise LayoutParseError(f"Line {line_no}: Row '{row_label}' produced zero seats")
        if declared_count is not None and parsed_count != declared_count:
            raise LayoutParseError(f"Row '{row_label}' seat count mismatch: declared {declared_count}, parsed {parsed_count}")
        if parsed_count > 100:
            raise LayoutParseError(f"Row '{row_label}' exceeds maximum physical capacity (100)")
        parsed_rows.append(ParsedRow(label=row_label, section=section, price_paise=default_price_paise, seats=seats))
    return parsed_rows
