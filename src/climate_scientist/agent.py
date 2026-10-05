from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

import pandas as pd

from .data import (CITY_DAILY_PATH, discover_datasets, load_dataset,
                   load_experiment_dataset, load_city_daily_dataset, validate_dataset)
from .llm import model_interpretation
from .science import (anomaly_correlation, correlation, descriptive, analysis_frame,
                      linear_trend, monthly_statistics, seasonal_statistics)
from .time_range import parse_time_range
from .visualization import create_analysis_plot

VARIABLE_TERMS = {
    "temperature_c": ["temperature", "temp"],
    "precipitation_mm": ["precipitation", "precip", "rainfall", "rain"],
    "relative_humidity_pct": ["humidity"], "surface_pressure_hpa": ["pressure"],
    "wind_speed_kmh": ["wind speed"], "cloud_cover_pct": ["cloud"],
    "direct_radiation_wm2": ["direct radiation", "solar radiation"],
}


def select_source_for_question(question: str) -> tuple[str, list[str], bool]:
    """Select the multi-city source only for a named city or explicit city-wide request."""
    if re.search(r"\bopen[ -]?meteo\b", question, re.I):
        return "open_meteo_single_location", [], False
    if not CITY_DAILY_PATH.exists():
        return "open_meteo_single_location", [], False
    frame, _ = load_city_daily_dataset()
    q = question.casefold()
    locations = [str(city) for city in frame.city.dropna().unique()
                 if re.search(rf"\b{re.escape(str(city).casefold())}\b", q)]
    all_cities = bool(re.search(
        r"\b(all cities|across cities|among cities|by city|city-wise|cities|across india|nationwide)\b", q))
    city_only_terms = ("apparent temperature", "weather code", "condition code",
                       "wind gust", "gust", "wind direction")
    city_only_variable = any(term in q for term in city_only_terms)
    if locations or all_cities or city_only_variable:
        if city_only_variable and not locations:
            all_cities = True
        return "india_daily_multicity_2000_2024", locations, all_cities
    return "open_meteo_single_location", [], False


