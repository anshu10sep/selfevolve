import logging
import traceback
import sys
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

def setup_global_error_handler():
    """
    Set up a global exception handler to catch unhandled exceptions
    and log them in a structured format instead of plain text.
    This prevents 'plain_text_error' bugs in the log scanner.
    """
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.error("Unhandled exception", extra={
            "error_type": exc_type.__name__,
            "error_message": str(exc_value),
            "traceback": tb_str,
            "event": "unhandled_exception",
            "type": "error"
        })

    sys.excepthook = handle_exception

def handle_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Handle an error by logging it and returning a structured error response.
    """
    error_message = str(error)
    tb = traceback.format_exc()
    
    logger.error(f"Error occurred: {error_message}", extra={
        "error_type": type(error).__name__,
        "traceback": tb,
        "context": context or {},
        "event": "handled_error",
        "type": "error"
    })
    
    return {
        "status": "error",
        "error_type": type(error).__name__,
        "message": error_message,
        "traceback": tb,
        "context": context or {}
    }

def safe_execute(func: Callable, *args, **kwargs) -> Any:
    """
    Safely execute a function and handle any exceptions structurally.
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        return handle_error(e, context={"function": func.__name__, "args": args, "kwargs": kwargs})

def parse_plain_text_error(error_text: str) -> Dict[str, str]:
    """
    Parse a plain text error (like a traceback) into a structured format.
    """
    lines = error_text.strip().split('\n')
    error_type = "UnknownError"
    error_message = "An unknown error occurred"
    
    if lines:
        last_line = lines[-1]
        if ":" in last_line:
            parts = last_line.split(":", 1)
            error_type = parts[0].strip()
            error_message = parts[1].strip()
            
    return {
        "type": error_type,
        "message": error_message,
        "full_traceback": error_text
    }