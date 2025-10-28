#!/usr/bin/env python3
"""
Test different NSE API approaches to bypass 403
"""
import asyncio
import aiohttp
import json
import time

async def test_approach_1():
    """Approach 1: Session with cookies from homepage"""
    print("\n" + "="*60)
    print("APPROACH 1: Session + Homepage Cookies")
    print("="*60)
    
    url = "https://www.nseindia.com/api/allIndices"
    homepage = "https://www.nseindia.com/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Visit homepage
            print("Step 1: Visiting homepage...")
            async with session.get(homepage, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"  Homepage status: {resp.status}")
                print(f"  Cookies received: {len(session.cookie_jar)}")
                
            await asyncio.sleep(1)
            
            # Add Referer after homepage visit
            headers['Referer'] = homepage
            
            # Call API
            print("Step 2: Calling API...")
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"  API status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  ✅ Success! Got {len(data.get('data', []))} indices")
                    return True
                else:
                    text = await resp.text()
                    print(f"  ❌ Failed: {text[:100]}")
                    return False
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return False

async def test_approach_2():
    """Approach 2: More realistic browser headers"""
    print("\n" + "="*60)
    print("APPROACH 2: Full Browser Headers")
    print("="*60)
    
    url = "https://www.nseindia.com/api/allIndices"
    homepage = "https://www.nseindia.com/"
    
    headers = {
        'authority': 'www.nseindia.com',
        'method': 'GET',
        'scheme': 'https',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Priority': 'u=1, i',
        'Sec-Ch-Ua': '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    }
    
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Visit homepage
            print("Step 1: Visiting homepage...")
            async with session.get(homepage, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"  Homepage status: {resp.status}")
                
            await asyncio.sleep(2)
            
            # Update headers with Referer
            headers['Referer'] = homepage
            headers['path'] = '/api/allIndices'
            
            # Call API
            print("Step 2: Calling API...")
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"  API status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  ✅ Success! Got {len(data.get('data', []))} indices")
                    
                    # Show NIFTY 50 data
                    for idx in data.get('data', []):
                        if 'NIFTY 50' in idx.get('index', '').upper():
                            print(f"\n  NIFTY 50 Data:")
                            print(f"    Last: {idx.get('last')}")
                            print(f"    P/E: {idx.get('pe')}")
                            print(f"    P/B: {idx.get('pb')}")
                            print(f"    Change: {idx.get('percentChange')}%")
                            break
                    return True
                else:
                    text = await resp.text()
                    print(f"  ❌ Failed: {text[:100]}")
                    return False
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return False

async def test_approach_3():
    """Approach 3: Visit market status page first (different warm-up)"""
    print("\n" + "="*60)
    print("APPROACH 3: Market Status Page Warm-up")
    print("="*60)
    
    url = "https://www.nseindia.com/api/allIndices"
    warmup = "https://www.nseindia.com/market-data/live-equity-market"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
    }
    
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Visit market page
            print("Step 1: Visiting market data page...")
            async with session.get(warmup, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"  Page status: {resp.status}")
                
            await asyncio.sleep(2)
            
            # Change headers for API call
            headers['Accept'] = 'application/json'
            headers['Referer'] = warmup
            
            # Call API
            print("Step 2: Calling API...")
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"  API status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  ✅ Success! Got {len(data.get('data', []))} indices")
                    return True
                else:
                    text = await resp.text()
                    print(f"  ❌ Failed: {text[:100]}")
                    return False
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return False

async def main():
    print("\n" + "="*60)
    print("TESTING NSE API - MULTIPLE APPROACHES")
    print("="*60)
    
    results = []
    
    results.append(("Approach 1", await test_approach_1()))
    results.append(("Approach 2", await test_approach_2()))
    results.append(("Approach 3", await test_approach_3()))
    
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{name}: {status}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
