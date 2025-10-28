# NEW MODELS FOR AUTOINVEST ENHANCEMENT
# Add these after MarketStateLog class (around line 192)

# ===== USER PROFILE & AUTHENTICATION MODELS =====

class UserProfile(BaseModel):
    """User profile with manually set name and settings"""
    id: str = "main"
    name: str = "User"  # Manually set by user
    email: Optional[str] = None
    angel_one_client_id: Optional[str] = None
    created_at: str = Field(default_factory=get_ist_timestamp)
    updated_at: str = Field(default_factory=get_ist_timestamp)

class User(BaseModel):
    """User authentication model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    password_hash: str
    full_name: str
    email: Optional[str] = None
    is_active: bool = True
    created_at: str = Field(default_factory=get_ist_timestamp)

# ===== MARKET DATA MODELS =====

class TechnicalIndicators(BaseModel):
    """Technical indicators from Alpha Vantage"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    date: str  # YYYY-MM-DD
    rsi_14: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    adx_14: Optional[float] = None
    atr_14: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    obv: Optional[float] = None
    cmf: Optional[float] = None
    timestamp: str = Field(default_factory=get_ist_timestamp)
    source: str = "alpha_vantage"

class IndexValuation(BaseModel):
    """NSE Index valuation data"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    index_name: str  # NIFTY 50, NIFTY 500, etc.
    date: str  # YYYY-MM-DD
    pe: Optional[float] = None
    pb: Optional[float] = None
    div_yield: Optional[float] = None
    last_price: Optional[float] = None
    timestamp: str = Field(default_factory=get_ist_timestamp)
    source: str = "nse"

class MarketTrend(BaseModel):
    """Market trend analysis"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=get_ist_timestamp)
    date: str  # YYYY-MM-DD
    trend: str  # "bullish", "neutral", "bearish"
    volatility: str  # "low", "medium", "high"
    fii_dii_sentiment: Optional[str] = None
    index_trend: Optional[Dict] = None  # {"NIFTY 50": "bullish", etc}
    confidence_score: Optional[float] = None
    notes: Optional[str] = None

class ETFProxyMapping(BaseModel):
    """Map ETFs to their underlying indices"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    etf_symbol: str
    etf_name: str
    proxy_index: str  # e.g., "NIFTY 50", "NIFTY 500"
    isin: Optional[str] = None
    created_at: str = Field(default_factory=get_ist_timestamp)
    updated_at: str = Field(default_factory=get_ist_timestamp)

class PortfolioSnapshot(BaseModel):
    """Daily portfolio snapshot for tracking"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: str  # YYYY-MM-DD
    timestamp: str = Field(default_factory=get_ist_timestamp)
    holdings_count: int
    total_value: float
    total_pnl: float
    available_cash: float
    holdings: List[Dict]  # Full holdings data
    sync_source: str = "angel_one"

class DataFreshnessLog(BaseModel):
    """Track data freshness for monitoring"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=get_ist_timestamp)
    data_type: str  # "portfolio", "technical", "index_valuation", "market_trend"
    last_updated: str
    is_fresh: bool
    age_minutes: int
    status: str  # "success", "failed", "stale"
    error_message: Optional[str] = None

class BotExecutionLog(BaseModel):
    """Monitor bot execution for reliability"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=get_ist_timestamp)
    execution_time: str  # Expected execution time
    actual_time: Optional[str] = None
    status: str  # "executed", "missed", "delayed", "failed"
    trigger_type: str  # "scheduled", "manual"
    duration_seconds: Optional[float] = None
    items_processed: Optional[int] = None
    items_skipped: Optional[int] = None
    error_message: Optional[str] = None
