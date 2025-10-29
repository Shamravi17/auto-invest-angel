#!/usr/bin/env python3
"""
Check EODHD API key in database
"""
import asyncio
import sys
import os
sys.path.insert(0, '/app/backend')

from motor.motor_asyncio import AsyncIOMotorClient
from cryptography.fernet import Fernet

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', Fernet.generate_key().decode())

def decrypt_value(encrypted_value: str) -> str:
    """Decrypt a value"""
    f = Fernet(ENCRYPTION_KEY.encode())
    return f.decrypt(encrypted_value.encode()).decode()

async def check_key():
    """Check EODHD API key"""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client.trading_bot
    
    print("Checking EODHD API key in database...")
    
    creds = await db.credentials.find_one({"_id": "main"})
    
    if not creds:
        print("❌ No credentials document found!")
        return
    
    print(f"✅ Credentials document found")
    print(f"Fields: {list(creds.keys())}")
    
    if 'eodhd_api_key' in creds:
        print(f"✅ eodhd_api_key field exists")
        encrypted = creds['eodhd_api_key']
        print(f"   Encrypted value (first 50 chars): {encrypted[:50]}...")
        
        try:
            decrypted = decrypt_value(encrypted)
            print(f"✅ Decryption successful!")
            print(f"   Decrypted key: {decrypted}")
        except Exception as e:
            print(f"❌ Decryption failed: {e}")
    else:
        print(f"❌ eodhd_api_key field NOT found in document")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_key())
