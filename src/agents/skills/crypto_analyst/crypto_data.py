import logging
import time
import os
import requests
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

class CryptoDataClient:
    """
    A robust client for fetching cryptocurrency data from Alpaca.
    Handles API rate limits and server errors gracefully through chunking and exponential backoff.
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Initialize the CryptoDataClient.
        
        Args:
            api_key: Alpaca API key. Defaults to APCA_API_KEY_ID environment variable.
            api_secret: Alpaca API secret. Defaults to APCA_API_SECRET_KEY environment variable.
        """
        self.api_key = api_key or os.environ.get("APCA_API_KEY_ID")
        self.api_secret = api_secret or os.environ.get("APCA_API_SECRET_KEY")
        self.base_url = "https://data.alpaca.markets/v1beta3/crypto/us"
        
    def _chunked_request(self, endpoint: str, symbols: Union[str, List[str]], data_key: str, chunk_size: int = 5, max_retries: int = 3, extra_params: Dict = None) -> Dict[str, Any]:
        """
        Helper method to perform chunked requests with retries to avoid 500 Internal Server Errors.
        
        Args:
            endpoint: The API endpoint to call.
            symbols: List of crypto symbols or comma-separated string.
            data_key: The key in the JSON response containing the data.
            chunk_size: Number of symbols to request per API call.
            max_retries: Maximum number of retries for failed requests.
            extra_params: Additional query parameters.
            
        Returns:
            Dictionary mapping symbols to their requested data.
        """
        if not self.api_key or not self.api_secret:
            logger.error("Alpaca API credentials missing. Please set APCA_API_KEY_ID and APCA_API_SECRET_KEY.")
            return {}
            
        headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "accept": "application/json"
        }
        
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.split(',')]
            
        all_data = {}
        
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i + chunk_size]
            symbols_str = ",".join(chunk)
            params = {"symbols": symbols_str}
            if extra_params:
                params.update(extra_params)
            
            retries = 0
            success = False
            
            while retries < max_retries and not success:
                try:
                    response = requests.get(endpoint, headers=headers, params=params, timeout=15)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data_key in data:
                            all_data.update(data[data_key])
                        success = True
                    elif response.status_code >= 500:
                        logger.warning(f"Server error {response.status_code} for {symbols_str}. Retrying {retries+1}/{max_retries}...")
                        retries += 1
                        time.sleep(2 ** retries)
                    elif response.status_code == 429:
                        logger.warning(f"Rate limited. Retrying {retries+1}/{max_retries}...")
                        retries += 1
                        time.sleep(5 * retries)
                    else:
                        logger.error(f"Error {response.status_code} for {symbols_str}: {response.text}")
                        break
                        
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Request exception for {symbols_str}: {e}. Retrying {retries+1}/{max_retries}...")
                    retries += 1
                    time.sleep(2 ** retries)
                    
            if not success:
                logger.error(f"crypto_screening_failed: Failed to fetch {data_key} for {symbols_str} after {max_retries} retries.")
                
        return all_data

    def get_snapshots(self, symbols: Union[str, List[str]], chunk_size: int = 5, max_retries: int = 3) -> Dict[str, Any]:
        """
        Fetch snapshots for multiple symbols, chunking requests to avoid 500 errors.
        
        Args:
            symbols: List of crypto symbols or comma-separated string.
            chunk_size: Number of symbols to request per API call.
            max_retries: Maximum number of retries for failed requests.
            
        Returns:
            Dictionary mapping symbols to their snapshot data.
        """
        endpoint = f"{self.base_url}/snapshots"
        return self._chunked_request(endpoint, symbols, "snapshots", chunk_size, max_retries)

    def get_latest_bars(self, symbols: Union[str, List[str]], chunk_size: int = 5, max_retries: int = 3) -> Dict[str, Any]:
        """
        Fetch latest bars for multiple symbols.
        
        Args:
            symbols: List of crypto symbols or comma-separated string.
            chunk_size: Number of symbols to request per API call.
            max_retries: Maximum number of retries for failed requests.
            
        Returns:
            Dictionary mapping symbols to their latest bar data.
        """
        endpoint = f"{self.base_url}/latest/bars"
        return self._chunked_request(endpoint, symbols, "bars", chunk_size, max_retries)

    def get_latest_quotes(self, symbols: Union[str, List[str]], chunk_size: int = 5, max_retries: int = 3) -> Dict[str, Any]:
        """
        Fetch latest quotes for multiple symbols.
        
        Args:
            symbols: List of crypto symbols or comma-separated string.
            chunk_size: Number of symbols to request per API call.
            max_retries: Maximum number of retries for failed requests.
            
        Returns:
            Dictionary mapping symbols to their latest quote data.
        """
        endpoint = f"{self.base_url}/latest/quotes"
        return self._chunked_request(endpoint, symbols, "quotes", chunk_size, max_retries)

def fetch_crypto_snapshots(symbols: Union[str, List[str]], chunk_size: int = 5) -> Dict[str, Any]:
    """
    Convenience function to fetch crypto snapshots robustly.
    
    Args:
        symbols: List of crypto symbols or comma-separated string.
        chunk_size: Number of symbols to request per API call.
        
    Returns:
        Dictionary mapping symbols to their snapshot data.
    """
    client = CryptoDataClient()
    return client.get_snapshots(symbols, chunk_size=chunk_size)

def screen_crypto_candidates(symbols: Union[str, List[str]], min_volume: float = 0.0) -> List[str]:
    """
    Screen crypto candidates based on minimum volume using robust data fetching.
    
    Args:
        symbols: List of crypto symbols or comma-separated string.
        min_volume: Minimum daily volume required to pass screening.
        
    Returns:
        List of symbols that passed the screening criteria.
    """
    client = CryptoDataClient()
    snapshots = client.get_snapshots(symbols)
    passed = []
    
    for symbol, data in snapshots.items():
        try:
            daily_bar = data.get("dailyBar", {})
            volume = daily_bar.get("v", 0)
            if volume >= min_volume:
                passed.append(symbol)
        except Exception as e:
            logger.error(f"Error processing snapshot for {symbol}: {e}")
            
    return passed