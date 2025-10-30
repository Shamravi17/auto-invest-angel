from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from SmartApi import SmartConnect
import pyotp
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import asyncio
from emergentintegrations.llm.chat import LlmChat, UserMessage
import uuid
from cryptography.fernet import Fernet
import base64
import pytz

# Import market data service
try:
    from market_data_service import market_data_service
except ImportError:
    logger.warning("market_data_service not available - will use fallback data")
    market_data_service = None

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Encryption key - in production, store this securely
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', Fernet.generate_key().decode())
cipher_suite = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

# IST timezone
IST = pytz.timezone('Asia/Kolkata')

def get_ist_timestamp():
    """Get current timestamp in IST"""
    return datetime.now(IST).isoformat()

def convert_to_ist(dt_string: str) -> str:
    """Convert UTC timestamp string to IST"""
    try:
        dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ist_dt = dt.astimezone(IST)
        return ist_dt.isoformat()
    except:
        return dt_string

def encrypt_value(value: str) -> str:
    """Encrypt a string value"""
    if not value:
        return value
    return cipher_suite.encrypt(value.encode()).decode()

def decrypt_value(encrypted_value: str) -> str:
    """Decrypt a string value"""
    if not encrypted_value:
        return encrypted_value
    try:
        return cipher_suite.decrypt(encrypted_value.encode()).decode()
    except:
        return encrypted_value  # Return as-is if decryption fails (backwards compatibility)

app = FastAPI(title="AI Trading Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
scheduler = AsyncIOScheduler()
smart_api: Optional[SmartConnect] = None
auth_tokens: Optional[Dict] = None
current_session_id = None

# EODHD API Base URL
EODHD_BASE_URL = "https://eodhd.com/api"

# ===== MODELS =====
class BotConfig(BaseModel):
    is_active: bool = False
    schedule_type: str = "interval"  # interval, daily, hourly
    schedule_minutes: int = 30  # For interval mode
    schedule_time: Optional[str] = None  # For daily mode (HH:MM format in IST)
    schedule_hours_interval: Optional[int] = None  # For hourly mode
    llm_provider: str = "emergent"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: Optional[str] = None
    telegram_chat_ids: List[str] = []
    telegram_bot_token: Optional[str] = None
    enable_notifications: bool = True
    auto_execute_trades: bool = False
    enable_tax_harvesting: bool = False
    tax_harvesting_loss_slab: float = 50000.0
    profit_threshold_percent: float = 15.0  # Minimum PROFIT % to consider selling
    minimum_gain_threshold_percent: float = 5.0  # For exit/re-entry after charges
    analysis_parameters: str = "Consider P/E ratio, volume trends, RSI indicators, support/resistance levels, and overall market sentiment."
    last_updated: str = Field(default_factory=get_ist_timestamp)

class Credentials(BaseModel):
    angel_api_key: Optional[str] = None
    angel_client_id: Optional[str] = None
    angel_password: Optional[str] = None
    angel_totp_secret: Optional[str] = None
    angel_mpin: Optional[str] = None
    eodhd_api_key: Optional[str] = None  # EODHD Financial API key
    last_updated: str = Field(default_factory=get_ist_timestamp)

class WatchlistItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    exchange: str = "NSE"
    symbol_token: str
    action: str = "hold"  # sip, buy, sell, hold
    last_sip_date: Optional[str] = None  # Last SIP execution date (IST)
    next_action_date: Optional[str] = None
    re_entry_price: Optional[float] = None  # Target price for re-entry after exit
    quantity: Optional[int] = None
    avg_price: Optional[float] = None
    notes: Optional[str] = ""
    added_at: str = Field(default_factory=get_ist_timestamp)
    
    # SIP Exit and Re-entry fields
    awaiting_reentry: bool = False  # Flag indicating position was exited, waiting to re-enter
    exit_price: Optional[float] = None  # Price at which position was exited
    exit_amount: Optional[float] = None  # Total amount from exit (reserved for re-entry)
    exit_date: Optional[str] = None  # Date when position was exited
    exit_quantity: Optional[int] = None  # Quantity that was sold during exit
    
    # NSE Index Data fields
    instrument_type: Optional[str] = None  # ETF or Equity
    proxy_index: Optional[str] = None  # Optional mapping to NSE index (e.g., "NIFTY 50")

class ExecutedOrder(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=get_ist_timestamp)
    symbol: str
    order_type: str  # SIP, BUY, SELL, EXIT_AND_REENTER
    transaction_type: str  # BUY or SELL
    quantity: int
    price: float
    total_value: float
    order_id: Optional[str] = None  # Can be None if order placement fails
    status: str  # SUCCESS, FAILED, PENDING
    notes: Optional[str] = ""

class LLMPromptLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=get_ist_timestamp)
    symbol: str
    action_type: str
    full_prompt: str
    llm_response: str
    model_used: str
    decision_made: str

class AnalysisLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=get_ist_timestamp)
    symbol: str
    action: str
    llm_decision: str
    market_data: Dict[str, Any]
    executed: bool = False
    order_id: Optional[str] = None
    error: Optional[str] = None
    execution_status: Optional[str] = None  # NEW: "EXECUTED", "SKIPPED_AUTO_EXECUTE_DISABLED", "SKIPPED_LLM_DECISION", "FAILED"

class TelegramNotification(BaseModel):
    message: str

class AngelOneAPILog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=get_ist_timestamp)
    endpoint: str
    method: str
    request_data: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None
    status_code: Optional[int] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None

class MarketStateLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=get_ist_timestamp)
    date: str  # Date in IST (YYYY-MM-DD)
    market_status: str  # Open, Closed, Pre-open, Post Close
    bot_executed: bool  # Whether bot ran on this day
    reason: Optional[str] = None  # Why bot didn't run (if applicable)

class EODHDAPILog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=get_ist_timestamp)
    symbol: str  # The watchlist symbol
    exchange_symbol: str  # Symbol with exchange suffix (e.g., RELIANCE.NSE)
    data_type: str  # "fundamentals" or "technical"
    indicator: Optional[str] = None  # For technical: RSI, MACD, etc.
    request_url: str
    response_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status: str  # "SUCCESS" or "FAILED"
    execution_time_ms: Optional[float] = None

# ===== STARTUP & TTL SETUP =====
@app.on_event("startup")
async def startup_tasks():
    """Setup TTL indexes and initialize scheduler"""
    try:
        # TTL for Angel One API logs - delete after 7 days
        await db.angel_one_api_logs.create_index(
            "timestamp",
            expireAfterSeconds=7 * 24 * 60 * 60  # 7 days
        )
        
        # TTL for LLM prompt logs - delete after 7 days
        await db.llm_prompt_logs.create_index(
            "timestamp",
            expireAfterSeconds=7 * 24 * 60 * 60  # 7 days
        )
        
        logger.info("TTL indexes created for logs (7-day retention)")
        
        # Initialize scheduler if bot is configured as active
        config_doc = await db.bot_config.find_one({"_id": "main"})
        if config_doc and config_doc.get('is_active', False):
            config = BotConfig(**config_doc)
            await schedule_bot(config)
            logger.info(f"Bot scheduler initialized on startup (schedule_type: {config.schedule_type})")
        
    except Exception as e:
        logger.error(f"Startup tasks error: {str(e)}")

async def log_angel_one_api_call(
    endpoint: str,
    method: str,
    request_data: Optional[Dict] = None,
    response_data: Optional[Dict] = None,
    status_code: Optional[int] = None,
    error: Optional[str] = None,
    execution_time_ms: Optional[float] = None
):
    """Log Angel One API call for monitoring and debugging"""
    try:
        log_entry = AngelOneAPILog(
            endpoint=endpoint,
            method=method,
            request_data=request_data,
            response_data=response_data,
            status_code=status_code,
            error=error,
            execution_time_ms=execution_time_ms
        )
        await db.angel_one_api_logs.insert_one(log_entry.model_dump())
    except Exception as e:
        logger.error(f"Failed to log Angel One API call: {str(e)}")

# ===== CREDENTIALS MANAGEMENT =====
async def get_credentials() -> Dict[str, str]:
    """Get decrypted credentials from database or environment"""
    creds_doc = await db.credentials.find_one({"_id": "main"})
    
    if creds_doc:
        # Decrypt from database
        return {
            "api_key": decrypt_value(creds_doc.get("angel_api_key", "")),
            "client_id": decrypt_value(creds_doc.get("angel_client_id", "")),
            "password": decrypt_value(creds_doc.get("angel_password", "")),
            "totp_secret": decrypt_value(creds_doc.get("angel_totp_secret", "")),
            "mpin": decrypt_value(creds_doc.get("angel_mpin", ""))
        }
    else:
        # Fallback to environment variables (for backwards compatibility)
        return {
            "api_key": os.environ.get('ANGEL_TRADING_API_KEY', ''),
            "client_id": os.environ.get('ANGEL_CLIENT_ID', ''),
            "password": os.environ.get('ANGEL_PASSWORD', ''),
            "totp_secret": os.environ.get('ANGEL_TOTP_SECRET', ''),
            "mpin": os.environ.get('ANGEL_MPIN', '')
        }

@app.get("/api/credentials")
async def get_credentials_api():
    """Get credentials (masked for security)"""
    creds_doc = await db.credentials.find_one({"_id": "main"})
    
    if creds_doc:
        return {
            "angel_api_key": "*" * 8 if creds_doc.get("angel_api_key") else "",
            "angel_client_id": decrypt_value(creds_doc.get("angel_client_id", "")),  # Can show client ID
            "angel_password": "*" * 8 if creds_doc.get("angel_password") else "",
            "angel_totp_secret": "*" * 8 if creds_doc.get("angel_totp_secret") else "",
            "angel_mpin": "*" * 4 if creds_doc.get("angel_mpin") else "",
            "last_updated": creds_doc.get("last_updated", "")
        }
    return {
        "angel_api_key": "",
        "angel_client_id": "",
        "angel_password": "",
        "angel_totp_secret": "",
        "angel_mpin": "",
        "last_updated": ""
    }

@app.put("/api/credentials")
async def update_credentials(credentials: Credentials):
    """Update credentials in database (encrypted)"""
    encrypted_creds = {
        "_id": "main",
        "angel_api_key": encrypt_value(credentials.angel_api_key) if credentials.angel_api_key else None,
        "angel_client_id": encrypt_value(credentials.angel_client_id) if credentials.angel_client_id else None,
        "angel_password": encrypt_value(credentials.angel_password) if credentials.angel_password else None,
        "angel_totp_secret": encrypt_value(credentials.angel_totp_secret) if credentials.angel_totp_secret else None,
        "angel_mpin": encrypt_value(credentials.angel_mpin) if credentials.angel_mpin else None,
        "last_updated": get_ist_timestamp()
    }
    
    await db.credentials.update_one(
        {"_id": "main"},
        {"$set": encrypted_creds},
        upsert=True
    )
    
    # Reset authentication when credentials change
    global smart_api, auth_tokens
    smart_api = None
    auth_tokens = None
    
    return {"success": True, "message": "Credentials updated successfully"}

