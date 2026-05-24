import asyncio
import httpx
from config.settings import get_settings

async def test_alpaca_crypto_trade():
    settings = get_settings()
    print(f"Testing Alpaca API at: {settings.alpaca_base_url}")
    
    order_data = {
        "symbol": "DOGE/USD", 
        "notional": "10", # Buy $10 worth of DOGE
        "side": "buy",
        "type": "market",
        "time_in_force": "gtc",
    }
    
    try:
        async with httpx.AsyncClient(
            headers={
                "APCA-API-KEY-ID": settings.alpaca_api_key,
                "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
            },
            timeout=15,
        ) as hc:
            print("Submitting market order for $10 of DOGE/USD...")
            r = await hc.post(f"{settings.alpaca_base_url}/v2/orders", json=order_data)
            
            if r.status_code in (200, 201):
                order = r.json()
                print(f"SUCCESS! Order placed. Order ID: {order.get('id')}")
                print(f"Status: {order.get('status')}")
                print(f"Filled: {order.get('filled_qty', 0)}")
            else:
                print(f"FAILED. Status Code: {r.status_code}")
                print(f"Response: {r.text}")
    except Exception as e:
        print(f"Error placing trade: {e}")

if __name__ == "__main__":
    asyncio.run(test_alpaca_crypto_trade())
