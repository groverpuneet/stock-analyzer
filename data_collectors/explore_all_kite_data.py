from kiteconnect import KiteConnect
import os
from dotenv import load_dotenv
import json

load_dotenv()

with open('.kite_access_token', 'r') as f:
    access_token = f.read().strip()

kite = KiteConnect(api_key=os.getenv('KITE_API_KEY'))
kite.set_access_token(access_token)

print("\n" + "="*60)
print("COMPLETE QUOTE DATA STRUCTURE")
print("="*60)

quote = kite.quote(["NSE:RELIANCE"])
print(json.dumps(quote, indent=2, default=str))

print("\n" + "="*60)
print("OHLC DATA")
print("="*60)

ohlc = kite.ohlc(["NSE:RELIANCE"])
print(json.dumps(ohlc, indent=2, default=str))

print("\n" + "="*60)
print("LTP (Last Traded Price)")
print("="*60)

ltp = kite.ltp(["NSE:RELIANCE"])
print(json.dumps(ltp, indent=2, default=str))

print("\n" + "="*60)
print("INSTRUMENTS - Sample fields")
print("="*60)

instruments = kite.instruments('NSE')
print(json.dumps(instruments[0], indent=2, default=str))