# ===== ANGEL ONE AUTH =====
async def authenticate_angel_one():
    global smart_api, auth_tokens
    
    start_time = datetime.now()
    try:
        creds = await get_credentials()
        
        if not all([creds["api_key"], creds["client_id"], creds["password"], creds["totp_secret"], creds["mpin"]]):
            raise Exception("Angel One credentials not configured")
        
        smart_api = SmartConnect(api_key=creds["api_key"])
        
        totp = pyotp.TOTP(creds["totp_secret"])
        totp_code = totp.now()
        
        # Use MPIN instead of password as per Angel One's new policy
        request_data = {
            "clientCode": creds["client_id"],
            "totp": totp_code
            # Not logging password/mpin for security
        }
        
        session = smart_api.generateSession(
            clientCode=creds["client_id"],
            password=creds["mpin"],  # Use MPIN as password
            totp=totp_code
        )
        
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        if session['status']:
            auth_tokens = session['data']
            logger.info("Angel One authentication successful")
            
            # Log successful authentication
            await log_angel_one_api_call(
                endpoint="/user/login",
                method="POST",
                request_data=request_data,
                response_data={"status": "success", "message": "Authentication successful"},
                status_code=200,
                execution_time_ms=execution_time
            )
            return True
        else:
            error_msg = session.get('message', 'Unknown error')
            logger.error(f"Angel One auth failed: {error_msg}")
            
            # Log failed authentication
            await log_angel_one_api_call(
                endpoint="/user/login",
                method="POST",
                request_data=request_data,
                response_data=session,
                status_code=401,
                error=error_msg,
                execution_time_ms=execution_time
            )
            return False
            
    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        error_msg = str(e)
        logger.error(f"Angel One authentication error: {error_msg}")
        
        # Log exception
        await log_angel_one_api_call(
            endpoint="/user/login",
            method="POST",
            request_data={"error": "Exception during auth"},
            response_data=None,
            status_code=500,
            error=error_msg,
            execution_time_ms=execution_time
        )
        
        smart_api = None
        auth_tokens = None
        return False

@app.post("/api/auth/angel")
async def trigger_angel_auth():
    success = await authenticate_angel_one()
    if success:
        return {"success": True, "message": "Angel One authenticated"}
    else:
        raise HTTPException(status_code=401, detail="Authentication failed")

@app.get("/api/status")
async def get_status():
    # Try to authenticate if not already authenticated
    if not smart_api or not auth_tokens:
        await authenticate_angel_one()
    
    # Get config to check if bot is active
    config_doc = await db.bot_config.find_one({"_id": "main"})
    is_active = config_doc.get('is_active', False) if config_doc else False
    
    # Get watchlist count
    watchlist_count = await db.watchlist.count_documents({})
    
    # Get analyses count (portfolio analyses)
    analyses_count = await db.portfolio_analyses.count_documents({})
    
    # Get executed orders count
    orders_count = await db.executed_orders.count_documents({})
    
    return {
        "angel_one_connected": smart_api is not None and auth_tokens is not None,
        "bot_running": scheduler.running,
        "bot_active": is_active and scheduler.running,  # Both config active and scheduler running
        "scheduled_jobs": len(scheduler.get_jobs()),
        "watchlist_symbols": watchlist_count,
        "analyses_completed": analyses_count,
        "orders_executed": orders_count
    }

# ===== ANGEL ONE API =====
async def get_portfolio():
    if not smart_api or not auth_tokens:
        await authenticate_angel_one()
    
    if not smart_api:
        raise HTTPException(status_code=401, detail="Angel One not authenticated")
    
    start_time = datetime.now()
    try:
        # Fetch holdings
        holdings = smart_api.holding()
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Fetch available funds
        available_cash = 0
        try:
            rms_limits = smart_api.rmsLimit()
            if rms_limits and rms_limits.get('status'):
                # Get available cash from RMS limits
                rms_data = rms_limits.get('data', {})
                available_cash = float(rms_data.get('availablecash', 0))
                logger.info(f"Available cash from Angel One: ₹{available_cash:.2f}")
        except Exception as rms_error:
            logger.warning(f"Could not fetch RMS limits: {str(rms_error)}")
            available_cash = 0
        
        if holdings['status']:
            # Log successful portfolio fetch
            await log_angel_one_api_call(
                endpoint="/portfolio/holdings",
                method="GET",
                request_data=None,
                response_data={"status": "success", "holdings_count": len(holdings.get('data', [])), "available_cash": available_cash},
                status_code=200,
                execution_time_ms=execution_time
            )
            
            return {
                "holdings": holdings['data'],
                "available_cash": available_cash
            }
        else:
            error_msg = holdings.get('message', 'Unknown error')
            logger.error(f"Error fetching portfolio: {error_msg}")
            
            # Log failed portfolio fetch
            await log_angel_one_api_call(
                endpoint="/portfolio/holdings",
                method="GET",
                request_data=None,
                response_data=holdings,
                status_code=500,
                error=error_msg,
                execution_time_ms=execution_time
            )
            
            raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        error_msg = str(e)
        logger.error(f"Error fetching portfolio: {error_msg}")
        
        # Log exception
        await log_angel_one_api_call(
            endpoint="/portfolio/holdings",
            method="GET",
            request_data=None,
            response_data=None,
            status_code=500,
            error=error_msg,
            execution_time_ms=execution_time
        )
        
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/portfolio")
async def get_portfolio_api():
    return await get_portfolio()

# ===== TRADE EXECUTION =====
async def execute_angel_one_order(symbol: str, transaction_type: str, quantity: int, symbol_token: str = "", order_type: str = "MARKET") -> Dict:
    """Execute order with Angel One API with comprehensive logging"""
    if not smart_api or not auth_tokens:
        await authenticate_angel_one()
    
    if not smart_api:
        logger.error("Angel One API not authenticated - cannot place order")
        return {
            "success": False,
            "order_id": None,
            "message": "Angel One not authenticated",
            "response": None
        }
    
    start_time = datetime.now()
    order_params = None
    order_response = None
    
    try:
        # Prepare order parameters
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": symbol_token,  # Token from watchlist
            "transactiontype": transaction_type,  # BUY or SELL
            "exchange": "NSE",
            "ordertype": order_type,  # MARKET or LIMIT
            "producttype": "DELIVERY",
            "duration": "DAY",
            "quantity": str(quantity)
        }
        
        logger.info(f"========== ANGEL ONE ORDER PLACEMENT ==========")
        logger.info(f"Action: {transaction_type} {quantity} units of {symbol}")
        logger.info(f"Order Parameters: {order_params}")
        
        # Place order
        order_response = smart_api.placeOrder(order_params)
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(f"Order Response Type: {type(order_response)}")
        logger.info(f"Order Response: {order_response}")
        logger.info(f"Execution Time: {execution_time:.2f}ms")
        
        # Handle different response types
        if order_response is None:
            error_msg = "Angel One API returned None response"
            logger.error(error_msg)
            
            await log_angel_one_api_call(
                endpoint="/order/place",
                method="POST",
                request_data=order_params,
                response_data=None,
                status_code=500,
                error=error_msg,
                execution_time_ms=execution_time
            )
            
            return {
                "success": False,
                "order_id": None,
                "message": error_msg,
                "response": None
            }
        
        # If response is a string (order ID), it's a success
        if isinstance(order_response, str):
            order_id = order_response
            logger.info(f"✓ Order placed successfully!")
            logger.info(f"  Order ID: {order_id}")
            logger.info(f"=" * 50)
            
            await log_angel_one_api_call(
                endpoint="/order/place",
                method="POST",
                request_data=order_params,
                response_data={"order_id": order_id, "status": "success"},
                status_code=200,
                execution_time_ms=execution_time
            )
            
            return {
                "success": True,
                "order_id": order_id,
                "message": "Order placed successfully",
                "response": {"order_id": order_id}
            }
        
        # If response is not a dict, convert it
        if not isinstance(order_response, dict):
            logger.warning(f"Unexpected response type: {type(order_response)}")
            order_response = {"raw_response": str(order_response)}
        
        # Log the order attempt
        status_code = 200 if order_response.get('status', False) else 400
        await log_angel_one_api_call(
            endpoint="/order/place",
            method="POST",
            request_data=order_params,
            response_data=order_response,
            status_code=status_code,
            execution_time_ms=execution_time
        )
        
        # Check if order was successful
        if order_response.get('status', False):
            order_data = order_response.get('data', {})
            order_id = order_data.get('orderid', 'N/A') if order_data else 'N/A'
            
            logger.info(f"✓ Order placed successfully!")
            logger.info(f"  Order ID: {order_id}")
            logger.info(f"  Message: {order_response.get('message', 'No message')}")
            logger.info(f"=" * 50)
            
            return {
                "success": True,
                "order_id": order_id,
                "message": order_response.get('message', 'Order placed'),
                "response": order_response
            }
        else:
            error_msg = order_response.get('message', 'Order failed - no error message')
            error_code = order_response.get('errorcode', 'N/A')
            
            logger.error(f"✗ Order placement failed!")
            logger.error(f"  Error Code: {error_code}")
            logger.error(f"  Error Message: {error_msg}")
            logger.error(f"  Full Response: {order_response}")
            logger.error(f"=" * 50)
            
            return {
                "success": False,
                "order_id": None,
                "message": f"{error_msg} (Code: {error_code})",
                "response": order_response
            }
            
    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        error_msg = str(e)
        
        logger.error(f"✗ Order execution exception!")
        logger.error(f"  Exception: {error_msg}")
        logger.error(f"  Request: {order_params}")
        logger.error(f"  Response: {order_response}")
        logger.error(f"=" * 50)
        
        await log_angel_one_api_call(
            endpoint="/order/place",
            method="POST",
            request_data=order_params,
            response_data=order_response,
            status_code=500,
            error=error_msg,
            execution_time_ms=execution_time
        )
        
        return {
            "success": False,
            "order_id": None,
            "message": error_msg,
            "response": order_response
        }

# ===== BOT CONFIG =====
@app.get("/api/config")
async def get_config():
    config_doc = await db.bot_config.find_one({"_id": "main"})
    if config_doc:
        config_doc.pop('_id', None)
        return config_doc
    return BotConfig().model_dump()

@app.put("/api/config")
async def update_config(config: BotConfig):
    config_dict = config.model_dump()
    config_dict['_id'] = 'main'
    config_dict['last_updated'] = get_ist_timestamp()
    
    await db.bot_config.update_one(
        {"_id": "main"},
        {"$set": config_dict},
        upsert=True
    )
    
    # Reschedule bot if active
    if config.is_active:
        await schedule_bot(config)
    else:
        for job in scheduler.get_jobs():
            job.remove()
    
    return config_dict

# ===== WATCHLIST =====
@app.get("/api/watchlist")
async def get_watchlist():
    items = await db.watchlist.find({}, {"_id": 0}).to_list(1000)
    return items

@app.post("/api/watchlist")
async def add_watchlist_item(item: WatchlistItem):
    item_dict = item.model_dump()
    await db.watchlist.insert_one(item_dict)
    return item_dict

@app.put("/api/watchlist/{item_id}")
async def update_watchlist_item(item_id: str, item: WatchlistItem):
    item_dict = item.model_dump()
    await db.watchlist.update_one(
        {"id": item_id},
        {"$set": item_dict}
    )
    return item_dict

@app.delete("/api/watchlist/{item_id}")
async def delete_watchlist_item(item_id: str):
    result = await db.watchlist.delete_one({"id": item_id})
    if result.deleted_count:
        return {"success": True}
    raise HTTPException(status_code=404, detail="Item not found")


