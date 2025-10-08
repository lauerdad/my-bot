import requests
import time
from datetime import datetime
import json
import hmac
import hashlib

# API keys
BITSGAP_API_KEY = 'ICsKLW8ArFzRJSPHG5ebvk0BCzsXq9nROsctaq3zsG4niOxhoycoMQZPnuCnBums'
BITSGAP_SECRET = 'apMeuoC9VSYmUE80m5zkFKjUmLvqDlzBfiDKE2VbJ9wJVx7PbzooNI26TMfK6TJB'
COINGECKO_WHALE_URL = 'https://api.coingecko.com/api/v3/exchanges/binance/tickers?coin_ids=ethereum&include_exchange_logo=false&precision=2'

class WhaleBot:
    def __init__(self):
        self.portfolio = 345.82  # Updated balance 45.82
        self.trades_log = 'trades.log'
        self.whale_threshold = 1000000  # M+ buys
        self.stop_loss_pct = 0.10  # 10%

    def get_whale_buys(self):
        try:
            response = requests.get(COINGECKO_WHALE_URL)
            response.raise_for_status()
            data = response.json()
            # Look for large trades on ETH
            buys = []
            for ticker in data['tickers']:
                if ticker['base'] == 'ETH' and ticker['converted_volume']['usd'] > self.whale_threshold:
                    print(f"Whale buy detected: {ticker['converted_volume']['usd']} USD volume on {ticker['target']}")
                    buys.append(ticker)
            return buys
        except Exception as e:
            print(f"Error fetching whale data: {e}")
            return []

    def place_bitsgap_buy_order(self, symbol, amount_usd):
        try:
            url = 'https://api.bitsgap.com/private/v1/trading/order'
            timestamp = str(int(time.time() * 1000))
            payload = {
                'exchange': 'binanceus',
                'symbol': symbol,  # e.g., ETHUSDT
                'amount': amount_usd,
                'side': 'buy',
                'type': 'market',
                'stop_loss': 0.9  # 10% stop loss
            }
            query_string = json.dumps(payload, separators=(',', ':'))
            signature = hmac.new(BITSGAP_SECRET.encode(), (timestamp + query_string).encode(), hashlib.sha256).hexdigest()
            headers = {
                'X-API-KEY': BITSGAP_API_KEY,
                'X-API-TIMESTAMP': timestamp,
                'X-API-SIGNATURE': signature
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
                print(f"Bitsgap order failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Bitsgap error: {e}")
            return False

    def main(self):
        print("Auto-Trading Bot Started - Buying Altseason Winners...")
        allocations = {'ETHUSDT': 138.33, 'SOLUSDT': 103.74, 'AIOZUSDT': 103.75}  # 45.82 split
        last_tx = {}
        while True:
            for symbol, amount in allocations.items():
                currency = symbol.split('USDT')[0].lower()
                buys = self.get_whale_buys()
                for tx in buys:
                    unique_id = f"{tx['market']['identifier']}_{tx['timestamp']}"
                    if tx['base'].lower() == currency and unique_id not in last_tx.get(currency, []):
                        print(f"Whale buy detected: {tx['converted_volume']['usd']} USD in {currency}")
                        self.place_bitsgap_buy_order(symbol, amount * 0.3)  # 30% of allocation
                        last_tx.setdefault(currency, []).append(unique_id)
                        if len(last_tx[currency]) > 10:
                            last_tx[currency].pop(0)
            time.sleep(300)  # Check every 5 minutes

if __name__ == "__main__":
    bot = WhaleBot()
    bot.main()
