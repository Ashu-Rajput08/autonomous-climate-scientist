# Autonomous Climate Scientist (V1)

A local, reproducible climate research workflow for the included Open-Meteo dataset. It converts a research question into a bounded analysis plan, runs deterministic Python tools, checks methodological risks, and saves an experiment record and structured report. The project uses India Standard Time (`Asia/Kolkata`, UTC+05:30).

**No RAG is implemented.** There are no embeddings, vector stores, document ingestion, or literature retrieval. An optional LLM may assist with question interpretation; Python performs all numerical calculations and the critic applies explicit checks. The workflow also runs without an API key.

## Quick start (Windows / VS Code)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app/streamlit_app.py
```

After pulling or editing project dependencies, rerun `python -m pip install -r requirements.txt` in the activated `.venv`, then restart Streamlit so the dark theme and Plotly charts load.

Set `OPENAI_API_KEY` in `.env` only if you want optional model-assisted question interpretation. CLI: `python -m climate_scientist "Is temperature related to precipitation?"` after `pip install -e .`.

## Dataset and time handling

The supplied CSV contains hourly and daily tables separated by blank lines. Original UTC `time` values and all existing fields are preserved. The added `time_ist` column is the UTC timestamp plus 05:30, and is included in both tables. Analyses that need daily data aggregate the hourly observations on IST calendar days in memory; the source daily values remain untouched.

The project also catalogs `india_2000_2024_daily_weather.csv` as an additional multi-city daily source. It contains 91,320 rows, 10 city labels, and date-only records from 2000-01-01 through 2024-12-31. All columns currently have zero missing values; each city has 9,132 unique daily records and there are no duplicate city/date rows. Its CSV does not provide units, coordinates, provider provenance, timezone, or a weather-code legend. These metadata remain explicitly unspecified; date labels are not converted to IST. `discover_datasets()` exposes both sources, while `load_city_daily_dataset()` reads this source without renaming or changing its columns and returns its observed schema, per-city coverage, missingness, and duplicate/gap metadata. The question router uses the city source when a supported city, city-only field, or city comparison is requested, and otherwise uses the configured Open-Meteo source. City comparisons are calculated separately; records from the two sources are not pooled because their locations, temporal structures, and documented metadata differ.

## Workflow and scope

The V1 workflow checks likely spelling errors and asks for confirmation before using a suggested correction. Ambiguous questions ask for the missing variable instead of silently choosing one. It produces a short answer and saves the full Markdown report and JSON provenance under `experiments/runs/`. The dark Streamlit chat stores conversations locally under `experiments/chats/`. Graphs are question-specific and include date, month, and season filters with multiple complementary views. Unsupported variables such as UV index receive a data-availability explanation instead of an unrelated plot. The analyses do not infer causation. Machine learning, forecasting, and autonomous model-driven code execution are intentionally out of this initial version.

## Layout

- `src/climate_scientist/data.py`: loading, metadata, quality validation
- `src/climate_scientist/science.py`: deterministic preprocessing and statistics
- `src/climate_scientist/agent.py`: question interpretation, experiment planning, analysis, critique, concise and full reports
- `src/climate_scientist/question_check.py`: spelling suggestions requiring user confirmation
- `src/climate_scientist/plotly_visualizations.py`: multiple dark-mode chart views and date/month/season filters
- `src/climate_scientist/chat_store.py`: persistent local conversation history
- `src/climate_scientist/workflow.py`: LangGraph orchestration with a fallback
- `app/streamlit_app.py`: local interface
- `experiments/runs/`: saved experiment records and reports

The registered sources include one hourly single-location dataset and one daily multi-city dataset. Correlation and trend results are observational; seasonality, autocorrelation, endpoint incompleteness, and source coverage constrain interpretation.