# ===== EODHD FINANCIAL API SERVICE =====
import aiohttp
import time

async def fetch_eodhd_fundamentals(symbol: str, exchange: str, api_key: str) -> Optional[Dict]:
    """
    Fetch fundamental data from EODHD API with daily caching
    
    Args:
        symbol: Stock symbol (e.g., "RELIANCE")
        exchange: Exchange (NSE or BSE)
        api_key: EODHD API key
    
    Returns:
        Dictionary with fundamental data or None if failed
    """
    exchange_symbol = f"{symbol}.{exchange}"
    today_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Check cache first
    cache_entry = await db.eodhd_cache.find_one({
        "exchange_symbol": exchange_symbol,
        "date": today_date,
        "data_type": "fundamentals"
    })
    
    if cache_entry and cache_entry.get('data'):
        logger.info(f"📦 Using cached fundamentals for {exchange_symbol} (from {today_date})")
        return cache_entry['data']
    
    # Not in cache or expired - fetch from API
    start_time = time.time()
    url = f"{EODHD_BASE_URL}/fundamentals/{exchange_symbol}"
    
    params = {
        'api_token': api_key,
        'fmt': 'json'
    }
    
    log_entry = EODHDAPILog(
        symbol=symbol,
        exchange_symbol=exchange_symbol,
        data_type="fundamentals",
        request_url=url,
        status="PENDING"
    )
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                execution_time = (time.time() - start_time) * 1000
                
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract key fundamental metrics
                    highlights = data.get('Highlights', {})
                    valuation = data.get('Valuation', {})
                    financials = data.get('Financials', {})
                    
                    fundamentals = {
                        'pe_ratio': highlights.get('PERatio'),
                        'pb_ratio': highlights.get('PriceBookMRQ'),
                        'dividend_yield': highlights.get('DividendYield'),
                        'roe': highlights.get('ReturnOnEquityTTM'),
                        'market_cap': highlights.get('MarketCapitalization'),
                        'eps': highlights.get('EarningsShare'),
                        'peg_ratio': valuation.get('PEGRatio'),
                        'ebitda': highlights.get('EBITDA'),
                        'week_52_high': highlights.get('52WeekHigh'),
                        'week_52_low': highlights.get('52WeekLow'),
                        'price_sales_ttm': valuation.get('PriceSalesTTM')
                    }
                    
                    # Store in cache
                    await db.eodhd_cache.update_one(
                        {
                            "exchange_symbol": exchange_symbol,
                            "date": today_date,
                            "data_type": "fundamentals"
                        },
                        {
                            "$set": {
                                "data": fundamentals,
                                "cached_at": get_ist_timestamp()
                            }
                        },
                        upsert=True
                    )
                    
                    log_entry.response_data = fundamentals
                    log_entry.status = "SUCCESS"
                    log_entry.execution_time_ms = execution_time
                    await db.eodhd_api_logs.insert_one(log_entry.model_dump())
                    
                    logger.info(f"✅ EODHD Fundamentals: {exchange_symbol} PE={fundamentals.get('pe_ratio')} (cached)")
                    return fundamentals
                else:
                    error_msg = f"EODHD API status {response.status}"
                    text = await response.text()
                    log_entry.error = f"{error_msg}: {text[:200]}"
                    log_entry.status = "FAILED"
                    log_entry.execution_time_ms = execution_time
                    await db.eodhd_api_logs.insert_one(log_entry.model_dump())
                    logger.warning(f"⚠️ {error_msg} for {exchange_symbol}")
                    return None
                    
    except Exception as e:
        error_msg = f"EODHD error: {str(e)}"
        log_entry.error = error_msg
        log_entry.status = "FAILED"
        log_entry.execution_time_ms = (time.time() - start_time) * 1000
        await db.eodhd_api_logs.insert_one(log_entry.model_dump())
        logger.error(f"❌ {error_msg} for {exchange_symbol}")
        return None

async def fetch_eodhd_technical(symbol: str, exchange: str, api_key: str) -> Optional[Dict]:
    """
    Technical indicators disabled - API returns 403
    Returning None to skip technical data
    """
    return None

async def fetch_eodhd_data(symbol: str, exchange: str, api_key: str) -> Dict:
    """
    Fetch fundamental data from EODHD (technical disabled)
    
    Args:
        symbol: Stock symbol
        exchange: Exchange (NSE or BSE)
        api_key: EODHD API key
    
    Returns:
        Dictionary with 'fundamentals' and 'technical' keys (technical always None)
    """
    if not api_key:
        logger.warning("⚠️ EODHD API key not configured")
        return {'fundamentals': None, 'technical': None}
    
    logger.info(f"📊 Fetching EODHD data for {symbol}.{exchange}...")
    
    # Only fetch fundamentals (technical disabled due to API limitations)
    fundamentals = await fetch_eodhd_fundamentals(symbol, exchange, api_key)
    
    return {
        'fundamentals': fundamentals,
        'technical': None  # Disabled - API returns 403
    }


