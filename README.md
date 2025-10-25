# AI-Powered Auto-Invest Trading Bot

An intelligent trading bot that uses AI (LLM) to make trading decisions for automatic investing through Angel One broker API.

## Features

### 🤖 Intelligent Trading Bot
- **AI-Driven Decisions**: Uses LLM (GPT/Claude) to analyze market conditions before executing trades
- **Multiple Actions**: Supports SIP (Systematic Investment Plan), Buy, Sell, and Hold strategies
- **Auto-Execution**: Can automatically execute trades based on AI recommendations
- **Scheduled Analysis**: Configurable bot runs (every 5-180 minutes)

### 📊 Portfolio Management
- **Live Portfolio**: Real-time view of Angel One holdings and positions
- **Portfolio Value Tracking**: Automatic calculation of total portfolio value
- **P&L Monitoring**: Track profit/loss on each holding

### 📈 Watchlist & Strategy
- **Action-Based Watchlist**: Add stocks/ETFs with specific actions (SIP/Buy/Sell/Hold)
- **Auto-Import Portfolio**: Automatically shows your Angel One holdings
- **Flexible Configuration**: Set SIP amount, frequency, quantity for each symbol
- **Smart Removal**: Sold items automatically removed from watchlist

### 🧠 AI Analysis
- **Custom Parameters**: Provide free-text analysis parameters for LLM
- **Market Intelligence**: AI considers technical indicators, trends, and your custom criteria
- **Actionable Insights**: Get clear EXECUTE/WAIT/SKIP decisions with reasoning

### 🔔 Notifications
- **Telegram Integration**: Real-time alerts for all trades
- **Manual Notifications**: Send custom notifications anytime
- **Detailed Reports**: Trade confirmations with P&L, order IDs, and AI reasoning

## Tech Stack

### Backend
- **FastAPI**: High-performance Python web framework
- **MongoDB**: Database for configuration and logs
- **APScheduler**: Background job scheduler for bot runs
- **Angel One SmartAPI**: Broker API for trading
- **Emergent LLM**: AI integration for market analysis

### Frontend
- **React**: Modern UI framework
- **Shadcn/UI**: Beautiful component library
- **Tailwind CSS**: Utility-first styling
- **Axios**: API communication

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB
- Angel One trading account
- LLM API key (Emergent or OpenAI)

### Backend Setup

```bash
cd backend
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your Angel One credentials

# Run server
uvicorn server:app --reload --host 0.0.0.0 --port 8001
```

### Frontend Setup

```bash
cd frontend
yarn install

# Create .env file
cp .env.example .env
# Edit .env with backend URL

# Run development server
yarn start
```

## Configuration

### Angel One API Keys

Get your API keys from [Angel One SmartAPI](https://smartapi.angelone.in/):

1. Login to Angel One
2. Go to My Profile → My API
3. Generate API Key
4. Enable TOTP (using Google Authenticator)
5. Add credentials to `.env` file

### Environment Variables

**Backend (.env):**
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=trading_bot_db
ANGEL_TRADING_API_KEY=your_key
ANGEL_CLIENT_ID=your_client_id
ANGEL_PASSWORD=your_password
ANGEL_TOTP_SECRET=your_totp_secret
EMERGENT_LLM_KEY=your_llm_key
OPENAI_API_KEY=your_openai_key (optional)
```

**Frontend (.env):**
```
REACT_APP_BACKEND_URL=http://localhost:8001
```

## Usage

### 1. Configure Bot

- Go to **Control Panel** tab
- Toggle **Bot Status** ON
- Set **Schedule Frequency** (default: 30 minutes)
- Configure **LLM Provider** (Emergent or OpenAI)
- Set **Analysis Parameters** (free text describing what LLM should consider)
- Configure **Telegram** notifications

### 2. Add Watchlist Items

- Go to **Watchlist & Strategy** tab
- Your portfolio items are automatically listed
- Click **Add Symbol** to add new stocks/ETFs
- For each item, select **Action**:
  - **SIP**: Automatic periodic investing (set amount & frequency)
  - **Buy**: One-time purchase (set quantity)
  - **Sell**: Exit position (uses quantity from holdings)
  - **Hold**: Monitor only, no action

### 3. Enable Auto-Execute

⚠️ **Important**: By default, bot only sends notifications. To execute trades automatically:

- Go to **Control Panel**
- Toggle **Auto Execute Trades** ON
- Bot will execute trades when LLM says "EXECUTE"

### 4. Monitor Activity

- **Portfolio Tab**: View live holdings and P&L
- **Analysis Logs**: See all bot decisions and executed trades
- **Telegram**: Receive real-time notifications

## Bot Behavior

### How Bot Processes Watchlist:

1. **Check Schedule**: Runs every X minutes (configurable)
2. **Filter Actions**: Only processes items with action = SIP/Buy/Sell
3. **Fetch Market Data**: Gets current price and 30-day candle data
4. **Ask LLM**: "Should I execute this action NOW?"
5. **LLM Analyzes**:
   - Current price trends
   - Technical indicators
   - Your custom analysis parameters
   - Risk/reward ratio
6. **LLM Decides**: EXECUTE / WAIT / SKIP
7. **Execute Trade** (if auto-execute ON and LLM says EXECUTE)
8. **Send Notification**: Telegram alert with details
9. **Update Records**: Log in database
10. **Remove Sold Items**: Auto-remove from watchlist after successful sell

### SIP Logic:

- Bot checks `next_action_date`
- If date is reached, asks LLM for timing
- If LLM says EXECUTE, calculates quantity based on SIP amount
- Places buy order
- Updates `next_action_date` to + frequency_days

### Sell Logic:

- Bot checks holdings for matching symbol
- Considers current P&L vs buy price
- LLM evaluates if it's good time to sell
- If executed, removes item from watchlist

## Safety Features

- **Manual Approval Mode**: Auto-execute OFF by default
- **LLM Validation**: Every trade validated by AI before execution
- **Error Handling**: Graceful failure handling, logs all errors
- **Notification Alerts**: Get notified for every action
- **Audit Trail**: Complete logs of all decisions and trades

## API Endpoints

### Configuration
- `GET /api/config` - Get bot configuration
- `PUT /api/config` - Update bot configuration

### Portfolio & Watchlist
- `GET /api/portfolio` - Get Angel One holdings
- `GET /api/watchlist` - Get watchlist items
- `POST /api/watchlist` - Add new item
- `PUT /api/watchlist/{symbol}` - Update item
- `DELETE /api/watchlist/{symbol}` - Remove item

### Bot Control
- `GET /api/status` - Get bot status
- `POST /api/run-bot` - Manually trigger bot
- `POST /api/send-notification` - Send test notification

### Logs
- `GET /api/logs` - Get analysis logs

## Troubleshooting

### Bot Not Running?
- Check bot status in header (should show "Active")
- Verify Angel One connection (should show "Connected")
- Check backend logs for errors

### Orders Not Executing?
- Ensure **Auto Execute Trades** is ON
- Check if LLM decision is "EXECUTE" in logs
- Verify Angel One API credentials
- Check if sufficient funds in account

### No Telegram Notifications?
- Verify bot token in Control Panel
- Check chat IDs are correct
- Test with "Send Test Notification" button

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## License

MIT License - feel free to use for personal or commercial projects.

## Disclaimer

⚠️ **Trading involves risk. This bot executes real trades with real money. Use at your own risk. Always test in paper trading mode first. The developers are not responsible for any financial losses.**

## Support

For issues or questions:
- Open a GitHub issue
- Check logs in `/var/log/supervisor/` (if using supervisor)
- Review MongoDB logs collection
