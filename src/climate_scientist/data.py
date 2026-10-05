from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import StringIO
from pathlib import Path

import pandas as pd

from .config import DATA_PATH, PROJECT_ROOT

DEFAULT_DATA = DATA_PATH
CITY_DAILY_PATH = PROJECT_ROOT / "india_2000_2024_daily_weather.csv"
COLUMN_MAP = {
    "temperature_2m (°C)": "temperature_c",
    "temperature_2m_max (°C)": "temperature_max_c",
    "temperature_2m_min (°C)": "temperature_min_c",
    "relative_humidity_2m (%)": "relative_humidity_pct",
    "precipitation (mm)": "precipitation_mm",
    "surface_pressure (hPa)": "surface_pressure_hpa",
    "wind_speed_10m (km/h)": "wind_speed_kmh",
    "wind_direction_10m (°)": "wind_direction_deg",
    "cloud_cover (%)": "cloud_cover_pct",
    "direct_radiation (W/m²)": "direct_radiation_wm2",
}
EXPECTED = {
    "temperature_c": (-90, 65), "temperature_max_c": (-90, 65),
    "temperature_min_c": (-100, 60), "relative_humidity_pct": (0, 100),
    "precipitation_mm": (0, None), "wind_speed_kmh": (0, None), "cloud_cover_pct": (0, 100),
}


@dataclass
class ClimateData:
    hourly: pd.DataFrame
    daily: pd.DataFrame
    metadata: dict
    source: str
    dataset_id: str = "open_meteo_single_location"

    def inspect(self) -> dict:
        return {
            "source": self.source,
            "timezone": "not specified" if self.dataset_id == "india_daily_multicity_2000_2024" else "Asia/Kolkata",
            "location": self.metadata,
            "hourly_rows": int(len(self.hourly)), "daily_rows": int(len(self.daily)),
            "hourly_start_ist": str(self.hourly.time_ist.min()) if "time_ist" in self.hourly else None,
            "hourly_end_ist": str(self.hourly.time_ist.max()) if "time_ist" in self.hourly else None,
            "hourly_columns": list(self.hourly.columns), "daily_columns": list(self.daily.columns),
        }


