"""Optional language-level assistance. No retrieval, embeddings, or generated code."""
from pydantic import BaseModel, Field

from .config import MODEL_NAME


class QuestionPlan(BaseModel):
    objective: str = Field(description="One of descriptive, correlation, anomaly_correlation, seasonal, monthly, trend")
    variables: list[str] = Field(description="Dataset variable names; choose only from the supplied list")
    temporal_resolution: str = "daily"
    assumptions: list[str] = Field(default_factory=list)


def model_interpretation(question: str) -> dict | None:
    """Use the configured LangChain chat model only when a key is present."""
    try:
        import os
        if not os.getenv("OPENAI_API_KEY"):
            return None
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(model=MODEL_NAME, temperature=0).with_structured_output(QuestionPlan)
        prompt = (
            "Interpret a climate analysis question for a deterministic local tool. "
            "Do not answer it, calculate anything, invent unavailable data, or request retrieved documents. "
            "Allowed objectives: descriptive, correlation, anomaly_correlation, seasonal, monthly, trend. "
            "Allowed variables: temperature_c, temperature_c_min, temperature_c_max, precipitation_mm, "
            "relative_humidity_pct, surface_pressure_hpa, wind_speed_kmh, cloud_cover_pct, direct_radiation_wm2. "
            "Use daily resolution. Use IST (Asia/Kolkata). Do not infer a location or date range.\n"
            f"Question: {question}"
        )
        parsed = model.invoke(prompt)
        result = parsed.model_dump()
        if result["objective"] not in {"descriptive", "correlation", "anomaly_correlation", "seasonal", "monthly", "trend"}:
            return None
        allowed = {"temperature_c", "temperature_c_min", "temperature_c_max", "precipitation_mm",
                   "relative_humidity_pct", "surface_pressure_hpa", "wind_speed_kmh", "cloud_cover_pct",
                   "direct_radiation_wm2"}
        if any(variable not in allowed for variable in result["variables"]):
            return None
        return result
    except Exception:
        # An unavailable optional provider never blocks the deterministic workflow.
        return None
