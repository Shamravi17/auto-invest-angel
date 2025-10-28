# AUTOINVEST BACKEND ENHANCEMENT - IMPLEMENTATION TRACKER
# Track progress of all requirements

## PHASE 1: MODELS & DATABASE SETUP ✅ IN PROGRESS
- [ ] Add UserProfile model
- [ ] Add User authentication model
- [ ] Add TechnicalIndicators model
- [ ] Add IndexValuation model
- [ ] Add MarketTrend model
- [ ] Add ETFProxyMapping model
- [ ] Add PortfolioSnapshot model
- [ ] Add DataFreshnessLog model
- [ ] Add BotExecutionLog model
- [ ] Update WatchlistItem with proxy_index field
- [ ] Create TTL indexes for new collections

## PHASE 2: AUTHENTICATION LAYER
- [ ] Install dependencies (python-jose, passlib, bcrypt)
- [ ] Add JWT authentication utilities
- [ ] Implement /api/auth/register endpoint
- [ ] Implement /api/auth/login endpoint
- [ ] Implement /api/auth/me endpoint
- [ ] Add authentication middleware
- [ ] Implement /api/profile endpoints (get, update)
- [ ] Frontend: Add login page
- [ ] Frontend: Add profile settings page
- [ ] Frontend: Add user name to header

## PHASE 3: SCHEDULER SERVICES
- [ ] Install Alpha Vantage library
- [ ] Add scheduler configuration
- [ ] Implement PortfolioMorningUpdater (8:00 AM)
- [ ] Implement AlphaVantageDataUpdater (8:10 AM)
- [ ] Implement NSEValuationFetcher (8:15 AM)
- [ ] Implement MarketTrendAnalyzer (every 3 hours)
- [ ] Implement PortfolioRefresher (every 2 hours)
- [ ] Add bot execution monitoring
- [ ] Add data freshness tracking

## PHASE 4: ETF-INDEX PROXY MAPPING
- [ ] Add proxy_index field to WatchlistItem
- [ ] Create default ETF mappings
- [ ] Add /api/etf-mappings endpoints
- [ ] Update LLM calls to include proxy index data
- [ ] Frontend: Add proxy index to watchlist UI
- [ ] Frontend: Add ETF mapping management

## PHASE 5: LLM ENHANCEMENT
- [ ] Update SIP LLM call with technical indicators
- [ ] Update SIP LLM call with proxy index data
- [ ] Update SIP LLM call with market trend
- [ ] Update SELL LLM call with technical indicators
- [ ] Update RE-ENTRY LLM call with technical indicators
- [ ] Add NSE valuation data to prompts
- [ ] Test LLM responses with new data

## PHASE 6: MONITORING & LOGGING
- [ ] Implement data freshness monitoring
- [ ] Implement bot execution monitoring
- [ ] Add service health checks
- [ ] Frontend: Add monitoring dashboard
- [ ] Frontend: Add data freshness indicators
- [ ] Add alerting for missed runs

## PHASE 7: TESTING & VALIDATION
- [ ] Test all new schedulers
- [ ] Test authentication flow
- [ ] Test LLM calls with new data
- [ ] Test bot execution reliability
- [ ] Validate data fetching from all sources
- [ ] End-to-end testing

## NOTES
- All times are in IST (Asia/Kolkata)
- Alpha Vantage free tier: 5 API calls/minute, 500/day
- NSE API doesn't require key but needs proper headers
- Market hours: 09:15-15:30 IST
