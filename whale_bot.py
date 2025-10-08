import requests
import time
from datetime import datetime
import json
import hmac
import hashlib

# Binance US API keys
BINANCE_API_KEY = 'ICsKLW8ArFzRJSPHG5ebvk0BCzsXq9nROsctaq3zsG4niOxhoycoMQZPnuCnBums'
BINANCE_SECRET = 'apMeuoC9VSYmUE80m5zkFKjUmLvqDlzBfiDKE2VbJ9wJVx7PbzooNI26TMfK6TJB'
COINGECKO_WHALE_URL = 'https://api.coingecko.com/api/v3/exchanges/binance/tickers?coin_ids=ethereum&include_exchange_logo=false&precision=2'

class WhaleBot:
    def __init__(self):
        self.portfolio = 348.00  # Updated balance 48.00
        self.trades_log = 'trades.log'
        self.whale_threshold = 1000000  # M+ buys
        self.stop_loss_pct = 0.10  # 10%

    def get_account_balance(self):
        try:
            url = 'https://api.binance.us/api/v3/account'
            timestamp = str(int(time.time() * 1000))
            params = {'timestamp': timestamp}
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = hmac.new(BINANCE_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
            params['signature'] = signature
            headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                balances = response.json()['balances']
                usdt_balance = float(next((b['free'] for b in balances if b['asset'] == 'USDT'), 0))
                eth_balance = float(next((b['free'] for b in balances if b['asset'] == 'ETH'), 0))
                print(f"Available USDT balance: {usdt_balance}, ETH balance: {eth_balance}")
                return usdt_balance, eth_balance
            else:
                print(f"Balance check failed: {response.text}")
                return 0, 0
        except Exception as e:
            print(f"Balance check error: {e}")
            return 0, 0

    def convert_eth_to_usdt(self, eth_amount):
        try:
            url = 'https://api.binance.us/api/v3/order'
            timestamp = str(int(time.time() * 1000))
            params = {
                'symbol': 'ETHUSDT',
                'side': 'SELL',
                'type': 'MARKET',
                'quantity': f"{eth_amount:.8f}",  # Ensure 8 decimal precision
                'timestamp': timestamp
            }
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = hmac.new(BINANCE_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
            params['signature'] = signature
            headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
            response = requests.post(url, headers=headers, params=params)
            if response.status_code == 200:
                order = response.json()
                usdt_received = float(order['cummulativeQuoteQty'])
                print(f"Converted {eth_amount:.8f} ETH to {usdt_received} USDT")
                return usdt_received
            else:
                print(f"ETH to USDT conversion failed: {response.status_code} - {response.text}")
                return 0
        except Exception as e:
            print(f"Conversion error: {e}")
            return 0

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

    def place_binance_buy_order(self, symbol, amount_usd):
        try:
            # Check balance and convert ETH to USDT if needed
            usdt_balance, eth_balance = self.get_account_balance()
            if usdt_balance < amount_usd and eth_balance >= 0.07757957:
                eth_to_sell = 0.07757957  # Sell exact available ETH
                usdt_received = self.convert_eth_to_usdt(eth_to_sell)
                if usdt_received == 0:
                    return False
                usdt_balance += usdt_received
            if usdt_balance < amount_usd:
                print(f"Insufficient USDT balance: {usdt_balance} < {amount_usd}")
                return False
            url = 'https://api.binance.us/api/v3/order'
            timestamp = str(int(time.time() * 1000))
            params = {
                'symbol': symbol,  # e.g., ETHUSDT
                'side': 'BUY',
                'type': 'MARKET',
                'quoteOrderQty': amount_usd,  # Amount in USD
                'timestamp': timestamp
            }
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = hmac.new(BINANCE_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
            params['signature'] = signature
            headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
            response = requests.post(url, headers=headers, params=params)
            if response.status_code == 200:
                order = response.json()
                price = float(order['fills'][0]['price'])
                quantity = float(order['executedQty'])
                print(f"Binance: Bought {quantity} {symbol} at {price}, stop loss at {price * 0.9}")
                with open(self.trades_log, 'a') as f:
                    f.write(f"{datetime.now()}: Binance Bought {quantity} {symbol} at {price}\n")
                return True
            else:
                print(f"Binance order failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Binance error: {e}")
            return False

    def main(self):
        print("Auto-Trading Bot Started - Buying Altseason Winners...")
        allocations = {'ETHUSDT': 138.33, 'SOLUSDT': 103.74, 'AIOZUSDT': 103.75}  # 48.00 split
        last_tx = {}
        while True:
            for symbol, amount in allocations.items():
                currency = symbol.split('USDT')[0].lower()
                buys = self.get_whale_buys()
                for tx in buys:
                    unique_id = f"{tx['market']['identifier']}_{tx['timestamp']}"
                    if tx['base'].lower() == currency and unique_id not in last_tx.get(currency, []):
                        print(f"Whale buy detected: {tx['converted_volume']['usd']} USD in {currency}")
                        self.place_binance_buy_order(symbol, amount * 0.3)  # 30% of allocation
                        last_tx.setdefault(currency, []).append(unique_id)
                        if len(last_tx[currency]) > 10:
                            last_tx[currency].pop(0)
            time.sleep(300)  # Check every 5 minutes

if __name__ == "__main__":
    bot = WhaleBot()
    bot.main()
