#!/usr/bin/env python3
"""
AI Trading Bot Backend Testing Suite
Tests critical fixes for auto_execute_trades flag and market status checks
"""

import asyncio
import aiohttp
import json
import time
import sys
from datetime import datetime

# Backend URL from frontend/.env
BACKEND_URL = "https://botfolio-3.preview.emergentagent.com"

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
    
    async def test_scenario_1_auto_execute_false_manual(self):
        """Scenario 1: Test auto_execute_trades=False with manual trigger"""
        print("=" * 60)
        print("SCENARIO 1: auto_execute_trades=False with manual trigger")
        print("=" * 60)
        
        # Step 1: Get current config
        status, config = await self.make_request("GET", "/api/config")
        if status != 200:
            self.log_test("Get Config", "FAIL", f"Failed to get config: {config}")
            return False
        
        self.log_test("Get Config", "PASS", "Successfully retrieved bot config", {
            "auto_execute_trades": config.get("auto_execute_trades"),
            "is_active": config.get("is_active")
        })
        
        # Step 2: Set auto_execute_trades to False
        config["auto_execute_trades"] = False
        status, response = await self.make_request("PUT", "/api/config", config)
        if status != 200:
            self.log_test("Update Config", "FAIL", f"Failed to update config: {response}")
            return False
        
        self.log_test("Update Config", "PASS", "Set auto_execute_trades=False", {
            "auto_execute_trades": response.get("auto_execute_trades")
        })
        
        # Step 3: Trigger manual bot run
        status, response = await self.make_request("POST", "/api/run-bot", {"manual": True})
        if status != 200:
            self.log_test("Manual Bot Trigger", "FAIL", f"Failed to trigger bot: {response}")
            return False
        
        self.log_test("Manual Bot Trigger", "PASS", "Successfully triggered manual bot run", {
            "manual": response.get("manual"),
            "message": response.get("message")
        })
        
        # Step 4: Wait for bot to complete
        print("⏳ Waiting 10 seconds for bot to complete...")
        await asyncio.sleep(10)
        
        # Step 5: Check backend logs for SKIPPING messages
        logs = await self.get_backend_logs()
        skip_messages = []
        execute_messages = []
        
        for line in logs.split('\n'):
            if "⏭️ SKIPPING order execution" in line:
                skip_messages.append(line.strip())
            elif "✅ PROCEEDING with order execution" in line:
                execute_messages.append(line.strip())
        
        if skip_messages:
            self.log_test("Log Verification - SKIP", "PASS", f"Found {len(skip_messages)} SKIP messages", {
                "skip_count": len(skip_messages),
                "sample_message": skip_messages[0] if skip_messages else "None"
            })
        else:
            self.log_test("Log Verification - SKIP", "WARN", "No SKIP messages found in logs")
        
        if execute_messages:
            self.log_test("Log Verification - EXECUTE", "FAIL", f"Found {len(execute_messages)} EXECUTE messages (should be 0)", {
                "execute_count": len(execute_messages),
                "sample_message": execute_messages[0] if execute_messages else "None"
            })
            return False
        else:
            self.log_test("Log Verification - EXECUTE", "PASS", "No EXECUTE messages found (correct)")
        
        # Step 6: Check executed orders
        status, orders = await self.make_request("GET", "/api/executed-orders?limit=10")
        if status == 200:
            recent_orders = [o for o in orders if o.get("timestamp", "").startswith(datetime.now().date().isoformat())]
            if recent_orders:
                self.log_test("Order Verification", "FAIL", f"Found {len(recent_orders)} new orders (should be 0)", {
                    "recent_orders": len(recent_orders)
                })
                return False
            else:
                self.log_test("Order Verification", "PASS", "No new orders placed (correct)")
        else:
            self.log_test("Order Verification", "WARN", f"Could not fetch orders: {orders}")
        
        return True
    
    async def test_scenario_2_auto_execute_false_automatic(self):
        """Scenario 2: Test auto_execute_trades=False with automatic trigger"""
        print("=" * 60)
        print("SCENARIO 2: auto_execute_trades=False with automatic trigger")
        print("=" * 60)
        
        # Ensure config still has auto_execute_trades=False
        status, config = await self.make_request("GET", "/api/config")
        if status != 200 or config.get("auto_execute_trades") != False:
            self.log_test("Config Check", "FAIL", "auto_execute_trades not set to False")
            return False
        
        self.log_test("Config Check", "PASS", "Confirmed auto_execute_trades=False")
        
        # Trigger automatic bot run
        status, response = await self.make_request("POST", "/api/run-bot", {"manual": False})
        if status != 200:
            self.log_test("Automatic Bot Trigger", "FAIL", f"Failed to trigger bot: {response}")
            return False
        
        self.log_test("Automatic Bot Trigger", "PASS", "Successfully triggered automatic bot run", {
            "manual": response.get("manual"),
            "message": response.get("message")
        })
        
        # Wait for bot to complete
        print("⏳ Waiting 10 seconds for bot to complete...")
        await asyncio.sleep(10)
        
        # Check logs for SKIPPING messages
        logs = await self.get_backend_logs()
        skip_messages = []
        execute_messages = []
        
        for line in logs.split('\n'):
            if "⏭️ SKIPPING order execution" in line:
                skip_messages.append(line.strip())
            elif "✅ PROCEEDING with order execution" in line:
                execute_messages.append(line.strip())
        
        if skip_messages:
            self.log_test("Log Verification - SKIP", "PASS", f"Found {len(skip_messages)} SKIP messages")
        else:
            self.log_test("Log Verification - SKIP", "WARN", "No SKIP messages found in logs")
        
        if execute_messages:
            self.log_test("Log Verification - EXECUTE", "FAIL", f"Found {len(execute_messages)} EXECUTE messages (should be 0)")
            return False
        else:
            self.log_test("Log Verification - EXECUTE", "PASS", "No EXECUTE messages found (correct)")
        
        return True
    
    async def test_scenario_3_market_status_check(self):
        """Scenario 3: Test market status check for automatic runs"""
        print("=" * 60)
        print("SCENARIO 3: Market status check for automatic runs")
        print("=" * 60)
        
        # Trigger automatic bot run
        status, response = await self.make_request("POST", "/api/run-bot", {"manual": False})
        if status != 200:
            self.log_test("Automatic Bot Trigger", "FAIL", f"Failed to trigger bot: {response}")
            return False
        
        self.log_test("Automatic Bot Trigger", "PASS", "Successfully triggered automatic bot run")
        
        # Wait for bot to complete
        print("⏳ Waiting 10 seconds for bot to complete...")
        await asyncio.sleep(10)
        
        # Check logs for market status messages
        logs = await self.get_backend_logs()
        market_open_msg = False
        market_closed_msg = False
        
        for line in logs.split('\n'):
            if "✓ Market is OPEN. Proceeding with bot execution" in line:
                market_open_msg = True
            elif "⏸️ Market is CLOSED. Automatic bot execution aborted" in line:
                market_closed_msg = True
        
        if market_open_msg:
            self.log_test("Market Status Check", "PASS", "Found market OPEN message - bot proceeded")
        elif market_closed_msg:
            self.log_test("Market Status Check", "PASS", "Found market CLOSED message - bot aborted")
        else:
            self.log_test("Market Status Check", "WARN", "No clear market status messages found")
        
        # Check market state logs
        status, market_logs = await self.make_request("GET", "/api/market-state-logs?limit=5")
        if status == 200 and market_logs:
            latest_log = market_logs[0]
            self.log_test("Market State Logs", "PASS", "Retrieved market state logs", {
                "latest_status": latest_log.get("market_status"),
                "bot_executed": latest_log.get("bot_executed"),
                "reason": latest_log.get("reason")
            })
        else:
            self.log_test("Market State Logs", "WARN", f"Could not fetch market logs: {market_logs}")
        
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