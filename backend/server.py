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
class BotConfig(BaseModel):
    is_active: bool = False
    schedule_minutes: int = 30
    llm_provider: str = "emergent"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: Optional[str] = None
    telegram_chat_ids: List[str] = []
    telegram_bot_token: Optional[str] = None
    enable_notifications: bool = True
    auto_execute_trades: bool = False
    analysis_parameters: str = "Consider P/E ratio, volume trends, RSI indicators, support/resistance levels, and overall market sentiment."
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class WatchlistItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    exchange: str = "NSE"
    symbol_token: str
    action: str = "hold"  # sip, buy, sell, hold
    sip_amount: Optional[float] = None
    sip_frequency_days: Optional[int] = 30
    next_action_date: Optional[str] = None
    quantity: Optional[int] = None
    avg_price: Optional[float] = None
    notes: Optional[str] = ""
    added_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AnalysisLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    symbol: str
    action: str
    llm_decision: str
    market_data: Dict[str, Any]
    executed: bool = False
    order_id: Optional[str] = None
    error: Optional[str] = None

class TelegramNotification(BaseModel):
    message: str

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
            logger.info(f"✅ Angel One login successful")
            return True
        else:
            logger.error(f"❌ Angel One login failed: {response.get('message')}")
            return False
    except Exception as e:
        logger.error(f"❌ Angel One login exception: {str(e)}")
        return False