def interpret_question(question: str, dataset_id: str = "open_meteo_single_location") -> dict:
    q = question.lower()
    city_dataset = dataset_id == "india_daily_multicity_2000_2024"
    if re.search(r"\b(?:uv|ultraviolet)\b", q):
        available = ("daily maximum/minimum temperature, apparent temperature, precipitation, rain, weather-code "
                     "counts, wind speed/gust, and wind direction" if city_dataset else
                     "temperature, relative humidity, precipitation, surface pressure, wind speed, cloud cover, and direct radiation")
        raise ValueError(f"UV index is not present in the selected source. Available fields include {available}.")
    if city_dataset:
        field_terms = {
            "temperature_2m_max": ("maximum temperature", "max temperature", "highest temperature", "temperature", "temp"),
            "temperature_2m_min": ("minimum temperature", "min temperature", "lowest temperature"),
            "apparent_temperature_max": ("maximum apparent temperature", "max apparent temperature", "apparent temperature"),
            "apparent_temperature_min": ("minimum apparent temperature", "min apparent temperature"),
            "precipitation_sum": ("precipitation", "precip", "rainfall"),
            "rain_sum": ("rain",),
            "weather_code": ("weather code", "condition code", "weather"),
            "wind_speed_10m_max": ("wind speed", "wind"),
            "wind_gusts_10m_max": ("wind gust", "gust"),
            "wind_direction_10m_dominant": ("wind direction",),
        }
        variables = [name for name, terms in field_terms.items()
                     if any(re.search(rf"\b{re.escape(term)}\b", q) for term in terms)]
        if any(term in q for term in ("apparent temperature",)):
            variables = [name for name in variables if not name.startswith("temperature_2m_")]
        if "minimum apparent temperature" in q or "min apparent temperature" in q:
            variables = [name for name in variables if name != "apparent_temperature_max"]
        elif "apparent temperature" in q:
            variables = [name for name in variables if name != "apparent_temperature_min"]
        if any(term in q for term in ("minimum temperature", "min temperature", "min temp", "lowest temperature")):
            variables = [name for name in variables if name != "temperature_2m_max"]
        elif any(term in q for term in ("maximum temperature", "max temperature", "max temp", "highest temperature")):
            variables = [name for name in variables if name != "temperature_2m_min"]
        else:
            variables = [name for name in variables if name != "temperature_2m_min"]
        model_plan = None
    else:
        variables = [name for name, terms in VARIABLE_TERMS.items()
                     if any(re.search(rf"\b{re.escape(term)}\b", q) for term in terms)]
        model_plan = model_interpretation(question)
    if "temperature_c" in variables:
        if any(re.search(rf"\b{re.escape(term)}\b", q) for term in
               ("minimum temperature", "min temperature", "lowest temperature", "temperature minimum")):
            variables[variables.index("temperature_c")] = "temperature_c_min"
        elif any(re.search(rf"\b{re.escape(term)}\b", q) for term in
                 ("maximum temperature", "max temperature", "highest temperature", "temperature maximum")):
            variables[variables.index("temperature_c")] = "temperature_c_max"
    if any(term in q for term in ("trend", "long-term", "long term", "over time", "change over time")):
        objective = "trend"
    elif any(term in q for term in ("season", "monsoon", "winter", "summer", "pre-monsoon", "post-monsoon")):
        objective = "seasonal"
    elif "monthly" in q or "by month" in q or "each month" in q:
        objective = "monthly"
    elif "anomal" in q:
        objective = "anomaly_correlation"
    elif any(term in q for term in ("relationship", "correlation", "associated", "relate", "association",
                                    "compare", "versus", " vs ", "impact of", "effect of")):
        objective = "correlation"
    else:
        objective = "descriptive"
    if (city_dataset and objective == "correlation" and len(variables) == 1 and
            re.search(r"\b(compare|comparison|across|among)\b", q) and
            re.search(r"\b(cities|city)\b", q)):
        objective = "descriptive"
    if objective in {"correlation", "anomaly_correlation"} and len(variables) < 2:
        raise ValueError("Please name both climate variables to compare (for example, temperature and precipitation).")
    detected_variables = list(variables)
    if model_plan:
        objective, variables = model_plan["objective"], model_plan["variables"]
        explicit_temperature = next((name for name in ("temperature_c_min", "temperature_c_max")
                                     if name in detected_variables), None)
        if explicit_temperature:
            variables = [explicit_temperature if name == "temperature_c" else name for name in variables]
        if objective in {"correlation", "anomaly_correlation"} and len(variables) < 2:
            raise ValueError("Please name both climate variables to compare (for example, temperature and precipitation).")
        assumptions = model_plan["assumptions"]
        source = "langchain_model"
    else:
        assumptions = []
        source = "deterministic_rules"
    if objective in {"trend", "seasonal", "monthly"} and not variables:
        raise ValueError("Which dataset variable should I analyze? For example: temperature, precipitation, or humidity.")
    if objective == "descriptive" and not variables:
        if any(term in q for term in ("overview", "all variables", "dataset summary")):
            variables = (["temperature_2m_max", "temperature_2m_min", "precipitation_sum"]
                         if city_dataset else ["temperature_c", "precipitation_mm", "relative_humidity_pct"])
        else:
            raise ValueError("I couldn’t identify the variable or analysis. Try asking about temperature, precipitation, humidity, or a trend/seasonal comparison.")
    assumptions += ["Use the supplied location and available observation period."]
    assumptions.append("Use date-only labels as supplied; timezone is unspecified." if city_dataset
                       else "Use derived IST timestamps for local calendar grouping.")
    return {"research_question": question, "domain": "climate science", "variables": variables,
        "objective": objective, "timezone": "unspecified" if city_dataset else "Asia/Kolkata", "temporal_resolution": "daily",
        "planner": source, "assumptions": assumptions}


