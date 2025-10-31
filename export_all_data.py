#!/usr/bin/env python3
"""
Complete Data Export Script
Exports ALL data from your trading bot to JSON files for migration
"""

import requests
import json
import os
from datetime import datetime

# Backend URL
BACKEND_URL = "https://investbot-4.preview.emergentagent.com"

def export_data():
    """Export all collections from the database"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = f"/tmp/trading_bot_export_{timestamp}"
    os.makedirs(export_dir, exist_ok=True)
    
    print("="*70)
    print("TRADING BOT DATA EXPORT")
    print("="*70)
    print(f"Export directory: {export_dir}")
    print()
    
    # Define all endpoints to export
    endpoints = {
        "watchlist": "/api/watchlist",
        "portfolio": "/api/portfolio",
        "bot_config": "/api/config",
        "analysis_logs": "/api/logs?limit=10000",
        "llm_logs": "/api/llm-logs?limit=10000",
        "angel_one_logs": "/api/angel-one-logs?limit=10000",
        "executed_orders": "/api/executed-orders?limit=10000",
        "market_state_logs": "/api/market-state-logs?limit=10000",
        "status": "/api/status"
    }
    
    exported_files = []
    total_records = 0
    
    for collection_name, endpoint in endpoints.items():
        try:
            print(f"Exporting {collection_name}...", end=" ")
            response = requests.get(f"{BACKEND_URL}{endpoint}", timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Count records
                if isinstance(data, list):
                    count = len(data)
                elif isinstance(data, dict):
                    # For nested data structures
                    if 'holdings' in data:
                        count = len(data.get('holdings', []))
                    else:
                        count = len(data)
                else:
                    count = 1
                
                # Save to file
                filename = f"{export_dir}/{collection_name}.json"
                with open(filename, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                
                exported_files.append(filename)
                total_records += count
                print(f"✓ ({count} records)")
            else:
                print(f"✗ (HTTP {response.status_code})")
        
        except Exception as e:
            print(f"✗ (Error: {str(e)})")
    
    print()
    print("="*70)
    print("EXPORT SUMMARY")
    print("="*70)
    print(f"Total collections: {len(exported_files)}")
    print(f"Total records: {total_records}")
    print()
    
    print("Exported files:")
    for filepath in exported_files:
        size = os.path.getsize(filepath)
        print(f"  - {os.path.basename(filepath)} ({size:,} bytes)")
    
    print()
    print("="*70)
    print("CREATING IMPORT SCRIPT")
    print("="*70)
    
    # Create import script
    import_script = f"""#!/usr/bin/env python3
'''
MongoDB Import Script
Run this on your own server to import the exported data
'''

import json
import os
from pymongo import MongoClient

# Configure your MongoDB connection
MONGO_URL = "mongodb://localhost:27017"  # Change this to your MongoDB URL
DB_NAME = "trading_bot_db"

def import_data():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    
    export_dir = "{export_dir}"
    
    print("="*70)
    print("IMPORTING DATA TO YOUR MONGODB")
    print("="*70)
    print(f"MongoDB: {{MONGO_URL}}")
    print(f"Database: {{DB_NAME}}")
    print()
    
    # Import each collection
    collections = {{
        "watchlist": "watchlist",
        "bot_config": "bot_config",
        "analysis_logs": "analysis_logs",
        "llm_logs": "llm_prompt_logs",
        "angel_one_logs": "angel_one_api_logs",
        "executed_orders": "executed_orders",
        "market_state_logs": "market_state_logs"
    }}
    
    for filename, collection_name in collections.items():
        filepath = os.path.join(export_dir, f"{{filename}}.json")
        if os.path.exists(filepath):
            print(f"Importing {{collection_name}}...", end=" ")
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            if isinstance(data, list) and len(data) > 0:
                # Clear existing data (optional - comment out to keep existing)
                # db[collection_name].delete_many({{}})
                
                # Insert data
                if len(data) > 0:
                    db[collection_name].insert_many(data)
                    print(f"✓ ({{len(data)}} records)")
                else:
                    print("⊘ (empty)")
            elif isinstance(data, dict):
                # For single documents like config
                db[collection_name].delete_many({{}})
                db[collection_name].insert_one(data)
                print("✓ (1 record)")
            else:
                print("⊘ (no data)")
    
    print()
    print("="*70)
    print("IMPORT COMPLETE!")
    print("="*70)
    print()
    print("Your data has been imported to MongoDB.")
    print("You can now run your FastAPI backend and it will use this data.")
    
    client.close()

