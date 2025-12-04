import os
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('KITE_API_KEY')
API_SECRET = os.getenv('KITE_API_SECRET')

kite = KiteConnect(api_key=API_KEY)

print("=" * 60)
print("KITE CONNECT AUTHENTICATION")
print("=" * 60)

login_url = kite.login_url()
print(f"\n1. Open this URL in your browser and login:")
print(f"\n{login_url}\n")

request_token = input("\nPaste the request_token here: ").strip()

try:
    data = kite.generate_session(request_token, api_secret=API_SECRET)
    access_token = data["access_token"]
    
    with open('.kite_access_token', 'w') as f:
        f.write(access_token)
    
    print(f"\n✓ Authentication successful!")
    print(f"\nAccess Token: {access_token}")
    print(f"\n✓ Token saved to file")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
