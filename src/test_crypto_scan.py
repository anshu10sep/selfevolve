import asyncio
import structlog
from main import SelfEvolveSystem
from config.settings import get_settings

logger = structlog.get_logger("test_crypto")

async def test_crypto():
    settings = get_settings()
    print(f"Testing with Alpaca URL: {settings.alpaca_base_url}")
    print(f"Environment: {settings.environment}")
    
    system = SelfEvolveSystem()
    await system.startup()
    
    print("\n--- TRIGGERING CRYPTO SCAN ---")
    await system._run_crypto_scan()
    print("--- CRYPTO SCAN COMPLETE ---\n")
    
    await system.shutdown()

if __name__ == "__main__":
    asyncio.run(test_crypto())
