import websockets
import asyncio
import json
import time
from datetime import datetime
import requests

# API keys
BITSGAP_API_KEY = 'oWT319GDCXaycRl8qrUXr4FDRPLtCwxpH0cMQIB9ZSnesFkDu31qy9tSJaa8AHcv'
BITSGAP_SECRET = 'ykpHpGZis85wcxxN7pMVzn0L96UFlzZN8gAKAWFIax3dHUziZHiDzjkmYgAJ1H31'
WHALE_ALERT_WS = 'wss://api.whale-alert.io/v1/feed?api_key=nv3rUbq3b2g0QWhcDZ2kC3ZN1Q6vj2zF'

class WhaleBot:
    def __init__(self):
        self.portfolio = 348.66  # Starting $348.66
        self.trades_log = 'trades.log'
        self.whale_threshold = 1000000  # $1M+ buys
        self.stop_loss_pct = 0.10  # 10%

    async def get_whale_buys(self):
        try:
            async with websockets.connect(WHALE_ALERT_WS) as websocket:
                await websocket.send(json.dumps({
                    'type': 'subscribe',
                    'channels': [{'name': 'transactions', 'currencies': ['eth'], 'min_value': 1000000}]
                }))
                async for message in websocket:
                    data = json.loads(message)
                    print(f"WebSocket Response: {json.dumps(data, indent=2)}")  # Log formatted response
                    if 'type' in data and data['type'] == 'transaction':
                        tx = data
                        if float(tx.get('amount_usd', 0)) > self.whale_threshold:
                            print(f"Found whale buy: {tx.get('amount', 0)} {tx.get('symbol', '')} (${tx.get('amount_usd', 0)})")
                            return [tx]
                    return []
        except Exception as e:
            print(f"Error fetching whale data: {e}")
            return []

    def place_bitsgap_buy_order(self, symbol, amount_usd):
        try:
            url = 'https://api.bitsgap.com/v1/trade'
            headers = {'Authorization': f'Bearer {BITSGAP_API_KEY}'}
            payload = {
                'market': symbol,  # e.g., ETH/USDT
                'amount': amount_usd,
                'side': 'buy',
                'stop_loss': 0.9  # 10% stop loss
            }
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                price = response.json()['price']
                quantity = amount_usd / price
                print(f"Bitsgap: Bought {quantity} {symbol} at {price}, stop loss at {price * 0.9}")
                with open(self.trades_log, 'a') as f:
                    f.write(f"{datetime.now()}: Bitsgap Bought {quantity} {symbol} at {price}\n")
                return True
            else:
                print(f"Bitsgap order failed: {response.text}")
                return False
        except Exception as e:
            print(f"Bitsgap error: {e}")
            return False

    async def main(self):
        print("Auto-Trading Bot Started - Buying Altseason Winners...")
        allocations = {'ETH/USDT': 139.46, 'SOL/USDT': 104.60, 'AIOZ/USDT': 104.60}  # $348.66 split
        last_tx = {}
        while True:
            for symbol, amount in allocations.items():
                currency = symbol.split('/')[0].lower()
                if currency != 'eth':  # Only process ETH for now
                    continue
                buys = await self.get_whale_buys()
                for tx in buys:
                    if tx['symbol'].lower() == currency and tx['hash'] not in last_tx.get(currency, []):
                        print(f"Whale buy detected: {tx['amount']} {currency} (${tx['amount_usd']})")
                        self.place_bitsgap_buy_order(symbol, amount * 0.3)  # 30% of allocation
                        last_tx.setdefault(currency, []).append(tx['hash'])
                        if len(last_tx[currency]) > 10:
                            last_tx[currency].pop(0)
            await asyncio.sleep(300)  # Check every 5 minutes

if __name__ == "__main__":
    bot = WhaleBot()
    asyncio.run(bot.main())
