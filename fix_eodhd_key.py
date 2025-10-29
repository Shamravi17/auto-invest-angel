#!/usr/bin/env python3
"""
Re-add EODHD API key with correct encryption key
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from cryptography.fernet import Fernet

# Use the actual encryption key from .env
MONGO_URL = 'mongodb://localhost:27017'
ENCRYPTION_KEY = "XjzsHrHCTJJ24Dn9v1NxX2UfbH4Qi633WM7mg6Kibno="

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
    print(f"Encryption key: {ENCRYPTION_KEY[:20]}...")
    print(f"Encrypted (first 50): {encrypted_key[:50]}...")
    
    # Update credentials
    result = await db.credentials.update_one(
        {"_id": "main"},
        {"$set": {"eodhd_api_key": encrypted_key}},
        upsert=True
    )
    
    print(f"✅ Key added/updated")
    
    # Verify decryption
    creds = await db.credentials.find_one({"_id": "main"})
    if creds and creds.get('eodhd_api_key'):
        try:
            f = Fernet(ENCRYPTION_KEY.encode())
            decrypted = f.decrypt(creds['eodhd_api_key'].encode()).decode()
            print(f"✅ Verified - decrypted: {decrypted}")
        except Exception as e:
            print(f"❌ Verification failed: {e}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(add_eodhd_key())