# ===== LLM DECISION LOGIC =====
async def get_llm_decision(symbol: str, action: str, market_data: Dict, config: BotConfig, item: Dict, portfolio: Dict = None, total_sip_count: int = 0, isin: str = None, eodhd_technical: Dict = None, eodhd_fundamentals: Dict = None, proxy_index_data: Dict = None) -> Dict:
    """Get LLM decision for a trading action with EODHD market data"""
    try:
        # Get API key
        if config.llm_provider == "openai" and config.openai_api_key:
            api_key = config.openai_api_key
        else:
            api_key = os.environ.get('EMERGENT_LLM_KEY')
        
        # Build ISIN info string
        isin_info = f"\n**ISIN**: {isin}" if isin else ""
        
        # Build Technical Indicators section from EODHD
        tech_info = ""
        if eodhd_technical:
            tech_parts = []
            if eodhd_technical.get('rsi_14') is not None:
                rsi = eodhd_technical['rsi_14']
                rsi_signal = "OVERSOLD" if rsi < 30 else "OVERBOUGHT" if rsi > 70 else "NEUTRAL"
                tech_parts.append(f"RSI(14): {rsi:.1f} ({rsi_signal})")
            if eodhd_technical.get('macd') is not None and eodhd_technical.get('macd_signal') is not None:
                macd_trend = "BULLISH" if eodhd_technical['macd'] > eodhd_technical['macd_signal'] else "BEARISH"
                tech_parts.append(f"MACD: {eodhd_technical['macd']:.2f} / Signal: {eodhd_technical['macd_signal']:.2f} ({macd_trend})")
            if eodhd_technical.get('adx_14') is not None:
                adx = eodhd_technical['adx_14']
                adx_strength = "STRONG TREND" if adx > 25 else "WEAK TREND"
                tech_parts.append(f"ADX(14): {adx:.1f} ({adx_strength})")
            if eodhd_technical.get('atr_14') is not None:
                tech_parts.append(f"ATR(14): {eodhd_technical['atr_14']:.2f} (Volatility measure)")
            if eodhd_technical.get('mfi_14') is not None:
                tech_parts.append(f"MFI(14): {eodhd_technical['mfi_14']:.1f} (Money Flow)")
            
            if tech_parts:
                tech_info = "\n\n**TECHNICAL INDICATORS**:\n" + "\n".join([f"- {part}" for part in tech_parts])
        
        # Build Fundamentals section from EODHD
        fundamentals_info = ""
        if eodhd_fundamentals:
            fund_parts = []
            if eodhd_fundamentals.get('pe_ratio') is not None:
                fund_parts.append(f"P/E Ratio: {eodhd_fundamentals['pe_ratio']:.2f}")
            if eodhd_fundamentals.get('pb_ratio') is not None:
                fund_parts.append(f"P/B Ratio: {eodhd_fundamentals['pb_ratio']:.2f}")
            if eodhd_fundamentals.get('dividend_yield') is not None:
                fund_parts.append(f"Dividend Yield: {eodhd_fundamentals['dividend_yield']:.2f}%")
            if eodhd_fundamentals.get('roe') is not None:
                fund_parts.append(f"ROE: {eodhd_fundamentals['roe']:.2f}%")
            if eodhd_fundamentals.get('market_cap') is not None:
                fund_parts.append(f"Market Cap: ₹{eodhd_fundamentals['market_cap']/10000000:.2f} Cr")
            if eodhd_fundamentals.get('eps') is not None:
                fund_parts.append(f"EPS: ₹{eodhd_fundamentals['eps']:.2f}")
            if eodhd_fundamentals.get('peg_ratio') is not None:
                fund_parts.append(f"PEG Ratio: {eodhd_fundamentals['peg_ratio']:.2f}")
            if eodhd_fundamentals.get('week_52_high') is not None and eodhd_fundamentals.get('week_52_low') is not None:
                fund_parts.append(f"52W Range: ₹{eodhd_fundamentals['week_52_low']:.2f} - ₹{eodhd_fundamentals['week_52_high']:.2f}")
            
            if fund_parts:
                fundamentals_info = "\n\n**FUNDAMENTALS**:\n" + "\n".join([f"- {part}" for part in fund_parts])
        
        # Build Proxy Index Data section
        proxy_info = ""
        if proxy_index_data:
            proxy_name = item.get('proxy_index', 'Benchmark Index')
            proxy_fund = proxy_index_data.get('fundamentals')
            proxy_tech = proxy_index_data.get('technical')
            
            if proxy_fund or proxy_tech:
                proxy_parts = []
                
                # Add fundamentals
                if proxy_fund:
                    if proxy_fund.get('pe_ratio') is not None:
                        proxy_parts.append(f"P/E: {proxy_fund['pe_ratio']:.2f}")
                    if proxy_fund.get('pb_ratio') is not None:
                        proxy_parts.append(f"P/B: {proxy_fund['pb_ratio']:.2f}")
                    if proxy_fund.get('dividend_yield') is not None:
                        proxy_parts.append(f"Div Yield: {proxy_fund['dividend_yield']:.2f}%")
                
                # Add technicals
                if proxy_tech:
                    if proxy_tech.get('rsi_14') is not None:
                        rsi = proxy_tech['rsi_14']
                        rsi_signal = "OVERSOLD" if rsi < 30 else "OVERBOUGHT" if rsi > 70 else "NEUTRAL"
                        proxy_parts.append(f"RSI: {rsi:.1f} ({rsi_signal})")
                
                if proxy_parts:
                    proxy_info = f"\n\n**BENCHMARK INDEX** ({proxy_name}):\n" + "\n".join([f"- {part}" for part in proxy_parts])
        
        # Build prompt based on action
        if action == "sip":
            quantity = item.get('quantity', 0)
            avg_price = item.get('avg_price', 0)
            current_price = market_data.get('ltp', 0)
            
            # Check if this is a re-entry scenario
            awaiting_reentry = item.get('awaiting_reentry', False)
            exit_price = item.get('exit_price', 0)
            exit_amount = item.get('exit_amount', 0)
            exit_quantity = item.get('exit_quantity', 0)
            exit_date = item.get('exit_date', '')
            
            # Calculate current position value and P&L
            investment = quantity * avg_price if quantity and avg_price else 0
            current_value = quantity * current_price if quantity and current_price else 0
            pnl = current_value - investment if investment > 0 else 0
            pnl_pct = (pnl / investment * 100) if investment > 0 else 0
            
            # Get available balance from portfolio (already adjusted for reserved amounts)
            available_balance = portfolio.get('available_cash', 0) if portfolio else 0
            
            # SPECIAL CASE: Re-entry Decision
            if awaiting_reentry and exit_price > 0 and exit_amount > 0:
                # This position was exited, now check if it's time to re-enter
                # Calculate price change (positive = price went up, negative = price dropped)
                price_change_pct = ((current_price - exit_price) / exit_price * 100) if exit_price > 0 else 0
                price_direction = "INCREASED" if price_change_pct > 0 else "DECREASED" if price_change_pct < 0 else "UNCHANGED"
                
                reentry_prompt = f"""
You are a stock market analyst. This SIP position was EXITED for profit booking. Now decide if it's time to RE-ENTER.

**STOCK**: {symbol}{isin_info}
**CURRENT PRICE**: ₹{current_price:.2f}

**EXIT DETAILS** (When position was sold for profit):
- Exit Price: ₹{exit_price:.2f}
- Exit Quantity: {exit_quantity} units
- Exit Amount Received: ₹{exit_amount:.2f}
- Exit Date: {exit_date}
- **Price Change Since Exit: {price_change_pct:+.1f}%** ({price_direction}: ₹{exit_price:.2f} → ₹{current_price:.2f})

**RESERVED AMOUNT FOR RE-ENTRY**: ₹{exit_amount:.2f}

**USER'S ANALYSIS PARAMETERS**:
{config.analysis_parameters}

**YOUR TASK**: Decide if NOW is a GOOD time to RE-ENTER this position.

**CRITICAL RE-ENTRY RULES**:

1. **ONLY RE-ENTER IF PRICE HAS DROPPED BELOW OR NEAR EXIT PRICE**
   - Ideal: Price dropped 5-15% from exit (good discount)
   - Acceptable: Price at or slightly below exit (0% to -5%)
   - DO NOT re-enter if price is significantly ABOVE exit (expensive!)

2. **Price Analysis**:
   - If current price > exit price: Usually WAIT (price too high)
   - If current price ≈ exit price: Consider other factors (support, RSI)
   - If current price < exit price: Good opportunity (buying at discount)

3. **Technical Confirmation** (secondary factors):
   - RSI: Below 40 (oversold) is positive
   - Support: Price at strong support level
   - Volume: Increased buying volume shows confidence
   - Trend: Downtrend reversing or consolidating

4. **Timing Strategy**:
   - Don't chase - if price keeps rising, accept you exited well
   - Be patient - wait for proper pullback/correction
   - Risk-reward - ensure better price than exit or strong bullish setup

**RESPONSE FORMAT** (must follow exactly):
REENTRY_ACTION: EXECUTE or WAIT
AMOUNT: {exit_amount:.2f}
REASONING: <Brief explanation of price levels, indicators, and timing decision>

**GOOD RE-ENTRY EXAMPLES**:
✅ Exit ₹100, Now ₹90 (-10%): "REENTRY_ACTION: EXECUTE\\nAMOUNT: {exit_amount:.2f}\\nREASONING: Price dropped 10% from exit, now at ₹90. RSI 35 oversold. Strong support at ₹88. Good discount for re-entry."

✅ Exit ₹100, Now ₹98 (-2%): "REENTRY_ACTION: EXECUTE\\nAMOUNT: {exit_amount:.2f}\\nREASONING: Price slightly below exit at ₹98. Strong support confirmed, volume pickup, RSI 42. Early re-entry before bounce."

**BAD RE-ENTRY EXAMPLES**:
❌ Exit ₹100, Now ₹110 (+10%): "REENTRY_ACTION: WAIT\\nAMOUNT: 0\\nREASONING: Price up 10% from exit to ₹110. Expensive re-entry. Wait for pullback to ₹95-100 or skip if momentum continues."

❌ Exit ₹100, Now ₹105 (+5%): "REENTRY_ACTION: WAIT\\nAMOUNT: 0\\nREASONING: Price higher at ₹105. RSI 65 near overbought. No discount, poor risk-reward. Exit was good, don't chase."

❌ Exit ₹100, Now ₹95 (-5%), but RSI 70: "REENTRY_ACTION: WAIT\\nAMOUNT: 0\\nREASONING: Though price dropped to ₹95, RSI 70 overbought suggests short-term correction. Wait for RSI below 50 or deeper drop to ₹90."

**REMEMBER**: 
- Primary criterion is PRICE DISCOUNT from exit
- Don't re-enter at higher prices unless extremely strong bullish setup
- It's okay to WAIT - better opportunities will come!
"""
                
                try:
                    session_id = f"{symbol}_reentry_{uuid.uuid4().hex[:8]}"
                    chat = LlmChat(
                        api_key=api_key,
                        session_id=session_id,
                        system_message="You are an expert at timing re-entry points after profit booking."
                    )
                    chat.with_model("openai", config.llm_model)
                    response = await chat.send_message(UserMessage(text=reentry_prompt))
                    
                    # Parse re-entry response
                    decision = "SKIP"
                    reasoning = "No clear signal"
                    
                    for line in response.split('\n'):
                        if 'REENTRY_ACTION:' in line:
                            action_value = line.split(':')[1].strip().upper()
                            decision = "EXECUTE" if action_value == "EXECUTE" else "SKIP"
                        elif 'REASONING:' in line:
                            reasoning = line.split(':', 1)[1].strip()
                    
                    # Log the re-entry check
                    await db.llm_prompt_logs.insert_one({
                        "symbol": symbol,
                        "action_type": "sip_reentry",
                        "full_prompt": reentry_prompt,
                        "llm_response": response,
                        "decision_made": decision,
                        "model_used": config.llm_model,
                        "timestamp": get_ist_timestamp()
                    })
                    
                    return {
                        "decision": decision,
                        "sip_amount": exit_amount if decision == "EXECUTE" else 0,
                        "reasoning": reasoning
                    }
                    
                except Exception as reentry_error:
                    logger.error(f"Re-entry LLM decision error: {str(reentry_error)}")
                    return {
                        "decision": "SKIP",
                        "sip_amount": 0,
                        "reasoning": f"Error in re-entry analysis: {str(reentry_error)}"
                    }
            
            # STEP 1: Check if should EXIT (profit booking) - Only if position exists
            should_exit = False
            exit_reasoning = ""
            
            if quantity > 0 and current_price > 0:
                exit_check_prompt = f"""
You are a stock market analyst analyzing if this SIP position has reached its PEAK and should be EXITED for profit booking.

**STOCK**: {symbol}{isin_info}
**CURRENT PRICE**: ₹{current_price:.2f}
**YOUR POSITION**:
- Quantity: {quantity}
- Average Price: ₹{avg_price:.2f}
- Investment: ₹{investment:.2f}
- Current Value: ₹{current_value:.2f}
- **Profit: ₹{pnl:.2f} ({pnl_pct:+.2f}%)**

**USER'S ANALYSIS PARAMETERS**:
{config.analysis_parameters}

**YOUR TASK**: Decide if this stock has reached MAXIMUM value and should be SOLD NOW for profit booking.

**EXIT CRITERIA** (Check these):
1. Stock price significantly overvalued (P/E ratio very high, price >> fair value)
2. Technical indicators showing overbought (RSI > 70, hitting resistance)
3. Profit already substantial (>50-100% gains) and risk of correction high
4. Fundamental deterioration or sector headwinds
5. Better opportunities elsewhere

**IMPORTANT**: 
- This is ONLY for profit booking when stock has peaked
- After exit, SIP will resume in next cycle when price corrects
- Be conservative - only exit if strong signals of overvaluation

**RESPONSE FORMAT** (must follow exactly):
EXIT_DECISION: YES or NO
REASONING: <2-3 line explanation>

**EXAMPLES**:
- "EXIT_DECISION: YES\\nREASONING: Stock up 120% with RSI at 78. Fundamentals stretched with P/E at 45 vs industry avg 25. Clear overvaluation signals."
- "EXIT_DECISION: NO\\nREASONING: Despite 40% gains, fundamentals remain strong. Growth trajectory intact. Hold and continue SIP."
"""
                
                try:
                    # Make exit check LLM call
                    exit_session_id = f"{symbol}_sip_exit_check_{uuid.uuid4().hex[:8]}"
                    exit_chat = LlmChat(
                        api_key=api_key,
                        session_id=exit_session_id,
                        system_message="You are an expert at identifying peak valuations and profit booking opportunities."
                    )
                    exit_chat.with_model("openai", config.llm_model)
                    exit_response = await exit_chat.send_message(UserMessage(text=exit_check_prompt))
                    
                    # Parse exit response
                    for line in exit_response.split('\n'):
                        if "EXIT_DECISION:" in line.upper():
                            if "YES" in line.upper():
                                should_exit = True
                        if "REASONING:" in line:
                            exit_reasoning = line.split("REASONING:")[-1].strip()
                    
                    # Log exit check
                    try:
                        exit_log = LLMPromptLog(
                            symbol=symbol,
                            action_type="sip_exit_check",
                            full_prompt=exit_check_prompt,
                            llm_response=exit_response,
                            model_used=config.llm_model,
                            decision_made="EXIT" if should_exit else "CONTINUE_SIP"
                        )
                        await db.llm_prompt_logs.insert_one(exit_log.model_dump())
                    except Exception as log_err:
                        logger.error(f"Failed to log exit check: {str(log_err)}")
                    
                except Exception as exit_err:
                    logger.error(f"Exit check LLM error: {str(exit_err)}")
                    should_exit = False
            
            # If should exit, return EXIT decision
            if should_exit:
                prompt = exit_check_prompt
                response = f"SIP_ACTION: EXIT\nAMOUNT: {current_value:.2f}\nREASONING: {exit_reasoning}"
            else:
                # STEP 2: Normal SIP decision with detailed dynamic amount logic
                price_ratio = (current_price / avg_price) if avg_price > 0 else 1.0
                
                prompt = f"""
You are a stock market analyst. Analyze this stock for SIP (Systematic Investment Plan) decision RIGHT NOW.

**STOCK**: {symbol}{isin_info}
**CURRENT PRICE**: ₹{current_price:.2f}

**YOUR CURRENT POSITION**:
- Quantity Held: {quantity}
- Average Price: ₹{avg_price:.2f}
- Price vs Avg: {((price_ratio - 1) * 100):+.1f}% (Current is {price_ratio:.2f}x of avg)
- Investment: ₹{investment:.2f}
- Current Value: ₹{current_value:.2f}
- P&L: ₹{pnl:.2f} ({pnl_pct:+.2f}%)

**AVAILABLE BALANCE**: ₹{available_balance:.2f}
**TOTAL SIP STOCKS IN WATCHLIST**: {total_sip_count} stocks (including this one)
**BALANCE PER SIP STOCK**: ₹{(available_balance / total_sip_count) if total_sip_count > 0 else 0:.2f} (if divided equally)
{tech_info}{fundamentals_info}{proxy_info}

**USER'S ANALYSIS PARAMETERS**:
{config.analysis_parameters}

**YOUR TASK**: Decide SIP amount with SMART DYNAMIC ADJUSTMENT based on price levels, technical indicators, and market conditions.

**IMPORTANT CONTEXT**:
- You have {total_sip_count} total SIP stocks to manage
- Available balance needs to be distributed across all SIPs
- Consider both this stock's opportunity AND fair allocation
- If this stock shows exceptional opportunity (very low price), you can suggest MORE than equal share
- If this stock is expensive, suggest LESS to save balance for other SIPs

**CRITICAL: DYNAMIC AMOUNT LOGIC** (Apply this strictly):

1. **Price SIGNIFICANTLY BELOW Average** (price <0.8x of avg):
   - Great buying opportunity, accumulate aggressively
   - Suggest higher amount (e.g., ₹8000-₹12000)

2. **Price BELOW Average** (price 0.8x-0.95x of avg):
   - Good entry point, above-normal investment
   - Suggest moderate-high amount (e.g., ₹6000-₹9000)

3. **Price NEAR Average** (price 0.95x-1.05x of avg):
   - Fair valuation, normal investment
   - Suggest standard amount (e.g., ₹4000-₹6000)

4. **Price ABOVE Average** (price 1.05x-1.2x of avg):
   - Reduce investment, manage risk
   - Suggest lower amount (e.g., ₹2500-₹4000)

5. **Price SIGNIFICANTLY ABOVE Average** (price >1.2x of avg):
   - High risk zone, minimal investment
   - Suggest minimal amount (e.g., ₹1500-₹2500)

**ADDITIONAL INDICATORS TO CONSIDER**:
- RSI: Low (<30) = increase amount, High (>70) = decrease amount
- Volume: High buying volume = confidence, increase amount
- Support/Resistance: Near support = increase, near resistance = decrease
- Momentum: Strong uptrend = moderate increase, weak/falling = reduce

**RESPONSE FORMAT** (must follow exactly):
SIP_ACTION: SKIP or EXECUTE
AMOUNT: <dynamically calculated amount based on above rules>
REASONING: <Explain price level, indicators, and why this specific amount>

**EXAMPLES WITH DYNAMIC AMOUNTS**:
- Price ₹85, Avg ₹100 (0.85x): "SIP_ACTION: EXECUTE\\nAMOUNT: 9000\\nREASONING: Price 15% below avg at ₹85 vs ₹100. RSI at 35 shows oversold. Increased to ₹9000 to accumulate aggressively."

- Price ₹105, Avg ₹100 (1.05x): "SIP_ACTION: EXECUTE\\nAMOUNT: 4500\\nREASONING: Price 5% above avg. Momentum positive but reducing to ₹4500 to manage valuation risk."

- Price ₹130, Avg ₹100 (1.3x): "SIP_ACTION: EXECUTE\\nAMOUNT: 2000\\nREASONING: Price 30% above avg showing extended valuations. RSI 68. Minimal investment at ₹2000 to maintain discipline."

- Price ₹95, Avg ₹100 (0.95x), RSI 75: "SIP_ACTION: SKIP\\nREASONING: Though price near avg, RSI 75 overbought. Market overheated. Skip this cycle."

**REMEMBER**: Your amount suggestion should clearly reflect the price level dynamics and available balance!
"""
                
                try:
                    session_id = f"{symbol}_sip_{uuid.uuid4().hex[:8]}"
                    chat = LlmChat(
                        api_key=api_key,
                        session_id=session_id,
                        system_message="You are an expert at dynamic SIP strategies with data-driven amount adjustments."
                    )
                    chat.with_model("openai", config.llm_model)
                    response = await chat.send_message(UserMessage(text=prompt))
                except Exception as llm_error:
                    logger.error(f"SIP LLM error: {str(llm_error)}")
                    response = f"SIP_ACTION: SKIP\nAMOUNT: 0\nREASONING: LLM error - {str(llm_error)[:100]}"

        elif action == "sell":
            quantity = item.get('quantity', 0) or 0
            avg_price = item.get('avg_price', 0) or 0
            ltp = market_data.get('ltp', 0) or 0
            
            current_value = quantity * ltp
            investment = quantity * avg_price
            pnl = current_value - investment
            pnl_pct = (pnl / investment * 100) if investment > 0 else 0
            
            prompt = f"""
You are a stock market analyst. Analyze whether to sell this holding.

**STOCK**: {symbol}{isin_info}
**QUANTITY**: {quantity}
**AVG PRICE**: ₹{avg_price:.2f}
**CURRENT PRICE**: ₹{ltp:.2f}
**INVESTMENT**: ₹{investment:.2f}
**CURRENT VALUE**: ₹{current_value:.2f}
**P&L**: ₹{pnl:.2f} ({pnl_pct:.2f}%)
{tech_info}{fundamentals_info}{proxy_info}

**USER'S ANALYSIS PARAMETERS**:
{config.analysis_parameters}

**YOUR TASK**: Decide whether to sell this holding based on current market conditions, fundamentals, and technical analysis.

**RESPONSE FORMAT** (must follow exactly):
SELL_ACTION: HOLD or SELL or EXIT_AND_REENTER
RE_ENTRY_PRICE: <price in rupees if EXIT_AND_REENTER, else 0>
TAX_HARVESTING: YES or NO
REASONING: <brief 2-3 line explanation>

**GUIDELINES**:
1. Consider stock fundamentals, market trends, and technical indicators
2. EXIT_AND_REENTER: Use when stock is temporarily overvalued but has strong long-term potential
3. SELL: Use when fundamentals have deteriorated or better opportunities exist
4. HOLD: When stock has more upside potential
5. Consider brokerage charges (~0.5%) in your decision
6. Use the provided technical indicators and market data to make informed decisions
"""
        elif action == "buy":
            quantity = item.get('quantity', 0) or 0
            avg_price = item.get('avg_price', 0) or 0
            ltp = market_data.get('ltp', 0) or 0
            
            prompt = f"""
You are a stock market analyst. Analyze this stock for BUY action.

**STOCK**: {symbol}{isin_info}
**CURRENT PRICE**: ₹{ltp:.2f}

**PORTFOLIO CONTEXT**:
- Current Quantity: {quantity}
- Avg Price: ₹{avg_price:.2f}
{tech_info}{fundamentals_info}{proxy_info}

**USER'S ANALYSIS PARAMETERS**:
{config.analysis_parameters}

**YOUR TASK**: Decide whether to buy this stock based on current market conditions and your analysis.

**RESPONSE FORMAT**:
BUY_ACTION: EXECUTE or SKIP
AMOUNT: <suggested investment amount in rupees>
REASONING: <brief 2-3 line explanation>

Provide your recommendation based on fundamentals, technical analysis, and market data.
"""
        else:
            # For other actions
            quantity = item.get('quantity', 0) or 0
            avg_price = item.get('avg_price', 0) or 0
            ltp = market_data.get('ltp', 0) or 0
            
            prompt = f"""
You are a stock market analyst. Analyze this stock for {action.upper()} action.

**STOCK**: {symbol}{isin_info}
**CURRENT PRICE**: ₹{ltp:.2f}
**PORTFOLIO CONTEXT**: Quantity: {quantity}, Avg Price: ₹{avg_price:.2f}
{tech_info}{fundamentals_info}{proxy_info}

**USER'S ANALYSIS PARAMETERS**:
{config.analysis_parameters}

Provide your recommendation based on current market conditions and fundamentals.
"""
        
        # Make LLM call
        try:
            session_id = f"{symbol}_{action}_{uuid.uuid4().hex[:8]}"
            chat = LlmChat(
                api_key=api_key,
                session_id=session_id,
                system_message="You are an expert stock market analyst providing specific trading recommendations."
            )
            
            # Always use openai provider (emergentintegrations supports both)
            chat.with_model("openai", config.llm_model)
            
            user_message = UserMessage(text=prompt)
            response = await chat.send_message(user_message)
            
        except Exception as llm_error:
            logger.error(f"LLM API error: {str(llm_error)}")
            error_msg = str(llm_error)
            
            # Check for specific errors
            if "AuthenticationError" in error_msg or "Incorrect API key" in error_msg:
                response = f"SIP_ACTION: SKIP\nAMOUNT: 0\nERROR: Invalid {config.llm_provider.upper()} API key. Please check your API key in Control Panel."
            elif "insufficient_quota" in error_msg or "quota" in error_msg.lower():
                response = f"SIP_ACTION: SKIP\nAMOUNT: 0\nERROR: {config.llm_provider.upper()} quota exceeded. Please add credits or switch to Emergent LLM."
            else:
                response = f"SIP_ACTION: SKIP\nAMOUNT: 0\nERROR: LLM error - {error_msg[:100]}"
        
        # Parse response
        decision = "SKIP"
        sip_amount = 0
        re_entry_price = 0
        tax_harvesting = "NO"
        
        lines = response.split('\n')
        for line in lines:
            line_upper = line.upper()
            
            if "SIP_ACTION:" in line_upper:
                # Extract value after colon
                value = line_upper.split("SIP_ACTION:")[-1].strip()
                if "EXIT" in value:
                    decision = "EXIT"  # SIP profit booking
                elif "EXECUTE" in value:
                    decision = "EXECUTE"
                else:
                    decision = "SKIP"
                    
            elif "SELL_ACTION:" in line_upper:
                # Extract value after colon
                value = line_upper.split("SELL_ACTION:")[-1].strip()
                if "EXIT_AND_REENTER" in value or "EXIT AND REENTER" in value:
                    decision = "EXIT_AND_REENTER"
                elif "SELL" in value and "HOLD" not in value:
                    decision = "SELL"
                elif "HOLD" in value:
                    decision = "SKIP"
                else:
                    decision = "SKIP"
                    
            elif "BUY_ACTION:" in line_upper:
                # Extract value after colon
                value = line_upper.split("BUY_ACTION:")[-1].strip()
                if "EXECUTE" in value:
                    decision = "EXECUTE"
                else:
                    decision = "SKIP"
                    
            elif "AMOUNT:" in line_upper:
                try:
                    sip_amount = float(line.split(':')[1].strip().replace('₹', '').replace(',', '').replace('<','').replace('>',''))
                except:
                    sip_amount = item.get('sip_amount', 0) if decision == "EXECUTE" else 0
                    
            elif "RE_ENTRY_PRICE:" in line_upper or "RE-ENTRY PRICE:" in line_upper:
                try:
                    re_entry_price = float(line.split(':')[1].strip().replace('₹', '').replace(',', '').replace('<','').replace('>',''))
                except:
                    pass
                    
            elif "TAX_HARVESTING:" in line_upper or "TAX HARVESTING:" in line_upper:
                if "YES" in line_upper:
                    tax_harvesting = "YES"
        
        # Log prompt & response
        try:
            log_entry = LLMPromptLog(
                symbol=symbol,
                action_type=action,
                full_prompt=prompt,
                llm_response=response,
                model_used=config.llm_model,
                decision_made=decision
            )
            await db.llm_prompt_logs.insert_one(log_entry.model_dump())
        except Exception as log_error:
            logger.error(f"Failed to log prompt: {str(log_error)}")
        
        return {
            "decision": decision,
            "sip_amount": sip_amount,
            "re_entry_price": re_entry_price,
            "tax_harvesting": tax_harvesting,
            "reasoning": response,
            "prompt": prompt
        }
        
    except Exception as e:
        logger.error(f"LLM decision error: {str(e)}")
        return {
            "decision": "SKIP",
            "sip_amount": 0,
            "re_entry_price": 0,
            "tax_harvesting": "NO",
            "reasoning": f"Error: {str(e)}",
            "prompt": ""
        }

