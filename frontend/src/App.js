import React, { useState, useEffect } from 'react';
import '@/App.css';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import { Activity, Bot, Settings, TrendingUp, BarChart3, Bell, Plus, Trash2, Play, Pause, RefreshCw, Brain, Zap, Eye, Wallet, DollarSign, Edit2, Save } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [status, setStatus] = useState({});
  const [config, setConfig] = useState(null);
  const [watchlist, setWatchlist] = useState([]);
  const [logs, setLogs] = useState([]);
  const [portfolio, setPortfolio] = useState({ holdings: [], positions: [] });
  const [portfolioAnalyses, setPortfolioAnalyses] = useState([]);
  const [analyzingPortfolio, setAnalyzingPortfolio] = useState(false);
  const [configChanged, setConfigChanged] = useState(false);
  const [tempConfig, setTempConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [newSymbol, setNewSymbol] = useState({ symbol: '', exchange: 'NSE', symbol_token: '', action: 'hold' });
  const [showAddSymbol, setShowAddSymbol] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [testTelegram, setTestTelegram] = useState({ bot_token: '', chat_ids: [''] });
  const [notificationMessage, setNotificationMessage] = useState('');
  const [testingLLM, setTestingLLM] = useState(false);
  const [credentials, setCredentials] = useState(null);
  const [llmLogs, setLlmLogs] = useState([]);
  const [tempCredentials, setTempCredentials] = useState(null);
  const [credentialsChanged, setCredentialsChanged] = useState(false);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (config && !tempConfig) {
      setTempConfig({...config});
    }
  }, [config]);

  useEffect(() => {
    if (credentials && !tempCredentials) {
      setTempCredentials({...credentials});
    }
  }, [credentials]);

  const fetchData = async () => {
    try {
      const [statusRes, configRes, watchlistRes, logsRes, portfolioRes, analysesRes, credsRes, llmLogsRes] = await Promise.all([
        axios.get(`${API}/status`),
        axios.get(`${API}/config`),
        axios.get(`${API}/watchlist`),
        axios.get(`${API}/logs?limit=20`),
        axios.get(`${API}/portfolio`).catch(e => ({ data: { holdings: [], positions: [] } })),
        axios.get(`${API}/portfolio-analyses?limit=5`),
        axios.get(`${API}/credentials`).catch(e => ({ data: null })),
        axios.get(`${API}/llm-logs?limit=50`)
      ]);
      
      setStatus(statusRes.data);
      setConfig(configRes.data);
      setWatchlist(watchlistRes.data);
      setLogs(logsRes.data);
      setPortfolio(portfolioRes.data);
      setPortfolioAnalyses(analysesRes.data);
      setCredentials(credsRes.data);
      setLlmLogs(llmLogsRes.data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching data:', error);
      toast.error('Failed to fetch data');
      setLoading(false);
    }
  };

  const updateConfig = async (updates) => {
    try {
      const updatedConfig = { ...config, ...updates };
      await axios.put(`${API}/config`, updatedConfig);
      setConfig(updatedConfig);
      setTempConfig(updatedConfig);
      setConfigChanged(false);
      toast.success('Configuration saved successfully');
      fetchData();
    } catch (error) {
      toast.error('Failed to save configuration');
    }
  };

  const updateTempConfig = (updates) => {
    setTempConfig({...tempConfig, ...updates});
    setConfigChanged(true);
  };

  const saveConfig = async () => {
    await updateConfig(tempConfig);
  };

  const updateTempCredentials = (updates) => {
    setTempCredentials({...tempCredentials, ...updates});
    setCredentialsChanged(true);
  };

  const saveCredentials = async () => {
    try {
      await axios.put(`${API}/credentials`, tempCredentials);
      setCredentials(tempCredentials);
      setCredentialsChanged(false);
      toast.success('Credentials saved successfully. Angel One will reconnect.');
      fetchData();
    } catch (error) {
      toast.error('Failed to save credentials');
    }
  };

  const addSymbol = async () => {
    if (!newSymbol.symbol || !newSymbol.symbol_token) {
      toast.error('Please enter both symbol and token');
      return;
    }
    try {
      await axios.post(`${API}/watchlist`, newSymbol);
      toast.success(`${newSymbol.symbol} added to watchlist`);
      setNewSymbol({ symbol: '', exchange: 'NSE', symbol_token: '', action: 'hold' });
      setShowAddSymbol(false);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add symbol');
    }
  };

  const syncPortfolio = async () => {
    try {
      const res = await axios.post(`${API}/sync-portfolio`);
      toast.success(res.data.message);
      fetchData();
    } catch (error) {
      toast.error('Failed to sync portfolio');
    }
  };

  const analyzePortfolio = async () => {
    setAnalyzingPortfolio(true);
    try {
      const res = await axios.post(`${API}/analyze-portfolio`);
      toast.success('Portfolio analysis complete!');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to analyze portfolio');
    } finally {
      setAnalyzingPortfolio(false);
    }
  };

  const testLLMConnection = async () => {
    setTestingLLM(true);
    try {
      const res = await axios.post(`${API}/test-llm`);
      if (res.data.success) {
        toast.success(res.data.message);
      } else {
        toast.error(res.data.message);
      }
    } catch (error) {
      toast.error('Failed to test LLM connection');
    } finally {
      setTestingLLM(false);
    }
  };

  const updateWatchlistItem = async (symbol, updates) => {
    try {
      await axios.put(`${API}/watchlist/${symbol}`, updates);
      toast.success(`${symbol} updated successfully`);
      fetchData();
      setShowEditDialog(false);
      setEditingItem(null);
    } catch (error) {
      toast.error('Failed to update symbol');
    }
  };

  const removeSymbol = async (symbol) => {
    try {
      await axios.delete(`${API}/watchlist/${symbol}`);
      toast.success(`${symbol} removed from watchlist`);
      fetchData();
    } catch (error) {
      toast.error('Failed to remove symbol');
    }
  };

  const triggerAnalysis = async () => {
    try {
      await axios.post(`${API}/run-bot`);
      toast.success('Analysis triggered! Check logs in a moment.');
      setTimeout(fetchData, 3000);
    } catch (error) {
      toast.error('Failed to trigger analysis');
    }
  };

  const testTelegramNotification = async () => {
    if (!testTelegram.bot_token || !testTelegram.chat_ids[0]) {
      toast.error('Please enter bot token and chat ID');
      return;
    }
    try {
      await axios.post(`${API}/test-telegram`, testTelegram);
      toast.success('Test notification sent!');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to send notification');
    }
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(value);
  };

  const calculatePortfolioValue = () => {
    const holdingsValue = portfolio.holdings.reduce((sum, h) => {
      return sum + (parseFloat(h.ltp || 0) * parseInt(h.quantity || 0));
    }, 0);
    return holdingsValue;
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-slate-600 text-lg">Loading AI Trading Bot...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      <Toaster position="top-right" richColors />
      
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-lg border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-lg">
                <Bot className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-slate-800" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>
                  AI Trading Bot
                </h1>
                <p className="text-sm text-slate-500">Intelligent Market Analysis System</p>
              </div>
            </div>
            
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100">
                <Activity className={`w-4 h-4 ${status.bot_active ? 'text-green-500 animate-pulse' : 'text-slate-400'}`} />
                <span className="text-sm font-medium text-slate-700">
                  {status.bot_active ? 'Active' : 'Inactive'}
                </span>
              </div>
              
              <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100">
                <Zap className={`w-4 h-4 ${status.angel_one_connected ? 'text-yellow-500' : 'text-slate-400'}`} />
                <span className="text-sm font-medium text-slate-700">
                  {status.angel_one_connected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <Card data-testid="portfolio-value-card" className="bg-white/90 backdrop-blur border-slate-200 hover:shadow-xl transition-all duration-300">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-semibold text-slate-700">Portfolio Value</CardTitle>
                <Wallet className="w-5 h-5 text-green-600" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold text-green-600" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>
                {formatCurrency(calculatePortfolioValue())}
              </p>
              <p className="text-sm text-slate-500 mt-1">{portfolio.holdings.length} holdings</p>
            </CardContent>
          </Card>

          <Card data-testid="watchlist-card" className="bg-white/90 backdrop-blur border-slate-200 hover:shadow-xl transition-all duration-300">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-semibold text-slate-700">Watchlist</CardTitle>
                <TrendingUp className="w-5 h-5 text-blue-600" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold text-blue-600" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>
                {status.watchlist_symbols || 0}
              </p>
              <p className="text-sm text-slate-500 mt-1">Symbols monitored</p>
            </CardContent>
          </Card>

          <Card data-testid="analyses-card" className="bg-white/90 backdrop-blur border-slate-200 hover:shadow-xl transition-all duration-300">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-semibold text-slate-700">Analyses</CardTitle>
                <BarChart3 className="w-5 h-5 text-indigo-600" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold text-indigo-600" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>
                {status.total_analyses || 0}
              </p>
              <p className="text-sm text-slate-500 mt-1">Completed</p>
            </CardContent>
          </Card>

          <Card data-testid="scheduler-card" className="bg-white/90 backdrop-blur border-slate-200 hover:shadow-xl transition-all duration-300">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-semibold text-slate-700">Scheduler</CardTitle>
                <Activity className="w-5 h-5 text-green-600" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold text-green-600" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>
                {config?.schedule_minutes || 0}m
              </p>
              <p className="text-sm text-slate-500 mt-1">Analysis interval</p>
            </CardContent>
          </Card>
        </div>

        {/* Main Tabs */}
        <Tabs defaultValue="portfolio" className="space-y-6">
          <TabsList className="bg-white/90 backdrop-blur border border-slate-200 p-1">
            <TabsTrigger value="portfolio" data-testid="portfolio-tab" className="data-[state=active]:bg-blue-600 data-[state=active]:text-white">
              <Wallet className="w-4 h-4 mr-2" />
              Portfolio
            </TabsTrigger>
            <TabsTrigger value="analysis" data-testid="analysis-tab" className="data-[state=active]:bg-blue-600 data-[state=active]:text-white">
              <Brain className="w-4 h-4 mr-2" />
              Portfolio Analysis
            </TabsTrigger>
            <TabsTrigger value="watchlist" data-testid="watchlist-tab" className="data-[state=active]:bg-blue-600 data-[state=active]:text-white">
              <TrendingUp className="w-4 h-4 mr-2" />
              Watchlist & Strategy
            </TabsTrigger>
            <TabsTrigger value="control" data-testid="control-tab" className="data-[state=active]:bg-blue-600 data-[state=active]:text-white">
              <Settings className="w-4 h-4 mr-2" />
              Control Panel
            </TabsTrigger>
            <TabsTrigger value="logs" data-testid="logs-tab" className="data-[state=active]:bg-blue-600 data-[state=active]:text-white">
              <Eye className="w-4 h-4 mr-2" />
              Analysis Logs
            </TabsTrigger>
            <TabsTrigger value="llm-logs" data-testid="llm-logs-tab" className="data-[state=active]:bg-blue-600 data-[state=active]:text-white">
              <Brain className="w-4 h-4 mr-2" />
              LLM Logs
            </TabsTrigger>
          </TabsList>

          {/* Portfolio Tab */}
          <TabsContent value="portfolio">
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Angel One Portfolio</CardTitle>
                    <CardDescription>Your current holdings and positions</CardDescription>
                  </div>
                  <Button onClick={fetchData} variant="outline">
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Refresh
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {portfolio.holdings.length === 0 ? (
                  <div className="text-center py-12">
                    <Wallet className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-500 text-lg mb-2">No holdings found</p>
                    <p className="text-slate-400 text-sm">Your Angel One portfolio will appear here</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {portfolio.holdings.map((holding, idx) => {
                      const quantity = parseInt(holding.quantity || 0);
                      const avgPrice = parseFloat(holding.averageprice || 0);
                      const ltp = parseFloat(holding.ltp || 0);
                      const investedValue = avgPrice * quantity;
                      const currentValue = ltp * quantity;
                      const profitLoss = currentValue - investedValue;
                      const profitLossPct = investedValue > 0 ? (profitLoss / investedValue) * 100 : 0;

                      return (
                        <div
                          key={idx}
                          data-testid={`holding-${holding.tradingsymbol}`}
                          className="p-4 rounded-lg border border-slate-200 bg-white hover:shadow-md transition-shadow"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex-1">
                              <h3 className="font-bold text-slate-800 text-lg">{holding.tradingsymbol}</h3>
                              <p className="text-sm text-slate-500">{holding.exchange}</p>
                            </div>
                            <div className="text-right">
                              <p className="text-2xl font-bold text-slate-800">{formatCurrency(ltp)}</p>
                              <Badge className={profitLoss >= 0 ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}>
                                {profitLossPct >= 0 ? '+' : ''}{profitLossPct.toFixed(2)}%
                              </Badge>
                            </div>
                          </div>
                          <Separator className="my-3" />
                          <div className="grid grid-cols-4 gap-4 text-sm">
                            <div>
                              <p className="text-slate-500">Quantity</p>
                              <p className="font-semibold text-slate-800">{quantity}</p>
                            </div>
                            <div>
                              <p className="text-slate-500">Avg Price</p>
                              <p className="font-semibold text-slate-800">{formatCurrency(avgPrice)}</p>
                            </div>
                            <div>
                              <p className="text-slate-500">Invested</p>
                              <p className="font-semibold text-slate-800">{formatCurrency(investedValue)}</p>
                            </div>
                            <div>
                              <p className="text-slate-500">Current Value</p>
                              <p className="font-semibold text-slate-800">{formatCurrency(currentValue)}</p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Portfolio Analysis Tab */}
          <TabsContent value="analysis">
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Brain className="w-5 h-5 text-indigo-600" />
                      AI Portfolio Analysis
                    </CardTitle>
                    <CardDescription>Get comprehensive LLM-powered analysis of your portfolio</CardDescription>
                  </div>
                  <Button 
                    onClick={analyzePortfolio} 
                    disabled={analyzingPortfolio || portfolio.holdings.length === 0}
                    className="bg-gradient-to-r from-indigo-600 to-purple-600"
                  >
                    {analyzingPortfolio ? (
                      <><RefreshCw className="w-4 h-4 mr-2 animate-spin" />Analyzing...</>
                    ) : (
                      <><Brain className="w-4 h-4 mr-2" />Analyze Portfolio</>
                    )}
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {portfolio.holdings.length === 0 ? (
                  <div className="text-center py-12">
                    <Brain className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-500 text-lg mb-2">No portfolio to analyze</p>
                    <p className="text-slate-400 text-sm">Add holdings to your portfolio first</p>
                  </div>
                ) : portfolioAnalyses.length === 0 ? (
                  <div className="text-center py-12">
                    <Brain className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-500 text-lg mb-2">No analyses yet</p>
                    <p className="text-slate-400 text-sm">Click \"Analyze Portfolio\" to get AI-powered insights</p>
                  </div>
                ) : (
                  <div className="space-y-6">
                    {portfolioAnalyses.map((analysis) => (
                      <div key={analysis.id} className="border border-slate-200 rounded-lg overflow-hidden">
                        {/* Analysis Header */}
                        <div className="bg-gradient-to-r from-indigo-50 to-purple-50 p-4 border-b">
                          <div className="flex items-center justify-between mb-3">
                            <h3 className="text-lg font-bold text-slate-800">Portfolio Analysis</h3>
                            <span className="text-sm text-slate-500">{new Date(analysis.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</span>
                          </div>
                          
                          {/* Summary Stats */}
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                            <div className="bg-white p-3 rounded-lg">
                              <p className="text-xs text-slate-500">Investment</p>
                              <p className="text-lg font-bold text-slate-800">{formatCurrency(analysis.portfolio_summary.total_investment)}</p>
                            </div>
                            <div className="bg-white p-3 rounded-lg">
                              <p className="text-xs text-slate-500">Current Value</p>
                              <p className="text-lg font-bold text-slate-800">{formatCurrency(analysis.portfolio_summary.current_value)}</p>
                            </div>
                            <div className="bg-white p-3 rounded-lg">
                              <p className="text-xs text-slate-500">P&L</p>
                              <p className={`text-lg font-bold ${analysis.portfolio_summary.overall_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {analysis.portfolio_summary.overall_pnl >= 0 ? '+' : ''}{formatCurrency(analysis.portfolio_summary.overall_pnl)}
                              </p>
                            </div>
                            <div className="bg-white p-3 rounded-lg">
                              <p className="text-xs text-slate-500">P&L %</p>
                              <p className={`text-lg font-bold ${analysis.portfolio_summary.overall_pnl_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {analysis.portfolio_summary.overall_pnl_pct >= 0 ? '+' : ''}{analysis.portfolio_summary.overall_pnl_pct.toFixed(2)}%
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* LLM Analysis */}
                        <div className="p-6 bg-white">
                          <h4 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
                            <Brain className="w-4 h-4 text-indigo-600" />
                            AI Insights & Recommendations
                          </h4>
                          <div className="prose prose-sm max-w-none">
                            <div className="whitespace-pre-wrap text-slate-700 leading-relaxed">
                              {analysis.llm_analysis}
                            </div>
                          </div>
                        </div>

                        {/* Holdings Breakdown */}
                        <details className="border-t">
                          <summary className="p-4 cursor-pointer hover:bg-slate-50 text-sm font-medium text-slate-700">
                            View Holdings Breakdown ({analysis.holdings.length} stocks)
                          </summary>
                          <div className="p-4 bg-slate-50 space-y-2">
                            {analysis.holdings.map((h, idx) => (
                              <div key={idx} className="flex items-center justify-between p-3 bg-white rounded border">
                                <div>
                                  <p className="font-semibold text-slate-800">{h.symbol}</p>
                                  <p className="text-xs text-slate-500">Qty: {h.quantity} | Avg: {formatCurrency(h.avg_price)}</p>
                                </div>
                                <div className="text-right">
                                  <p className="font-semibold text-slate-800">{formatCurrency(h.ltp)}</p>
                                  <p className={`text-sm font-medium ${h.pnl_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                    {h.pnl_pct >= 0 ? '+' : ''}{h.pnl_pct.toFixed(2)}%
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </details>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Watchlist & Strategy Tab */}
          <TabsContent value="watchlist">
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Watchlist & Trading Strategy</CardTitle>
                    <CardDescription>Portfolio items + manual watchlist with trading actions</CardDescription>
                  </div>
                  <div className="flex gap-2">
                    <Button onClick={syncPortfolio} variant="outline">
                      <RefreshCw className="w-4 h-4 mr-2" />
                      Sync Portfolio
                    </Button>
                    <Dialog open={showAddSymbol} onOpenChange={setShowAddSymbol}>
                      <DialogTrigger asChild>
                        <Button data-testid="add-symbol-btn" className="bg-gradient-to-r from-blue-600 to-indigo-600">
                          <Plus className="w-4 h-4 mr-2" />
                          Add Symbol
                        </Button>
                      </DialogTrigger>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>Add Symbol to Watchlist</DialogTitle>
                        <DialogDescription>Enter stock/ETF details</DialogDescription>
                      </DialogHeader>
                      <div className="space-y-4 pt-4">
                        <div className="space-y-2">
                          <Label>Symbol</Label>
                          <Input
                            data-testid="symbol-input"
                            placeholder="RELIANCE"
                            value={newSymbol.symbol}
                            onChange={(e) => setNewSymbol({ ...newSymbol, symbol: e.target.value })}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Exchange</Label>
                          <Select
                            value={newSymbol.exchange}
                            onValueChange={(value) => setNewSymbol({ ...newSymbol, exchange: value })}
                          >
                            <SelectTrigger data-testid="exchange-select">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="NSE">NSE</SelectItem>
                              <SelectItem value="BSE">BSE</SelectItem>
                              <SelectItem value="NFO">NFO</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-2">
                          <Label>Symbol Token</Label>
                          <Input
                            data-testid="symbol-token-input"
                            placeholder="3045"
                            value={newSymbol.symbol_token}
                            onChange={(e) => setNewSymbol({ ...newSymbol, symbol_token: e.target.value })}
                          />
                          <p className="text-xs text-slate-500">Find token from Angel One API docs</p>
                        </div>
                        <div className="space-y-2">
                          <Label>Action</Label>
                          <Select
                            value={newSymbol.action}
                            onValueChange={(value) => setNewSymbol({ ...newSymbol, action: value })}
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="hold">Hold (Monitor Only)</SelectItem>
                              <SelectItem value="sip">SIP (Systematic Investment)</SelectItem>
                              <SelectItem value="buy">Buy (One-time Purchase)</SelectItem>
                              <SelectItem value="sell">Sell (Exit Position)</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <Button data-testid="confirm-add-symbol-btn" onClick={addSymbol} className="w-full">
                          Add to Watchlist
                        </Button>
                      </div>
                    </DialogContent>
                  </Dialog>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {watchlist.length === 0 ? (
                  <div className="text-center py-12">
                    <TrendingUp className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-500 text-lg mb-2">No symbols in watchlist</p>
                    <p className="text-slate-400 text-sm">Add stocks or ETFs to configure trading strategies</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {watchlist.map((item) => {
                      // Find matching portfolio holding
                      const holding = portfolio.holdings.find(h => h.tradingsymbol === item.symbol);
                      const ltp = holding ? parseFloat(holding.ltp || 0) : 0;
                      const avgPrice = item.avg_price || (holding ? parseFloat(holding.averageprice || 0) : 0);
                      const qty = item.quantity || (holding ? parseInt(holding.quantity || 0) : 0);
                      const pnl = avgPrice > 0 && ltp > 0 ? ((ltp - avgPrice) / avgPrice) * 100 : 0;

                      return (
                        <div
                          key={item.id}
                          data-testid={`watchlist-item-${item.symbol}`}
                          className="p-4 rounded-lg border border-slate-200 bg-white hover:shadow-md transition-shadow"
                        >
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center">
                                <TrendingUp className="w-5 h-5 text-white" />
                              </div>
                              <div>
                                <div className="flex items-center gap-2">
                                  <p className="font-semibold text-slate-800 text-lg">{item.symbol}</p>
                                  <Badge 
                                    variant={item.action === 'sip' ? 'default' : item.action === 'buy' ? 'secondary' : item.action === 'sell' ? 'destructive' : 'outline'}
                                  >
                                    {item.action.toUpperCase()}
                                  </Badge>
                                  {holding && <Badge className="bg-green-100 text-green-800">In Portfolio</Badge>}
                                </div>
                                <p className="text-sm text-slate-500">{item.exchange} • Token: {item.symbol_token}</p>
                              </div>
                            </div>
                            <div className="flex gap-2">
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => {
                                  setEditingItem(item);
                                  setShowEditDialog(true);
                                }}
                                className="text-blue-600 hover:bg-blue-50"
                                data-testid={`edit-${item.symbol}-btn`}
                              >
                                <Edit2 className="w-4 h-4" />
                              </Button>
                              <Button
                                data-testid={`remove-${item.symbol}-btn`}
                                variant="ghost"
                                size="icon"
                                onClick={() => removeSymbol(item.symbol)}
                                className="text-red-600 hover:bg-red-50"
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </div>
                          </div>

                          {/* Portfolio Info */}
                          {holding && (
                            <div className="grid grid-cols-4 gap-4 text-sm border-t pt-3 mb-3">
                              <div>
                                <p className="text-slate-500">Quantity</p>
                                <p className="font-semibold">{qty}</p>
                              </div>
                              <div>
                                <p className="text-slate-500">Avg Price</p>
                                <p className="font-semibold">{formatCurrency(avgPrice)}</p>
                              </div>
                              <div>
                                <p className="text-slate-500">LTP</p>
                                <p className="font-semibold">{formatCurrency(ltp)}</p>
                              </div>
                              <div>
                                <p className="text-slate-500">P&L</p>
                                <p className={`font-semibold ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                  {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}%
                                </p>
                              </div>
                            </div>
                          )}

                          {/* Action Config Display */}
                          {item.action === 'sip' && item.sip_amount && (
                            <div className="p-3 rounded bg-green-50 border border-green-200 text-sm">
                              <p className="font-semibold text-green-800">SIP: Rs.{item.sip_amount} every {item.sip_frequency_days} days</p>
                            </div>
                          )}
                          {item.action === 'buy' && item.quantity && (
                            <div className="p-3 rounded bg-blue-50 border border-blue-200 text-sm">
                              <p className="font-semibold text-blue-800">Buy: {item.quantity} shares</p>
                            </div>
                          )}
                          {item.action === 'sell' && (
                            <div className="p-3 rounded bg-red-50 border border-red-200 text-sm">
                              <p className="font-semibold text-red-800">Sell: Exit position when LLM confirms</p>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Edit Strategy Dialog */}
            <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
              <DialogContent className="max-w-2xl">
                <DialogHeader>
                  <DialogTitle>Configure Strategy: {editingItem?.symbol}</DialogTitle>
                  <DialogDescription>Set action and parameters</DialogDescription>
                </DialogHeader>
                {editingItem && (
                  <div className="space-y-6 pt-4">
                    {/* Action Selection */}
                    <div className="space-y-2">
                      <Label className="font-semibold">Action</Label>
                      <Select
                        value={editingItem.action}
                        onValueChange={(value) => setEditingItem({ ...editingItem, action: value })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="hold">Hold (Monitor Only)</SelectItem>
                          <SelectItem value="sip">SIP (Systematic Investment)</SelectItem>
                          <SelectItem value="buy">Buy (One-time Purchase)</SelectItem>
                          <SelectItem value="sell">Sell (Exit Position)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <Separator />

                    {/* SIP Configuration */}
                    {editingItem.action === 'sip' && (
                      <div className="space-y-4">
                        <div className="space-y-2">
                          <Label>SIP Amount (Rs.)</Label>
                          <Input
                            type="number"
                            placeholder="5000"
                            value={editingItem.sip_amount || ''}
                            onChange={(e) => setEditingItem({ ...editingItem, sip_amount: parseFloat(e.target.value) || 0 })}
                          />
                          <p className="text-xs text-slate-500">LLM will adjust this based on market conditions</p>
                        </div>
                        <div className="space-y-2">
                          <Label>Frequency (days)</Label>
                          <Input
                            type="number"
                            placeholder="30"
                            value={editingItem.sip_frequency_days || 30}
                            onChange={(e) => setEditingItem({ ...editingItem, sip_frequency_days: parseInt(e.target.value) || 30 })}
                          />
                        </div>
                      </div>
                    )}

                    {/* Buy Configuration */}
                    {editingItem.action === 'buy' && (
                      <div className="space-y-4">
                        <div className="space-y-2">
                          <Label>Quantity</Label>
                          <Input
                            type="number"
                            placeholder="10"
                            value={editingItem.quantity || ''}
                            onChange={(e) => setEditingItem({ ...editingItem, quantity: parseInt(e.target.value) || 0 })}
                          />
                        </div>
                      </div>
                    )}

                    {/* Sell Info */}
                    {editingItem.action === 'sell' && (
                      <div className="p-4 rounded-lg bg-yellow-50 border border-yellow-200">
                        <p className="text-sm text-yellow-800">
                          LLM will analyze market conditions and decide the optimal time to sell this position.
                          The bot will monitor price trends, technical indicators, and your analysis parameters.
                        </p>
                      </div>
                    )}

                    {/* Notes */}
                    <div className="space-y-2">
                      <Label>Notes (Optional)</Label>
                      <Input
                        placeholder="Add notes..."
                        value={editingItem.notes || ''}
                        onChange={(e) => setEditingItem({ ...editingItem, notes: e.target.value })}
                      />
                    </div>

                    <Button
                      onClick={() => updateWatchlistItem(editingItem.symbol, editingItem)}
                      className="w-full"
                      data-testid="save-strategy-btn"
                    >
                      <Save className="w-4 h-4 mr-2" />
                      Save Changes
                    </Button>
                  </div>
                )}
              </DialogContent>
            </Dialog>
          </TabsContent>

          {/* Control Panel */}
          <TabsContent value="control" className="space-y-6">
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader><CardTitle className="flex items-center gap-2"><Bot className="w-5 h-5 text-blue-600" />Bot Control</CardTitle></CardHeader>
              <CardContent className="space-y-6">
                <div className="flex items-center justify-between p-4 rounded-lg bg-slate-50">
                  <div>
                    <Label className="text-base font-semibold text-slate-700">Bot Status</Label>
                    <p className="text-sm text-slate-500 mt-1">Enable or disable automated analysis</p>
                  </div>
                  <Switch
                    data-testid="bot-toggle"
                    checked={tempConfig?.is_active || false}
                    onCheckedChange={(checked) => {
                      updateTempConfig({ is_active: checked });
                      updateConfig({ is_active: checked });
                    }}
                    className="data-[state=checked]:bg-green-600"
                  />
                </div>

                <div className="flex items-center justify-between p-4 rounded-lg bg-yellow-50 border border-yellow-200">
                  <div>
                    <Label className="text-base font-semibold text-yellow-800">Auto Execute Trades</Label>
                    <p className="text-sm text-yellow-700 mt-1">⚠️ Will execute real orders</p>
                  </div>
                  <Switch
                    data-testid="auto-trade-toggle"
                    checked={tempConfig?.auto_execute_trades || false}
                    onCheckedChange={(checked) => {
                      updateTempConfig({ auto_execute_trades: checked });
                      updateConfig({ auto_execute_trades: checked });
                    }}
                    className="data-[state=checked]:bg-yellow-600"
                  />
                </div>

                <Separator />

                <div className="space-y-4">
                  <Label className="text-base font-semibold text-slate-700">Schedule Frequency</Label>
                  
                  <div className="space-y-2">
                    <Label className="text-sm">Frequency Type</Label>
                    <Select
                      value={tempConfig?.schedule_type || "interval"}
                      onValueChange={(value) => updateTempConfig({ schedule_type: value })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="interval">Every X Minutes</SelectItem>
                        <SelectItem value="hourly">Multiple Times Daily (Every X Hours)</SelectItem>
                        <SelectItem value="daily">Once Daily (Specific Time)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {tempConfig?.schedule_type === "interval" && (
                    <div className="space-y-2">
                      <Label className="text-sm">Minutes Interval</Label>
                      <div className="flex items-center gap-4">
                        <Slider
                          value={[tempConfig?.schedule_minutes || 30]}
                          onValueChange={([value]) => updateTempConfig({ schedule_minutes: value })}
                          min={5}
                          max={180}
                          step={5}
                          className="flex-1"
                        />
                        <span className="text-lg font-bold text-blue-600 min-w-[80px] text-right">
                          {tempConfig?.schedule_minutes || 30} min
                        </span>
                      </div>
                    </div>
                  )}

                  {tempConfig?.schedule_type === "hourly" && (
                    <div className="space-y-2">
                      <Label className="text-sm">Hours Interval</Label>
                      <Select
                        value={String(tempConfig?.schedule_hours_interval || 1)}
                        onValueChange={(value) => updateTempConfig({ schedule_hours_interval: parseInt(value) })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="1">Every 1 Hour</SelectItem>
                          <SelectItem value="2">Every 2 Hours</SelectItem>
                          <SelectItem value="3">Every 3 Hours</SelectItem>
                          <SelectItem value="4">Every 4 Hours</SelectItem>
                          <SelectItem value="6">Every 6 Hours</SelectItem>
                          <SelectItem value="12">Every 12 Hours</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}

                  {tempConfig?.schedule_type === "daily" && (
                    <div className="space-y-2">
                      <Label className="text-sm">Time (24-hour format)</Label>
                      <Input
                        type="time"
                        value={tempConfig?.schedule_time || "09:00"}
                        onChange={(e) => updateTempConfig({ schedule_time: e.target.value })}
                      />
                      <p className="text-xs text-slate-500">Bot will run once daily at this time</p>
                    </div>
                  )}
                </div>

                <div className="flex gap-3">
                  <Button
                    data-testid="run-now-btn"
                    onClick={triggerAnalysis}
                    className="flex-1 bg-gradient-to-r from-blue-600 to-indigo-600"
                  >
                    <Play className="w-4 h-4 mr-2" />
                    Run Analysis Now
                  </Button>
                  <Button
                    data-testid="refresh-btn"
                    onClick={fetchData}
                    variant="outline"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Save Configuration Button */}
            {configChanged && (
              <Card className="bg-gradient-to-r from-green-50 to-emerald-50 border-green-200">
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-semibold text-green-800">Configuration Changed</p>
                      <p className="text-sm text-green-600">Save your changes to apply the new schedule settings</p>
                    </div>
                    <Button
                      onClick={saveConfig}
                      className="bg-green-600 hover:bg-green-700"
                    >
                      <Save className="w-4 h-4 mr-2" />
                      Save Configuration
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Angel One Credentials */}
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Settings className="w-5 h-5 text-blue-600" />
                  Angel One Credentials
                </CardTitle>
                <CardDescription>Configure your Angel One API credentials securely</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>API Key</Label>
                    <Input
                      type="text"
                      placeholder="Enter Angel One API Key"
                      value={tempCredentials?.angel_api_key || ''}
                      onChange={(e) => updateTempCredentials({ angel_api_key: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Client ID</Label>
                    <Input
                      type="text"
                      placeholder="Enter Client ID"
                      value={tempCredentials?.angel_client_id || ''}
                      onChange={(e) => updateTempCredentials({ angel_client_id: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Password</Label>
                    <Input
                      type="password"
                      placeholder="Enter Password"
                      value={tempCredentials?.angel_password || ''}
                      onChange={(e) => updateTempCredentials({ angel_password: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>TOTP Secret</Label>
                    <Input
                      type="text"
                      placeholder="Enter TOTP Secret"
                      value={tempCredentials?.angel_totp_secret || ''}
                      onChange={(e) => updateTempCredentials({ angel_totp_secret: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>MPIN</Label>
                    <Input
                      type="password"
                      placeholder="Enter MPIN"
                      value={tempCredentials?.angel_mpin || ''}
                      onChange={(e) => updateTempCredentials({ angel_mpin: e.target.value })}
                    />
                  </div>
                </div>

                {credentialsChanged && (
                  <div className="flex justify-end">
                    <Button
                      onClick={saveCredentials}
                      className="bg-blue-600 hover:bg-blue-700"
                    >
                      <Save className="w-4 h-4 mr-2" />
                      Save Credentials
                    </Button>
                  </div>
                )}

                <p className="text-xs text-slate-500 mt-2">
                  🔒 Credentials are encrypted and stored securely in the database. They will not be committed to Git.
                </p>
              </CardContent>
            </Card>

            {/* Rest of control panel (LLM, Analysis Params, Telegram) - keeping original code */}
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Brain className="w-5 h-5 text-indigo-600" />
                  LLM Configuration
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Provider</Label>
                    <Select value={config?.llm_provider || 'emergent'} onValueChange={(value) => updateConfig({ llm_provider: value })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="emergent">Emergent LLM</SelectItem>
                        <SelectItem value="openai">OpenAI</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Model</Label>
                    <Select value={config?.llm_model || 'gpt-4o-mini'} onValueChange={(value) => updateConfig({ llm_model: value })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gpt-4o-mini">GPT-4o Mini</SelectItem>
                        <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                        <SelectItem value="gpt-5">GPT-5</SelectItem>
                        <SelectItem value="o1">O1</SelectItem>
                        <SelectItem value="o1-mini">O1 Mini</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                {config?.llm_provider === 'openai' && (
                  <Input
                    type="password"
                    placeholder="OpenAI API Key (sk-...)"
                    value={config?.openai_api_key || ''}
                    onChange={(e) => updateConfig({ openai_api_key: e.target.value })}
                  />
                )}
                <Button 
                  onClick={testLLMConnection} 
                  variant="outline" 
                  className="w-full"
                  disabled={testingLLM}
                >
                  {testingLLM ? <><RefreshCw className="w-4 h-4 mr-2 animate-spin" />Testing...</> : <><Brain className="w-4 h-4 mr-2" />Test LLM Connection</>}
                </Button>
              </CardContent>
            </Card>

            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader><CardTitle>Analysis Parameters</CardTitle><CardDescription>Tell LLM what to consider (free text)</CardDescription></CardHeader>
              <CardContent>
                <Textarea 
                  rows={4} 
                  placeholder="e.g., Consider P/E ratio below 25, RSI oversold conditions, volume spike above 50%, resistance levels, market sentiment..."
                  value={config?.analysis_parameters || ''}
                  onChange={(e) => updateConfig({ analysis_parameters: e.target.value })}
                  className="w-full"
                />
              </CardContent>
            </Card>

            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader><CardTitle>Trading Thresholds</CardTitle><CardDescription>NEVER sell at loss except tax harvesting</CardDescription></CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Profit Threshold for Selling (%)</Label>
                  <div className="flex items-center gap-4">
                    <Slider
                      value={[tempConfig?.profit_threshold_percent || 15]}
                      onValueChange={([v]) => updateTempConfig({ profit_threshold_percent: v })}
                      min={5}
                      max={50}
                      step={1}
                      className="flex-1"
                    />
                    <span className="text-lg font-bold text-green-600 min-w-[60px] text-right">
                      {tempConfig?.profit_threshold_percent || 15}%
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">Minimum PROFIT % required to consider selling. Never sell at loss (except tax harvesting).</p>
                </div>

                <div className="space-y-2">
                  <Label>Minimum Gain Threshold (%) - After Charges</Label>
                  <div className="flex items-center gap-4">
                    <Slider
                      value={[tempConfig?.minimum_gain_threshold_percent || 5]}
                      onValueChange={([v]) => updateTempConfig({ minimum_gain_threshold_percent: v })}
                      min={1}
                      max={20}
                      step={0.5}
                      className="flex-1"
                    />
                    <span className="text-lg font-bold text-blue-600 min-w-[60px] text-right">
                      {tempConfig?.minimum_gain_threshold_percent || 5}%
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">Net gain (after brokerage, STT, GST) required for exit/re-entry strategy</p>
                </div>

                <Button onClick={saveConfig} className="w-full" variant="outline">
                  <Save className="w-4 h-4 mr-2" />
                  Save Thresholds
                </Button>
              </CardContent>
            </Card>

            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader><CardTitle>Tax Harvesting</CardTitle><CardDescription>Configure tax loss harvesting strategy</CardDescription></CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between p-4 rounded-lg bg-slate-50">
                  <div>
                    <Label className="font-semibold">Enable Tax Harvesting</Label>
                    <p className="text-sm text-slate-500 mt-1">Let LLM suggest tax loss harvesting opportunities</p>
                  </div>
                  <Switch
                    checked={config?.enable_tax_harvesting || false}
                    onCheckedChange={(c) => updateConfig({ enable_tax_harvesting: c })}
                  />
                </div>

                {config?.enable_tax_harvesting && (
                  <div className="space-y-2">
                    <Label>Tax Harvesting Loss Slab (Rs.)</Label>
                    <Input
                      type="number"
                      step="1000"
                      value={config?.tax_harvesting_loss_slab || 50000}
                      onChange={(e) => updateConfig({ tax_harvesting_loss_slab: parseFloat(e.target.value) })}
                    />
                    <p className="text-xs text-slate-500">Minimum loss required to trigger tax harvesting (default: Rs.50,000)</p>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bell className="w-5 h-5 text-yellow-600" />
                  Telegram Notifications
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between p-4 rounded-lg bg-slate-50">
                  <Label>Enable Notifications</Label>
                  <Switch checked={config?.enable_notifications || false} onCheckedChange={(checked) => updateConfig({ enable_notifications: checked })} />
                </div>
                <Input placeholder="Bot Token" type="password" value={config?.telegram_bot_token || ''} onChange={(e) => updateConfig({ telegram_bot_token: e.target.value })} />
                <Input placeholder="Chat IDs (comma separated)" value={config?.telegram_chat_ids?.join(', ') || ''} onChange={(e) => updateConfig({ telegram_chat_ids: e.target.value.split(',').map(id => id.trim()).filter(Boolean) })} />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Analysis Logs */}
          <TabsContent value="logs">
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <CardTitle>Analysis Logs</CardTitle>
                <CardDescription>Recent trading analysis results</CardDescription>
              </CardHeader>
              <CardContent>
                {logs.length === 0 ? (
                  <div className="text-center py-12">
                    <BarChart3 className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-500 text-lg mb-2">No analyses yet</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {logs.map((log) => (
                      <div key={log.id} className="p-4 rounded-lg border bg-white">
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <Badge className={log.llm_decision === 'EXECUTE' ? 'bg-green-100 text-green-800' : log.llm_decision === 'SELL' ? 'bg-red-100 text-red-800' : 'bg-slate-100'}>
                              {log.llm_decision || 'SKIP'}
                            </Badge>
                            <span className="font-semibold">{log.symbol}</span>
                            <span className="text-xs text-slate-500 capitalize">{log.action}</span>
                          </div>
                          <span className="text-xs text-slate-500">{new Date(log.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</span>
                        </div>
                        {log.executed && <p className="text-xs text-green-600 mb-2">✓ Executed</p>}
                        {log.error && <p className="text-xs text-red-600">{log.error}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* LLM Logs */}
          <TabsContent value="llm-logs">
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <CardTitle>LLM Prompt & Response Logs</CardTitle>
                <CardDescription>Detailed prompts and responses from AI analysis</CardDescription>
              </CardHeader>
              <CardContent>
                {llmLogs.length === 0 ? (
                  <div className="text-center py-12">
                    <Brain className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-500 text-lg mb-2">No LLM logs yet</p>
                    <p className="text-slate-400 text-sm">LLM prompts and responses will appear here</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {llmLogs.map((log) => (
                      <div key={log.id} className="p-4 rounded-lg border bg-white">
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <Badge className={log.decision_made === 'EXECUTE' || log.decision_made === 'SELL' ? 'bg-green-100 text-green-800' : log.decision_made === 'EXIT_AND_REENTER' ? 'bg-yellow-100 text-yellow-800' : 'bg-slate-100'}>
                              {log.decision_made}
                            </Badge>
                            <span className="font-semibold">{log.symbol}</span>
                            <span className="text-xs text-slate-500 capitalize">{log.action_type}</span>
                            <Badge variant="outline" className="text-xs">{log.model_used}</Badge>
                          </div>
                          <span className="text-xs text-slate-500">{new Date(log.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</span>
                        </div>
                        
                        <div className="space-y-3">
                          <div>
                            <p className="text-xs font-semibold text-slate-700 mb-1">Prompt:</p>
                            <pre className="text-xs bg-slate-50 p-3 rounded border overflow-x-auto whitespace-pre-wrap">{log.full_prompt.substring(0, 500)}...</pre>
                          </div>
                          
                          <div>
                            <p className="text-xs font-semibold text-slate-700 mb-1">LLM Response:</p>
                            <pre className="text-xs bg-blue-50 p-3 rounded border overflow-x-auto whitespace-pre-wrap">{log.llm_response}</pre>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}

export default App;
