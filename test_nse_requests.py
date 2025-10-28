#!/usr/bin/env python3
"""
Test NSE API using requests library (like user's example)
"""
import requests
import time
import json

def test_nse_requests():
    """Test using requests library with session"""
    print("\n" + "="*60)
    print("Testing NSE API with requests.Session()")
    print("="*60)
    
    # Headers
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    
    # Create session
    s = requests.Session()
    
    try:
        # Step 1: Warm up with homepage
        print("Step 1: Initializing session with NSE homepage...")
        resp = s.get("https://www.nseindia.com/", headers=headers, timeout=10)
        print(f"  Homepage status: {resp.status_code}")
        print(f"  Cookies: {len(s.cookies)}")
        
        if resp.status_code == 403:
            print("  ❌ Homepage blocked with 403")
            return False
        
        # Step 2: Wait
        print("Step 2: Waiting 1 second...")
        time.sleep(1)
        
        # Step 3: Call API
        print("Step 3: Fetching index data...")
        url = "https://www.nseindia.com/api/allIndices"
        r = s.get(url, headers=headers, timeout=15)
        print(f"  API status: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            print(f"  ✅ Success! Got {len(data.get('data', []))} indices")
            
            # Find NIFTY 50
            nifty = next((x for x in data["data"] if x["index"] == "NIFTY 50"), None)
            if nifty:
                print("\n  NIFTY 50 Data:")
                print(json.dumps(nifty, indent=2))
                return True
            else:
                print("  NIFTY 50 not found")
                return False
        else:
            print(f"  ❌ API failed: {r.text[:200]}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = test_nse_requests()
    print("\n" + "="*60)
    if result:
        print("✅ TEST PASSED")
    else:
        print("❌ TEST FAILED - Datacenter IP likely blocked by NSE")
        print("\nNOTE: NSE blocks datacenter IPs. This will work from:")
        print("  - Residential IPs")
        print("  - During market hours from allowed IPs")
        print("  - Using a proxy service")
    print("="*60)
