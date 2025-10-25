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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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
class SIPConfig(BaseModel):
    enabled: bool = False
    amount: float = 0
    frequency_days: int = 30  # How often to invest (e.g., 30 days = monthly)
    next_sip_date: Optional[str] = None

class SellStrategy(BaseModel):
    enabled: bool = False
    stop_loss_percent: float = 5.0
    target_profit_percent: float = 15.0
    trailing_stop_percent: float = 0.0
    use_llm_signals: bool = True

class BotConfig(BaseModel):
    is_active: bool = False
    schedule_minutes: int = 30
    llm_provider: str = "emergent"  # emergent or openai
    llm_model: str = "gpt-4o-mini"
    openai_api_key: Optional[str] = None
    telegram_chat_ids: List[str] = []
    telegram_bot_token: Optional[str] = None
    enable_notifications: bool = True
    auto_execute_trades: bool = False  # Safety: require manual approval by default
    analysis_params: Dict[str, Any] = {
        "pe_ratio_threshold": 25,
        "volume_spike_percentage": 50,
        "rsi_overbought": 70,
        "rsi_oversold": 30,
        "enable_technical_analysis": True,
        "enable_fundamental_analysis": True
    }
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class Watchlist(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    exchange: str = "NSE"
    symbol_token: Optional[str] = None
    asset_type: str = "stock"  # stock or etf
    sip_config: SIPConfig = Field(default_factory=SIPConfig)
    sell_strategy: SellStrategy = Field(default_factory=SellStrategy)
    added_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AnalysisLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    symbol: str
    prompt: str
    llm_response: str
    analysis_summary: str
    market_data: Dict[str, Any]
    signal: Optional[str] = None
    status: str = "success"
    error: Optional[str] = None

class TelegramConfig(BaseModel):
    bot_token: str
    chat_ids: List[str]

# ===== ANGEL ONE AUTH =====
def generate_totp() -> str:
    totp = pyotp.TOTP(os.environ['ANGEL_TOTP_SECRET'])
    return totp.now()

async def angel_login():
    global smart_api, auth_tokens
    try:
        smart_api = SmartConnect(api_key=os.environ['ANGEL_TRADING_API_KEY'])
        totp_code = generate_totp()
        
        response = smart_api.generateSession(
            clientCode=os.environ['ANGEL_CLIENT_ID'],
            password=os.environ['ANGEL_PASSWORD'],
            totp=totp_code
        )
        
        if response.get('status'):
            auth_tokens = response['data']
            logger.info(f"✅ Angel One login successful for {auth_tokens.get('clientcode')}")
            return True
        else:
            logger.error(f"❌ Angel One login failed: {response.get('message')}")
            return False
    except Exception as e:
        logger.error(f"❌ Angel One login exception: {str(e)}")
        return False

async def get_market_data(symbol: str, token: str, exchange: str = "NSE") -> Dict[str, Any]:
    try:
        # Get last traded price
        ltp_params = {
            "exchange": exchange,
            "tradingsymbol": symbol,
            "symboltoken": token
        }
        ltp_response = smart_api.ltpData(ltp_params)
        
        # Get historical data (last 30 days)
        to_date = datetime.now()
        from_date = to_date - timedelta(days=30)
        
        candle_params = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": "ONE_DAY",
            "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
            "todate": to_date.strftime("%Y-%m-%d %H:%M")
        }
        candle_response = smart_api.getCandleData(candle_params)
        
        market_data = {
            "symbol": symbol,
            "ltp": ltp_response.get('data', {}).get('ltp', 0) if ltp_response.get('status') else 0,
            "candles": candle_response.get('data', []) if candle_response.get('status') else [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return market_data
    except Exception as e:
        logger.error(f"Error fetching market data for {symbol}: {str(e)}")
        return {"symbol": symbol, "error": str(e)}

# ===== PORTFOLIO FUNCTIONS =====
async def get_portfolio():
    """Get complete Angel One portfolio"""
    try:
        if not smart_api or not auth_tokens:
            await angel_login()
        
        # Get holdings
        holdings_response = smart_api.holding()
        holdings = []
        if holdings_response and holdings_response.get('status'):
            holdings = holdings_response.get('data', [])
        
        # Get positions
        positions_response = smart_api.position()
        positions = []
        if positions_response and positions_response.get('status'):
            positions = positions_response.get('data', [])
        
        return {
            "holdings": holdings,
            "positions": positions,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching portfolio: {str(e)}")
        return {"holdings": [], "positions": [], "error": str(e)}

# ===== TRADE EXECUTION =====
async def execute_buy_order(symbol: str, token: str, exchange: str, quantity: int, order_type: str = "MARKET"):
    """Execute a buy order"""
    try:
        if not smart_api or not auth_tokens:
            await angel_login()
        
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": "BUY",
            "exchange": exchange,
            "ordertype": order_type,
            "producttype": "DELIVERY",
            "duration": "DAY",
            "quantity": str(quantity),
            "price": "0"
        }
        
        logger.info(f"📈 Placing BUY order for {symbol}, qty: {quantity}")
        order_response = smart_api.placeOrder(order_params)
        
        if order_response and isinstance(order_response, str):
            logger.info(f"✅ Buy order placed. Order ID: {order_response}")
            return {"success": True, "order_id": order_response}
        else:
            logger.error(f"❌ Buy order failed: {order_response}")
            return {"success": False, "error": str(order_response)}
    except Exception as e:
        logger.error(f"Exception placing buy order: {str(e)}")
        return {"success": False, "error": str(e)}

async def execute_sell_order(symbol: str, token: str, exchange: str, quantity: int, order_type: str = "MARKET"):
    """Execute a sell order"""
    try:
        if not smart_api or not auth_tokens:
            await angel_login()
        
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": "SELL",
            "exchange": exchange,
            "ordertype": order_type,
            "producttype": "DELIVERY",
            "duration": "DAY",
            "quantity": str(quantity),
            "price": "0"
        }
        
        logger.info(f"📉 Placing SELL order for {symbol}, qty: {quantity}")
        order_response = smart_api.placeOrder(order_params)
        
        if order_response and isinstance(order_response, str):
            logger.info(f"✅ Sell order placed. Order ID: {order_response}")
            return {"success": True, "order_id": order_response}
        else:
            logger.error(f"❌ Sell order failed: {order_response}")
            return {"success": False, "error": str(order_response)}
    except Exception as e:
        logger.error(f"Exception placing sell order: {str(e)}")
        return {"success": False, "error": str(e)}

# ===== LLM ANALYSIS =====
async def analyze_with_llm(market_data: Dict[str, Any], config: BotConfig) -> Dict[str, Any]:
    global current_session_id
    
    try:
        # Prepare analysis prompt
        params = config.analysis_params
        candles = market_data.get('candles', [])
        ltp = market_data.get('ltp', 0)
        
        # Calculate basic technical indicators
        analysis_context = f"""
You are an expert stock market analyst. Analyze the following stock data and provide actionable insights:

Stock: {market_data['symbol']}
Current Price: ₹{ltp}
Recent Price History: {len(candles)} days of data available

Analysis Parameters:
- P/E Ratio Threshold: {params.get('pe_ratio_threshold', 25)}
- Volume Spike Threshold: {params.get('volume_spike_percentage', 50)}%
- RSI Overbought: {params.get('rsi_overbought', 70)}
- RSI Oversold: {params.get('rsi_oversold', 30)}

Recent Candle Data (last 5 days):
{candles[-5:] if len(candles) >= 5 else candles}

Provide:
1. Technical Analysis Summary
2. Price Trend Analysis
3. Trading Signal (BUY/SELL/HOLD)
4. Key Support and Resistance Levels
5. Risk Assessment

Be concise and actionable.
"""
        
        # Initialize LLM
        if config.llm_provider == "openai" and config.openai_api_key:
            api_key = config.openai_api_key
        else:
            api_key = os.environ.get('EMERGENT_LLM_KEY')
        
        if not current_session_id:
            current_session_id = f"trading_bot_{uuid.uuid4().hex[:8]}"
        
        chat = LlmChat(
            api_key=api_key,
            session_id=current_session_id,
            system_message="You are an expert stock market analyst providing actionable trading insights."
        )
        
        if config.llm_provider == "openai":
            chat.with_model("openai", config.llm_model)
        else:
            chat.with_model("openai", config.llm_model)
        
        # Send message
        user_message = UserMessage(text=analysis_context)
        response = await chat.send_message(user_message)
        
        # Extract signal from response
        signal = "HOLD"
        if "BUY" in response.upper():
            signal = "BUY"
        elif "SELL" in response.upper():
            signal = "SELL"
        
        return {
            "prompt": analysis_context,
            "llm_response": response,
            "signal": signal,
            "summary": response[:200] + "..." if len(response) > 200 else response
        }
        
    except Exception as e:
        logger.error(f"LLM analysis error: {str(e)}")
        return {
            "prompt": "Error occurred",
            "llm_response": f"Error: {str(e)}",
            "signal": None,
            "summary": f"Analysis failed: {str(e)}"
        }

# ===== TELEGRAM NOTIFICATIONS =====
async def send_telegram_notification(message: str, config: BotConfig):
    if not config.enable_notifications or not config.telegram_bot_token:
        return
    
    try:
        from telegram import Bot
        bot = Bot(token=config.telegram_bot_token)
        
        for chat_id in config.telegram_chat_ids:
            try:
                await bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
                logger.info(f"✅ Notification sent to {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send to {chat_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Telegram notification error: {str(e)}")

# ===== BOT EXECUTION =====
async def run_bot_analysis():
    try:
        logger.info("🤖 Starting bot analysis cycle...")
        
        # Get config
        config_doc = await db.bot_config.find_one({"_id": "main"})
        if not config_doc or not config_doc.get('is_active'):
            logger.info("Bot is inactive. Skipping analysis.")
            return
        
        config = BotConfig(**config_doc)
        
        # Get watchlist
        watchlist = await db.watchlist.find().to_list(100)
        if not watchlist:
            logger.info("No symbols in watchlist")
            return
        
        # Login to Angel One if needed
        if not auth_tokens:
            await angel_login()
        
        # Analyze each symbol
        for item in watchlist:
            symbol = item['symbol']
            token = item.get('symbol_token', '')
            exchange = item.get('exchange', 'NSE')
            
            logger.info(f"📊 Analyzing {symbol}...")
            
            # Get market data
            market_data = await get_market_data(symbol, token, exchange)
            
            # Analyze with LLM
            llm_result = await analyze_with_llm(market_data, config)
            
            # Save log
            log = AnalysisLog(
                symbol=symbol,
                prompt=llm_result['prompt'],
                llm_response=llm_result['llm_response'],
                analysis_summary=llm_result['summary'],
                market_data=market_data,
                signal=llm_result['signal']
            )
            
            await db.analysis_logs.insert_one(log.model_dump())
            
            # Send notification if signal found
            if llm_result['signal'] in ['BUY', 'SELL']:
                notification = f"""
🚨 *Trading Signal Alert*

📈 Symbol: {symbol}
💡 Signal: *{llm_result['signal']}*
💰 Price: ₹{market_data.get('ltp', 0)}

📝 Analysis:
{llm_result['summary']}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
                await send_telegram_notification(notification, config)
            
            logger.info(f"✅ {symbol} analysis complete. Signal: {llm_result['signal']}")
        
        logger.info("✅ Bot analysis cycle completed")
        
    except Exception as e:
        logger.error(f"Bot execution error: {str(e)}")

# ===== SCHEDULER MANAGEMENT =====
def schedule_bot():
    config_doc = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        config_doc = loop.run_until_complete(db.bot_config.find_one({"_id": "main"}))
    except:
        pass
    
    if config_doc and config_doc.get('is_active'):
        minutes = config_doc.get('schedule_minutes', 30)
        
        # Remove existing jobs
        scheduler.remove_all_jobs()
        
        # Add new job
        scheduler.add_job(
            run_bot_analysis,
            trigger=IntervalTrigger(minutes=minutes),
            id='bot_analysis',
            replace_existing=True
        )
        logger.info(f"⏰ Bot scheduled to run every {minutes} minutes")
    else:
        scheduler.remove_all_jobs()
        logger.info("⏸️  Bot scheduling disabled")

# ===== API ENDPOINTS =====
@app.on_event("startup")
async def startup_event():
    scheduler.start()
    await angel_login()
    schedule_bot()
    logger.info("🚀 AI Trading Bot started")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    client.close()

@app.get("/api/")
async def root():
    return {"status": "operational", "app": "AI Trading Bot"}

@app.get("/api/status")
async def get_status():
    config = await db.bot_config.find_one({"_id": "main"})
    watchlist_count = await db.watchlist.count_documents({})
    logs_count = await db.analysis_logs.count_documents({})
    
    return {
        "bot_active": config.get('is_active', False) if config else False,
        "angel_one_connected": auth_tokens is not None,
        "watchlist_symbols": watchlist_count,
        "total_analyses": logs_count,
        "scheduler_running": scheduler.running
    }

# Bot Config
@app.get("/api/config")
async def get_config():
    config = await db.bot_config.find_one({"_id": "main"}, {"_id": 0})
    if not config:
        # Create default config
        default_config = BotConfig().model_dump()
        await db.bot_config.insert_one({"_id": "main", **default_config})
        return default_config
    return config

@app.put("/api/config")
async def update_config(config: BotConfig, background_tasks: BackgroundTasks):
    config_dict = config.model_dump()
    config_dict['last_updated'] = datetime.now(timezone.utc).isoformat()
    
    await db.bot_config.update_one(
        {"_id": "main"},
        {"$set": config_dict},
        upsert=True
    )
    
    # Reschedule bot
    background_tasks.add_task(schedule_bot)
    
    return {"success": True, "message": "Configuration updated"}

# Watchlist
@app.get("/api/watchlist")
async def get_watchlist():
    watchlist = await db.watchlist.find({}, {"_id": 0}).to_list(100)
    return watchlist

@app.post("/api/watchlist")
async def add_to_watchlist(item: Watchlist):
    # Check if already exists
    existing = await db.watchlist.find_one({"symbol": item.symbol})
    if existing:
        raise HTTPException(status_code=400, detail="Symbol already in watchlist")
    
    await db.watchlist.insert_one(item.model_dump())
    return {"success": True, "message": f"{item.symbol} added to watchlist"}

@app.delete("/api/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str):
    result = await db.watchlist.delete_one({"symbol": symbol})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return {"success": True, "message": f"{symbol} removed from watchlist"}

# Analysis Logs
@app.get("/api/logs")
async def get_logs(limit: int = 50, symbol: Optional[str] = None):
    query = {"symbol": symbol} if symbol else {}
    logs = await db.analysis_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return logs

@app.delete("/api/logs")
async def clear_logs():
    result = await db.analysis_logs.delete_many({})
    return {"success": True, "deleted_count": result.deleted_count}

# Manual trigger
@app.post("/api/run-analysis")
async def trigger_analysis(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_bot_analysis)
    return {"success": True, "message": "Analysis triggered"}

# Test Telegram
@app.post("/api/test-telegram")
async def test_telegram(telegram_config: TelegramConfig):
    try:
        from telegram import Bot
        bot = Bot(token=telegram_config.bot_token)
        
        for chat_id in telegram_config.chat_ids:
            await bot.send_message(
                chat_id=chat_id,
                text="🤖 *Test Notification*\n\nYour AI Trading Bot is configured correctly!",
                parse_mode='Markdown'
            )
        
        return {"success": True, "message": "Test notification sent"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
