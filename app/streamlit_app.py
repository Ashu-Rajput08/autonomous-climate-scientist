from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st
from html import escape

from climate_scientist.chat_store import add_message, create_chat, list_chats, load_chat, save_chat
from climate_scientist.data import (discover_datasets, load_dataset,
                                    load_experiment_dataset, validate_dataset)
from climate_scientist.plotly_visualizations import (build_charts, date_bounds, MONTHS,
    SEASON_ORDER, build_coverage_map)
from climate_scientist.question_check import suggest_corrected_question
from climate_scientist.workflow import invoke


st.set_page_config(page_title="Autonomous Climate Scientist", page_icon="🌦️", layout="wide")
st.markdown("""
<style>
.parameter-chip-list { display: flex; flex-wrap: wrap; gap: .38rem; margin: .35rem 0 .65rem; }
.parameter-chip { 
  display: inline-block; border-radius: 999px; padding: .25rem .55rem;
  font-size: .73rem; line-height: 1.25rem; font-family: ui-monospace, Consolas, monospace;
  border: 1px solid rgba(158,174,201,.22); color: #E8EDF5;
}
.parameter-chip.teal { background: rgba(48,179,159,.13); border-color: rgba(75,213,190,.34); }
.parameter-chip.violet { background: rgba(129,112,232,.14); border-color: rgba(164,149,255,.32); }
.parameter-icon { font-family: sans-serif; margin-right: .3rem; font-size: .9rem; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_data_bundle():
    data = load_dataset()
    return data, data.inspect(), validate_dataset(data)


@st.cache_resource
def get_analysis_data(dataset_id: str):
    return load_experiment_dataset(dataset_id)


@st.cache_resource
def get_coverage_figure():
    """Build the static coverage map once per app process, not on every chat rerun."""
    return build_coverage_map(discover_datasets())


def render_data_overview() -> None:
    sources = discover_datasets()
    if not sources:
        return
    with st.container(border=True):
        st.markdown("#### Data coverage and available parameters")
        st.caption("A quick guide to the fields available for research questions. Dataset units and time handling stay source-specific.")
        map_column, catalog_column = st.columns([1.2, 1], gap="large")
        with map_column:
            st.plotly_chart(get_coverage_figure(), width="stretch",
                            config={"displayModeBar": False}, key="india-coverage-map")
            st.caption("City markers show approximate city centers for orientation; the multi-city file contains no coordinates. The star uses the Open-Meteo file's supplied coordinates.")
        with catalog_column:
            st.markdown("**Open-Meteo · one site · hourly**")
            open_source = next((source for source in sources
                                if source.get("dataset_id") == "open_meteo_single_location"), {})
            st.caption(f"{open_source.get('hourly_rows', 0):,} hourly observations · "
                       f"{str(open_source.get('time_start', ''))[:10]} to {str(open_source.get('time_end', ''))[:10]} · IST")
            open_parameters = {
                "temperature_c": "temperature_c · °C",
                "temperature_c_min": "temperature_c_min · °C",
                "temperature_c_max": "temperature_c_max · °C",
                "relative_humidity_pct": "relative_humidity_pct · %",
                "precipitation_mm": "precipitation_mm · mm",
                "surface_pressure_hpa": "surface_pressure_hpa · hPa",
                "wind_speed_kmh": "wind_speed_kmh · km/h",
                "cloud_cover_pct": "cloud_cover_pct · %",
                "direct_radiation_wm2": "direct_radiation_wm2 · W/m²",
                "wind_direction_deg": "wind_direction_deg · degrees",
            }
            open_names = open_source.get("variables", [])
            _render_parameter_chips([open_parameters.get(name, name) for name in open_names], "teal")
            st.caption("Original hourly timestamps are retained; analysis time is shown in IST.")

            st.markdown("**India multi-city · daily · 10 cities**")
            city_source = next((source for source in sources
                                if source.get("dataset_id") == "india_daily_multicity_2000_2024"), {})
            st.caption(f"{city_source.get('rows', 0):,} daily rows · "
                       f"{city_source.get('time_start', '—')} to {city_source.get('time_end', '—')} · "
                       f"{city_source.get('location_count', 0)} cities")
            city_parameters = [name for name in city_source.get("columns", [])
                               if name not in {"city", "date"}]
            _render_parameter_chips(city_parameters, "violet")
            st.caption("Units, provider timezone, and the weather-code legend are not specified in this file.")


def _render_parameter_chips(parameters: list[str], tone: str) -> None:
    if not parameters:
        return
    def icon_for(parameter: str) -> str:
        name = parameter.casefold()
        if any(word in name for word in ("precipitation", "rain")):
            return "🌧️"
        if any(word in name for word in ("wind", "gust")):
            return "🌬️"
        if "humidity" in name:
            return "💧"
        if "pressure" in name:
            return "🧭"
        if "cloud" in name:
            return "☁️"
        if "radiation" in name or "solar" in name:
            return "☀️"
        if "weather_code" in name:
            return "⛅"
        if "temperature" in name or "apparent" in name:
            return "🌡️"
        return "📊"
    items = "".join(
        f'<span class="parameter-chip {tone}"><span class="parameter-icon">{icon_for(parameter)}</span>{escape(parameter)}</span>'
        for parameter in parameters
    )
    st.markdown(f'<div class="parameter-chip-list">{items}</div>', unsafe_allow_html=True)


def answer_question(question: str) -> tuple[str, dict]:
    """Run the investigation and return a concise answer plus expandable provenance."""
    try:
        outcome = invoke(question)
        if outcome.get("error"):
            error = outcome["error"]
            for prefix in ("ValueError: ", "KeyError: ", "TypeError: "):
                if error.startswith(prefix):
                    error = error[len(prefix):]
                    break
            return error, {}
        record = outcome.get("result", {})
        if not record:
            return "I could not produce an analysis result. Please try a more specific question.", {}
        metadata = {
            "analysis": {"experiment": record["experiment"], "results": record["results"]},
            "quality": record["data_quality"], "critic": record["critic"],
            "report_path": record["report_path"], "record_path": record["record_path"],
            "research_question": record["experiment"].get("research_question", question),
        }
        return record.get("answer", "Analysis complete."), metadata
    except Exception as exc:
        return str(exc), {}


def render_explorer(metadata: dict, widget_id: str, expanded: bool = False) -> None:
    analysis = metadata.get("analysis")
    if not analysis:
        return
    try:
        plan = analysis["experiment"]
        data = get_analysis_data(plan.get("dataset_id", "open_meteo_single_location"))
        min_day, max_day = date_bounds(data, plan)
        with st.expander("Explore graphs and filters", expanded=expanded):
            timezone_note = "India Standard Time" if plan.get("timezone") == "Asia/Kolkata" else "source date labels (timezone unspecified)"
            st.caption(f"Filters apply to all charts and use {timezone_note}.")
            date_value = st.date_input("Time range", value=(min_day, max_day),
                min_value=min_day, max_value=max_day, key=f"date-{widget_id}")
            if isinstance(date_value, (tuple, list)) and len(date_value) == 2:
                date_range = (date_value[0], date_value[1])
            elif date_value:
                date_range = (date_value, date_value)
            else:
                date_range = (min_day, max_day)
            selected_months = st.multiselect("Months", MONTHS, default=MONTHS,
                key=f"months-{widget_id}")
            selected_seasons = st.multiselect("Seasons", SEASON_ORDER, default=SEASON_ORDER,
                key=f"seasons-{widget_id}")
            chart_plan = dict(plan)
            if "city" in data.daily:
                cities = sorted(data.daily.city.dropna().astype(str).unique().tolist())
                default_cities = plan.get("locations") or cities
                chart_plan["locations"] = st.multiselect("Cities", cities, default=default_cities,
                    key=f"cities-{widget_id}")
            charts = build_charts(data, chart_plan, date_range,
                                  selected_months, selected_seasons)
            chart_names = [name for name, _ in charts]
            selected_chart = st.selectbox("Chart view", ["All charts", *chart_names],
                key=f"chart-{widget_id}")
            for index, (name, figure) in enumerate(charts):
                if selected_chart == "All charts" or selected_chart == name:
                    st.plotly_chart(figure, width="stretch",
                        key=f"plot-{widget_id}-{index}")
    except Exception as exc:
        st.warning(f"Charts could not be displayed: {exc}")


def render_scientific_details(metadata: dict, widget_id: str) -> None:
    if not metadata:
        return
    with st.expander("Scientific notes and full report", expanded=False):
        analysis = metadata.get("analysis", {})
        plan = analysis.get("experiment", {})
        quality = metadata.get("quality", {})
        if plan:
            st.write(f"**Dataset:** {plan.get('dataset_id', 'open_meteo_single_location')}")
            st.write(f"**Method:** {', '.join(plan.get('methods', [])) or plan.get('objective', 'analysis')}")
            st.write(f"**Date semantics:** {plan.get('timezone', 'Asia/Kolkata')} · **Resolution:** {plan.get('temporal_resolution', 'daily')}")
        issues = metadata.get("critic", {}).get("issues", [])
        if issues:
            st.write("**Limitations**")
            for issue in issues[:3]:
                st.markdown(f"- {issue['finding']}")
        st.caption(f"Hourly records: {quality.get('hourly_rows', 0):,} · "
                   f"Daily records: {quality.get('daily_rows', '—'):,} · "
                   f"Incomplete IST days excluded: {quality.get('incomplete_ist_calendar_days', 0)}")
        report_path = metadata.get("report_path")
        if report_path and Path(report_path).exists():
            st.download_button("Download full scientific report", Path(report_path).read_bytes(),
                file_name=Path(report_path).name, mime="text/markdown",
                key=f"report-{widget_id}")


with st.sidebar:
    st.title("Climate Scientist")
    if st.button("＋ New chat", width="stretch", type="primary"):
        chat = create_chat()
        st.session_state.active_chat_id = chat["id"]
        st.rerun()

    st.subheader("Chat history")
    chat_summaries = list_chats()
    if "active_chat_id" not in st.session_state and chat_summaries:
        st.session_state.active_chat_id = chat_summaries[0]["id"]
    active_id = st.session_state.get("active_chat_id")
    if active_id and not any(item["id"] == active_id for item in chat_summaries):
        st.session_state.active_chat_id = None
        active_id = None
    for summary in chat_summaries:
        label = summary["title"] or "New chat"
        if st.button(label, key=f"open-{summary['id']}", width="stretch",
                     type="secondary" if summary["id"] != active_id else "primary"):
            st.session_state.active_chat_id = summary["id"]
            st.rerun()

    st.divider()
    st.caption("Default source · Open-Meteo · IST (UTC+05:30); city questions can route to the multi-city source.")
    try:
        _, info, quality = get_data_bundle()
        st.metric("Hourly observations", f"{info['hourly_rows']:,}")
        st.caption(f"{info['hourly_start_ist']} — {info['hourly_end_ist']}")
        st.caption(f"Duplicate timestamps: {quality['duplicate_utc_timestamps']}")
        with st.expander("Available data sources"):
            for source in discover_datasets():
                st.markdown(f"**{source['dataset_id']}**")
                if source["dataset_id"] == "india_daily_multicity_2000_2024":
                    st.caption(f"{source['rows']:,} daily rows · {source['location_count']} cities · "
                               f"{source['time_start']} to {source['time_end']}")
                    st.caption("Date-only labels; units, timezone, coordinates, and provider are unspecified in the file.")
                    st.caption("Fields: " + ", ".join(source["columns"]))
                else:
                    st.caption(f"Hourly: {source['hourly_rows']:,} · daily: {source['daily_rows']:,} · "
                               f"timezone: {source['timezone']}")
    except Exception as exc:
        st.error(f"Dataset unavailable: {exc}")


active_id = st.session_state.get("active_chat_id")
chat = load_chat(active_id) if active_id else None
st.title(chat["title"] if chat and chat["messages"] else "Autonomous Climate Scientist")
st.caption("Ask a climate question. I’ll check likely spelling corrections before analyzing. No RAG.")
render_data_overview()

with st.container():
    if chat:
      for index, message in enumerate(chat["messages"]):
        with st.chat_message(message["role"]):
            metadata = message.get("metadata", {})
            confirmation = metadata.get("confirmation")
            widget_id = f"{chat['id']}-{index}"
            is_old_report = (message["role"] == "assistant" and not metadata
                             and message["content"].lstrip().startswith("# Scientific Investigation"))
            is_old_plot_error = (message["role"] == "assistant" and not metadata
                                 and "Axes.boxplot() got an unexpected keyword argument 'labels'" in message["content"])
            if is_old_report:
                st.caption("Saved detailed answer from the previous app version.")
                with st.expander("Show saved answer"):
                    st.markdown(message["content"])
            elif is_old_plot_error:
                st.warning("The previous version failed while drawing this chart.")
            else:
                st.markdown(message["content"])

            if (is_old_report or is_old_plot_error):
                previous_question = next((item["content"] for item in reversed(chat["messages"][:index])
                                          if item["role"] == "user"), None)
                if previous_question and st.button("Re-run with the improved analysis", key=f"rerun-{widget_id}"):
                    with st.spinner("Re-running with the updated answer and charts…"):
                        answer, answer_metadata = answer_question(previous_question)
                    add_message(chat, "assistant", answer, metadata=answer_metadata)
                    st.rerun()

            if confirmation and confirmation.get("status") == "pending":
                st.markdown(f"Did you mean **“{confirmation['suggested']}”**?")
                yes_col, no_col = st.columns(2)
                if yes_col.button("Yes, analyze this", key=f"yes-{widget_id}", type="primary"):
                    confirmation["status"] = "confirmed"
                    save_chat(chat)
                    with st.spinner("Analyzing the confirmed question…"):
                        answer, answer_metadata = answer_question(confirmation["suggested"])
                    add_message(chat, "assistant", answer, metadata=answer_metadata)
                    st.rerun()
                if no_col.button("No, use my original wording", key=f"no-{widget_id}"):
                    confirmation["status"] = "original"
                    save_chat(chat)
                    with st.spinner("Analyzing your original question…"):
                        answer, answer_metadata = answer_question(confirmation["original"])
                    add_message(chat, "assistant", answer, metadata=answer_metadata)
                    st.rerun()
            elif message["role"] == "assistant":
                render_explorer(metadata, widget_id, expanded=index == len(chat["messages"]) - 1)
                render_scientific_details(metadata, widget_id)
    else:
        st.info("Try: “How does precipitation vary by season?” or “Is temperature related to rainfall?”")


prompt = st.chat_input("Ask a climate research question…")
if prompt and prompt.strip():
    if not active_id:
        chat = create_chat()
        active_id = chat["id"]
        st.session_state.active_chat_id = active_id
    else:
        chat = load_chat(active_id)

    question = prompt.strip()
    add_message(chat, "user", question)
    suggestion = suggest_corrected_question(question)
    if suggestion:
        add_message(chat, "assistant", "I noticed a possible spelling correction.", metadata={
            "confirmation": {"original": question, "suggested": suggestion, "status": "pending"}
        })
        st.rerun()
    else:
        with st.spinner("Planning and running the scientific analysis…"):
            answer, answer_metadata = answer_question(question)
        add_message(chat, "assistant", answer, metadata=answer_metadata)
        st.rerun()
