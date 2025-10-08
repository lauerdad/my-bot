import requests
import time
from datetime import datetime
import json
import hmac
import hashlib

# Binance US API keys
BINANCE_API_KEY = 'ICsKLW8ArFzRJSPHG5ebvk0BCzsXq9nROsctaq3zsG4niOxhoycoMQZPnuCnBums'
BINANCE_SECRET = 'apMeuoC9VSYmUE80m5zkFKjUmLvqDlzBfiDKE2VbJ9wJVx7PbzooNI26TMfK6TJB'
COINGECKO_WHALE_URL = 'https://api.coingecko.com/api/v3/exchanges/binance/tickers?coin_ids=ethereum,solana,aioz-network&include_exchange_logo=false&precision=2'

class WhaleBot:
    def __init__(self):
        self.portfolio = 334.83  # Updated balance 34.83
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
                sol_balance = float(next((b['free'] for b in balances if b['asset'] == 'SOL'), 0))
                aioz_balance = float(next((b['free'] for b in balances if b['asset'] == 'AIOZ'), 0))
                print(f"Available USDT balance: {usdt_balance}, ETH balance: {eth_balance}, SOL balance: {sol_balance}, AIOZ balance: {aioz_balance}")
                return usdt_balance, eth_balance, sol_balance, aioz_balance
            else:
                print(f"Balance check failed: {response.text}")
                return 0, 0, 0, 0
        except Exception as e:
            print(f"Balance check error: {e}")
            return 0, 0, 0, 0

    def cancel_open_orders(self, symbol):
        try:
            url = 'https://api.binance.us/api/v3/openOrders'
            timestamp = str(int(time.time() * 1000))
            params = {'symbol': symbol, 'timestamp': timestamp}
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = hmac.new(BINANCE_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
            params['signature'] = signature
            headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
            response = requests.delete(url, headers=headers, params=params)
            if response.status_code == 200:
                print(f"Canceled open orders for {symbol}")
                return True
            else:
                print(f"Failed to cancel orders: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Cancel orders error: {e}")
            return False

    def convert_to_usdt(self, asset, amount):
        try:
            if amount < 0.0001:  # Minimum lot size check
                print(f"Amount {amount} {asset} too small for conversion")
                return 0
            symbol = f"{asset}USDT"
            url = 'https://api.binance.us/api/v3/order'
            timestamp = str(int(time.time() * 1000))
            precision = 6 if asset == 'ETH' else 2  # ETH: 6 decimals, SOL/AIOZ: 2 decimals
            rounded_amount = round(amount - (amount % 0.0001), precision)  # Align to step size 0.0001
            if rounded_amount < 0.0001:
                print(f"Rounded amount {rounded_amount} {asset} too small for conversion")
                return 0
            params = {
                'symbol': symbol,
                'side': 'SELL',
                'type': 'MARKET',
                'quantity': f"{rounded_amount:.{precision}f}",
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
                print(f"Converted {rounded_amount:.{precision}f} {asset} to {usdt_received} USDT")
                return usdt_received
            else:
                print(f"{asset} to USDT conversion failed: {response.status_code} - {response.text}")
                return 0
        except Exception as e:
            print(f"Conversion error: {e}")
            return 0

    def get_whale_buys(self):
        try:
            response = requests.get(COINGECKO_WHALE_URL)
            response.raise_for_status()
            data = response.json()
            # Look for large trades on ETH, SOL, AIOZ
            buys = []
            for ticker in data['tickers']:
                if ticker['base'] in ['ETH', 'SOL', 'AIOZ'] and ticker['converted_volume']['usd'] > self.whale_threshold:
                    print(f"Whale buy detected: {ticker['converted_volume']['usd']} USD volume on {ticker['target']} for {ticker['base']}")
                    buys.append(ticker)
            return buys
        except Exception as e:
            print(f"Error fetching whale data: {e}")
            return []

    def place_stop_loss_order(self, symbol, quantity, stop_price):
        try:
            # Cancel existing stop-loss orders to avoid MAX_NUM_ALGO_ORDERS
            self.cancel_open_orders(symbol)
            url = 'https://api.binance.us/api/v3/order'
            timestamp = str(int(time.time() * 1000))
            params = {
                'symbol': symbol,
                'side': 'SELL',
                'type': 'STOP_LOSS_LIMIT',
                'quantity': f"{quantity:.{6 if symbol == 'ETHUSDT' else 2}f}",
                'price': f"{stop_price * 0.99:.2f}",  # Slightly below stop for execution
                'stopPrice': f"{stop_price:.2f}",
                'timeInForce': 'GTC',
                'timestamp': timestamp
            }
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = hmac.new(BINANCE_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
            params['signature'] = signature
            headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
            response = requests.post(url, headers=headers, params=params)
            if response.status_code == 200:
                print(f"Stop-loss order placed for {quantity} {symbol} at {stop_price}")
                return True
            else:
                print(f"Stop-loss order failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Stop-loss error: {e}")
            return False

    def place_binance_buy_order(self, symbol, amount_usd):
        try:
            # Check balance
            usdt_balance, eth_balance, sol_balance, aioz_balance = self.get_account_balance()
            if usdt_balance < amount_usd:
                print(f"Insufficient USDT balance: {usdt_balance} < {amount_usd}")
                return False
            url = 'https://api.binance.us/api/v3/order'
            timestamp = str(int(time.time() * 1000))
            params = {
                'symbol': symbol,
                'side': 'BUY',
                'type': 'MARKET',
                'quoteOrderQty': f"{amount_usd:.2f}",  # 2 decimal precision for USD
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
                # Place stop-loss order
                self.place_stop_loss_order(symbol, quantity, price * 0.9)
                return True
            else:
                print(f"Binance order failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Binance error: {e}")
            return False

    def main(self):
        print("Auto-Trading Bot Started - Buying Altseason Winners...")
        allocations = {'ETHUSDT': 10.00, 'SOLUSDT': 10.00, 'AIOZUSDT': 0.0}  # 0 minimum notional
        last_tx = {}
        while True:
            for symbol, amount in allocations.items():
                if amount == 0:
                    continue  # Skip AIOZ if no allocation
                currency = symbol.split('USDT')[0].lower()
                buys = self.get_whale_buys()
                for tx in buys:
                    unique_id = f"{tx['market']['identifier']}_{tx['timestamp']}"
                    if tx['base'].lower() == currency and unique_id not in last_tx.get(currency, []):
                        print(f"Whale buy detected: {tx['converted_volume']['usd']} USD in {currency}")
                        self.place_binance_buy_order(symbol, amount)  # Use minimum notional amount
                        last_tx.setdefault(currency, []).append(unique_id)
                        if len(last_tx[currency]) > 10:
                            last_tx[currency].pop(0)
            time.sleep(300)  # Check every 5 minutes

if __name__ == "__main__":
    bot = WhaleBot()
    bot.main()
