import pandas as pd
from typing import List, Dict, Any

def recognize_chart_patterns(price_data: pd.DataFrame, pattern_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Identifies common chart patterns in historical price data.

    This skill scans price data for predefined technical chart patterns such as
    head and shoulders, double tops/bottoms, triangles, flags, etc.

    Args:
        price_data (pd.DataFrame): A DataFrame containing historical price data,
                                   typically with 'open', 'high', 'low', 'close' columns.
        pattern_config (Dict[str, Any]): A dictionary specifying which patterns to look for
                                         and their recognition parameters (e.g., {'double_top': {'min_peak_distance': 10}}).

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary describes an
                              identified pattern, including its type, start/end dates,
                              and other relevant characteristics. Returns an empty list if no patterns are found.
    """
    if price_data.empty or not isinstance(price_data, pd.DataFrame):
        print("Warning: No price data provided for chart pattern recognition.")
        return []

    if 'close' not in price_data.columns:
        print("Error: 'close' column not found in price data, cannot recognize patterns.")
        return []

    identified_patterns = []
    patterns_to_check = pattern_config.get('patterns', ['double_top', 'double_bottom', 'head_and_shoulders'])

    print(f"Attempting to recognize chart patterns: {patterns_to_check}")
    print(f"Pattern configuration: {pattern_config}")

    # Placeholder for actual pattern recognition logic
    # In a real scenario, this would involve:
    # 1. Smoothing data (optional)
    # 2. Identifying peaks and troughs
    # 3. Applying geometric rules to detect patterns

    # Simulate finding a 'double_top' pattern
    if 'double_top' in patterns_to_check:
        # Very simplified logic: check for two consecutive peaks followed by a dip
        if len(price_data) > 5:
            # Example: Peak at index -4, dip at -3, peak at -2, then drop
            # This is highly illustrative and not a robust pattern detection
            if (price_data['high'].iloc[-4] > price_data['high'].iloc[-5] and
                price_data['high'].iloc[-2] > price_data['high'].iloc[-3] and
                price_data['high'].iloc[-4] > price_data['high'].iloc[-2] * 0.95 and # Peaks are similar
                price_data['high'].iloc[-4] < price_data['high'].iloc[-2] * 1.05 and
                price_data['close'].iloc[-1] < price_data['close'].iloc[-2] # Current price below last peak
            ):
                identified_patterns.append({
                    'pattern_type': 'double_top',
                    'start_date': price_data.index[-5],
                    'end_date': price_data.index[-1],
                    'peak1_date': price_data.index[-4],
                    'peak2_date': price_data.index[-2],
                    'confidence': 0.75, # Example confidence score
                    'description': 'Potential double top pattern identified.'
                })
                print("Simulated detection of a Double Top pattern.")

    # Simulate finding a 'head_and_shoulders' pattern
    if 'head_and_shoulders' in patterns_to_check:
        # Another highly simplified placeholder
        if len(price_data) > 7:
            # Example: Left shoulder, head, right shoulder
            # This is purely illustrative
            if (price_data['high'].iloc[-6] < price_data['high'].iloc[-4] and # Left shoulder < Head
                price_data['high'].iloc[-2] < price_data['high'].iloc[-4] and # Right shoulder < Head
                price_data['high'].iloc[-6] * 0.9 < price_data['high'].iloc[-2] < price_data['high'].iloc[-6] * 1.1 # Shoulders similar height
            ):
                identified_patterns.append({
                    'pattern_type': 'head_and_shoulders',
                    'start_date': price_data.index[-7],
                    'end_date': price_data.index[-1],
                    'left_shoulder_date': price_data.index[-6],
                    'head_date': price_data.index[-4],
                    'right_shoulder_date': price_data.index[-2],
                    'confidence': 0.80,
                    'description': 'Potential Head and Shoulders pattern identified.'
                })
                print("Simulated detection of a Head and Shoulders pattern.")

    return identified_patterns

if __name__ == '__main__':
    # Example Usage:
    sample_data = pd.DataFrame({
        'open': [100, 102, 101, 103, 105, 104, 106, 107, 108, 109, 107, 105, 103, 101, 99],
        'high': [103, 104, 103, 105, 107, 106, 108, 109, 110, 111, 109, 107, 105, 103, 101],
        'low': [99, 101, 100, 102, 103, 102, 104, 105, 106, 107, 105, 103, 101, 99, 97],
        'close': [102, 103, 102, 104, 106, 105, 107, 108, 109, 110, 108, 106, 104, 102, 100],
        'volume': [1000, 1100, 900, 1200, 1300, 1150, 1400, 1500, 1600, 1700, 1500, 1300, 1100, 900, 800]
    }, index=pd.to_datetime(pd.date_range(start='2023-01-01', periods=15, freq='D')))

    # Simulate data that might trigger a double top (e.g., peak, dip, similar peak, drop)
    double_top_data = pd.DataFrame({
        'open': [100, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 109, 108, 106],
        'high': [103, 105, 107, 106, 108, 107, 109, 108, 110, 109, 111, 110, 112, 111, 109],
        'low': [99, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 105],
        'close': [102, 104, 106, 105, 107, 106, 108, 107, 109, 108, 110, 109, 111, 110, 108],
        'volume': [1000, 1100, 1200, 1150, 1300, 1250, 1400, 1350, 1500, 1450, 1600, 1550, 1700, 1650, 1500]
    }, index=pd.to_datetime(pd.date_range(start='2023-01-01', periods=15, freq='D')))
    # Manually adjust to create a double top for the placeholder logic
    double_top_data.loc[double_top_data.index[-5], 'high'] = 115 # Peak 1
    double_top_data.loc[double_top_data.index[-4], 'high'] = 110 # Dip
    double_top_data.loc[double_top_data.index[-3], 'high'] = 114 # Peak 2
    double_top_data.loc[double_top_data.index[-1], 'close'] = 100 # Drop

    print("--- Running recognize_chart_patterns (Double Top) ---")
    config_double_top = {'patterns': ['double_top']}
    patterns_dt = recognize_chart_patterns(double_top_data, config_double_top)
    print("\nIdentified Patterns (Double Top):")
    for p in patterns_dt:
        print(p)

    # Simulate data that might trigger a head and shoulders (e.g., shoulder, head, shoulder)
    hs_data = pd.DataFrame({
        'open': [100, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 109, 108, 106],
        'high': [103, 105, 107, 106, 108, 107, 109, 108, 110, 109, 111, 110, 112, 111, 109],
        'low': [99, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 105],
        'close': [102, 104, 106, 105, 107, 106, 108, 107, 109, 108, 110, 109, 111, 110, 108],
        'volume': [1000, 1100, 1200, 1150, 1300, 1250, 1400, 1350, 1500, 1450, 1600, 1550, 1700, 1650, 1500]
    }, index=pd.to_datetime(pd.date_range(start='2023-01-01', periods=15, freq='D')))
    # Manually adjust to create a head and shoulders for the placeholder logic
    hs_data.loc[hs_data.index[-6], 'high'] = 110 # Left Shoulder
    hs_data.loc[hs_data.index[-4], 'high'] = 115 # Head
    hs_data.loc[hs_data.index[-2], 'high'] = 109 # Right Shoulder

    print("\n--- Running recognize_chart_patterns (Head and Shoulders) ---")
    config_hs = {'patterns': ['head_and_shoulders']}
    patterns_hs = recognize_chart_patterns(hs_data, config_hs)
    print("\nIdentified Patterns (Head and Shoulders):")
    for p in patterns_hs:
        print(p)

    print("\n--- Running with empty data ---")
    empty_patterns = recognize_chart_patterns(pd.DataFrame(), config_double_top)
    print(f"Empty data patterns: {empty_patterns}")

    print("\n--- Running with missing 'close' column ---")
    data_no_close = sample_data.drop(columns=['close'])
    patterns_no_close = recognize_chart_patterns(data_no_close, config_double_top)
    print(f"Patterns without 'close' column: {patterns_no_close}")
===