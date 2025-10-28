# Market Data Models for LLM Enhancement
from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime
import uuid
import pytz

IST = pytz.timezone('Asia/Kolkata')

def get_ist_timestamp():
    return datetime.now(IST).isoformat()

class TechnicalIndicators(BaseModel):
    """Technical indicators for LLM analysis"""
    symbol: str
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
    volume: Optional[float] = None
    
    def get_summary(self) -> str:
        """Generate summary for LLM prompt"""
        parts = []
        if self.rsi_14:
            parts.append(f"RSI(14): {self.rsi_14:.1f}")
        if self.macd and self.macd_signal:
            parts.append(f"MACD: {self.macd:.2f} / Signal: {self.macd_signal:.2f}")
        if self.adx_14:
            parts.append(f"ADX(14): {self.adx_14:.1f}")
        if self.bb_middle:
            parts.append(f"BB Middle: ₹{self.bb_middle:.2f}")
        return " | ".join(parts) if parts else "No technical data available"

class IndexValuation(BaseModel):
    """NSE Index valuation data"""
    index_name: str
    pe: Optional[float] = None
    pb: Optional[float] = None
    div_yield: Optional[float] = None
    last_price: Optional[float] = None
    
    def get_summary(self) -> str:
        """Generate summary for LLM prompt"""
        parts = []
        if self.pe:
            parts.append(f"P/E: {self.pe:.2f}")
        if self.pb:
            parts.append(f"P/B: {self.pb:.2f}")
        if self.div_yield:
            parts.append(f"Div Yield: {self.div_yield:.2f}%")
        if self.last_price:
            parts.append(f"Level: {self.last_price:.2f}")
        return " | ".join(parts) if parts else "No valuation data available"

class MarketTrend(BaseModel):
    """Market trend analysis"""
    trend: str = "neutral"  # "bullish", "neutral", "bearish"
    volatility: str = "medium"  # "low", "medium", "high"
    confidence: float = 0.5
    notes: Optional[str] = None
    
    def get_summary(self) -> str:
        """Generate summary for LLM prompt"""
        return f"Market: {self.trend.upper()} | Volatility: {self.volatility.upper()}"
