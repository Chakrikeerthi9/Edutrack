import httpx
import os
from dotenv import load_dotenv

load_dotenv()

print("Testing Supabase REST API connection...")
print(f"URL: {os.getenv('SUPABASE_URL')}")

url = f"{os.getenv('SUPABASE_URL')}/rest/v1/users?select=count"
headers = {
    "apikey": os.getenv("SUPABASE_ANON_KEY"),
    "Authorization": f"Bearer {os.getenv('SUPABASE_ANON_KEY')}"
}

try:
    response = httpx.get(url, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("✅ Supabase connected successfully via REST API")
        print(f"Response: {response.text}")
    elif response.status_code == 401:
        print("❌ Auth failed — check your SUPABASE_ANON_KEY")
    else:
        print(f"❌ Unexpected response: {response.text}")
except Exception as e:
    print(f"❌ Failed: {e}")