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
CMC_API_URL = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/info'
CMC_API_KEY = '06b8fe2f-9630-4f99-b6f1-0f5f2bc4894e'

class WhaleBot:
    def __init__(self):
        self.portfolio = 334.83  # Initial balance $334.83
        self.trades_log = 'trades.log'
        self.whale_threshold = 1000000  # $1M+ buys
        self.stop_loss_pct = 0.05  # 5% for quick exits
        self.min_notional = 10.0  # Trade size $10 to meet Binance US minimum
        self.min_conversion = 0.10  # Minimum $0.10 for conversions
        self.max_market_cap = 1000000000  # Max $1B market cap
        self.performance_threshold = 0.05  # Hold if >5% gain in 24h
        self.sell_threshold = 0.0  # Sell if <0% (dropping)
        self.excluded_coins = ['BTC', 'ETH', 'BNB', 'USDC', 'SOL', 'DOGE', 'ADA']  # Exclude high-cap coins
        self.priority_coins = ['FARTCOIN', 'PIPPIN', 'MOBY', 'VINE', 'JELLYJELLY', 'POPCAT', 'PNUT', 'TST', 'CHEEMS', 'W', 'XRP', 'APT', 'TRX', 'LINK', 'NEAR', 'DOT', 'UNI', 'LTC', 'ZEC', 'PAXG', 'FLOKI', 'PENGU', 'ETHA', 'FOUR', 'AVANTIS', 'AVNT', 'HEMI', 'OPEN', 'MIRA', 'S', 'TUT', 'NEIRO', 'AAVE', 'ONDO', 'HBAR', 'CRV', 'WLFI', 'ARB', 'OP', 'LDO', 'TWT', 'XLM', 'WBTC', 'BCH', 'PEPE', 'SEI', 'BONK', 'PLUME', 'SOMI', 'TAO', 'LINEA', 'XPLA', 'SUI', 'PUMP', 'FDUSD', 'API3', 'ORDI', 'PENDLE', 'THE', 'WLD']  # Expanded priority coins
        self.market_cap_cache = {}  # Cache for market cap data
        self.cache_expiry = 3600  # Cache for 1 hour
        self.valid_pairs = []  # Cache for valid trading pairs
        self.min_notional_cache = {}  # Cache for pair-specific minimum notional

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

    def get_valid_pairs(self):
        try:
            if self.valid_pairs:
                return self.valid_pairs
            url = 'https://api.binance.us/api/v3/exchangeInfo'
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                self.valid_pairs = [s['symbol'] for s in data['symbols'] if s['status'] == 'TRADING']
                return self.valid_pairs
            print(f"Failed to fetch exchange info: {response.text}")
            return []
        except Exception as e:
            print(f"Exchange info error: {e}")
            return []

    def get_account_balance(self):
        try:
            url = 'https://api.binance.us/api/v3/account'
            timestamp = str(self.get_server_time())
            params = {'timestamp': timestamp, 'recvWindow': 10000}
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
                # Sell excluded coins immediately if sufficient value
                for asset in self.excluded_coins:
                    if asset in asset_balances and asset_balances[asset] >= 0.000001:
                        price = self.get_current_price(f"{asset}USDT")
                        min_notional = self.get_symbol_precision(f"{asset}USDT")[1]
                        if price * asset_balances[asset] >= min_notional:
                            usdt_received = self.convert_to_usdt(asset, asset_balances[asset])
                            if usdt_received > 0:
                                usdt_balance += usdt_received
                                portfolio_value += usdt_received
                                asset_balances[asset] = 0.0
                print(f"Available USDT balance: {usdt_balance}, Asset balances: {asset_balances}, Portfolio value: ${portfolio_value:.2f}")
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
            if symbol in self.min_notional_cache:
                return self.min_notional_cache[symbol]['precision'], self.min_notional_cache[symbol]['min_notional']
            url = 'https://api.binance.us/api/v3/exchangeInfo'
            params = {'symbol': symbol}
            response = requests.get(url, params=params)
            if response.status_code == 200:
                symbol_info = response.json()['symbols'][0]
                precision = 6  # Default precision
                min_notional = self.min_conversion  # Default minimum
                for f in symbol_info['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step_size = float(f['stepSize'])
                        precision = int(-math.log10(step_size))
                    if f['filterType'] == 'MIN_NOTIONAL':
                        min_notional = float(f['minNotional'])
                self.min_notional_cache[symbol] = {'precision': precision, 'min_notional': min_notional}
                return precision, min_notional
            return 6, self.min_conversion
        except Exception as e:
            print(f"Symbol precision error for {symbol}: {e}")
            return 6, self.min_conversion

    def get_price_change(self, symbol):
        try:
            url = 'https://api.binance.us/api/v3/ticker/24hr'
            params = {'symbol': symbol}
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return float(response.json()['priceChangePercent']) / 100
            return 0
        except Exception as e:
            print(f"Price change fetch error for {symbol}: {e}")
            return 0

    def is_low_market_cap(self, coin_id):
        try:
            if coin_id in self.priority_coins:
                return True  # Skip market cap check for priority coins
            # Check cache first
            if coin_id in self.market_cap_cache and time.time() - self.market_cap_cache[coin_id]['timestamp'] < self.cache_expiry:
                market_cap = self.market_cap_cache[coin_id]['market_cap']
                if market_cap == 0:
                    print(f"No market cap data for {coin_id} (cached). Skipping as potential risk.")
                    return False
                if market_cap > self.max_market_cap:
                    print(f"{coin_id} market cap ${market_cap:,} exceeds ${self.max_market_cap:,} (cached). Skipping.")
                    return False
                return True
            # Map ticker to CoinMarketCap symbol
            symbol_map = {
                'XPL': 'XPLA', 'USDE': 'ETHA', 'FORM': 'FORM', 'CAKE': 'CAKE', 'SUI': 'SUI', 'PUMP': 'PUMP',
                'BROCCOLI714': 'BROCCOLI', 'BEAMX': 'BEAM', 'USD1': 'WLFI', 'MUBARAK': 'MUBARAK', 'XUSD': 'XUSD',
                'FDUSD': 'FDUSD', 'API3': 'API3', 'ORDI': 'ORDI', 'PENDLE': 'PENDLE', 'THE': 'THE', 'WLD': 'WLD'
            }
            cmc_symbol = symbol_map.get(coin_id, coin_id)
            url = CMC_API_URL
            params = {'symbol': cmc_symbol, 'CMC_PRO_API_KEY': CMC_API_KEY}
            response = requests.get(url, params=params)
            time.sleep(3)  # Increased to avoid rate limit
            if response.status_code == 200:
                data = response.json()
                market_cap = data.get('data', {}).get(cmc_symbol, {}).get('quote', {}).get('USD', {}).get('market_cap', 0)
                self.market_cap_cache[coin_id] = {'market_cap': market_cap, 'timestamp': time.time()}
                if market_cap == 0:
                    print(f"No market cap data for {coin_id}. Skipping as potential risk.")
                    return False
                if market_cap > self.max_market_cap:
                    print(f"{coin_id} market cap ${market_cap:,} exceeds ${self.max_market_cap:,}. Skipping.")
                    return False
                return True
            print(f"Failed to fetch market cap for {coin_id}: {response.text}")
            return False
        except Exception as e:
            print(f"Market cap check error for {coin_id}: {e}")
            return False

    def get_open_orders(self):
        try:
            url = 'https://api.binance.us/api/v3/openOrders'
            timestamp = str(self.get_server_time())
            params = {'timestamp': timestamp, 'recvWindow': 10000}
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
                params = {'symbol': symbol, 'timestamp': timestamp, 'recvWindow': 10000}
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
            if amount < 0.000001:
                print(f"Amount {amount} {asset} too small for conversion")
                return 0
            symbol = f"{asset}USDT"
            if symbol not in self.get_valid_pairs():
                print(f"Trading pair {symbol} not available on Binance US. Skipping.")
                return 0
            url = 'https://api.binance.us/api/v3/order'
            timestamp = str(self.get_server_time())
            precision, min_notional = self.get_symbol_precision(symbol)
            rounded_amount = round(amount, precision)
            if rounded_amount < 0.000001:
                print(f"Rounded amount {rounded_amount} {asset} too small for conversion")
                return 0
            price = self.get_current_price(symbol)
            if price * rounded_amount < min_notional:
                print(f"Value {price * rounded_amount} USDT for {rounded_amount} {asset} below minimum ${min_notional}. Skipping.")
                return 0
            params = {
                'symbol': symbol,
                'side': 'SELL',
                'type': 'MARKET',
                'quantity': f"{rounded_amount:.{precision}f}",
                'timestamp': timestamp,
                'recvWindow': 10000
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

    def sell_underperforming(self, asset_balances):
        usdt_balance = 0
        for asset, balance in asset_balances.items():
            if asset in self.excluded_coins or balance < 0.000001:
                continue
            price_change = self.get_price_change(f"{asset}USDT")
            if price_change >= self.performance_threshold:
                print(f"{asset} price change {price_change*100:.2f}% >= {self.performance_threshold*100:.2f}%. Holding.")
                continue
            if price_change < self.sell_threshold:
                print(f"{asset} price change {price_change*100:.2f}% < {self.sell_threshold*100:.2f}%. Selling.")
                usdt_received = self.convert_to_usdt(asset, balance)
                if usdt_received > 0:
                    usdt_balance += usdt_received
        return usdt_balance

    def get_whale_buys(self):
        try:
            response = requests.get(COINGECKO_WHALE_URL)
            response.raise_for_status()
            data = response.json()
            buys = []
            valid_pairs = self.get_valid_pairs()
            for ticker in data['tickers']:
                if ticker['converted_volume']['usd'] > self.whale_threshold and ticker['target'] == 'USDT' and ticker['base'] not in self.excluded_coins:
                    symbol = f"{ticker['base']}USDT"
                    if symbol not in valid_pairs:
                        print(f"Trading pair {symbol} not available on Binance US. Skipping.")
                        continue
                    if ticker['base'] in self.priority_coins or self.is_low_market_cap(ticker['base']):
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
            precision, _ = self.get_symbol_precision(symbol)
            params = {
                'symbol': symbol,
                'side': 'SELL',
                'type': 'STOP_LOSS_LIMIT',
                'quantity': f"{quantity:.{precision}f}",
                'price': f"{stop_price * 0.99:.2f}",
                'stopPrice': f"{stop_price:.2f}",
                'timeInForce': 'GTC',
                'timestamp': timestamp,
                'recvWindow': 10000
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
            if symbol not in self.get_valid_pairs():
                print(f"Trading pair {symbol} not available on Binance US. Skipping.")
                return False
            usdt_balance, asset_balances, portfolio_value = self.get_account_balance()
            if portfolio_value < self.min_notional:
                print(f"Portfolio value ${portfolio_value:.2f} below minimum notional {self.min_notional}. Stopping trades.")
                return False
            usdt_balance += self.sell_underperforming(asset_balances)
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
                'timestamp': timestamp,
                'recvWindow': 10000
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
        print("Auto-Trading Bot Started - Tracking Low Market Cap Meme Coin Whale Buys...")
        last_tx = {}
        while True:
            usdt_balance, asset_balances, portfolio_value = self.get_account_balance()
            if portfolio_value < self.min_notional:
                print(f"Portfolio value ${portfolio_value:.2f} below minimum notional {self.min_notional}. Stopping bot.")
                break
            buys = self.get_whale_buys()
            for tx in buys:
                symbol = f"{tx['base']}USDT"
                currency = tx['base'].lower()
                unique_id = f"{tx['market']['identifier']}_{tx['timestamp']}"
                if currency not in last_tx or unique_id not in last_tx[currency]:
                    if self.get_current_price(symbol) > 0:
                        print(f"Whale buy detected: {tx['converted_volume']['usd']} USD in {currency}")
                        self.place_binance_buy_order(symbol, self.min_notional)
                        last_tx.setdefault(currency, []).append(unique_id)
                        if len(last_tx[currency]) > 10:
                            last_tx[currency].pop(0)
            time.sleep(300)  # Check every 5 minutes

if __name__ == "__main__":
    bot = WhaleBot()
    bot.main()