def plan_experiment(question: str, data, locations: list[str] | None = None,
                    all_cities: bool = False) -> dict:
    interpretation = interpret_question(question, data.dataset_id)
    time_column = data.daily.time_ist if data.dataset_id == "india_daily_multicity_2000_2024" else data.hourly.time_ist
    requested_range = parse_time_range(question, time_column.min().date(), time_column.max().date())
    timezone_label = "unspecified (date-only source labels)" if data.dataset_id == "india_daily_multicity_2000_2024" else "Asia/Kolkata"
    return {"experiment_id": "EXP-" + uuid.uuid4().hex[:10].upper(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "objective": interpretation["objective"], "research_question": question,
        "variables": interpretation["variables"], "dataset": data.source,
        "dataset_id": data.dataset_id, "locations": locations or [],
        "all_cities": all_cities,
        "timezone": timezone_label,
        "time_range": requested_range,
        "preprocessing": (["Use source daily records and date-only labels; do not assign a timezone.",
                           "Retain source field names and values."]
                          if data.dataset_id == "india_daily_multicity_2000_2024" else [
            "Parse original timestamps as UTC.", "Use derived time_ist for local-calendar grouping.",
            "Aggregate hourly values by IST calendar day in memory; keep source observations untouched."]),
        "methods": [], "refinement_count": 0}


def _run(plan: dict, data) -> dict:
    frame = analysis_frame(data, plan)
    objective, variables = plan["objective"], plan["variables"]
    if (data.dataset_id == "india_daily_multicity_2000_2024"
            and objective != "descriptive"
            and {"weather_code", "wind_direction_10m_dominant"}.intersection(variables)):
        raise ValueError("Weather codes and dominant wind directions are treated as categorical values in this source; trend, correlation, and mean-based grouping are unavailable.")
    grouped_city_run = (data.dataset_id == "india_daily_multicity_2000_2024"
                        and "city" in frame
                        and (plan.get("all_cities") or len(plan.get("locations") or []) > 1))
    if grouped_city_run:
        results = {}
        for city, city_frame in frame.groupby("city", sort=True):
            city_plan = dict(plan, locations=[str(city)], all_cities=False)
            results[str(city)] = _run(city_plan, data)
        plan["methods"] = ["Run the selected daily analysis separately for each city; do not pool city records."]
        return {"by_city": results}
    if objective == "trend":
        col = variables[0]
        result = linear_trend(frame if col in frame else data.hourly, col)
        plan["methods"] = ["ordinary least squares trend"]
    elif objective == "seasonal":
        col = variables[0]
        result = {"variable": col, "seasonal_statistics": seasonal_statistics(frame if col in frame else data.hourly, col)}
        plan["methods"] = ["IST meteorological-season grouping"]
    elif objective == "monthly":
        col = variables[0]
        result = {"variable": col, "monthly_statistics": monthly_statistics(frame if col in frame else data.hourly, col)}
        plan["methods"] = ["monthly climatology grouped by IST calendar month"]
    elif objective == "anomaly_correlation":
        result = anomaly_correlation(frame, *variables[:2])
        plan["methods"] = ["calendar-day climatology anomalies", "Pearson and Spearman correlation"]
    elif objective == "correlation":
        result = correlation(frame, *variables[:2])
        plan["methods"] = ["Pearson and Spearman correlation on daily observations"]
    else:
        columns = variables or ["temperature_c", "precipitation_mm", "relative_humidity_pct"]
        result = descriptive(frame, columns)
        if data.dataset_id == "india_daily_multicity_2000_2024":
            for categorical in {"weather_code", "wind_direction_10m_dominant"}.intersection(columns):
                values = frame[categorical].dropna()
                result[categorical] = {"counts": {str(code): int(count)
                    for code, count in values.value_counts().sort_index().items()},
                    "n": int(len(values)),
                    "legend": "not provided" if categorical == "weather_code" else "units/interpretation not provided"}
        plan["methods"] = ["descriptive statistics"]
    return result


def _critic(plan: dict, quality: dict) -> dict:
    issues = []
    if quality["duplicate_utc_timestamps"]:
        issues.append({"severity": "high", "type": "duplicate timestamps",
            "finding": f"{quality['duplicate_utc_timestamps']} duplicate UTC timestamps were found."})
    if any(item["out_of_range_count"] for item in quality["physical_range_checks"].values()):
        issues.append({"severity": "medium", "type": "physical range",
            "finding": "Values outside broad plausibility bounds are retained and should be investigated."})
    if plan["objective"] in {"correlation", "anomaly_correlation"}:
        issues.append({"severity": "medium", "type": "temporal dependence and confounding",
            "finding": "Serial autocorrelation, seasonality, and omitted variables may affect nominal correlation p-values."})
        issues.append({"severity": "low", "type": "causal inference", "finding": "Association does not establish causation."})
    if plan["objective"] == "trend":
        issues.append({"severity": "medium", "type": "trend inference",
            "finding": "The OLS nominal p-value does not adjust for serial autocorrelation, breaks, or confounding."})
    return {"valid": True, "issues": issues, "confidence": 0.78 if issues else 0.9,
        "refinement_recommended": (plan["objective"] == "correlation"
                                   and not plan.get("all_cities")
                                   and len(plan.get("locations") or []) <= 1),
        "decision": "Run a seasonal-anomaly sensitivity analysis for raw correlation." if plan["objective"] == "correlation"
            else "Proceed with stated limitations; the detected inference limitations require scientific interpretation."}


def _markdown(plan: dict, quality: dict, result: dict, critique: dict) -> str:
    findings = "\n".join(f"- {i['severity'].title()}: {i['finding']}" for i in critique["issues"])
    if not findings:
        findings = "- No critical data or method issue flagged."
    return f"""# Scientific Investigation

## Research question
{plan['research_question']}

## Objective and design
Objective: `{plan['objective']}`. Resolution: daily. Analysis timezone/date semantics: `{plan['timezone']}`.

## Dataset
Source: `{plan['dataset']}`. Analysis period: {quality['analysis_start']} to {quality['analysis_end']}.
{f"Question-requested period: {plan['time_range']['label']}." if plan.get('time_range') else "No narrower period was requested."}

## Data quality
- Hourly records: {quality['hourly_rows']:,}; daily records: {quality['daily_rows']:,}.
- Duplicate UTC timestamps: {quality['duplicate_utc_timestamps']}; invalid timestamps: {quality['invalid_utc_timestamps']}; non-hour intervals: {quality['non_hourly_intervals']}.
- Incomplete IST calendar days: {quality['incomplete_ist_calendar_days']}; these are excluded when aggregating the hourly source.
- Missing counts and range checks are in the experiment JSON. Suspicious observations were not deleted.

## Methods
{', '.join(plan['methods'])}.

## Results
```json
{json.dumps(result, indent=2, ensure_ascii=False)}
```

## Visualization
Generated plot: `{quality.get('plot_path', 'not available')}`.

## Scientific validation and limitations
Critic decision: {critique['decision']} Confidence: {critique['confidence']:.2f}.
{findings}

{("The source provides daily date-only observations; timezone and units are unspecified. City analyses are run separately when multiple cities are requested." if plan.get('dataset_id') == 'india_daily_multicity_2000_2024' else "Daily analysis values are aggregated from hourly observations on IST calendar days; the provider's daily table is retained for provenance and is not rewritten.")} Correlations and trends are observational; no causal conclusion is supported.

## Conclusion
The numerical results answer the selected analysis for this dataset and period. Interpret them with the data-quality record and limitations; they do not establish causation or climate attribution.

## Provenance
Experiment `{plan['experiment_id']}`; created {plan['created_at_utc']}; timezone/date semantics `{plan['timezone']}`.
"""


def _strength(value: float) -> str:
    magnitude = abs(value)
    label = "weak" if magnitude < 0.3 else "moderate" if magnitude < 0.6 else "strong"
    direction = "positive" if value >= 0 else "negative"
    return f"{label} {direction} association"


def _display_name(variable: str) -> str:
    names = {"temperature_c": "Temperature (°C)", "precipitation_mm": "Precipitation (mm/day)",
        "temperature_c_min": "Minimum temperature (°C)", "temperature_c_max": "Maximum temperature (°C)",
        "relative_humidity_pct": "Relative humidity (%)", "surface_pressure_hpa": "Surface pressure (hPa)",
        "wind_speed_kmh": "Wind speed (km/h)", "cloud_cover_pct": "Cloud cover (%)",
        "direct_radiation_wm2": "Direct radiation (W/m²)"}
    return names.get(variable, variable.replace("_", " ").title())


def format_chat_answer(plan: dict, quality: dict, result: dict) -> str:
    """Turn technical outputs into a short answer; the full reproducible report is separate."""
    objective, variables = plan["objective"], plan["variables"]
    lines = ["### Answer"]
    if "by_city" in result:
        lines.append("Results are calculated separately for each city.")
        if objective == "descriptive":
            lines.append("| City | Variable | Mean | Median | n |\n|---|---|---:|---:|---:|")
            for city, city_result in result["by_city"].items():
                for variable, metrics in city_result.items():
                    if "mean" not in metrics:
                        continue
                    lines.append(f"| {city} | {_display_name(variable)} | {metrics['mean']:.2f} | "
                                 f"{metrics['median']:.2f} | {metrics['n']:,} |")
            if "weather_code" in variables:
                lines.append("Weather-code frequencies are stored in the experiment report; no code meanings are inferred.")
            if plan.get("dataset_id") == "india_daily_multicity_2000_2024":
                lines.append("Units are not stated in the source file.")
        elif objective in {"seasonal", "monthly"}:
            key = "seasonal_statistics" if objective == "seasonal" else "monthly_statistics"
            lines.append("| City | Group | Mean | Median | n |\n|---|---|---:|---:|---:|")
            for city, city_result in result["by_city"].items():
                for group, metrics in city_result.get(key, {}).items():
                    lines.append(f"| {city} | {group} | {metrics['mean']:.2f} | "
                                 f"{metrics['median']:.2f} | {metrics['n']:,} |")
            lines.append("Units are not stated in the source file.")
        elif objective == "trend":
            lines.append("| City | Change per decade (source units) | n |\n|---|---:|---:|")
            for city, city_result in result["by_city"].items():
                lines.append(f"| {city} | {city_result['slope_per_decade']:.3f} | {city_result['n']:,} |")
            lines.append("The source does not specify measurement units.")
        elif objective in {"correlation", "anomaly_correlation"}:
            lines.append("| City | Pearson r | Paired days |\n|---|---:|---:|")
            for city, city_result in result["by_city"].items():
                lines.append(f"| {city} | {city_result['pearson_r']:.3f} | {city_result['n']:,} |")
            lines.append("Associations do not establish causation.")
        else:
            for city, city_result in result["by_city"].items():
                lines.append(f"- **{city}:** {json.dumps(city_result, ensure_ascii=False)}")
        lines.append(f"Source date labels: {quality['analysis_start'][:10]} to {quality['analysis_end'][:10]}; timezone unspecified.")
        return "\n".join(lines)
    if objective in {"seasonal", "monthly"}:
        key = "seasonal_statistics" if objective == "seasonal" else "monthly_statistics"
        stats_by_group = result.get(key, {})
        if stats_by_group:
            best_group, best_stats = max(stats_by_group.items(), key=lambda item: item[1]["mean"])
            value = variables[0]
            display = _display_name(value)
            base_name, _, unit = display.partition("(")
            unit = unit.rstrip(")")
            mean_display = f"{best_stats['mean']:.2f} {unit}".strip()
            lines.append(f"The highest average {base_name.strip().lower()} was in **{best_group}** "
                         f"({mean_display}).")
            lines.append(f"| Group | Mean ({unit}) | Median | Days |\n|---|---:|---:|---:|")
            for group, metrics in stats_by_group.items():
                lines.append(f"| {group} | {metrics['mean']:.2f} | {metrics['median']:.2f} | {metrics['n']:,} |")
            if value == "precipitation_mm":
                lines.append("Each daily precipitation value is the total for that IST calendar day.")
    elif objective == "trend":
        value = result["slope_per_decade"]
        verb = "increased" if value > 0 else "decreased"
        display = _display_name(variables[0])
        _, has_unit, unit_text = display.partition("(")
        unit = "" if plan.get("dataset_id") == "india_daily_multicity_2000_2024" or not has_unit else f" {unit_text.rstrip(')')}"
        period = "daily source records" if unit == "" else "complete IST days"
        lines.append(f"{_display_name(variables[0])} {verb} by about **{abs(value):.3f}{unit} per decade** "
                     f"in a linear fit across {result['n']:,} {period}.")
        lines.append("This is a descriptive trend; serial correlation can make the reported p-value too optimistic.")
    elif objective == "correlation":
        initial = result.get("initial_raw_association", result)
        adjusted = result.get("seasonality_adjusted_sensitivity")
        lines.append(f"Daily {_display_name(initial['x'])} and {_display_name(initial['y'])} had a "
                     f"**{_strength(initial['pearson_r'])}** (Pearson r = {initial['pearson_r']:.2f}; "
                     f"{initial['n']:,} paired days).")
        if adjusted:
            lines.append(f"After removing the average seasonal cycle, the association was "
                         f"{_strength(adjusted['pearson_r'])} (r = {adjusted['pearson_r']:.2f}).")
        lines.append("These are associations, not evidence that one variable causes the other.")
    elif objective == "anomaly_correlation":
        lines.append(f"After removing the typical calendar-day pattern, {_display_name(result['x'])} and {_display_name(result['y'])} "
                     f"showed a **{_strength(result['pearson_r'])}** (r = {result['pearson_r']:.2f}; "
                     f"{result['n']:,} paired days). This does not establish causation.")
    else:
        lines.append("Summary statistics for the requested variables:")
        lines.append("| Variable | Mean | Median | Std. dev. | 5th–95th percentile | n |\n|---|---:|---:|---:|---:|---:|")
        for variable, metrics in result.items():
            if "mean" not in metrics:
                continue
            lines.append(f"| {_display_name(variable)} | {metrics['mean']:.2f} | {metrics['median']:.2f} | "
                         f"{metrics['std']:.2f} | {metrics['p05']:.2f}–{metrics['p95']:.2f} | {metrics['n']:,} |")
        for categorical in ("weather_code", "wind_direction_10m_dominant"):
            if categorical in result:
                counts = ", ".join(f"{code}: {count:,}" for code, count in result[categorical]["counts"].items())
                lines.append(f"{_display_name(categorical)} frequencies (no interpretation inferred): {counts}.")

    if plan.get("dataset_id") == "india_daily_multicity_2000_2024":
        lines.append(f"\n*Source date labels: {quality['analysis_start'][:10]} to {quality['analysis_end'][:10]}; timezone and units are unspecified.*")
        if "weather_code" in variables:
            lines.append("Weather-code meanings are not interpreted because this file has no code legend.")
    else:
        lines.append(f"\n*Data: {quality['analysis_start'][:10]} to {quality['analysis_end'][:10]}, IST. "
                     f"Incomplete local days excluded; {quality['incomplete_ist_calendar_days']} flagged.*")
    return "\n".join(lines)


def inspect_and_plan(question: str, data_path=None, dataset_id: str | None = None) -> dict:
    locations, all_cities = [], False
    if data_path:
        data = load_dataset(data_path)
    else:
        selected_id, locations, all_cities = select_source_for_question(question)
        data = load_experiment_dataset(dataset_id or selected_id)
    plan = plan_experiment(question, data, locations, all_cities)
    quality = validate_dataset(data)
    quality["available_datasets"] = discover_datasets()
    dates = data.daily.time_ist if data.dataset_id == "india_daily_multicity_2000_2024" else data.hourly.time_ist
    quality["source_start"] = str(dates.min())
    quality["source_end"] = str(dates.max())
    frame = analysis_frame(data, plan)
    if frame.empty:
        raise ValueError("No records are available in the requested date range and city selection.")
    quality["analysis_start"] = str(frame.time_ist.min())
    quality["analysis_end"] = str(frame.time_ist.max())
    quality["analysis_daily_rows"] = int(len(frame))
    quality["analysis_cities"] = sorted(frame.city.unique().tolist()) if "city" in frame else []
    return {"data": data, "plan": plan, "quality": quality}


def execute_experiment(state: dict) -> dict:
    return {"result": _run(state["plan"], state["data"])}


def critique_and_refine(state: dict) -> dict:
    plan, quality, data = state["plan"], state["quality"], state["data"]
    result = state["result"]
    critique = _critic(plan, quality)
    history = [{"stage": "initial", "objective": plan["objective"], "results": result,
                "critic_decision": critique["decision"]}]
    if critique["refinement_recommended"] and len(plan["variables"]) >= 2:
        refined = anomaly_correlation(analysis_frame(data, plan), *plan["variables"][:2])
        plan["refinement_count"] = 1
        plan["methods"].append("refinement: calendar-day climatology anomaly sensitivity analysis")
        result = {"initial_raw_association": result, "seasonality_adjusted_sensitivity": refined}
        history.append({"stage": "refinement", "objective": "anomaly_correlation",
                        "results": refined, "reason": "Critic flagged seasonal confounding risk."})
        critique["decision"] = "Report initial correlation alongside refined seasonal-anomaly sensitivity analysis."
    return {"result": result, "critique": critique, "history": history}


def produce_report(state: dict, output_dir="experiments/runs") -> dict:
    plan, quality = state["plan"], state["quality"]
    result, critique, history = state["result"], state["critique"], state["history"]
    plot_plan = dict(plan)
    if plan["refinement_count"]:
        plot_plan["objective"] = "anomaly_correlation"
    quality["plot_path"] = create_analysis_plot(state["data"], plot_plan,
        Path(output_dir) / f"{plan['experiment_id'].lower()}.png")
    record = {"experiment": plan, "data_quality": quality, "results": result, "critic": critique}
    record["experiment_history"] = history
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = plan["experiment_id"].lower()
    json_path, report_path = out / f"{stem}.json", out / f"{stem}.md"
    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report = _markdown(plan, quality, result, critique)
    report_path.write_text(report, encoding="utf-8")
    record.update(answer=format_chat_answer(plan, quality, result), report=report,
                  report_path=str(report_path.resolve()), record_path=str(json_path.resolve()))
    return record


def run_investigation(question: str, data_path=None, output_dir="experiments/runs") -> dict:
    state = inspect_and_plan(question, data_path)
    state.update(execute_experiment(state))
    state.update(critique_and_refine(state))
    return produce_report(state, output_dir)
