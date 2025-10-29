#!/usr/bin/env python3
"""
Add EODHD API key to credentials
"""
import asyncio
import sys
import os
sys.path.insert(0, '/app/backend')

from motor.motor_asyncio import AsyncIOMotorClient
from cryptography.fernet import Fernet

# Import from server
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', Fernet.generate_key().decode())

def encrypt_value(value: str) -> str:
    """Encrypt a value"""
    f = Fernet(ENCRYPTION_KEY.encode())
    return f.encrypt(value.encode()).decode()

async def add_eodhd_key():
    """Add EODHD API key to database"""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client.trading_bot
    
    # Test API key
    test_key = "690260a40e20d8.99834552"
    encrypted_key = encrypt_value(test_key)
    
    print(f"Adding EODHD API key to database...")
    print(f"Key: {test_key}")
    
    # Update credentials
    result = await db.credentials.update_one(
        {"_id": "main"},
        {"$set": {"eodhd_api_key": encrypted_key}},
        upsert=True
    )
    
    if result.modified_count > 0 or result.upserted_id:
        print("✅ EODHD API key added successfully!")
        
        # Verify
        creds = await db.credentials.find_one({"_id": "main"})
        if creds and creds.get('eodhd_api_key'):
            print("✅ Verified: Key exists in database")
        else:
            print("❌ Error: Key not found after insert")
    else:
        print("❌ Failed to add key")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(add_eodhd_key())
