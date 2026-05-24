def monitor_model_performance(model_id: str, metrics_data: dict) -> dict:
    """
    Monitors the real-time performance of deployed models, checking for drift, accuracy, and latency.

    Args:
        model_id: The identifier of the model being monitored.
        metrics_data: A dictionary of recent performance metrics (e.g., accuracy, F1-score, prediction latency).

    Returns:
        A dictionary summarizing the model's health, any detected performance degradation, and alerts.
    """
    print(f"Monitoring performance for model '{model_id}'.")
    # Placeholder for actual model monitoring logic
    if metrics_data.get("accuracy", 0) < 0.8:
        health_status = "degraded"
        alert = "Accuracy below threshold, potential data drift or model decay."
    else:
        health_status = "healthy"
        alert = "None"
    return {"health_status": health_status, "current_metrics": metrics_data, "alert": alert}