def load_dataset(path: str | Path | None = None) -> ClimateData:
    source = Path(path or DEFAULT_DATA).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Climate dataset not found: {source}")
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    headers = [i for i, line in enumerate(lines) if line.startswith("time,")]
    if len(headers) < 2:
        raise ValueError("Expected hourly and daily tables in the Open-Meteo CSV")
    metadata = dict(zip(lines[0].split(","), lines[1].split(",")))
    frames = []
    for header_index in headers[:2]:
        end = next((j for j in range(header_index + 1, len(lines)) if not lines[j].strip()), len(lines))
        frame = pd.read_csv(StringIO("\n".join(lines[header_index:end])))
        if "time_ist" not in frame.columns:
            raise ValueError("Dataset is missing the derived time_ist column")
        frame["time_utc"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
        # The derived CSV values are IST wall-clock timestamps without a suffix.
        frame["time_ist"] = pd.to_datetime(frame["time_ist"], errors="coerce").dt.tz_localize("Asia/Kolkata")
        frames.append(frame.rename(columns=COLUMN_MAP))
    return ClimateData(hourly=frames[0], daily=frames[1], metadata=metadata, source=str(source))


def load_city_daily_dataset(path: str | Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Load the multi-city daily table without rewriting or normalizing its fields.

    The file contains date-only labels and no timezone, coordinate, unit, or provider
    metadata. Those omissions are represented explicitly in the returned metadata.
    """
    source = Path(path or CITY_DAILY_PATH).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Climate dataset not found: {source}")
    frame = pd.read_csv(source)
    if "date" not in frame.columns or "city" not in frame.columns:
        raise ValueError("The city daily dataset must contain its observed 'city' and 'date' fields")
    parsed_dates = pd.to_datetime(frame["date"], errors="coerce")
    per_location = {}
    for location, indices in frame.groupby("city", dropna=False, sort=True).groups.items():
        local_dates = parsed_dates.loc[indices].dropna().sort_values()
        per_location[str(location)] = {
            "rows": int(len(indices)),
            "date_start": local_dates.min().date().isoformat() if len(local_dates) else None,
            "date_end": local_dates.max().date().isoformat() if len(local_dates) else None,
            "unique_dates": int(local_dates.nunique()),
            "duplicate_dates": int(local_dates.duplicated().sum()),
            "non_daily_gaps": int(((local_dates.diff().dropna()) != pd.Timedelta(days=1)).sum()),
        }
    metadata = {
        "dataset_id": "india_daily_multicity_2000_2024",
        "source": str(source),
        "format": "CSV; one row per city and date (as observed)",
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "shape": [int(len(frame)), int(len(frame.columns))],
        "dtypes": {name: str(dtype) for name, dtype in frame.dtypes.items()},
        "locations": sorted(frame["city"].dropna().astype(str).unique().tolist()),
        "location_field": "city",
        "location_count": int(frame["city"].nunique(dropna=True)),
        "records_by_location": per_location,
        "coordinates": "not provided",
        "time_field": "date",
        "time_semantics": "date-only daily labels; timezone not provided",
        "time_start": parsed_dates.min().date().isoformat() if parsed_dates.notna().any() else None,
        "time_end": parsed_dates.max().date().isoformat() if parsed_dates.notna().any() else None,
        "invalid_date_count": int(parsed_dates.isna().sum()),
        "missing_by_column": {name: int(count) for name, count in frame.isna().sum().items()},
        "duplicate_city_date_rows": int(frame.duplicated(["city", "date"]).sum()),
        "units": "not provided in the file; no unit conversions are registered",
        "provider": "not specified in the file",
        "variables": {
            name: {"field": name, "dtype": str(frame[name].dtype),
                   "missing_count": int(frame[name].isna().sum()),
                   "unit": None, "description": None,
                   "code_legend": "not provided" if name == "weather_code" else None}
            for name in frame.columns if name not in {"city", "date"}
        },
        "notes": [
            "The source CSV is read as-is; this loader does not add, convert, or rename fields.",
            "The dataset uses a city dimension and must be analyzed with city-aware daily methods.",
            "A date-only field is not converted to IST because its source timezone is unspecified.",
            "Variable meanings may be suggested by field names, but units and code definitions require source documentation.",
        ],
    }
    return frame, metadata


def load_experiment_dataset(dataset_id: str = "open_meteo_single_location") -> ClimateData:
    """Load a registered source into the common experiment container, in memory only."""
    if dataset_id == "open_meteo_single_location":
        return load_dataset()
    if dataset_id != "india_daily_multicity_2000_2024":
        raise ValueError(f"Unknown climate dataset: {dataset_id}")
    frame, metadata = load_city_daily_dataset()
    daily = frame.copy()
    # Internal datetime alias only; retain the original date column and its date-only semantics.
    daily["time_ist"] = pd.to_datetime(daily["date"], errors="coerce")
    return ClimateData(hourly=pd.DataFrame(), daily=daily, metadata=metadata,
                       source=str(CITY_DAILY_PATH.resolve()), dataset_id=dataset_id)


@lru_cache(maxsize=1)
def discover_datasets() -> list[dict]:
    """Return machine-readable metadata for the configured sources in this project."""
    sources = []
    if DEFAULT_DATA.exists():
        data = load_dataset(DEFAULT_DATA)
        sources.append({
            "dataset_id": "open_meteo_single_location",
            "source": data.source,
            "format": "CSV with hourly and daily tables",
            "locations": data.metadata,
            "location_dimension": False,
            "timezone": "Asia/Kolkata (derived time_ist field)",
            "hourly_rows": int(len(data.hourly)),
            "daily_rows": int(len(data.daily)),
            "time_start": str(data.hourly.time_ist.min()),
            "time_end": str(data.hourly.time_ist.max()),
            "variables": sorted(
                ({column for column in data.hourly.columns
                  if column not in {"time", "time_ist", "time_utc"}} |
                 {"temperature_c_min", "temperature_c_max"})),
        })
    if CITY_DAILY_PATH.exists():
        _, metadata = load_city_daily_dataset()
        metadata["location_dimension"] = True
        sources.append(metadata)
    return sources


def validate_dataset(data: ClimateData) -> dict:
    if data.dataset_id == "india_daily_multicity_2000_2024":
        frame = data.daily
        return {
            "hourly_rows": 0,
            "daily_rows": int(len(frame)),
            "hourly_missing_by_column": {},
            "daily_missing_by_column": {k: int(v) for k, v in frame.drop(columns=["time_ist"], errors="ignore").isna().sum().items()},
            "duplicate_utc_timestamps": 0,
            "invalid_utc_timestamps": int(frame.time_ist.isna().sum()),
            "non_hourly_intervals": 0,
            "incomplete_ist_calendar_days": 0,
            "physical_range_checks": {},
            "duplicate_city_date_rows": int(data.metadata["duplicate_city_date_rows"]),
            "time_semantics": data.metadata["time_semantics"],
            "units": data.metadata["units"],
            "notes": data.metadata["notes"],
        }
    frame = data.hourly
    ranges = {}
    for column, (low, high) in EXPECTED.items():
        if column not in frame:
            continue
        bad = pd.Series(False, index=frame.index)
        if low is not None:
            bad |= frame[column] < low
        if high is not None:
            bad |= frame[column] > high
        ranges[column] = {"out_of_range_count": int(bad.sum()), "bounds": [low, high]}
    diffs = frame.time_utc.sort_values().diff().dropna()
    hourly_by_ist_day = frame.set_index("time_ist").sort_index().resample("D").size()
    return {
        "hourly_rows": int(len(frame)), "daily_rows": int(len(data.daily)),
        "hourly_missing_by_column": {k: int(v) for k, v in frame.isna().sum().items()},
        "daily_missing_by_column": {k: int(v) for k, v in data.daily.isna().sum().items()},
        "duplicate_utc_timestamps": int(frame.time_utc.duplicated().sum()),
        "invalid_utc_timestamps": int(frame.time_utc.isna().sum()),
        "non_hourly_intervals": int((diffs != pd.Timedelta(hours=1)).sum()),
        "incomplete_ist_calendar_days": int((hourly_by_ist_day != 24).sum()),
        "physical_range_checks": ranges,
        "notes": ["Suspicious values are reported, never silently removed.",
                  "Provider daily aggregates are UTC-day aggregates; time_ist converts their labels only."],
    }
