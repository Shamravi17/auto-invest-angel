#!/usr/bin/env python3
"""
AI Trading Bot Backend Testing Suite
Tests Phase 1 & Phase 2 features: Market Data in LLM Calls + NSE Index Data Service
"""

import asyncio
import aiohttp
import json
import time
import sys
from datetime import datetime

# Backend URL from frontend/.env
BACKEND_URL = "https://autotrade-llm.preview.emergentagent.com"

class TradingBotTester:
    def __init__(self):
        self.session = None
        self.test_results = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def log_test(self, test_name, status, message, details=None):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.test_results.append(result)
        
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {message}")
        if details:
            for key, value in details.items():
                print(f"   {key}: {value}")
        print()
    
    async def make_request(self, method, endpoint, data=None, timeout=30):
        """Make HTTP request to backend"""
        url = f"{BACKEND_URL}{endpoint}"
        try:
            if method.upper() == "GET":
                async with self.session.get(url, timeout=timeout) as response:
                    return response.status, await response.json()
            elif method.upper() == "POST":
                async with self.session.post(url, json=data, timeout=timeout) as response:
                    return response.status, await response.json()
            elif method.upper() == "PUT":
                async with self.session.put(url, json=data, timeout=timeout) as response:
                    return response.status, await response.json()
        except Exception as e:
            return 500, {"error": str(e)}
    
    async def get_backend_logs(self):
        """Get recent backend logs"""
        try:
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "200", "/var/log/supervisor/backend.err.log"],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout
        except Exception as e:
            print(f"Could not fetch backend logs: {e}")
            return ""
    
    async def test_nse_index_options_api(self):
        """Test 1: NSE Index Options API"""
        print("=" * 60)
        print("TEST 1: NSE Index Options API")
        print("=" * 60)
        
        # Test GET /api/nse-index-options
        status, response = await self.make_request("GET", "/api/nse-index-options")
        if status != 200:
            self.log_test("NSE Index Options API", "FAIL", f"API call failed: {response}")
            return False
        
        # Verify response structure
        if not isinstance(response, list):
            self.log_test("NSE Index Options API", "FAIL", f"Expected list, got {type(response)}")
            return False
        
        # Check for expected indices
        expected_indices = ["NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY AUTO"]
        found_indices = [idx for idx in expected_indices if idx in response]
        
        if len(found_indices) < 3:
            self.log_test("NSE Index Options API", "FAIL", f"Missing expected indices. Found: {found_indices}")
            return False
        
        self.log_test("NSE Index Options API", "PASS", f"Retrieved {len(response)} NSE indices", {
            "total_indices": len(response),
            "sample_indices": response[:5],
            "expected_found": len(found_indices)
        })
        
        return True
    
    async def test_nse_api_logs_endpoint(self):
        """Test 2: NSE API Logs Endpoint"""
        print("=" * 60)
        print("TEST 2: NSE API Logs Endpoint")
        print("=" * 60)
        
        # Test GET /api/nse-api-logs
        status, response = await self.make_request("GET", "/api/nse-api-logs")
        if status != 200:
            self.log_test("NSE API Logs Endpoint", "FAIL", f"API call failed: {response}")
            return False
        
        # Verify response is a list (should be empty initially)
        if not isinstance(response, list):
            self.log_test("NSE API Logs Endpoint", "FAIL", f"Expected list, got {type(response)}")
            return False
        
        self.log_test("NSE API Logs Endpoint", "PASS", f"Retrieved NSE API logs", {
            "logs_count": len(response),
            "status": "Empty initially" if len(response) == 0 else "Has existing logs"
        })
        
        return True
    
    async def test_watchlist_crud_new_fields(self):
        """Test 3: Watchlist CRUD with New Fields"""
        print("=" * 60)
        print("TEST 3: Watchlist CRUD with New Fields")
        print("=" * 60)
        
        # Step 1: Get existing watchlist
        status, watchlist = await self.make_request("GET", "/api/watchlist")
        if status != 200:
            self.log_test("Get Watchlist", "FAIL", f"Failed to get watchlist: {watchlist}")
            return False
        
        if not watchlist:
            self.log_test("Get Watchlist", "FAIL", "Watchlist is empty - need at least one item to test")
            return False
        
        self.log_test("Get Watchlist", "PASS", f"Retrieved {len(watchlist)} watchlist items")
        
        # Step 2: Pick first item to update
        test_item = watchlist[0]
        item_id = test_item.get("id")
        
        if not item_id:
            self.log_test("Item Selection", "FAIL", "No ID found in watchlist item")
            return False
        
        # Step 3: Update item with new fields
        updated_item = test_item.copy()
        updated_item["instrument_type"] = "ETF"
        updated_item["proxy_index"] = "NIFTY 50"
        
        status, response = await self.make_request("PUT", f"/api/watchlist/{item_id}", updated_item)
        if status != 200:
            self.log_test("Update Watchlist Item", "FAIL", f"Failed to update item: {response}")
            return False
        
        self.log_test("Update Watchlist Item", "PASS", "Successfully updated with new fields", {
            "item_id": item_id,
            "instrument_type": response.get("instrument_type"),
            "proxy_index": response.get("proxy_index")
        })
        
        # Step 4: Verify fields were saved
        status, updated_watchlist = await self.make_request("GET", "/api/watchlist")
        if status != 200:
            self.log_test("Verify Update", "FAIL", f"Failed to re-fetch watchlist: {updated_watchlist}")
            return False
        
        # Find the updated item
        updated_test_item = None
        for item in updated_watchlist:
            if item.get("id") == item_id:
                updated_test_item = item
                break
        
        if not updated_test_item:
            self.log_test("Verify Update", "FAIL", "Updated item not found in watchlist")
            return False
        
        # Check if new fields are present
        if updated_test_item.get("instrument_type") != "ETF":
            self.log_test("Verify Update", "FAIL", f"instrument_type not saved correctly: {updated_test_item.get('instrument_type')}")
            return False
        
        if updated_test_item.get("proxy_index") != "NIFTY 50":
            self.log_test("Verify Update", "FAIL", f"proxy_index not saved correctly: {updated_test_item.get('proxy_index')}")
            return False
        
        self.log_test("Verify Update", "PASS", "New fields saved and retrieved correctly", {
            "instrument_type": updated_test_item.get("instrument_type"),
            "proxy_index": updated_test_item.get("proxy_index")
        })
        
        return True
    
    async def test_scenario_4_manual_bypass_market_check(self):
        """Scenario 4: Test manual trigger bypasses market check"""
        print("=" * 60)
        print("SCENARIO 4: Manual trigger bypasses market check")
        print("=" * 60)
        
        # Trigger manual bot run
        status, response = await self.make_request("POST", "/api/run-bot", {"manual": True})
        if status != 200:
            self.log_test("Manual Bot Trigger", "FAIL", f"Failed to trigger bot: {response}")
            return False
        
        self.log_test("Manual Bot Trigger", "PASS", "Successfully triggered manual bot run")
        
        # Wait for bot to complete
        print("⏳ Waiting 10 seconds for bot to complete...")
        await asyncio.sleep(10)
        
        # Check logs for bypass message
        logs = await self.get_backend_logs()
        bypass_msg = False
        
        for line in logs.split('\n'):
            if "🔧 Manual trigger - bypassing market status check" in line:
                bypass_msg = True
                break
        
        if bypass_msg:
            self.log_test("Market Bypass Check", "PASS", "Found manual bypass message")
        else:
            self.log_test("Market Bypass Check", "FAIL", "Manual bypass message not found")
            return False
        
        return True
    
    async def test_backend_connectivity(self):
        """Test basic backend connectivity"""
        print("=" * 60)
        print("PRELIMINARY: Backend Connectivity Test")
        print("=" * 60)
        
        # Test basic status endpoint
        status, response = await self.make_request("GET", "/api/status")
        if status != 200:
            self.log_test("Backend Connectivity", "FAIL", f"Backend not accessible: {response}")
            return False
        
        self.log_test("Backend Connectivity", "PASS", "Backend is accessible", {
            "angel_one_connected": response.get("angel_one_connected"),
            "bot_running": response.get("bot_running"),
            "bot_active": response.get("bot_active")
        })
        
        return True
    
    async def run_all_tests(self):
        """Run all test scenarios"""
        print(f"🤖 AI Trading Bot Backend Testing Suite")
        print(f"Backend URL: {BACKEND_URL}")
        print(f"Test Started: {datetime.now().isoformat()}")
        print()
        
        # Test connectivity first
        if not await self.test_backend_connectivity():
            print("❌ Backend connectivity failed. Aborting tests.")
            return
        
        # Run all scenarios
        scenarios = [
            self.test_scenario_1_auto_execute_false_manual,
            self.test_scenario_2_auto_execute_false_automatic,
            self.test_scenario_3_market_status_check,
            self.test_scenario_4_manual_bypass_market_check
        ]
        
        results = []
        for scenario in scenarios:
            try:
                result = await scenario()
                results.append(result)
            except Exception as e:
                print(f"❌ Scenario failed with exception: {e}")
                results.append(False)
        
        # Print summary
        print("=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        warnings = sum(1 for r in self.test_results if r["status"] == "WARN")
        
        print(f"✅ PASSED: {passed}")
        print(f"❌ FAILED: {failed}")
        print(f"⚠️ WARNINGS: {warnings}")
        print(f"📊 TOTAL: {len(self.test_results)}")
        print()
        
        # Show failed tests
        if failed > 0:
            print("FAILED TESTS:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"  ❌ {result['test']}: {result['message']}")
            print()
        
        # Show warnings
        if warnings > 0:
            print("WARNINGS:")
            for result in self.test_results:
                if result["status"] == "WARN":
                    print(f"  ⚠️ {result['test']}: {result['message']}")
            print()
        
        overall_success = failed == 0
        print(f"🎯 OVERALL RESULT: {'SUCCESS' if overall_success else 'FAILURE'}")
        
        return overall_success

async def main():
    """Main test runner"""
    async with TradingBotTester() as tester:
        success = await tester.run_all_tests()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())