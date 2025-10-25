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
    last_updated: str = Field(default_factory=get_ist_timestamp)

class WatchlistItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    exchange: str = "NSE"
    symbol_token: str
    action: str = "hold"  # sip, buy, sell, hold
    sip_amount: Optional[float] = None
    sip_frequency_days: Optional[int] = 30
    next_action_date: Optional[str] = None
    re_entry_price: Optional[float] = None  # Target price for re-entry after exit
    quantity: Optional[int] = None
    avg_price: Optional[float] = None
    notes: Optional[str] = ""
    added_at: str = Field(default_factory=get_ist_timestamp)

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
    
    return {
        "angel_one_connected": smart_api is not None and auth_tokens is not None,
        "bot_running": scheduler.running,
        "bot_active": is_active and scheduler.running,  # Both config active and scheduler running
        "scheduled_jobs": len(scheduler.get_jobs())
    }

# ===== ANGEL ONE API =====
async def get_portfolio():
    if not smart_api or not auth_tokens:
        await authenticate_angel_one()
    
    if not smart_api:
        raise HTTPException(status_code=401, detail="Angel One not authenticated")
    
    start_time = datetime.now()
    try:
        holdings = smart_api.holding()
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        if holdings['status']:
            # Log successful portfolio fetch
            await log_angel_one_api_call(
                endpoint="/portfolio/holdings",
                method="GET",
                request_data=None,
                response_data={"status": "success", "holdings_count": len(holdings.get('data', []))},
                status_code=200,
                execution_time_ms=execution_time
            )
            
            return {
                "holdings": holdings['data'],
                "available_cash": 10000.0  # Placeholder
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
        
        logger.info(f"Order Response: {order_response}")
        logger.info(f"Execution Time: {execution_time:.2f}ms")
        
        # Check if response is valid
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

# ===== LLM DECISION LOGIC =====
async def get_llm_decision(symbol: str, action: str, market_data: Dict, config: BotConfig, item: Dict, portfolio: Dict = None) -> Dict:
    """Get LLM decision for a trading action"""
    try:
        # Get API key
        if config.llm_provider == "openai" and config.openai_api_key:
            api_key = config.openai_api_key
        else:
            api_key = os.environ.get('EMERGENT_LLM_KEY')
        
        # Build prompt based on action
        if action == "sip":
            sip_amount = item.get('sip_amount') or 0
            quantity = item.get('quantity', 0)
            avg_price = item.get('avg_price', 0)
            current_price = market_data.get('ltp', 0)
            
            # Calculate current position value and P&L
            investment = quantity * avg_price if quantity and avg_price else 0
            current_value = quantity * current_price if quantity and current_price else 0
            pnl = current_value - investment if investment > 0 else 0
            pnl_pct = (pnl / investment * 100) if investment > 0 else 0
            
            # Get available balance from portfolio
            available_balance = portfolio.get('available_cash', 0) if portfolio else 0
            
            # STEP 1: Check if should EXIT (profit booking) - Only if position exists
            should_exit = False
            exit_reasoning = ""
            
            if quantity > 0 and current_price > 0:
                exit_check_prompt = f"""
You are a stock market analyst analyzing if this SIP position has reached its PEAK and should be EXITED for profit booking.

**STOCK**: {symbol}
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

**STOCK**: {symbol}
**CURRENT PRICE**: ₹{current_price:.2f}

**YOUR CURRENT POSITION**:
- Quantity Held: {quantity}
- Average Price: ₹{avg_price:.2f}
- Price vs Avg: {((price_ratio - 1) * 100):+.1f}% (Current is {price_ratio:.2f}x of avg)
- Investment: ₹{investment:.2f}
- Current Value: ₹{current_value:.2f}
- P&L: ₹{pnl:.2f} ({pnl_pct:+.2f}%)

**AVAILABLE BALANCE**: ₹{available_balance:.2f}
**BASE SIP AMOUNT**: ₹{sip_amount:.2f} (user's reference amount)

**USER'S ANALYSIS PARAMETERS**:
{config.analysis_parameters}

**YOUR TASK**: Decide SIP amount with SMART DYNAMIC ADJUSTMENT based on price levels and indicators.

**CRITICAL: DYNAMIC AMOUNT LOGIC** (Apply this strictly):

1. **Price SIGNIFICANTLY BELOW Average** (price 0.7x-0.9x of avg):
   - Excellent buying opportunity
   - Suggest 1.5x-2x base amount
   - Example: Base ₹5000 → Suggest ₹7500-10000

2. **Price MODERATELY BELOW Average** (price 0.9x-0.95x of avg):
   - Good accumulation zone
   - Suggest 1.2x-1.4x base amount
   - Example: Base ₹5000 → Suggest ₹6000-7000

3. **Price NEAR Average** (price 0.95x-1.05x of avg):
   - Neutral zone
   - Suggest 0.8x-1.2x base amount
   - Example: Base ₹5000 → Suggest ₹4000-6000

4. **Price MODERATELY ABOVE Average** (price 1.05x-1.2x of avg):
   - Reduce investment, manage risk
   - Suggest 0.5x-0.8x base amount
   - Example: Base ₹5000 → Suggest ₹2500-4000

5. **Price SIGNIFICANTLY ABOVE Average** (price >1.2x of avg):
   - High risk zone, minimal investment
   - Suggest 0.3x-0.5x base amount
   - Example: Base ₹5000 → Suggest ₹1500-2500

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
- Price ₹85, Avg ₹100 (0.85x): "SIP_ACTION: EXECUTE\\nAMOUNT: 9000\\nREASONING: Price 15% below avg at ₹85 vs ₹100. RSI at 35 shows oversold. Increased to 1.8x (₹9000) to accumulate aggressively."

- Price ₹105, Avg ₹100 (1.05x): "SIP_ACTION: EXECUTE\\nAMOUNT: 4500\\nREASONING: Price 5% above avg. Momentum positive but reducing to 0.9x (₹4500) to manage valuation risk."

- Price ₹130, Avg ₹100 (1.3x): "SIP_ACTION: EXECUTE\\nAMOUNT: 2000\\nREASONING: Price 30% above avg showing extended valuations. RSI 68. Minimal investment at 0.4x (₹2000) to maintain discipline."

- Price ₹95, Avg ₹100 (0.95x), RSI 75: "SIP_ACTION: SKIP\\nREASONING: Though price near avg, RSI 75 overbought. Market overheated. Skip this cycle."

**REMEMBER**: Your amount suggestion should clearly reflect the price level dynamics!
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
            current_value = item.get('quantity', 0) * market_data.get('ltp', 0)
            investment = item.get('quantity', 0) * item.get('avg_price', 0)
            pnl = current_value - investment
            pnl_pct = (pnl / investment * 100) if investment > 0 else 0
            
            prompt = f"""
You are a stock market analyst. Analyze whether to sell this holding.

**STOCK**: {symbol}
**QUANTITY**: {item.get('quantity', 0)}
**AVG PRICE**: ₹{item.get('avg_price', 0):.2f}
**CURRENT PRICE**: ₹{market_data.get('ltp', 0):.2f}
**INVESTMENT**: ₹{investment:.2f}
**CURRENT VALUE**: ₹{current_value:.2f}
**P&L**: ₹{pnl:.2f} ({pnl_pct:.2f}%)

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
"""
        elif action == "buy":
            prompt = f"""
You are a stock market analyst. Analyze this stock for BUY action.

**STOCK**: {symbol}
**CURRENT PRICE**: ₹{market_data.get('ltp', 0):.2f}

**PORTFOLIO CONTEXT**:
- Current Quantity: {item.get('quantity', 0)}
- Avg Price: ₹{item.get('avg_price', 0) or 0:.2f}

**USER'S ANALYSIS PARAMETERS**:
{config.analysis_parameters}

**YOUR TASK**: Decide whether to buy this stock based on current market conditions and your analysis.

**RESPONSE FORMAT**:
BUY_ACTION: EXECUTE or SKIP
AMOUNT: <suggested investment amount in rupees>
REASONING: <brief 2-3 line explanation>

Provide your recommendation based on fundamentals and technical analysis.
"""
        else:
            # For other actions
            prompt = f"""
You are a stock market analyst. Analyze this stock for {action.upper()} action.

**STOCK**: {symbol}
**CURRENT PRICE**: ₹{market_data.get('ltp', 0):.2f}
**PORTFOLIO CONTEXT**: Quantity: {item.get('quantity', 0)}, Avg Price: ₹{item.get('avg_price', 0) or 0:.2f}

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
async def run_trading_bot():
    logger.info("Trading bot started")
    
    try:
        # Get config
        config_doc = await db.bot_config.find_one({"_id": "main"})
        if not config_doc:
            logger.error("No bot config found")
            return
        
        config = BotConfig(**config_doc)
        
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
            else:
                # Use item's avg_price as placeholder if not in portfolio
                market_data = {
                    "ltp": item.get('avg_price', 100),
                    "volume": 0,
                    "change_pct": 0
                }
            
            # Get LLM decision
            llm_result = await get_llm_decision(symbol, action, market_data, config, item, portfolio)
            
            # Log analysis
            analysis_log = AnalysisLog(
                symbol=symbol,
                action=action,
                llm_decision=llm_result['decision'],
                market_data=market_data,
                executed=False,  # Will update to True if order placed
                order_id=None
            )
            
            # Execute trades if auto_execute is enabled
            order_result = None
            if config.auto_execute_trades and llm_result['decision'] in ["EXECUTE", "SELL", "EXIT_AND_REENTER", "EXIT"]:
                try:
                    # Determine transaction type and quantity
                    if llm_result['decision'] == "EXIT" and action == "sip":
                        # SIP profit booking - sell all holdings
                        transaction_type = "SELL"
                        quantity = item.get('quantity', 0)
                        order_type_desc = "SIP_PROFIT_BOOKING"
                        logger.info(f"Executing SIP profit booking (EXIT): Sell {quantity} units of {symbol}")
                    
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
                        # Calculate quantity from amount
                        sip_amount = llm_result['sip_amount']
                        current_price = market_data.get('ltp', 0)
                        quantity = int(sip_amount / current_price) if current_price > 0 else 0
                        order_type_desc = "SIP"
                        logger.info(f"Executing SIP: Buy {quantity} units of {symbol} for ₹{sip_amount:.2f}")
                    
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
                        
                        # Update analysis log
                        analysis_log.executed = order_result.get('success', False)
                        analysis_log.order_id = order_result.get('order_id')
                        if not order_result.get('success'):
                            analysis_log.error = order_result.get('message', 'Order failed')
                        
                        logger.info(f"Order {'SUCCESS' if order_result.get('success') else 'FAILED'}: {symbol} - {order_result.get('message')}")
                    else:
                        logger.warning(f"Invalid order parameters: {symbol} - transaction_type={transaction_type}, quantity={quantity}")
                        
                except Exception as order_error:
                    error_msg = str(order_error)
                    logger.error(f"Order execution failed for {symbol}: {error_msg}")
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
async def trigger_bot(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_trading_bot)
    return {"success": True, "message": "Bot triggered"}

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
