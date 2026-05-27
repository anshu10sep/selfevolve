import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

class MomentumStrategy:
    """
    Momentum trading strategy implementation.
    """
    def __init__(self, lookback_period: int = 14):
        self.lookback_period = lookback_period

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generates trading signals based on momentum.
        
        Args:
            data (pd.DataFrame): Market data containing at least a 'close' column.
            
        Returns:
            pd.DataFrame: DataFrame with momentum and signal columns.
        """
        if data is None or data.empty:
            logger.warning("Empty data provided to MomentumStrategy.")
            return pd.DataFrame()
            
        df = data.copy()
        
        # Calculate momentum
        if 'close' in df.columns:
            df['momentum'] = df['close'].diff(self.lookback_period)
            df['signal'] = np.where(df['momentum'] > 0, 1, -1)
            # Neutral signal if momentum is NaN
            df['signal'] = np.where(df['momentum'].isna(), 0, df['signal'])
        else:
            logger.error("Data does not contain 'close' column.")
            
        return df