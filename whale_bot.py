import requests
import time
from datetime import datetime
import json
import hmac
import hashlib
import math

# Binance US API keys
BINANCE_API_KEY = 'ICsKLW8ArFzRJSPHG5ebvk0BCzsXq9nROsctaq3zsG4niOxhoycoMQZPnuCnBums'
BINANCE_SECRET = 'apMeuoC9VSYmUE80m5zkFKjUmLvqDlzBfiDKE2VbJ9wJVx7PbzooNI26TMfK6TJB'
COINGECKO_WHALE_URL = 'https://api.coingecko.com/api/v3/exchanges/binance/tickers?include_exchange_logo=false&precision=2'

class WhaleBot:
    def __init__(self):
        self.portfolio = 334.83  # Initial balance 34.83
        self.trades_log = 'trades.log'
        self.whale_threshold = 1000000  # M+ buys
        self.stop_loss_pct = 0.05  # 5% for more upside
        self.min_notional = 30.0  # Trade size 0 for more trades
        self.safe_coins = ['ETH', 'SOL', 'BTC', 'BNB', 'ADA', 'XRP', 'DOGE', 'LTC', 'LINK', 'UNI', 'AVAX', 'NEAR', 'APT', 'DOT', 'TRX', 'MATIC', 'SHIB']  # Volatile alts

    def get_server_time(self):
        try:
            url = 'https://api.binance.us/api/v3/time'
            response = requests.get(url)
            if response.status_code == 200:
                return int(response.json()['serverTime'])
            return int(time.time() * 1000)
        except Exception as e:
            print(f"Server time fetch error: {e}")
            return int(time.time() * 1000)

    def get_account_balance(self):
        try:
            url = 'https://api.binance.us/api/v3/account'
            timestamp = str(self.get_server_time())
            params = {'timestamp': timestamp}
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = hmac.new(BINANCE_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
            params['signature'] = signature
            headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                balances = response.json()['balances']
                usdt_balance = float(next((b['free'] for b in balances if b['asset'] == 'USDT'), 0))
                portfolio_value = usdt_balance
                asset_balances = {}
                for b in balances:
                    if float(b['free']) > 0 and b['asset'] != 'USDT':
                        price = self.get_current_price(f"{b['asset']}USDT")
                        if price > 0:
                            portfolio_value += float(b['free']) * price
                        asset_balances[b['asset']] = float(b['free'])
                print(f"Available USDT balance: {usdt_balance}, Asset balances: {asset_balances}, Portfolio value: ")
                return usdt_balance, asset_balances, portfolio_value
            else:
                print(f"Balance check failed: {response.text}")
                return 0, {}, 0
        except Exception as e:
            print(f"Balance check error: {e}")
            return 0, {}, 0

    def get_current_price(self, symbol):
        try:
            url = 'https://api.binance.us/api/v3/ticker/price'
            params = {'symbol': symbol}
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return float(response.json()['price'])
            return 0
        except Exception:
            return 0

    def get_symbol_precision(self, symbol):
        try:
            url = 'https://api.binance.us/api/v3/exchangeInfo'
            params = {'symbol': symbol}
            response = requests.get(url, params=params)
            if response.status_code == 200:
                symbol_info = response.json()['symbols'][0]
                for f in symbol_info['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step_size = float(f['stepSize'])
                        precision = int(-math.log10(step_size))
                        return precision
            return 6  # Default precision
        except Exception as e:
            print(f"Symbol precision error for {symbol}: {e}")
            return 6

    def get_open_orders(self):
        try:
            url = 'https://api.binance.us/api/v3/openOrders'
            timestamp = str(self.get_server_time())
            params = {'timestamp': timestamp}
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = hmac.new(BINANCE_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
            params['signature'] = signature
            headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                orders = response.json()
                print(f"Found {len(orders)} total open orders across all symbols")
                return orders
            else:
                print(f"Failed to fetch open orders: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            print(f"Fetch open orders error: {e}")
            return []

    def cancel_open_orders(self, symbol):
        try:
            orders = self.get_open_orders()
            if len(orders) >= 8:
                url = 'https://api.binance.us/api/v3/openOrders'
                timestamp = str(self.get_server_time())
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
                    print(f"Failed to cancel orders for {symbol}: {response.status_code} - {response.text}")
                    return False
            else:
                print(f"No need to cancel orders for {symbol}: {len(orders)} open orders, below limit of 8")
                return True
        except Exception as e:
            print(f"Cancel orders error: {e}")
            return False

    def convert_to_usdt(self, asset, amount):
        try:
            if amount < 0.0001:
                print(f"Amount {amount} {asset} too small for conversion")
                return 0
            symbol = f"{asset}USDT"
            url = 'https://api.binance.us/api/v3/order'
            timestamp = str(self.get_server_time())
            precision = self.get_symbol_precision(symbol)
            rounded_amount = round(amount - (amount % 0.0001), precision)
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
            buys = []
            for ticker in data['tickers']:
                if ticker['converted_volume']['usd'] > self.whale_threshold and ticker['target'] == 'USDT':
                    if ticker['base'] in self.safe_coins:
                        buys.append(ticker)
                        print(f"Whale buy detected: {ticker['converted_volume']['usd']} USD in {ticker['base']} against {ticker['target']}")
            return buys
        except Exception as e:
            print(f"Error fetching whale data: {e}")
            return []

    def place_stop_loss_order(self, symbol, quantity, stop_price):
        try:
            self.cancel_open_orders(symbol)
            url = 'https://api.binance.us/api/v3/order'
            timestamp = str(self.get_server_time())
            precision = self.get_symbol_precision(symbol)
            params = {
                'symbol': symbol,
                'side': 'SELL',
                'type': 'STOP_LOSS_LIMIT',
                'quantity': f"{quantity:.{precision}f}",
                'price': f"{stop_price * 0.99:.2f}",
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
            usdt_balance, asset_balances, portfolio_value = self.get_account_balance()
            if portfolio_value < self.min_notional:
                print(f"Portfolio value  below minimum notional {self.min_notional}. Stopping trades.")
                return False
            if usdt_balance < amount_usd:
                for asset, balance in asset_balances.items():
                    if asset != 'XRP' and balance >= 0.0001:  # Prioritize holding XRP
                        usdt_received = self.convert_to_usdt(asset, balance)
                        if usdt_received > 0:
                            usdt_balance += usdt_received
                        if usdt_balance >= amount_usd:
                            break
            if usdt_balance < amount_usd:
                print(f"Insufficient USDT balance: {usdt_balance} < {amount_usd}")
                return False
            url = 'https://api.binance.us/api/v3/order'
            timestamp = str(self.get_server_time())
            params = {
                'symbol': symbol,
                'side': 'BUY',
                'type': 'MARKET',
                'quoteOrderQty': f"{amount_usd:.2f}",
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
                print(f"Binance: Bought {quantity} {symbol} at {price}, stop loss at {price * (1 - self.stop_loss_pct)}")
                with open(self.trades_log, 'a') as f:
                    f.write(f"{datetime.now()}: Binance Bought {quantity} {symbol} at {price}\n")
                self.place_stop_loss_order(symbol, quantity, price * (1 - self.stop_loss_pct))
                return True
            else:
                print(f"Binance order failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Binance error: {e}")
            return False

    def main(self):
        print("Auto-Trading Bot Started - Tracking All Whale Buys with Rug Pull Protection...")
        last_tx = {}
        while True:
            usdt_balance, asset_balances, portfolio_value = self.get_account_balance()
            if portfolio_value < self.min_notional:
                print(f"Portfolio value  below minimum notional {self.min_notional}. Stopping bot.")
                break
            buys = self.get_whale_buys()
            for tx in buys:
                symbol = f"{tx['base']}USDT"
                currency = tx['base'].lower()
                unique_id = f"{tx['market']['identifier']}_{tx['timestamp']}"
                if currency not in last_tx or unique_id not in last_tx[currency]:
                    if self.get_current_price(symbol) > 0:
                        # Prioritize XRP trades
                        amount = self.min_notional * 2 if currency == 'xrp' else self.min_notional
                        print(f"Whale buy detected: {tx['converted_volume']['usd']} USD in {currency}")
                        self.place_binance_buy_order(symbol, amount)
                        last_tx.setdefault(currency, []).append(unique_id)
                        if len(last_tx[currency]) > 10:
                            last_tx[currency].pop(0)
            time.sleep(300)  # Check every 5 minutes

if __name__ == "__main__":
    bot = WhaleBot()
    bot.main()
