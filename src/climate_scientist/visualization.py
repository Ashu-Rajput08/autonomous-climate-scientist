from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats

from .science import analysis_frame


def create_analysis_plot(data, plan: dict, destination: str | Path) -> str:
    """Create a reproducible summary plot for the selected experiment."""
    frame = analysis_frame(data, plan)
    variables = plan["variables"]
    objective = plan["objective"]
    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    if objective == "descriptive" and len(variables) > 1:
        plt.close(fig)
        fig, axes = plt.subplots(len(variables), 1, figsize=(10, 3 * len(variables)),
                                 sharex=True, constrained_layout=True)
        for axis, variable in zip(axes, variables):
            if variable in frame:
                if "city" in frame:
                    for city, group in frame.groupby("city"):
                        axis.plot(group.time_ist, group[variable], linewidth=.55, label=str(city))
                    axis.legend(ncol=2, fontsize="small")
                else:
                    axis.plot(frame.time_ist, frame[variable], linewidth=.55, color="#176b87")
                axis.set_ylabel(variable)
                axis.grid(alpha=.2)
        axes[-1].set_xlabel("Date (source label)" if "city" in frame else "Time (IST)")
        fig.suptitle("Daily climate variables")
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(destination, dpi=150)
        plt.close(fig)
        return str(destination.resolve())
    if objective in {"correlation", "anomaly_correlation"} and len(variables) >= 2:
        x, y = variables[:2]
        plot_frame = frame[[x, y] + (["city"] if "city" in frame else [])].copy()
        plot_frame[[x, y]] = plot_frame[[x, y]].apply(pd.to_numeric, errors="coerce")
        plot_frame = plot_frame.dropna()
        if objective == "anomaly_correlation":
            dates = frame.loc[plot_frame.index, "time_ist"]
            plot_frame["month_day"] = dates.dt.strftime("%m-%d")
            group_columns = ["month_day"] + (["city"] if "city" in plot_frame else [])
            for col in (x, y):
                plot_frame[col] -= plot_frame.groupby(group_columns)[col].transform("mean")
            xlabel, ylabel, title = f"{x} anomaly", f"{y} anomaly", "Seasonality-adjusted daily anomalies"
        else:
            xlabel, ylabel, title = x, y, f"Daily observations: {x} vs {y}"
        if "city" in plot_frame:
            for city, group in plot_frame.groupby("city"):
                ax.scatter(group[x], group[y], s=8, alpha=.25, edgecolors="none", label=str(city))
                if objective == "correlation" and len(group) >= 3:
                    line = stats.linregress(group[x], group[y])
                    limits = [group[x].min(), group[x].max()]
                    ax.plot(limits, [line.intercept + line.slope * value for value in limits], linewidth=1)
            ax.legend(ncol=2, fontsize="small")
        else:
            ax.scatter(plot_frame[x], plot_frame[y], s=8, alpha=.25, color="#176b87", edgecolors="none")
            if objective == "correlation" and len(plot_frame) >= 3:
                line = stats.linregress(plot_frame[x], plot_frame[y])
                limits = [plot_frame[x].min(), plot_frame[x].max()]
                ax.plot(limits, [line.intercept + line.slope * value for value in limits],
                        color="#d34e24", linewidth=2, label="Linear fit")
            ax.legend()
        ax.set(xlabel=xlabel, ylabel=ylabel, title=title)
    elif objective == "seasonal" and variables[0] in frame:
        work = frame[["time_ist", variables[0]] + (["city"] if "city" in frame else [])].dropna().copy()
        season_by_month = {12:"Winter", 1:"Winter", 2:"Winter", 3:"Pre-monsoon", 4:"Pre-monsoon",
            5:"Pre-monsoon", 6:"Monsoon", 7:"Monsoon", 8:"Monsoon", 9:"Monsoon",
            10:"Post-monsoon", 11:"Post-monsoon"}
        work["season"] = work.time_ist.dt.month.map(season_by_month)
        order = ["Winter", "Pre-monsoon", "Monsoon", "Post-monsoon"]
        if "city" in work:
            groups = [(city, season) for city in sorted(work.city.unique()) for season in order]
            labels = [f"{city}\n{season}" for city, season in groups]
            values = [work.loc[(work.city == city) & (work.season == season), variables[0]]
                      for city, season in groups]
        else:
            labels = order
            values = [work.loc[work.season == season, variables[0]] for season in order]
        ax.boxplot(values, tick_labels=labels, showfliers=False)
        ax.set(xlabel="Season (source date)" if "city" in work else "IST season",
               ylabel=variables[0], title=f"Seasonal distribution of {variables[0]}")
    elif objective == "monthly" and variables[0] in frame:
        work = frame[["time_ist", variables[0]] + (["city"] if "city" in frame else [])].dropna().copy()
        work["month"] = work.time_ist.dt.month
        months = list(range(1, 13))
        labels = [pd.Timestamp(2000, month, 1).strftime("%b") for month in months]
        if "city" in work:
            for city, group in work.groupby("city"):
                monthly = group.groupby("month")[variables[0]].mean().reindex(months)
                ax.plot(labels, monthly, marker="o", linewidth=1, label=str(city))
            ax.legend(ncol=2, fontsize="small")
            ax.set(xlabel="Calendar month (source date)", ylabel=variables[0],
                   title=f"Monthly means of {variables[0]} by city")
        else:
            ax.boxplot([work.loc[work.month == month, variables[0]] for month in months],
                       tick_labels=labels, showfliers=False)
            ax.set(xlabel="IST calendar month", ylabel=variables[0],
                   title=f"Monthly distribution of {variables[0]}")
    elif objective == "trend" and variables[0] in frame:
        work = frame[["time_ist", variables[0]] + (["city"] if "city" in frame else [])].dropna()
        for city, group in (work.groupby("city") if "city" in work else [(None, work)]):
            x, y = group.time_ist, pd.to_numeric(group[variables[0]], errors="coerce")
            ax.plot(x, y, linewidth=.55, alpha=.6, label=str(city) if city is not None else None)
            if y.notna().sum() >= 3:
                numeric_x = (x - x.iloc[0]).dt.total_seconds().to_numpy() / (86400 * 365.2425)
                slope, intercept = stats.linregress(numeric_x, y.to_numpy())[:2]
                ax.plot(x, slope * numeric_x + intercept, linewidth=1)
        if "city" in work:
            ax.legend(ncol=2, fontsize="small")
        x_label = "Date (source label)" if plan.get("timezone") != "Asia/Kolkata" else "Time (IST)"
        ax.set(xlabel=x_label, ylabel=variables[0], title=f"{variables[0]} over time")
    else:
        col = variables[0] if variables and variables[0] in frame else next(
            (name for name in frame.columns if name != "time_ist"), None)
        if col is None:
            plt.close(fig)
            raise ValueError("No available variable to plot")
        if "city" in frame:
            for city, group in frame.groupby("city"):
                ax.plot(group.time_ist, group[col], linewidth=.6, label=str(city))
            ax.legend(ncol=2, fontsize="small")
            x_label = "Date (source label)"
        else:
            ax.plot(frame.time_ist, frame[col], linewidth=.6, color="#176b87")
            x_label = "Time (IST)"
        ax.set(xlabel=x_label, ylabel=col, title=f"Daily {col}")
    ax.grid(alpha=.2)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=150)
    plt.close(fig)
    return str(destination.resolve())
