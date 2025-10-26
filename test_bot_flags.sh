#!/bin/bash

# Test script to verify auto_execute_trades flag and market status check behavior

# Get backend URL from frontend .env
BACKEND_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2 | tr -d '"' | tr -d "'")

echo "=================================================="
echo "AI Trading Bot - Flag Behavior Test"
echo "=================================================="
echo "Backend URL: $BACKEND_URL"
echo ""

# Function to check logs
check_logs() {
    echo "📋 Recent bot execution logs:"
    tail -n 100 /var/log/supervisor/backend.err.log | grep -E "(Trading bot started|Order Execution Check|SKIPPING|PROCEEDING|Market is|auto_execute_trades flag)" | tail -20
}

# Test 1: Set auto_execute_trades to FALSE
echo "TEST 1: Setting auto_execute_trades to FALSE"
echo "=============================================="

# First get current config
echo "Getting current config..."
curl -s -X GET "$BACKEND_URL/api/config" | python3 -m json.tool > /tmp/current_config.json

# Modify auto_execute_trades to false
echo "Setting auto_execute_trades=false..."
python3 << 'EOF'
import json
import requests
import os

backend_url = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2 | tr -d '\"' | tr -d \"'\"").read().strip()

# Get current config
response = requests.get(f"{backend_url}/api/config")
config = response.json()

# Update auto_execute_trades
config['auto_execute_trades'] = False

# Save config
response = requests.put(f"{backend_url}/api/config", json=config)
print(f"Config updated: {response.json()}")
EOF

echo ""
echo "Waiting 2 seconds..."
sleep 2

# Test 1a: Manual trigger with auto_execute_trades=False
echo ""
echo "TEST 1a: Manual trigger with auto_execute_trades=FALSE"
echo "--------------------------------------------------------"
curl -s -X POST "$BACKEND_URL/api/run-bot" -H "Content-Type: application/json" -d '{"manual": true}' | python3 -m json.tool
echo ""
echo "Waiting 15 seconds for bot to complete..."
sleep 15
check_logs
echo ""

# Test 1b: Automatic trigger with auto_execute_trades=False
echo ""
echo "TEST 1b: Automatic trigger with auto_execute_trades=FALSE"
echo "----------------------------------------------------------"
curl -s -X POST "$BACKEND_URL/api/run-bot" -H "Content-Type: application/json" -d '{"manual": false}' | python3 -m json.tool
echo ""
echo "Waiting 15 seconds for bot to complete..."
sleep 15
check_logs
echo ""

# Test 2: Check market status logs
echo ""
echo "TEST 2: Checking market status logs"
echo "===================================="
curl -s -X GET "$BACKEND_URL/api/market-state-logs?limit=5" | python3 -m json.tool
echo ""

echo ""
echo "=================================================="
echo "Test completed!"
echo "=================================================="
echo ""
echo "KEY THINGS TO VERIFY:"
echo "1. When auto_execute_trades=False:"
echo "   - Should see '⏭️ SKIPPING order execution' in logs"
echo "   - Should see 'auto_execute_trades is DISABLED'"
echo "   - Should see 'LLM analysis completed, but NO ORDER will be placed'"
echo ""
echo "2. For automatic trigger:"
echo "   - Should see market status check first"
echo "   - Should see 'Market is OPEN' or 'Market is CLOSED'"
echo ""
echo "3. For manual trigger:"
echo "   - Should see 'Manual trigger - bypassing market status check'"
echo "   - Should still respect auto_execute_trades flag"
