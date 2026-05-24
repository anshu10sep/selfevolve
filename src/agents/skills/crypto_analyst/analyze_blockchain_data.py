def analyze_blockchain_data(blockchain_name: str, data_type: str, time_range: str) -> dict:
    """
    Analyzes on-chain data for a specified blockchain, such as transaction volume, active addresses, or whale movements.

    Args:
        blockchain_name: The name of the blockchain (e.g., "Ethereum", "Bitcoin").
        data_type: The type of data to analyze (e.g., "transactions", "active_addresses", "whale_transfers").
        time_range: The time range for the analysis (e.g., "24h", "7d", "30d").

    Returns:
        A dictionary containing the analysis results and key insights.
    """
    print(f"Analyzing {data_type} on {blockchain_name} for the last {time_range}.")
    # Placeholder for actual blockchain data API calls and analysis
    if data_type == "transactions":
        return {"metric": "transaction_count", "value": 1500000, "trend": "increasing"}
    elif data_type == "active_addresses":
        return {"metric": "active_addresses", "value": 500000, "trend": "stable"}
    return {"metric": data_type, "value": "N/A", "trend": "N/A", "error": "Data type not supported."}
===