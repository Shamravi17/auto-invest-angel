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
    enable_tax_harvesting: bool = False
    tax_harvesting_loss_slab: float = 50000.0
    auto_sell_threshold_percent: float = 10.0
    minimum_gain_threshold_percent: float = 5.0
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
    re_entry_price: Optional[float] = None  # Target price for re-entry after exit
    quantity: Optional[int] = None
    avg_price: Optional[float] = None
    notes: Optional[str] = ""
    added_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ExecutedOrder(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    symbol: str
    order_type: str  # SIP, BUY, SELL, EXIT_AND_REENTER
    transaction_type: str  # BUY or SELL
    quantity: int
    price: float
    total_value: float
    order_id: str
    llm_decision: str
    llm_reasoning: str
    profit_loss: Optional[float] = None
    profit_loss_pct: Optional[float] = None

class LLMPromptLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    symbol: str
    action_type: str
    full_prompt: str
    llm_response: str
    model_used: str
    decision_made: str

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
        
        # Try MPIN login first (new method)
        try:
            response = smart_api.generateSession(
                clientCode=os.environ['ANGEL_CLIENT_ID'],
                password=os.environ['ANGEL_MPIN'],
                totp=totp_code
            )
        except:
            # Fallback to password login
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

async def calculate_profit_loss_after_charges(buy_price: float, sell_price: float, quantity: int) -> Dict[str, float]:
    """Calculate net P&L after all charges"""
    buy_value = buy_price * quantity
    sell_value = sell_price * quantity
    
    # Charges
    buy_brokerage = buy_value * 0.0003  # 0.03%
    sell_brokerage = sell_value * 0.0003
    stt = sell_value * 0.001  # 0.1% on sell
    gst = (buy_brokerage + sell_brokerage) * 0.18
    
    total_charges = buy_brokerage + sell_brokerage + stt + gst
    gross_pnl = sell_value - buy_value
    net_pnl = gross_pnl - total_charges
    net_pnl_pct = (net_pnl / buy_value) * 100 if buy_value > 0 else 0
    
    return {
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "net_pnl_pct": net_pnl_pct,
        "total_charges": total_charges
    }

# ===== LLM DECISION MAKING =====
async def get_llm_trading_decision(item: Dict, market_data: Dict, config: BotConfig, portfolio_info: Dict) -> Dict[str, Any]:
    """Enhanced LLM decision with EXIT_AND_REENTER logic"""
    global current_session_id
    
    try:
        action = item['action']
        symbol = item['symbol']
        ltp = market_data.get('ltp', 0)
        candles = market_data.get('candles', [])
        available_cash = portfolio_info.get('available_cash', 0)
        
        # Check if we already hold this position
        holding = next((h for h in portfolio_info.get('holdings', []) if h.get('tradingsymbol') == symbol), None)
        
        # Build comprehensive prompt
        prompt = f"""
You are an expert trading analyst making real-time trading decisions with TAX OPTIMIZATION awareness.

**SYMBOL**: {symbol}
**CURRENT PRICE**: ₹{ltp}
**ACTION TO EVALUATE**: {action.upper()}
**AVAILABLE CASH**: ₹{available_cash:,.2f}

**MARKET DATA**:
- Recent 30-day candle data: {len(candles)} days
- Latest close prices: {[c[4] for c in candles[-5:]] if candles else 'N/A'}
- Recent volume: {[c[5] for c in candles[-5:]] if candles else 'N/A'}
"""
        
        if holding:
            qty = int(holding.get('quantity', 0))
            avg_price = float(holding.get('averageprice', 0))
            current_value = ltp * qty
            invested = avg_price * qty
            unrealized_pnl = current_value - invested
            unrealized_pnl_pct = (unrealized_pnl / invested * 100) if invested > 0 else 0
            
            prompt += f"""

**CURRENT HOLDING**:
- Quantity: {qty} shares
- Average price: ₹{avg_price:.2f}
- Invested: ₹{invested:,.2f}
- Current value: ₹{current_value:,.2f}
- Unrealized P&L: ₹{unrealized_pnl:,.2f} ({unrealized_pnl_pct:+.2f}%)
"""
        
        prompt += f"""

**USER'S ANALYSIS PARAMETERS**:
{config.analysis_parameters}

**AUTO SELL THRESHOLD**: {config.auto_sell_threshold_percent}% (if loss exceeds this, consider selling)
"""
        
        # Tax harvesting section - only if toggle is enabled
        if config.enable_tax_harvesting and holding:
            unrealized_loss = (ltp - avg_price) * qty if holding else 0
            prompt += f"""

**TAX HARVESTING ENABLED**:
- Current unrealized loss: ₹{unrealized_loss:,.2f}
- Tax harvesting loss slab: ₹{config.tax_harvesting_loss_slab:,.2f}
- Question: Should we do TAX HARVESTING now?
  * Sell at loss to book tax benefit
  * Re-buy immediately to maintain position
  * Only if loss is significant (>= ₹{config.tax_harvesting_loss_slab})

**IMPORTANT**: If recommending tax harvesting, respond with:
TAX_HARVESTING: YES
And I will execute SELL + immediate RE-BUY.
"""
        else:
            prompt += "\n**TAX HARVESTING**: DISABLED (not considering tax loss harvesting)\n"
        
        if action == "sip":
            suggested_sip = item.get('sip_amount', 0)
            frequency = item.get('sip_frequency_days', 30)
            
            prompt += f"""

**SIP CONFIGURATION**:
- User suggested amount: ₹{suggested_sip}
- Frequency: Every {frequency} days
- This is SYSTEMATIC INVESTMENT - regular periodic investing

**YOUR TASK - ENHANCED SIP LOGIC**:
Determine if we should:
1. **EXECUTE** - Invest now (regular SIP)
2. **SKIP** - Wait for better conditions
3. **EXIT_AND_REENTER** - Stock is overvalued, sell current holding and re-enter at lower price

**EXIT_AND_REENTER Decision Criteria**:
- Current holding exists and is significantly overvalued (e.g., RSI > 75, P/E too high)
- Potential to re-enter at 5-10% lower price within next 30 days
- Tax implications are favorable (or tax harvesting enabled)
- After accounting for:
  * Brokerage charges: 0.03% on buy, 0.03% on sell
  * STT (Securities Transaction Tax): 0.1% on sell
  * GST on brokerage: 18%
  * Capital gains tax (if applicable)
- Net benefit should exceed {config.minimum_gain_threshold_percent}% threshold

**RESPOND WITH**:
Line 1: SIP_ACTION: [EXECUTE | SKIP | EXIT_AND_REENTER]
Line 2: AMOUNT: <amount in rupees to invest if EXECUTE>
Line 3: RE_ENTRY_PRICE: <target price for re-entry if EXIT_AND_REENTER>
Line 4: TAX_HARVESTING: [YES | NO] - recommend tax harvesting?
Lines 5+: Brief reasoning (why this decision, calculations if applicable)

**Example Response for EXIT_AND_REENTER**:
"SIP_ACTION: EXIT_AND_REENTER
AMOUNT: 0
RE_ENTRY_PRICE: 62
TAX_HARVESTING: YES
Stock overbought (RSI 78, P/E 45 vs industry 30). Current gain 8.5%. After taxes (1% STCG) and charges (0.2%), net gain ~7.3%. Exceeds 5% threshold. Technical indicators suggest correction to ₹62 level (10% down) likely in 2-3 weeks. Recommend exit now, re-enter at ₹62."
"""
        
        elif action == "buy":
            quantity = item.get('quantity', 1)
            total_cost = ltp * quantity
            prompt += f"""

**BUY ORDER**:
- Quantity: {quantity} shares
- Total cost: ₹{total_cost:,.2f}

**YOUR TASK**:
Analyze if NOW is right time to BUY.

**RESPOND WITH**:
Line 1: SIP_ACTION: [EXECUTE | WAIT | SKIP]
Line 2: AMOUNT: {total_cost}
Lines 3+: Reasoning
"""
        
        elif action == "sell":
            if holding:
                prompt += f"""

**SELL DECISION**:
Analyze if NOW is optimal time to EXIT.

Consider:
- Current P&L: {unrealized_pnl_pct:.2f}%
- Tax implications
- Market conditions
- Better opportunities

**RESPOND WITH**:
Line 1: SIP_ACTION: [EXECUTE | WAIT | SKIP]
Lines 2+: Reasoning
"""
        
        # Initialize LLM
        api_key = config.openai_api_key if config.llm_provider == "openai" and config.openai_api_key else os.environ.get('EMERGENT_LLM_KEY')
        
        if not current_session_id:
            current_session_id = f"trading_{uuid.uuid4().hex[:8]}"
        
        chat = LlmChat(
            api_key=api_key,
            session_id=current_session_id,
            system_message="You are an expert stock market analyst providing actionable trading decisions with tax optimization."
        )
        
        if config.llm_provider == "openai":
            chat.with_model("openai", config.llm_model)
        else:
            chat.with_model("openai", config.llm_model)
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        # Parse response
        decision = "WAIT"
        sip_amount = 0
        re_entry_price = 0
        tax_harvesting = "NO"
        
        lines = response.split('\n')
        for line in lines:
            if "SIP_ACTION:" in line:
                if "EXECUTE" in line.upper():
                    decision = "EXECUTE"
                elif "EXIT_AND_REENTER" in line.upper():
                    decision = "EXIT_AND_REENTER"
                elif "SKIP" in line.upper():
                    decision = "SKIP"
            elif "AMOUNT:" in line:
                try:
                    sip_amount = float(line.split(':')[1].strip().replace('₹', '').replace(',', ''))
                except:
                    sip_amount = item.get('sip_amount', 0)
            elif "RE_ENTRY_PRICE:" in line or "RE-ENTRY PRICE:" in line:
                try:
                    re_entry_price = float(line.split(':')[1].strip().replace('₹', '').replace(',', ''))
                except:
                    pass
            elif "TAX_HARVESTING:" in line:
                if "YES" in line.upper():
                    tax_harvesting = "YES"
        
        # Log prompt & response
        log_entry = LLMPromptLog(
            symbol=symbol,
            action_type=action,
            full_prompt=prompt,
            llm_response=response,
            model_used=config.llm_model,
            decision_made=decision
        )
        await db.llm_prompt_logs.insert_one(log_entry.model_dump())
        
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
        
        # Get portfolio info (for balance)
        portfolio = await get_portfolio()
        
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
            
            # Get LLM decision with portfolio balance
            llm_result = await get_llm_trading_decision(item, market_data, config, portfolio)
            
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
                        # Use LLM-decided SIP amount
                        sip_amount = llm_result.get('sip_amount', 0)
                        if sip_amount == 0:
                            sip_amount = item.get('sip_amount', 0)
                        
                        # Check if we have sufficient balance
                        if sip_amount > portfolio['available_cash']:
                            logger.warning(f"⚠️ Insufficient balance for SIP. Required: ₹{sip_amount}, Available: ₹{portfolio['available_cash']}")
                            analysis_log.error = f"Insufficient balance: ₹{portfolio['available_cash']}"
                            await db.analysis_logs.insert_one(analysis_log.model_dump())
                            continue
                        
                        quantity = int(sip_amount / current_price) if sip_amount > 0 else 0
                    else:
                        quantity = item.get('quantity', 1)
                        total_cost = quantity * current_price
                        if total_cost > portfolio['available_cash']:
                            logger.warning(f"⚠️ Insufficient balance for buy. Required: ₹{total_cost}, Available: ₹{portfolio['available_cash']}")
                            analysis_log.error = f"Insufficient balance"
                            await db.analysis_logs.insert_one(analysis_log.model_dump())
                            continue
                    
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
                            
                            # Update portfolio balance
                            portfolio['available_cash'] -= (quantity * current_price)
                            
                            notification = f"""
🎯 *{action.upper()} Executed*

📈 Symbol: {symbol}
📊 Quantity: {quantity}
💰 Price: ₹{current_price}
💵 Value: ₹{quantity * current_price:.2f}
💳 Remaining Balance: ₹{portfolio['available_cash']:.2f}
🆔 Order: {result['order_id']}

🤖 AI Reasoning:
{llm_result['reasoning'][:250]}

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
                            profit_loss_pct = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
                            
                            notification = f"""
💸 *SELL Executed*

📉 Symbol: {symbol}
📊 Quantity: {quantity}
💰 Sell Price: ₹{current_price}
📈 Avg Buy: ₹{avg_price}
💵 P&L: ₹{profit_loss:.2f} ({profit_loss_pct:.2f}%)
🆔 Order: {result['order_id']}

🤖 AI Reasoning:
{llm_result['reasoning'][:250]}

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
                
                sip_info = ""
                if action == "sip":
                    sip_amount = llm_result.get('sip_amount', 0)
                    sip_info = f"\n💰 LLM Suggested Amount: ₹{sip_amount}"
                
                notification = f"""
💡 *Trading Signal*

📈 Symbol: {symbol}
🎯 Action: {action.upper()}{sip_info}
💰 Price: ₹{current_price}
💳 Available Cash: ₹{portfolio['available_cash']:.2f}

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
                # Add to watchlist with hold action by default
                item = WatchlistItem(
                    symbol=symbol,
                    exchange=exchange,
                    symbol_token=token,
                    action="hold",
                    quantity=quantity,
                    avg_price=avg_price,
                    notes=f"Synced from portfolio"
                )
                await db.watchlist.insert_one(item.model_dump())
                synced += 1
            else:
                # Update quantity and avg_price from portfolio
                await db.watchlist.update_one(
                    {"symbol": symbol},
                    {"$set": {"quantity": quantity, "avg_price": avg_price}}
                )
        
        return {"success": True, "synced": synced, "message": f"Synced {synced} holdings to watchlist"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Executed Orders
@app.get("/api/executed-orders")
async def get_executed_orders(order_type: Optional[str] = None, limit: int = 100):
    """Get executed orders with optional filtering"""
    query = {"order_type": order_type} if order_type else {}
    orders = await db.executed_orders.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return orders

# Performance Summary
@app.get("/api/performance-summary")
async def get_performance_summary():
    """Get performance metrics"""
    try:
        # Get all executed orders
        orders = await db.executed_orders.find({}, {"_id": 0}).to_list(1000)
        
        # Calculate monthly/yearly P&L
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        monthly_pnl = sum(o.get('profit_loss', 0) for o in orders if o.get('profit_loss') and o.get('timestamp', '') >= month_start.isoformat())
        yearly_pnl = sum(o.get('profit_loss', 0) for o in orders if o.get('profit_loss') and o.get('timestamp', '') >= year_start.isoformat())
        
        # Get portfolio for top/worst performers
        portfolio = await get_portfolio()
        holdings = portfolio['holdings']
        
        performers = []
        for h in holdings:
            qty = int(h.get('quantity', 0))
            avg = float(h.get('averageprice', 0))
            ltp = float(h.get('ltp', 0))
            if avg > 0 and qty > 0:
                pnl_pct = ((ltp - avg) / avg) * 100
                performers.append({
                    "symbol": h.get('tradingsymbol'),
                    "pnl_pct": pnl_pct,
                    "pnl_amount": (ltp - avg) * qty
                })
        
        performers.sort(key=lambda x: x['pnl_pct'], reverse=True)
        
        return {
            "monthly_pnl": monthly_pnl,
            "yearly_pnl": yearly_pnl,
            "total_orders": len(orders),
            "top_performers": performers[:5] if performers else [],
            "worst_performers": performers[-5:] if len(performers) >= 5 else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# LLM Prompt Logs
@app.get("/api/llm-logs")
async def get_llm_logs(limit: int = 50):
    """Get LLM prompt logs"""
    logs = await db.llm_prompt_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
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
        
        # Save analysis
        analysis = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
