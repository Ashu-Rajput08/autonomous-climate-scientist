# Autonomous Climate Scientist

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Timezone](https://img.shields.io/badge/analysis%20timezone-Asia%2FKolkata-138808)


A local-first climate research application for asking questions about two supplied weather datasets. It translates a question into a bounded analysis plan, applies deterministic Python statistics, checks data and method caveats, and presents an answer with interactive charts and a reproducible report.

> **Scientific scope:** this is an exploratory descriptive-analysis tool. Correlations and trends are observational and do not establish causation, attribution, or a forecast.



## Highlights

- **Two usable sources:** an hourly single-location Open-Meteo CSV and an India-wide, ten-city daily CSV. Questions that name cities or request city comparisons can be routed to the city dataset.
- **IST-aware hourly analysis:** the Open-Meteo table retains its source `time` and includes a derived `time_ist` field. Daily aggregation uses IST calendar days. The city source has date-only labels and is deliberately not assigned an invented timezone.
- **Question-aware analysis:** supported objectives include descriptive summaries, trends, monthly and seasonal comparisons, correlations, and seasonality-adjusted correlation sensitivity analysis.
- **Question clarification:** likely spelling corrections are shown for user confirmation; unclear or unsupported analyses receive a clarification or availability response.
- **Interactive research workspace:** local chat history, dataset and parameter discovery, an India coverage map, question-specific Plotly visualizations, and date, month, season, and city filters.
- **Reproducible records:** each completed investigation saves a JSON record and Markdown report with its question, selected source, period, method, results, quality checks, and scientific caveats.
- **No RAG:** there is no document ingestion, embedding index, vector database, or literature retrieval. Numerical work runs through deterministic Python functions.



### Example saved app result

This example is taken from a locally saved investigation record for the included multi-city dataset. Values are shown as recorded; **the source CSV does not specify precipitation units**, so no unit is inferred here.

| Item | Recorded result |
|---|---|
| Question | “Check precipitation of Lucknow” |
| Selected source | India daily multi-city dataset |
| City and period | Lucknow · 2000-01-01 to 2024-12-31 |
| Variable and method | `precipitation_sum` · descriptive statistics |
| Valid daily observations | 9,132 |
| Mean / median | 2.7747 / 0.0 (source unit unspecified) |
| 5th / 95th percentile | 0.0 / 16.4 (source unit unspecified) |

The charts displayed for a question depend on its variable and analysis type; date, month, season, and (where applicable) city filters update the chart set.






### Main components

| Component | Responsibility |
|---|---|
| `app/streamlit_app.py` | Streamlit chat, correction confirmation, dataset overview, graph controls, notes, and chat navigation |
| `data.py` | Dataset loading, schema discovery, source routing support, and data-quality summaries |
| `agent.py` | Question interpretation, experiment planning, deterministic execution, critique, and report generation |
| `science.py` | Daily analysis frames, descriptive statistics, correlation, anomaly correlation, seasonal/monthly summaries, and trend calculations |
| `plotly_visualizations.py` | Question-specific chart collections, labels, India map, and date/month/season filtering |
| `question_check.py` | Likely spelling corrections that require user action |
| `time_range.py` | Interprets explicit time-period language in questions |
| `workflow.py` | LangGraph sequence with a direct workflow fallback if LangGraph is unavailable |
| `chat_store.py` | Local JSON-backed conversations and chat history |
| `llm.py` | Optional structured question interpretation; never performs the statistical calculations |

## Project structure

```text
.
├── app/
│   └── streamlit_app.py                 # Main Streamlit interface
├── src/
│   └── climate_scientist/
│       ├── __init__.py
│       ├── __main__.py                  # Command-line entry point
│       ├── agent.py                     # Planning, execution, critique, reports
│       ├── chat_store.py                # Local chat persistence
│       ├── config.py                    # Paths, timezone, environment loading
│       ├── data.py                      # Dataset loaders, discovery, validation
│       ├── llm.py                       # Optional structured interpretation
│       ├── plotly_visualizations.py     # Interactive chart builders and map
│       ├── question_check.py            # Spelling clarification
│       ├── report_export.py             # Word document builder module
│       ├── science.py                   # Statistical analysis routines
│       ├── time_range.py                # Requested-period parsing
│       ├── visualization.py             # Saved analysis plot helper
│       └── workflow.py                  # Investigation orchestration
├── .streamlit/
│   └── config.toml                      # Dark Streamlit theme
├── .env.example                        # Optional configuration template
├── .gitignore
├── india_2000_2024_daily_weather.csv    # Daily observations for 10 Indian cities
├── open-meteo-21.97N78.98E696m.csv     # Hourly/daily single-location source
├── pyproject.toml
├── README.md
└── requirements.txt
```

Runtime outputs such as experiment JSON/Markdown files, plots, and chat histories are written under `experiments/`, `plots/`, and related local folders. Those generated artifacts are git-ignored; the datasets and source code above are the project inputs.

## Data catalog

### 1. Open-Meteo single-site CSV

| Property | Details |
|---|---|
| Structure | One CSV containing hourly and daily tables separated by blank lines |
| Location metadata | 21.968365° N, 78.981476° E; elevation 696 m |
| Snapshot coverage | 2000-01-01 to 2026-10-02; 234,504 hourly and 9,771 daily rows |
| Source timestamp | `time`, reported in UTC/GMT by the file metadata |
| Analysis timestamp | `time_ist`, derived by adding 05:30; analysis timezone is `Asia/Kolkata` |
| Hourly variables | Temperature (°C), relative humidity (%), precipitation (mm), surface pressure (hPa), wind speed (km/h), wind direction (°), cloud cover (%), and direct radiation (W/m²) |
| Daily variables | Maximum and minimum temperature (°C) |

The project preserves the source `time` and meteorological values. For daily analyses that require aggregation, it forms daily frames from hourly data in memory using IST calendar days; it does not overwrite the supplied daily source table.

### 2. India multi-city daily CSV

| Property | Details |
|---|---|
| Structure | One row per city and date; 91,320 rows × 12 columns |
| Coverage | 2000-01-01 through 2024-12-31; 9,132 daily records per city |
| Cities | Ahmedabad, Bangalore, Chennai, Delhi, Hyderabad, Jaipur, Kolkata, Lucknow, Mumbai, Pune |
| Fields | `city`, `date`, `temperature_2m_max`, `temperature_2m_min`, `apparent_temperature_max`, `apparent_temperature_min`, `precipitation_sum`, `rain_sum`, `weather_code`, `wind_speed_10m_max`, `wind_gusts_10m_max`, `wind_direction_10m_dominant` |
| Observed quality | No missing values and no duplicate city/date rows in the included snapshot |
| Unspecified by source file | Units, provider, timezone, city coordinates, and weather-code legend |

The multi-city fields and values are retained as supplied. The UI map uses approximate city-center markers for orientation because the file itself has no coordinates; those markers are not data observations. Date-only labels are not converted to IST because the source timezone is not specified.

### Source routing

The question router selects the city dataset when a supported city or city-wide comparison is requested, or when the question uses fields available only in that dataset (for example, apparent temperature or wind gusts). Other questions use the single-site Open-Meteo source by default. City-wise results are kept separate; the two sources are not concatenated or pooled.

## Analysis methods and chart selection

| Question intent | Analysis approach | Common chart views |
|---|---|---|
| “Summarize …” | Count, mean, median, standard deviation, and selected percentiles | Distribution and summary views |
| “How does … change over time?” | Ordinary least-squares descriptive trend | Time series and trend line |
| “How does … vary by season?” | IST meteorological-season grouping for Open-Meteo; source date labels for city data | Seasonal comparison, distribution, and summary bars |
| “Show the monthly pattern …” | Calendar-month climatology | Monthly comparison and distribution |
| “Is … related to …?” | Pearson and Spearman correlations on daily observations | Scatter and time-series context |
| “Is the relationship still present after seasonality?” | Calendar-day climatology anomaly correlation as a sensitivity analysis | Raw and anomaly relationship views |

Supported display controls include a date range, selected months, selected seasons, selected cities where the source has a city dimension, and a chart-view selector. Filtering only changes the displayed analysis view; the original CSV files remain unchanged.

## Installation

### Windows PowerShell (VS Code terminal)

The project requires Python 3.10 or newer. First see which interpreters the Windows Python launcher can find:

```powershell
py --list-paths
```

Choose an installed version (the example uses Python 3.13):

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app/streamlit_app.py
```

Streamlit prints a local URL, usually `http://localhost:8501`, and normally opens it in the default browser. Keep the terminal process running while using the app; press **Ctrl+C** in that terminal to stop it.

If PowerShell activation is restricted, invoke the environment executables directly instead:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
```

If `py -3.13` reports that no suitable runtime exists, install Python 3.10+ and the Windows Python launcher, then verify it with `py --list-paths`. A failed `venv` creation means the activation script will not exist yet.

### CLI

After dependency installation, run an investigation from the project root:

```powershell
python -m climate_scientist "How has temperature changed over the past 10 years?"
```

The package console workflow writes experiment outputs to `experiments/runs/` by default.

## Use the app

Example questions:

```text
How does precipitation vary by season?
Show the temperature trend from 2016 to 2026.
Compare humidity across Delhi, Mumbai, and Chennai.
How does apparent temperature vary in Lucknow by month?
Is temperature related to precipitation in the last 10 years?
```

The interpreted date range is shown in the report so the chosen period can be checked. If a spelling correction is suggested, choose whether to analyze the proposed wording or continue with the original question. City and date filters are available with the generated charts.

## Configuration and privacy

`.env.example` documents the available environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_API_KEY` | Enables optional model-assisted structured question interpretation | Empty / disabled |
| `CLIMATE_AGENT_MODEL` | Model name used for that optional interpretation | `gpt-4o-mini` |
| `CLIMATE_DATA_PATH` | Path to the Open-Meteo CSV | `open-meteo-21.97N78.98E696m.csv` |
| `CLIMATE_TIMEZONE` | Documented project timezone setting | `Asia/Kolkata` |

Without an API key the deterministic question interpreter remains available. With a key configured, the question and a constrained interpretation prompt are sent to the configured model provider; the source CSV and statistical calculations are not sent as part of that request. The statistical calculations and validation remain local Python operations. Do not commit `.env` or API keys.

## Outputs and persistence

- **Experiment record:** `experiments/runs/EXP-*.json` — structured plan, source, quality summaries, results, critique, and provenance.
- **Scientific report:** `experiments/runs/EXP-*.md` — readable research question, dataset, methods, results, limitations, and conclusion.
- **Plots:** generated analysis plots are stored in the configured local output area.
- **Chat history:** conversations are stored locally under `experiments/chats/` and can be reopened from the app's history.
- **No cloud database:** these local output directories are ignored by Git so user conversations and generated runs do not enter normal source commits.

The codebase contains `report_export.py`, a Word-export helper module. The current Streamlit chat does not expose a Word-download control; the Markdown scientific report remains available from the answer's scientific-details section.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `No suitable Python runtime found` | Run `py --list-paths`; install Python 3.10+ and recreate `.venv` using an installed version. |
| `Activate.ps1` is missing | The virtual environment was not created successfully. Fix the Python launcher/version first, then run `py -3.13 -m venv .venv` again. |
| `-m is not recognized` | `-m` is a Python option. Use `python -m streamlit run app/streamlit_app.py`, or `streamlit run app/streamlit_app.py`; do not run `-m` by itself. |
| Browser does not open | Keep Streamlit running and open the `Local URL` printed in the terminal manually, typically `http://localhost:8501`. |
| A variable question is not understood | Use a parameter listed in the app's **Data coverage and available parameters** panel. Some source fields are descriptive-only or have unspecified units. |
| City comparison returns no result | Use a city name that appears in the dataset or ask for “all cities”; city source variables and Open-Meteo variables are not interchangeable. |
| Graph looks empty after filtering | Widen the date range and reselect at least one month, season, and city where those controls appear. |

## Limitations

- The city CSV does not state units, timezone, provider, coordinates, or a weather-code legend. The app reports those as unknown rather than guessing.
- Its city markers are approximate geographic context, not observed coordinates from the CSV.
- Weather codes and dominant wind direction are categorical. The current analysis supports descriptive frequency output for these fields, not a numeric mean, correlation, or trend.
- Open-Meteo-derived daily summaries are based on hourly observations and IST day boundaries; incomplete edge days can be excluded from aggregation.
- Ordinary least-squares trend p-values do not adjust for serial autocorrelation, structural breaks, or all confounding. Correlation and trend results require scientific interpretation.
- The included datasets cover specific locations, variables, and time windows. The app does not fetch live weather, produce forecasts, infer causation, or perform climate attribution.
- There is no RAG, external literature search, autonomous generated code, or machine-learning forecasting component.


The registered sources include one hourly single-location dataset and one daily multi-city dataset. Correlation and trend results are observational; seasonality, autocorrelation, endpoint incompleteness, and source coverage constrain interpretation.
