import requests
import logging
import time
from typing import Optional
from .network_diagnostics import verify_and_repair_network

logger = logging.getLogger(__name__)

class TelegramBot:
    """
    A robust Telegram Bot client that handles network and DNS failures gracefully.
    """
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def send_alert(self, message: str, retries: int = 3, backoff_factor: float = 2.0) -> bool:
        """
        Send an alert to Telegram with retry logic for network/DNS failures.
        
        Args:
            message (str): The message to send.
            retries (int): Number of retry attempts.
            backoff_factor (float): Multiplier for exponential backoff.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        for attempt in range(retries + 1):
            try:
                response = requests.post(self.api_url, json=payload, timeout=10)
                response.raise_for_status()
                logger.info("Telegram alert sent successfully.")
                return True
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error sending Telegram alert (Attempt {attempt + 1}/{retries + 1}): {e}")
                error_str = str(e)
                if "NameResolutionError" in error_str or "Temporary failure in name resolution" in error_str or "[Errno -3]" in error_str:
                    logger.error("DNS resolution failed. Triggering network diagnostics...")
                    verify_and_repair_network()
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to send Telegram alert (Attempt {attempt + 1}/{retries + 1}): {e}")
            
            if attempt < retries:
                sleep_time = backoff_factor ** attempt
                logger.info(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
                
        logger.error("All attempts to send Telegram alert failed.")
        return False

def send_telegram_alert(bot_token: str, chat_id: str, message: str) -> bool:
    """
    Helper function to send a Telegram alert.
    
    Args:
        bot_token (str): The Telegram bot token.
        chat_id (str): The chat ID to send the message to.
        message (str): The message content.
        
    Returns:
        bool: True if successful, False otherwise.
    """
    bot = TelegramBot(bot_token, chat_id)
    return bot.send_alert(message)