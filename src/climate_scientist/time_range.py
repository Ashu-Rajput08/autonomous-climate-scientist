"""Parse explicit and relative year ranges from climate questions."""
from __future__ import annotations

from datetime import date
import re

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}


def _year(value: str, latest_year: int) -> int:
    number = int(value)
    if len(value) == 4:
        return number
    return (latest_year // 100) * 100 + number if number <= latest_year % 100 else (latest_year // 100 - 1) * 100 + number


def parse_time_range(question: str, available_start: date, available_end: date) -> dict | None:
    """Return a date range only when the question contains a recognizable time scope.

    Relative year windows begin on January 1 of the start year, matching common user
    requests such as "past 10 years: 2016 to 2026".
    """
    text = question.lower()
    end_year = available_end.year

    iso_dates = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:to|through|until|[-–])\s*(\d{4}-\d{2}-\d{2})", text)
    if iso_dates:
        start, end = date.fromisoformat(iso_dates.group(1)), date.fromisoformat(iso_dates.group(2))
        label = f"{start.isoformat()} to {end.isoformat()}"
    else:
        years = re.search(r"\b(?:from\s+)?(\d{4}|\d{2})\s*(?:to|through|until|[-–])\s*(\d{4}|\d{2})\b", text)
        if years:
            start_year = _year(years.group(1), end_year)
            end_year_explicit = _year(years.group(2), end_year)
            start, end = date(start_year, 1, 1), date(end_year_explicit, 12, 31)
            label = f"{start_year} to {end_year_explicit}"
        else:
            since = re.search(r"\b(?:since|from)\s+(\d{4}|\d{2})\b", text)
            if since:
                start_year = _year(since.group(1), end_year)
                start, end = date(start_year, 1, 1), available_end
                label = f"since {start_year}"
            else:
                relative = re.search(r"\b(?:past|last|previous|preceding)\s+(\d+|[a-z]+)\s+(years?|yrs?)\b", text)
                decade = re.search(r"\b(?:past|last|previous)\s+decade\b", text)
                if decade:
                    count = 10
                elif relative:
                    raw = relative.group(1)
                    count = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw)
                else:
                    count = None
                if count is None:
                    return None
                start_year = end_year - count
                start, end = date(start_year, 1, 1), available_end
                label = f"past {count} years ({start_year} to {available_end.year})"

    # Respect the dataset's actual limits. The right endpoint is inclusive.
    start = max(start, available_start)
    end = min(end, available_end)
    if start > end:
        raise ValueError(f"The requested period is outside this dataset ({available_start} to {available_end}).")
    return {"start": start.isoformat(), "end": end.isoformat(), "label": label}