async def get_portfolio():
    """Get complete Angel One portfolio with funds"""
    try:
        if not smart_api or not auth_tokens:
            await angel_login()
        
        holdings_response = smart_api.holding()
        holdings = []
        if holdings_response and holdings_response.get('status'):
            holdings = holdings_response.get('data', [])
        
        positions_response = smart_api.position()
        positions = []
        if positions_response and positions_response.get('status'):
            positions = positions_response.get('data', [])
        
        # Get funds/balance
        funds_response = smart_api.rmsLimit()
        available_cash = 0
        if funds_response and funds_response.get('status'):
            funds_data = funds_response.get('data', {})
            available_cash = float(funds_data.get('availablecash', 0) or 0)
        
        return {
            "holdings": holdings,
            "positions": positions,
            "available_cash": available_cash,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching portfolio: {str(e)}")
        return {"holdings": [], "positions": [], "available_cash": 0, "error": str(e)}

async def get_market_data(symbol: str, token: str, exchange: str = "NSE") -> Dict[str, Any]:
    try:
        ltp_params = {
            "exchange": exchange,
            "tradingsymbol": symbol,
            "symboltoken": token
        }
        ltp_response = smart_api.ltpData(ltp_params)
        
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
        
        return {
            "symbol": symbol,
            "ltp": ltp_response.get('data', {}).get('ltp', 0) if ltp_response.get('status') else 0,
            "candles": candle_response.get('data', []) if candle_response.get('status') else [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching market data: {str(e)}")
        return {"symbol": symbol, "error": str(e)}

async def execute_order(symbol: str, token: str, exchange: str, transaction_type: str, quantity: int):
    """Execute buy or sell order"""
    try:
        if not smart_api or not auth_tokens:
            await angel_login()
        
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": transaction_type,
            "exchange": exchange,
            "ordertype": "MARKET",
            "producttype": "DELIVERY",
            "duration": "DAY",
            "quantity": str(quantity),
            "price": "0"
        }
        
        logger.info(f"📈 Placing {transaction_type} order for {symbol}, qty: {quantity}")
        order_response = smart_api.placeOrder(order_params)
        
        if order_response and isinstance(order_response, str):
            logger.info(f"✅ Order placed. Order ID: {order_response}")
            return {"success": True, "order_id": order_response}
        else:
            logger.error(f"❌ Order failed: {order_response}")
            return {"success": False, "error": str(order_response)}
    except Exception as e:
        logger.error(f"Exception placing order: {str(e)}")
        return {"success": False, "error": str(e)}

# ===== LLM DECISION MAKING =====
async def get_llm_trading_decision(item: Dict, market_data: Dict, config: BotConfig) -> Dict[str, Any]:
    """Ask LLM if we should execute the action NOW"""
    global current_session_id
    
    try:
        action = item['action']
        symbol = item['symbol']
        ltp = market_data.get('ltp', 0)
        candles = market_data.get('candles', [])
        
        # Build prompt
        prompt = f"""
You are an expert trading analyst. Analyze if we should execute a {action.upper()} action for {symbol} RIGHT NOW.

Current Price: ₹{ltp}
Recent 30-day candle data available: {len(candles)} days

User's Analysis Parameters:
{config.analysis_parameters}

Action to evaluate: {action.upper()}
"""
        
        if action == "sip":
            prompt += f"\nSIP Amount: ₹{item.get('sip_amount', 0)}\nSIP Frequency: Every {item.get('sip_frequency_days', 30)} days\n"
        elif action == "sell" and item.get('avg_price'):
            avg_price = item['avg_price']
            profit_loss = ((ltp - avg_price) / avg_price) * 100
            prompt += f"\nAverage Buy Price: ₹{avg_price}\nCurrent P&L: {profit_loss:.2f}%\n"
        
        prompt += """

Based on:
1. Current market conditions
2. Technical indicators from recent data
3. User's analysis parameters
4. Risk-reward ratio

Provide your decision:
- If you recommend executing the action NOW, respond with: EXECUTE
- If you recommend waiting, respond with: WAIT
- If conditions are unfavorable, respond with: SKIP

Then explain your reasoning in 2-3 sentences.
"""
        
        # Initialize LLM
        api_key = config.openai_api_key if config.llm_provider == "openai" and config.openai_api_key else os.environ.get('EMERGENT_LLM_KEY')
        
        if not current_session_id:
            current_session_id = f"trading_{uuid.uuid4().hex[:8]}"
        
        chat = LlmChat(
            api_key=api_key,
            session_id=current_session_id,
            system_message="You are an expert stock market analyst providing actionable trading decisions."
        )
        
        if config.llm_provider == "openai":
            chat.with_model("openai", config.llm_model)
        else:
            chat.with_model("openai", config.llm_model)
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        # Extract decision
        decision = "WAIT"
        if "EXECUTE" in response.upper():
            decision = "EXECUTE"
        elif "SKIP" in response.upper():
            decision = "SKIP"
        
        return {
            "decision": decision,
            "reasoning": response,
            "prompt": prompt
        }
        
    except Exception as e:
        logger.error(f"LLM decision error: {str(e)}")
        return {
            "decision": "SKIP",
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
                logger.info(f"✅ Notification sent")
            except Exception as e:
                logger.error(f"Failed to send notification: {str(e)}")
    except Exception as e:
        logger.error(f"Telegram error: {str(e)}")

# ===== BOT EXECUTION =====
async def run_trading_bot():
    """Main bot execution - checks watchlist and executes trades"""
    try:
        logger.info("🤖 Starting trading bot cycle...")
        
        # Get config
        config_doc = await db.bot_config.find_one({"_id": "main"})
        if not config_doc or not config_doc.get('is_active'):
            logger.info("Bot is inactive")
            return
        
        config = BotConfig(**config_doc)
        
        # Get watchlist items with actions
        watchlist = await db.watchlist.find({"action": {"$in": ["sip", "buy", "sell"]}}).to_list(100)
        
        if not watchlist:
            logger.info("No actionable items in watchlist")
            return
        
        # Login to Angel One
        if not auth_tokens:
            await angel_login()
        
        # Process each item
        for item in watchlist:
            symbol = item['symbol']
            token = item['symbol_token']
            exchange = item.get('exchange', 'NSE')
            action = item['action']
            
            logger.info(f"📊 Processing {symbol} - Action: {action}")
            
            # Check if action is due (for SIP)
            if action == "sip":
                next_date = item.get('next_action_date')
                if next_date and next_date > datetime.now().date().isoformat():
                    logger.info(f"⏰ SIP not due yet for {symbol}")
                    continue
            
            # Get market data
            market_data = await get_market_data(symbol, token, exchange)
            current_price = market_data.get('ltp', 0)
            
            if current_price == 0:
                logger.warning(f"⚠️ No price data for {symbol}")
                continue
            
            # Get LLM decision
            llm_result = await get_llm_trading_decision(item, market_data, config)
            
            # Log the analysis
            analysis_log = AnalysisLog(
                symbol=symbol,
                action=action,
                llm_decision=llm_result['decision'],
                market_data=market_data,
                executed=False
            )
            
            # Execute if LLM says yes and auto-execute is enabled
            if llm_result['decision'] == "EXECUTE" and config.auto_execute_trades:
                if action == "sip" or action == "buy":
                    # Calculate quantity
                    if action == "sip":
                        amount = item.get('sip_amount', 0)
                        quantity = int(amount / current_price) if amount > 0 else 0
                    else:
                        quantity = item.get('quantity', 1)
                    
                    if quantity > 0:
                        result = await execute_order(symbol, token, exchange, "BUY", quantity)
                        
                        if result['success']:
                            analysis_log.executed = True
                            analysis_log.order_id = result['order_id']
                            
                            # Update next SIP date
                            if action == "sip":
                                next_date = (datetime.now() + timedelta(days=item.get('sip_frequency_days', 30))).date().isoformat()
                                await db.watchlist.update_one(
                                    {"symbol": symbol},
                                    {"$set": {"next_action_date": next_date}}
                                )
                            
                            notification = f"""
🎯 *{action.upper()} Executed*

📈 Symbol: {symbol}
📊 Quantity: {quantity}
💰 Price: ₹{current_price}
💵 Value: ₹{quantity * current_price:.2f}
🆔 Order: {result['order_id']}

🤖 AI Reasoning:
{llm_result['reasoning'][:200]}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
                            await send_telegram_notification(notification, config)
                        else:
                            analysis_log.error = result.get('error')
                
                elif action == "sell":
                    quantity = item.get('quantity', 0)
                    if quantity > 0:
                        result = await execute_order(symbol, token, exchange, "SELL", quantity)
                        
                        if result['success']:
                            analysis_log.executed = True
                            analysis_log.order_id = result['order_id']
                            
                            avg_price = item.get('avg_price', 0)
                            profit_loss = (current_price - avg_price) * quantity if avg_price else 0
                            
                            notification = f"""
💸 *SELL Executed*

📉 Symbol: {symbol}
📊 Quantity: {quantity}
💰 Sell Price: ₹{current_price}
📈 Avg Buy: ₹{avg_price}
💵 P&L: ₹{profit_loss:.2f}
🆔 Order: {result['order_id']}

🤖 AI Reasoning:
{llm_result['reasoning'][:200]}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
                            await send_telegram_notification(notification, config)
                            
                            # Remove from watchlist after successful sell
                            await db.watchlist.delete_one({"symbol": symbol})
                            logger.info(f"✅ {symbol} removed from watchlist after sell")
                        else:
                            analysis_log.error = result.get('error')
            
            elif llm_result['decision'] == "EXECUTE" and not config.auto_execute_trades:
                logger.info(f"⚠️ Would execute {action} for {symbol} but auto-execute is disabled")
                notification = f"""
💡 *Trading Signal*

📈 Symbol: {symbol}
🎯 Action: {action.upper()}
💰 Price: ₹{current_price}

🤖 LLM Recommendation: EXECUTE
⚠️ Auto-execute is OFF

{llm_result['reasoning'][:200]}
"""
                await send_telegram_notification(notification, config)
            
            # Save log
            await db.analysis_logs.insert_one(analysis_log.model_dump())
            
            logger.info(f"✅ {symbol} processed - Decision: {llm_result['decision']}")
        
        logger.info("✅ Trading bot cycle completed")
        
    except Exception as e:
        logger.error(f"Bot execution error: {str(e)}")

def schedule_bot():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        config_doc = loop.run_until_complete(db.bot_config.find_one({"_id": "main"}))
        
        if config_doc and config_doc.get('is_active'):
            minutes = config_doc.get('schedule_minutes', 30)
            scheduler.remove_all_jobs()
            scheduler.add_job(
                run_trading_bot,
                trigger=IntervalTrigger(minutes=minutes),
                id='trading_bot',
                replace_existing=True
            )
            logger.info(f"⏰ Bot scheduled every {minutes} minutes")
        else:
            scheduler.remove_all_jobs()
    except:
        pass

# ===== API ENDPOINTS =====
@app.on_event("startup")
async def startup_event():
    scheduler.start()
    await angel_login()
    schedule_bot()
    logger.info("🚀 Trading Bot Started - Running on FastAPI with APScheduler")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    client.close()

@app.get("/api/")
async def root():
    return {"status": "operational", "app": "AI Trading Bot", "bot_location": "Running in FastAPI backend with APScheduler"}

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
        "scheduler_running": scheduler.running,
        "bot_location": "FastAPI Backend (APScheduler)"
    }

@app.get("/api/config")
async def get_config():
    config = await db.bot_config.find_one({"_id": "main"}, {"_id": 0})
    if not config:
        default_config = BotConfig().model_dump()
        await db.bot_config.insert_one({"_id": "main", **default_config})
        return default_config
    return config

@app.put("/api/config")
async def update_config(config: BotConfig, background_tasks: BackgroundTasks):
    config_dict = config.model_dump()
    config_dict['last_updated'] = datetime.now(timezone.utc).isoformat()
    await db.bot_config.update_one({"_id": "main"}, {"$set": config_dict}, upsert=True)
    background_tasks.add_task(schedule_bot)
    return {"success": True}

@app.get("/api/portfolio")
async def get_angel_portfolio():
    portfolio = await get_portfolio()
    return portfolio

@app.get("/api/watchlist")
async def get_watchlist():
    watchlist = await db.watchlist.find({}, {"_id": 0}).to_list(200)
    return watchlist

@app.post("/api/watchlist")
async def add_to_watchlist(item: WatchlistItem):
    existing = await db.watchlist.find_one({"symbol": item.symbol})
    if existing:
        raise HTTPException(status_code=400, detail="Symbol already exists")
    await db.watchlist.insert_one(item.model_dump())
    return {"success": True}

@app.put("/api/watchlist/{symbol}")
async def update_watchlist_item(symbol: str, updates: Dict[str, Any]):
    result = await db.watchlist.update_one({"symbol": symbol}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return {"success": True}

@app.delete("/api/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str):
    result = await db.watchlist.delete_one({"symbol": symbol})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return {"success": True}

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
