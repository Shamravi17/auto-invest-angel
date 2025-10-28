#!/usr/bin/env python3
"""
Test NSE API with session warm-up approach
"""
import asyncio
import aiohttp
import json
import time

async def test_nse_api():
    """Test NSE API call with session warm-up"""
    url = "https://www.nseindia.com/api/allIndices"
    homepage = "https://www.nseindia.com/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Referer': 'https://www.nseindia.com/'
    }
    
    try:
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            # Step 1: Visit homepage to get cookies
            print("🔄 Step 1: Warming up session with NSE homepage...")
            async with session.get(homepage, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as homepage_resp:
                print(f"   Homepage status: {homepage_resp.status}")
            
            # Step 2: Small delay for cookies to settle
            print("⏱️  Step 2: Waiting 1 second for cookies to settle...")
            await asyncio.sleep(1)
            
            # Step 3: Now call the actual API
            print("📊 Step 3: Fetching index data from API...")
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                elapsed = time.time() - start_time
                print(f"   API status: {response.status} (took {elapsed:.2f}s)")
                
                if response.status == 200:
                    data = await response.json()
                    
                    # Find NIFTY 50
                    nifty50 = None
                    for index_item in data.get('data', []):
                        if 'NIFTY 50' in index_item.get('index', '').upper():
                            nifty50 = index_item
                            break
                    
                    if nifty50:
                        print("\n✅ SUCCESS! NIFTY 50 data retrieved:")
                        print(f"   Index: {nifty50.get('index')}")
                        print(f"   Last: {nifty50.get('last')}")
                        print(f"   P/E: {nifty50.get('pe')}")
                        print(f"   P/B: {nifty50.get('pb')}")
                        print(f"   Div Yield: {nifty50.get('divYield')}")
                        print(f"   % Change: {nifty50.get('percentChange')}")
                        return True
                    else:
                        print("\n❌ NIFTY 50 not found in response")
                        print(f"   Available indices: {len(data.get('data', []))}")
                        return False
                else:
                    print(f"\n❌ API returned status {response.status}")
                    text = await response.text()
                    print(f"   Response: {text[:200]}")
                    return False
                    
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Testing NSE API with Session Warm-up")
    print("=" * 60)
    result = asyncio.run(test_nse_api())
    print("\n" + "=" * 60)
    if result:
        print("✅ NSE API Test PASSED")
    else:
        print("❌ NSE API Test FAILED")
    print("=" * 60)