# ===== TELEGRAM =====
async def send_telegram_notification(message: str, config: BotConfig):
    if not config.enable_notifications or not config.telegram_bot_token:
        return
    
    try:
        from telegram import Bot
        bot = Bot(token=config.telegram_bot_token)
        
        for chat_id in config.telegram_chat_ids:
            try:
                await bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Failed to send to {chat_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Telegram notification error: {str(e)}")

# ===== MARKET STATUS CHECK =====
async def is_market_open() -> bool:
    """Check if NSE market is open"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json'
            }
            async with session.get('https://www.nseindia.com/api/marketStatus', headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    # Check if any market is open
                    if isinstance(data, dict) and 'marketState' in data:
                        for market in data['marketState']:
                            market_status = market.get('marketStatus', '').lower()
                            market_name = market.get('market', 'Unknown')
                            logger.info(f"Market '{market_name}' status: {market_status}")
                            
                            # Market is open if status is "open" or "normal"
                            if market_status in ['open', 'normal']:
                                logger.info(f"✓ Market is OPEN: {market_name}")
                                return True
                    
                    logger.info("❌ All markets are CLOSED")
                    return False
                else:
                    logger.error(f"NSE API returned status {response.status}")
                    return False
    except Exception as e:
        logger.error(f"❌ Failed to check market status: {str(e)}")
        # For automatic runs, default to False (don't trade if we can't confirm market is open)
        logger.error("⚠️ Defaulting to CLOSED for safety")
        return False
    return False

# ===== BOT SCHEDULING =====
async def schedule_bot(config: BotConfig):
    # Remove existing jobs
    for job in scheduler.get_jobs():
        job.remove()
    
    if not config.is_active:
        return
    
    # Schedule based on type
    if config.schedule_type == "interval":
        scheduler.add_job(
            run_trading_bot,
            IntervalTrigger(minutes=config.schedule_minutes),
            id="trading_bot"
        )
    elif config.schedule_type == "daily" and config.schedule_time:
        from apscheduler.triggers.cron import CronTrigger
        hour, minute = config.schedule_time.split(':')
        # Schedule in IST
        scheduler.add_job(
            run_trading_bot,
            CronTrigger(hour=int(hour), minute=int(minute), timezone=IST),
            id="trading_bot"
        )
    elif config.schedule_type == "hourly" and config.schedule_hours_interval:
        scheduler.add_job(
            run_trading_bot,
            IntervalTrigger(hours=config.schedule_hours_interval),
            id="trading_bot"
        )
    
    if not scheduler.running:
        scheduler.start()

# ===== TRADING BOT =====
async def run_trading_bot(manual_trigger: bool = False):
    """
    Run trading bot with LLM analysis and optional order execution
    
    Parameters:
    - manual_trigger (bool): If True, bypasses market status check ONLY
    
    Important behavior:
    1. manual_trigger=True → Bypasses MARKET STATUS check, but still respects auto_execute_trades flag
    2. auto_execute_trades=False → Skips ORDER EXECUTION for both manual and automatic runs
    3. Bot ALWAYS performs LLM analysis regardless of these flags
    """
    logger.info(f"🤖 Trading bot started (manual_trigger={manual_trigger})")
    logger.info(f"   → manual_trigger controls: Market status check bypass")
    logger.info(f"   → auto_execute_trades controls: Whether to place actual orders")
    
    today_ist = datetime.now(IST).date().isoformat()
    
    try:
        # STEP 1: Check market status FIRST for automatic runs (before any other processing)
        if not manual_trigger:
            logger.info("📊 Checking market status for automatic run...")
            market_open = await is_market_open()
            
            # Log market state
            market_log = MarketStateLog(
                date=today_ist,
                market_status="Open" if market_open else "Closed",
                bot_executed=market_open,
                reason=None if market_open else "Market closed - automatic execution aborted"
            )
            await db.market_state_logs.insert_one(market_log.model_dump())
            
            if not market_open:
                logger.info("⏸️ Market is CLOSED. Automatic bot execution aborted.")
                return
            else:
                logger.info("✓ Market is OPEN. Proceeding with bot execution...")
        else:
            logger.info("🔧 Manual trigger - bypassing market status check")
            
            # Log manual execution
            market_log = MarketStateLog(
                date=today_ist,
                market_status="Manual Override",
                bot_executed=True,
                reason="Force run by user"
            )
            await db.market_state_logs.insert_one(market_log.model_dump())
        
        # STEP 2: Get config
        config_doc = await db.bot_config.find_one({"_id": "main"})
        if not config_doc:
            logger.error("❌ No bot config found")
            return
        
        config = BotConfig(**config_doc)
        logger.info(f"📋 Config loaded - auto_execute_trades={config.auto_execute_trades}")
        
        if not config.is_active:
            logger.info("Bot is not active")
            return
        
        # Get watchlist
        watchlist = await db.watchlist.find({}).to_list(1000)
        
        if not watchlist:
            logger.info("Watchlist is empty")
            return
        
        # Count actions
        action_counts = {}
        for item in watchlist:
            action = item['action']
            action_counts[action] = action_counts.get(action, 0) + 1
        
        logger.info(f"Watchlist items by action: {action_counts}")
        
        # Get portfolio for context
        try:
            portfolio = await get_portfolio()
        except Exception as e:
            logger.error(f"Failed to fetch portfolio: {str(e)}")
            portfolio = {"holdings": [], "available_cash": 0}
        
        # Calculate reserved balance for awaiting re-entry SIPs
        reserved_for_reentry = 0
        for item in watchlist:
            if item.get('awaiting_reentry', False) and item.get('action') == 'sip':
                exit_amount = item.get('exit_amount', 0)
                reserved_for_reentry += exit_amount
                logger.info(f"  → Reserved ₹{exit_amount:.2f} for re-entry: {item.get('symbol')}")
        
        # Calculate actual available balance after reservations
        angel_one_balance = portfolio.get('available_cash', 0)
        available_balance = angel_one_balance - reserved_for_reentry
        
        if reserved_for_reentry > 0:
            logger.info(f"💰 Balance Calculation:")
            logger.info(f"   Angel One Balance: ₹{angel_one_balance:.2f}")
            logger.info(f"   Reserved for Re-entry: ₹{reserved_for_reentry:.2f}")
            logger.info(f"   Available for Trading: ₹{available_balance:.2f}")
        
        # Check minimum balance requirement
        MIN_BALANCE = 2000
        
        if available_balance < MIN_BALANCE:
            error_msg = f"⚠️ Insufficient balance: ₹{available_balance:.2f} < ₹{MIN_BALANCE:.2f}. Bot execution aborted."
            logger.error(error_msg)
            
            # Send notification if enabled
            if config.enable_notifications:
                await send_telegram_notification(f"🚫 **Bot Execution Aborted**\n\n{error_msg}\n\nPlease add funds to continue trading.", config)
            
            return
        
        logger.info(f"✓ Balance check passed: ₹{available_balance:.2f} (Min: ₹{MIN_BALANCE:.2f})")
        
        # Process each watchlist item
        processed = 0
        skipped = 0
        for item in watchlist:
            symbol = item['symbol']
            action = item['action']
            
            # Skip items with "hold" action - only process SIP, Buy, Sell
            if action == 'hold':
                logger.debug(f"Skipping {symbol} - action is 'hold' (monitor only)")
                skipped += 1
                continue
            
            # Check SIP frequency (only once per day)
            if action == 'sip':
                last_sip_date = item.get('last_sip_date')
                today_ist = datetime.now(IST).date().isoformat()
                
                if last_sip_date and last_sip_date == today_ist:
                    logger.info(f"Skipping {symbol} - SIP already executed today ({today_ist})")
                    skipped += 1
                    continue
            
            logger.info(f"Processing {symbol} - action: {action.upper()}")
            processed += 1
            
            # Get market data from portfolio if available
            holding = next((h for h in portfolio['holdings'] if h.get('tradingsymbol') == symbol), None)
            if holding:
                market_data = {
                    "ltp": float(holding.get('ltp', 0)),
                    "volume": 0,
                    "change_pct": 0
                }
                isin = holding.get('isin')  # Get ISIN from Angel One
            else:
                # Use item's avg_price as placeholder if not in portfolio
                market_data = {
                    "ltp": item.get('avg_price', 100),
                    "volume": 0,
                    "change_pct": 0
                }
                isin = None
            
            # Fetch EODHD market data (fundamentals + technical)
            eodhd_fundamentals = None
            eodhd_technical = None
            proxy_index_data = None
            
            # Get EODHD API key from credentials
            logger.info(f"🔑 Fetching EODHD API key from database for {symbol}...")
            creds_doc = await db.credentials.find_one({"_id": "main"})
            logger.info(f"   Credentials document found: {creds_doc is not None}")
            if creds_doc:
                fields = [k for k in creds_doc.keys() if k != '_id']
                logger.info(f"   Fields in creds: {fields}")
                has_key = 'eodhd_api_key' in creds_doc
                logger.info(f"   Has eodhd_api_key: {has_key}")
                if has_key:
                    val = creds_doc.get('eodhd_api_key')
                    logger.info(f"   Value type: {type(val)}, length: {len(val) if val else 0}")
            
            eodhd_api_key = None
            if creds_doc and creds_doc.get('eodhd_api_key'):
                try:
                    eodhd_api_key = decrypt_value(creds_doc['eodhd_api_key'])
                    logger.info(f"✅ EODHD API key loaded: {eodhd_api_key[:10]}..." if eodhd_api_key else "❌ Decryption returned None")
                except Exception as e:
                    logger.error(f"❌ Error decrypting EODHD API key: {e}")
            else:
                logger.warning(f"❌ EODHD API key not found in database. creds_doc exists: {creds_doc is not None}")
            
            if eodhd_api_key:
                try:
                    # Determine exchange from holding or use NSE as default
                    exchange = "NSE"
                    if holding:
                        # Angel One might have exchange info in symbol or separately
                        exchange_info = holding.get('exchange', 'NSE')
                        if exchange_info in ['NSE', 'BSE']:
                            exchange = exchange_info
                    
                    # Clean symbol - remove -EQ suffix for EODHD
                    clean_symbol = symbol.replace('-EQ', '').replace('-eq', '')
                    
                    # Fetch EODHD data for the stock
                    eodhd_data = await fetch_eodhd_data(clean_symbol, exchange, eodhd_api_key)
                    eodhd_fundamentals = eodhd_data.get('fundamentals')
                    eodhd_technical = eodhd_data.get('technical')
                    
                    # Fetch EODHD data for proxy index if mapped
                    proxy_index = item.get('proxy_index')
                    logger.info(f"   Checking proxy_index for {symbol}: {proxy_index}")
                    
                    if proxy_index and proxy_index.strip():
                        logger.info(f"📊 Proxy index mapped: {proxy_index}")
                        logger.info(f"   Fetching EODHD data for index...")
                        
                        # Clean proxy index name and try different formats
                        proxy_clean = proxy_index.strip().upper()
                        
                        # Try common index symbol formats
                        index_symbols = [
                            f"{proxy_clean}.INDX",  # EODHD index format
                            f"^{proxy_clean}",       # Yahoo format
                            proxy_clean,             # As-is
                        ]
                        
                        # Also try removing spaces for indices like "NIFTY 50" -> "NIFTY50"
                        if ' ' in proxy_clean:
                            no_space = proxy_clean.replace(' ', '')
                            index_symbols.append(f"{no_space}.INDX")
                            index_symbols.append(f"^{no_space}")
                            index_symbols.append(no_space)
                        
                        # Try fetching with different formats
                        for idx_symbol in index_symbols:
                            try:
                                # For indices, exchange might be INDX or omitted
                                idx_data = await fetch_eodhd_data(idx_symbol, "INDX", eodhd_api_key)
                                if idx_data and (idx_data.get('fundamentals') or idx_data.get('technical')):
                                    proxy_index_data = idx_data
                                    logger.info(f"   ✅ Index data fetched using: {idx_symbol}")
                                    break
                            except Exception as e:
                                logger.debug(f"   Failed with {idx_symbol}: {e}")
                                continue
                        
                        if not proxy_index_data:
                            logger.warning(f"   ⚠️ Could not fetch index data for: {proxy_index}")
                    
                except Exception as e:
                    logger.warning(f"Error fetching EODHD data for {symbol}: {e}")
            else:
                logger.warning(f"⚠️ EODHD API key not configured - skipping market data fetch")
            
            # Get LLM decision with ISIN, adjusted available balance, and EODHD data
            llm_result = await get_llm_decision(
                symbol, action, market_data, config, item, 
                {"holdings": portfolio['holdings'], "available_cash": available_balance}, 
                action_counts.get('sip', 0), isin,
                eodhd_technical, eodhd_fundamentals, proxy_index_data
            )
            
            # Log analysis
            analysis_log = AnalysisLog(
                symbol=symbol,
                action=action,
                llm_decision=llm_result['decision'],
                market_data=market_data,
                executed=False,  # Will update to True if order placed
                order_id=None,
                execution_status=None  # Will be set based on execution flow
            )
            
            # Execute trades based on auto_execute_trades flag
            # IMPORTANT: This flag applies to BOTH manual and automatic triggers
            # manual_trigger only affects market status check, not order execution
            order_result = None
            logger.info(f"💰 Order Execution Check for {symbol}:")
            logger.info(f"   - auto_execute_trades flag: {config.auto_execute_trades} (controls order placement)")
            logger.info(f"   - LLM decision: {llm_result['decision']}")
            logger.info(f"   - Trigger type: {'Manual' if manual_trigger else 'Automatic'}")
            logger.info(f"   Note: auto_execute_trades flag applies to BOTH manual and automatic runs")
            
            if not config.auto_execute_trades:
                logger.warning(f"⏭️ SKIPPING order execution for {symbol}")
                logger.warning(f"   Reason: auto_execute_trades is DISABLED")
                logger.warning(f"   Trigger type: {'Manual' if manual_trigger else 'Automatic'}")
                logger.warning(f"   LLM analysis completed, but NO ORDER will be placed to Angel One")
                analysis_log.execution_status = "SKIPPED_AUTO_EXECUTE_DISABLED"
            elif llm_result['decision'] not in ["EXECUTE", "SELL", "EXIT_AND_REENTER", "EXIT"]:
                logger.info(f"⏭️ SKIPPING order execution for {symbol}")
                logger.info(f"   Reason: LLM decision is '{llm_result['decision']}' (not an execution decision)")
                analysis_log.execution_status = "SKIPPED_LLM_DECISION"
            elif config.auto_execute_trades and llm_result['decision'] in ["EXECUTE", "SELL", "EXIT_AND_REENTER", "EXIT"]:
                logger.info(f"✅ PROCEEDING with order execution for {symbol}")
                logger.info(f"   auto_execute_trades is ENABLED and LLM decided to execute")
                try:
                    # Determine transaction type and quantity
                    if llm_result['decision'] == "EXIT" and action == "sip":
                        # SIP profit booking - sell all holdings
                        transaction_type = "SELL"
                        quantity = item.get('quantity', 0)
                        order_type_desc = "SIP_PROFIT_BOOKING"
                        logger.info(f"Executing SIP profit booking (EXIT): Sell {quantity} units of {symbol}")
                        
                        # Mark for re-entry after successful order
                        exit_value = quantity * market_data.get('ltp', 0)
                        should_mark_reentry = True
                        exit_info = {
                            "exit_price": market_data.get('ltp', 0),
                            "exit_amount": exit_value,
                            "exit_quantity": quantity,
                            "exit_date": datetime.now(IST).date().isoformat()
                        }
                    
                    elif llm_result['decision'] == "SELL":
                        # Regular sell
                        transaction_type = "SELL"
                        quantity = item.get('quantity', 0)
                        order_type_desc = "SELL"
                        logger.info(f"Executing SELL: {quantity} units of {symbol}")
                    
                    elif llm_result['decision'] == "EXIT_AND_REENTER":
                        # Tax harvesting - sell and will re-buy
                        transaction_type = "SELL"
                        quantity = item.get('quantity', 0)
                        order_type_desc = "EXIT_AND_REENTER"
                        logger.info(f"Executing EXIT_AND_REENTER: Sell {quantity} units of {symbol}")
                    
                    elif llm_result['decision'] == "EXECUTE" and action == "sip":
                        # SIP execution - buy
                        transaction_type = "BUY"
                        
                        # Check if this is a re-entry after exit
                        is_reentry = item.get('awaiting_reentry', False)
                        if is_reentry:
                            # Use exit amount for re-entry
                            sip_amount = item.get('exit_amount', llm_result['sip_amount'])
                            order_type_desc = "SIP_REENTRY"
                            logger.info(f"Executing SIP RE-ENTRY: Using exit amount ₹{sip_amount:.2f} for {symbol}")
                        else:
                            # Regular SIP
                            sip_amount = llm_result['sip_amount']
                            order_type_desc = "SIP"
                            logger.info(f"Executing SIP: Buy {symbol} for ₹{sip_amount:.2f}")
                        
                        # Calculate quantity from amount
                        current_price = market_data.get('ltp', 0)
                        quantity = int(sip_amount / current_price) if current_price > 0 else 0
                    
                    elif llm_result['decision'] == "EXECUTE" and action == "buy":
                        # Buy execution
                        transaction_type = "BUY"
                        buy_amount = llm_result['sip_amount']  # Using same field
                        current_price = market_data.get('ltp', 0)
                        quantity = int(buy_amount / current_price) if current_price > 0 else 0
                        order_type_desc = "BUY"
                        logger.info(f"Executing BUY: {quantity} units of {symbol}")
                    
                    else:
                        transaction_type = None
                        quantity = 0
                        order_type_desc = "UNKNOWN"
                    
                    # Place order if valid
                    if transaction_type and quantity > 0:
                        # Get symbol token from item
                        symbol_token = item.get('symbol_token', '')
                        order_result = await execute_angel_one_order(symbol, transaction_type, quantity, symbol_token)
                        
                        # Log to executed_orders collection
                        executed_order = ExecutedOrder(
                            symbol=symbol,
                            order_type=order_type_desc,
                            transaction_type=transaction_type,
                            quantity=quantity,
                            price=market_data.get('ltp', 0),
                            total_value=quantity * market_data.get('ltp', 0),
                            order_id=order_result.get('order_id', 'N/A'),
                            status="SUCCESS" if order_result.get('success') else "FAILED",
                            notes=llm_result['reasoning'][:200]
                        )
                        await db.executed_orders.insert_one(executed_order.model_dump())
                        
                        # Update last_sip_date for SIP orders
                        if action == 'sip' and order_result.get('success'):
                            today_ist = datetime.now(IST).date().isoformat()
                            await db.watchlist.update_one(
                                {"id": item['id']},
                                {"$set": {"last_sip_date": today_ist}}
                            )
                            logger.info(f"Updated last_sip_date for {symbol} to {today_ist}")
                        
                        # Handle SIP exit re-entry marking
                        if (llm_result['decision'] == "EXIT" and action == "sip" and 
                            order_result.get('success') and 'should_mark_reentry' in locals() and 
                            should_mark_reentry):
                            
                            # Update watchlist item for re-entry
                            update_fields = {
                                "awaiting_reentry": True,
                                "exit_price": exit_info["exit_price"],
                                "exit_amount": exit_info["exit_amount"],
                                "exit_date": exit_info["exit_date"],
                                "exit_quantity": exit_info["exit_quantity"],
                                "quantity": 0,  # Reset quantity since we sold everything
                                "avg_price": 0  # Reset avg price
                            }
                            
                            await db.watchlist.update_one(
                                {"id": item['id']},
                                {"$set": update_fields}
                            )
                            
                            logger.info(f"✓ Marked {symbol} for re-entry: Exit amount ₹{exit_info['exit_amount']:.2f} at ₹{exit_info['exit_price']:.2f}")
                            logger.info(f"  → SIP will resume when price corrects and conditions are favorable")
                        
                        # Handle SIP re-entry completion
                        elif (llm_result['decision'] == "EXECUTE" and action == "sip" and 
                              order_result.get('success') and item.get('awaiting_reentry', False)):
                            
                            # Clear re-entry flags since we've successfully re-entered
                            clear_reentry_fields = {
                                "awaiting_reentry": False,
                                "exit_price": None,
                                "exit_amount": None,
                                "exit_date": None,
                                "exit_quantity": None
                            }
                            
                            await db.watchlist.update_one(
                                {"id": item['id']},
                                {"$set": clear_reentry_fields}
                            )
                            
                            logger.info(f"✓ Completed re-entry for {symbol}: Invested ₹{sip_amount:.2f}")
                            logger.info(f"  → Re-entry flags cleared, normal SIP cycle resumed")
                        
                        # Update analysis log with execution results
                        analysis_log.executed = order_result.get('success', False)
                        analysis_log.order_id = order_result.get('order_id')
                        
                        if order_result.get('success'):
                            analysis_log.execution_status = "EXECUTED"
                        else:
                            analysis_log.execution_status = "FAILED"
                            analysis_log.error = order_result.get('message', 'Order failed')
                        
                        logger.info(f"Order {'SUCCESS' if order_result.get('success') else 'FAILED'}: {symbol} - {order_result.get('message')}")
                    else:
                        logger.warning(f"Invalid order parameters: {symbol} - transaction_type={transaction_type}, quantity={quantity}")
                        analysis_log.execution_status = "FAILED"
                        analysis_log.error = f"Invalid order parameters: transaction_type={transaction_type}, quantity={quantity}"
                        
                except Exception as order_error:
                    error_msg = str(order_error)
                    logger.error(f"Order execution failed for {symbol}: {error_msg}")
                    analysis_log.execution_status = "FAILED"
                    analysis_log.error = error_msg
            
            # Save analysis log
            await db.analysis_logs.insert_one(analysis_log.model_dump())
            
            # Send notification
            if config.enable_notifications:
                if llm_result['decision'] == "EXIT" and action == "sip":
                    message = f"**{symbol}** - SIP PROFIT BOOKING 💰\nDecision: EXIT (Book Profit)\nAmount: ₹{llm_result['sip_amount']:.2f}\nReasoning: {llm_result['reasoning'][:200]}\n\n_Note: Will resume SIP in next cycle_"
                else:
                    message = f"**{symbol}** - {action.upper()}\nDecision: {llm_result['decision']}\nAmount: ₹{llm_result['sip_amount']:.2f}\nReasoning: {llm_result['reasoning'][:200]}"
                await send_telegram_notification(message, config)
        
        logger.info(f"Trading bot completed - Processed: {processed}, Skipped (hold): {skipped}")
        
    except Exception as e:
        logger.error(f"Trading bot error: {str(e)}")

@app.get("/api/logs")
async def get_logs(limit: int = 50):
    logs = await db.analysis_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs

@app.post("/api/run-bot")
async def trigger_bot(background_tasks: BackgroundTasks, manual: bool = False):
    """Trigger bot execution. If manual=True, bypasses market status check"""
    background_tasks.add_task(run_trading_bot, manual)
    return {"success": True, "message": "Bot triggered", "manual": manual}

@app.post("/api/send-notification")
async def send_test_notification(notification: TelegramNotification):
    config_doc = await db.bot_config.find_one({"_id": "main"})
    if not config_doc:
        raise HTTPException(status_code=400, detail="Configure Telegram settings first")
    
    config = BotConfig(**config_doc)
    await send_telegram_notification(notification.message, config)
    return {"success": True}

@app.post("/api/sync-portfolio")
async def sync_portfolio_to_watchlist():
    """Sync Angel One portfolio holdings to watchlist"""
    try:
        portfolio = await get_portfolio()
        synced = 0
        
        for holding in portfolio['holdings']:
            symbol = holding.get('tradingsymbol')
            token = holding.get('symboltoken', '')
            exchange = holding.get('exchange', 'NSE')
            quantity = int(holding.get('quantity', 0))
            avg_price = float(holding.get('averageprice', 0))
            
            # Check if already in watchlist
            existing = await db.watchlist.find_one({"symbol": symbol})
            
            if not existing:
                new_item = WatchlistItem(
                    symbol=symbol,
                    exchange=exchange,
                    symbol_token=token,
                    action="hold",
                    quantity=quantity,
                    avg_price=avg_price
                )
                await db.watchlist.insert_one(new_item.model_dump())
                synced += 1
            else:
                # Update quantity and avg price
                await db.watchlist.update_one(
                    {"symbol": symbol},
                    {"$set": {"quantity": quantity, "avg_price": avg_price}}
                )
                synced += 1
        
        return {"success": True, "synced": synced}
        
    except Exception as e:
        logger.error(f"Portfolio sync error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cleanup-duplicates")
async def cleanup_duplicate_watchlist():
    """Remove duplicate watchlist items, keeping the most recent one"""
    try:
        all_items = await db.watchlist.find({}).to_list(1000)
        
        # Group by symbol
        symbol_map = {}
        for item in all_items:
            symbol = item['symbol']
            if symbol not in symbol_map:
                symbol_map[symbol] = []
            symbol_map[symbol].append(item)
        
        # Remove duplicates - keep only the first one
        removed = 0
        for symbol, items in symbol_map.items():
            if len(items) > 1:
                # Sort by added_at to keep the oldest
                items.sort(key=lambda x: x.get('added_at', ''))
                # Remove all except first
                for item in items[1:]:
                    await db.watchlist.delete_one({"id": item['id']})
                    removed += 1
                    logger.info(f"Removed duplicate watchlist item: {symbol} (id: {item['id']})")
        
        return {"success": True, "removed": removed, "message": f"Removed {removed} duplicate items"}
        
    except Exception as e:
        logger.error(f"Cleanup duplicates error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/executed-orders")
async def get_executed_orders(limit: int = 50):
    orders = await db.executed_orders.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return orders

@app.get("/api/performance-summary")
async def get_performance_summary():
    """Get overall performance metrics"""
    try:
        portfolio = await get_portfolio()
        holdings = portfolio['holdings']
        
        total_investment = 0
        total_current_value = 0
        
        for holding in holdings:
            qty = int(holding.get('quantity', 0))
            avg_price = float(holding.get('averageprice', 0))
            ltp = float(holding.get('ltp', 0))
            total_investment += qty * avg_price
            total_current_value += qty * ltp
        
        total_pnl = total_current_value - total_investment
        total_pnl_pct = (total_pnl / total_investment * 100) if total_investment > 0 else 0
        
        # Get order statistics
        total_orders = await db.executed_orders.count_documents({})
        
        return {
            "total_investment": total_investment,
            "current_value": total_current_value,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "total_orders": total_orders,
            "holdings_count": len(holdings)
        }
    except Exception as e:
        logger.error(f"Performance summary error: {str(e)}")
        return {
            "total_investment": 0,
            "current_value": 0,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "total_orders": 0,
            "holdings_count": 0
        }

@app.get("/api/nse-index-options")
async def get_nse_index_options():
    """Get list of available NSE index names for proxy_index mapping - deprecated"""
    return {"indices": []}

@app.get("/api/llm-logs")
async def get_llm_logs(limit: int = 50):
    """Get LLM prompt logs"""
    logs = await db.llm_prompt_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs

@app.get("/api/angel-one-logs")
async def get_angel_one_logs(limit: int = 100):
    """Get Angel One API call logs"""
    logs = await db.angel_one_api_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs

@app.get("/api/market-state-logs")
async def get_market_state_logs(limit: int = 30):
    """Get market state logs (latest first)"""
    logs = await db.market_state_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs


@app.get("/api/eodhd-api-logs")
async def get_eodhd_api_logs(limit: int = 100):
    """Get EODHD API request/response logs (latest first)"""
    logs = await db.eodhd_api_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs


# Available LLM Models
@app.get("/api/llm-models")
async def get_available_models():
    """Get list of available LLM models"""
    return {
        "openai": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini", "gpt-5", "o1", "o1-mini"],
        "emergent": ["gpt-4o-mini", "gpt-4o", "gpt-5", "o1", "o1-mini"],
        "supports_custom": True
    }

@app.post("/api/test-llm")
async def test_llm_connection():
    """Test LLM connection with current config"""
    try:
        config_doc = await db.bot_config.find_one({"_id": "main"})
        if not config_doc:
            raise HTTPException(status_code=400, detail="Bot not configured")
        
        config = BotConfig(**config_doc)
        
        # Get API key
        if config.llm_provider == "openai" and config.openai_api_key:
            api_key = config.openai_api_key
            provider_name = "OpenAI"
        else:
            api_key = os.environ.get('EMERGENT_LLM_KEY')
            provider_name = "Emergent LLM"
        
        # Test connection
        chat = LlmChat(
            api_key=api_key,
            session_id="test_connection",
            system_message="You are a test assistant."
        )
        
        chat.with_model("openai", config.llm_model)
        
        message = UserMessage(text="Say 'Connection successful' in exactly those words.")
        response = await chat.send_message(message)
        
        return {
            "success": True,
            "provider": provider_name,
            "model": config.llm_model,
            "response": response
        }
        
    except Exception as e:
        logger.error(f"LLM test error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze-portfolio")
async def analyze_portfolio():
    """Get LLM analysis of entire portfolio"""
    try:
        # Get portfolio
        portfolio = await get_portfolio()
        holdings = portfolio['holdings']
        available_cash = portfolio['available_cash']
        
        if not holdings:
            raise HTTPException(status_code=400, detail="No holdings found in portfolio")
        
        # Get config for LLM settings
        config_doc = await db.bot_config.find_one({"_id": "main"})
        config = BotConfig(**config_doc) if config_doc else BotConfig()
        
        # Prepare portfolio summary
        total_investment = 0
        total_current_value = 0
        holdings_summary = []
        
        for holding in holdings:
            symbol = holding.get('tradingsymbol')
            qty = int(holding.get('quantity', 0))
            avg_price = float(holding.get('averageprice', 0))
            ltp = float(holding.get('ltp', 0))
            investment = qty * avg_price
            current_value = qty * ltp
            pnl = current_value - investment
            pnl_pct = (pnl / investment * 100) if investment > 0 else 0
            
            total_investment += investment
            total_current_value += current_value
            
            holdings_summary.append({
                "symbol": symbol,
                "quantity": qty,
                "avg_price": avg_price,
                "ltp": ltp,
                "investment": investment,
                "current_value": current_value,
                "pnl": pnl,
                "pnl_pct": pnl_pct
            })
        
        overall_pnl = total_current_value - total_investment
        overall_pnl_pct = (overall_pnl / total_investment * 100) if total_investment > 0 else 0
        
        # Create LLM prompt
        prompt = f"""
You are a portfolio analyst. Analyze this investment portfolio and provide actionable recommendations.

**PORTFOLIO SUMMARY**
Total Investment: ₹{total_investment:,.2f}
Current Value: ₹{total_current_value:,.2f}
Overall P&L: ₹{overall_pnl:,.2f} ({overall_pnl_pct:.2f}%)
Available Cash: ₹{available_cash:,.2f}

**HOLDINGS** ({len(holdings)} stocks):
"""
        
        for h in holdings_summary:
            prompt += f"""
- {h['symbol']}: Qty {h['quantity']} | Avg ₹{h['avg_price']:.2f} | LTP ₹{h['ltp']:.2f} | P&L: {h['pnl_pct']:.2f}%"""
        
        prompt += f"""

**USER'S ANALYSIS PARAMETERS**:
{config.analysis_parameters}

**PROVIDE ANALYSIS ON**:
1. **Portfolio Health**: Diversification, concentration risk, sector allocation
2. **Performance Review**: Best & worst performers, reasons
3. **Risk Assessment**: High-risk holdings, potential concerns
4. **Recommendations**: 
   - Which stocks to HOLD and continue SIP
   - Which stocks to consider SELLING (with reasons)
   - Which stocks to BUY MORE (averaging down/up)
   - Any rebalancing suggestions
5. **Cash Utilization**: How to deploy ₹{available_cash:,.2f} optimally

Be specific, actionable, and data-driven. Limit to 500 words.
"""
        
        # Get LLM analysis
        api_key = config.openai_api_key if config.llm_provider == "openai" and config.openai_api_key else os.environ.get('EMERGENT_LLM_KEY')
        
        session_id = f"portfolio_analysis_{uuid.uuid4().hex[:8]}"
        
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message="You are an expert portfolio analyst providing comprehensive investment analysis."
        )
        
        if config.llm_provider == "openai":
            chat.with_model("openai", config.llm_model)
        else:
            chat.with_model("openai", config.llm_model)
        
        user_message = UserMessage(text=prompt)
        llm_response = await chat.send_message(user_message)
        
        # Log the portfolio analysis LLM call
        try:
            log_entry = LLMPromptLog(
                symbol="PORTFOLIO",
                action_type="portfolio_analysis",
                full_prompt=prompt,
                llm_response=llm_response,
                model_used=config.llm_model,
                decision_made="ANALYSIS_COMPLETE"
            )
            await db.llm_prompt_logs.insert_one(log_entry.model_dump())
        except Exception as log_error:
            logger.error(f"Failed to log portfolio analysis prompt: {str(log_error)}")
        
        # Save analysis
        analysis = {
            "id": str(uuid.uuid4()),
            "timestamp": get_ist_timestamp(),
            "portfolio_summary": {
                "total_investment": total_investment,
                "current_value": total_current_value,
                "overall_pnl": overall_pnl,
                "overall_pnl_pct": overall_pnl_pct,
                "available_cash": available_cash,
                "holdings_count": len(holdings)
            },
            "holdings": holdings_summary,
            "llm_analysis": llm_response,
            "prompt": prompt
        }
        
        await db.portfolio_analyses.insert_one(analysis)
        
        return analysis
        
    except Exception as e:
        logger.error(f"Portfolio analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/portfolio-analyses")
async def get_portfolio_analyses(limit: int = 10):
    """Get recent portfolio analyses"""
    analyses = await db.portfolio_analyses.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return analyses

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