if __name__ == "__main__":
    import_data()
"""
    
    import_script_path = f"{export_dir}/import_to_mongodb.py"
    with open(import_script_path, 'w') as f:
        f.write(import_script)
    
    print(f"Created: {import_script_path}")
    print()
    
    # Create README
    readme = f"""# Trading Bot Data Export
Export Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Files Exported

{chr(10).join([f"- {os.path.basename(f)}" for f in exported_files])}

## How to Import to Your Own MongoDB

### Step 1: Install Dependencies
```bash
pip install pymongo
```

### Step 2: Edit Import Script
Open `import_to_mongodb.py` and update:
- MONGO_URL: Your MongoDB connection string
- DB_NAME: Your database name (default: trading_bot_db)

### Step 3: Run Import
```bash
python3 import_to_mongodb.py
```

## Manual Import (Alternative)

If you prefer using mongoimport:

```bash
# For each collection
mongoimport --db trading_bot_db --collection watchlist --file watchlist.json --jsonArray
mongoimport --db trading_bot_db --collection analysis_logs --file analysis_logs.json --jsonArray
mongoimport --db trading_bot_db --collection llm_prompt_logs --file llm_logs.json --jsonArray
mongoimport --db trading_bot_db --collection angel_one_api_logs --file angel_one_logs.json --jsonArray
mongoimport --db trading_bot_db --collection executed_orders --file executed_orders.json --jsonArray
mongoimport --db trading_bot_db --collection market_state_logs --file market_state_logs.json --jsonArray
```

## Portfolio Data
The `portfolio.json` file contains your current Angel One holdings.
This is fetched in real-time from Angel One API, so you don't need to import it.
Your watchlist configuration is what matters for the bot.

## Bot Configuration
The `bot_config.json` contains your bot settings:
- LLM model and provider
- Analysis parameters
- Auto-execute trades flag
- Scheduler configuration

## Next Steps

1. Export code to GitHub (use "Save to GitHub" in Emergent)
2. Clone your repository
3. Set up your own server (AWS/GCP/DigitalOcean)
4. Install MongoDB
5. Run the import script
6. Configure environment variables (.env file)
7. Run your backend: `uvicorn server:app --host 0.0.0.0 --port 8001`
8. Run your frontend: `yarn start`

## Important Notes

- Update your .env file with Angel One credentials
- Add your OpenAI/Emergent LLM API key
- The bot will continue working with your imported data
- All historical logs and configurations are preserved

Good luck with your self-hosted setup!
"""
    
    readme_path = f"{export_dir}/README.md"
    with open(readme_path, 'w') as f:
        f.write(readme)
    
    print(f"Created: {readme_path}")
    print()
    
    print("="*70)
    print("EXPORT COMPLETE!")
    print("="*70)
    print()
    print(f"All your data has been exported to: {export_dir}")
    print()
    print("Next steps:")
    print("1. Download all files from the export directory")
    print("2. Save to GitHub: Use 'Save to GitHub' feature to export code")
    print("3. On your server, run: python3 import_to_mongodb.py")
    print("4. Deploy your FastAPI backend and React frontend")
    print()
    print("Your trading bot will work exactly the same on your own server!")
    print()

if __name__ == "__main__":
    export_data()
