import logging
from typing import Any, Callable, Coroutine, TypeVar, Dict
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')

def handle_connection_errors(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
    """
    A decorator to catch and handle connection-related OSErrors in async functions.
    
    Args:
        func: The async function to wrap.
        
    Returns:
        The wrapped function.
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await func(*args, **kwargs)
        except OSError as e:
            error_msg = str(e)
            if "Connect call failed" in error_msg or getattr(e, 'errno', None) in (111, 104, 110): 
                # Connection refused, reset, timeout
                logger.error(f"Network/Connection error in {func.__name__}: {error_msg}")
                raise ConnectionError(f"Failed to execute {func.__name__} due to connection issue: {error_msg}") from e
            logger.error(f"OSError in {func.__name__}: {error_msg}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
            raise
            
    return wrapper

def analyze_connection_error(error: Exception) -> Dict[str, Any]:
    """
    Analyze a connection error to determine its root cause and suggest actions.
    
    Args:
        error: The exception to analyze.
        
    Returns:
        A dictionary containing the analysis results.
    """
    analysis = {
        "error_type": type(error).__name__,
        "message": str(error),
        "suggested_action": "Investigate logs",
        "severity": "high"
    }
    
    if isinstance(error, OSError):
        error_msg = str(error)
        errno = getattr(error, 'errno', None)
        
        if "Connect call failed" in error_msg:
            analysis["suggested_action"] = "Check if the target service is running and accessible. Verify network configuration and firewall rules."
            analysis["severity"] = "critical"
        elif errno == 111: # ECONNREFUSED
            analysis["suggested_action"] = "Connection refused. Target service is likely down or not listening on the specified port."
            analysis["severity"] = "critical"
        elif errno == 110: # ETIMEDOUT
            analysis["suggested_action"] = "Connection timed out. Check network latency, routing, or if the target service is overloaded."
            analysis["severity"] = "high"
        elif errno == 104: # ECONNRESET
            analysis["suggested_action"] = "Connection reset by peer. The remote server closed the connection unexpectedly."
            analysis["severity"] = "high"
            
    return analysis