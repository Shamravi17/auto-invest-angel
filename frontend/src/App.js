import React, { useState, useEffect } from 'react';
import '@/App.css';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import { Activity, Bot, Settings, TrendingUp, BarChart3, Bell, Plus, Trash2, Play, Pause, RefreshCw, Brain, Zap, Eye } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
  const [loading, setLoading] = useState(true);
  const [newSymbol, setNewSymbol] = useState({ symbol: '', exchange: 'NSE', symbol_token: '' });
  const [showAddSymbol, setShowAddSymbol] = useState(false);
  const [testTelegram, setTestTelegram] = useState({ bot_token: '', chat_ids: [''] });

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const [statusRes, configRes, watchlistRes, logsRes] = await Promise.all([
        axios.get(`${API}/status`),
        axios.get(`${API}/config`),
        axios.get(`${API}/watchlist`),
        axios.get(`${API}/logs?limit=20`)
      ]);
      
      setStatus(statusRes.data);
      setConfig(configRes.data);
      setWatchlist(watchlistRes.data);
      setLogs(logsRes.data);
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
      toast.success('Configuration updated successfully');
      fetchData();
    } catch (error) {
      toast.error('Failed to update configuration');
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
      setNewSymbol({ symbol: '', exchange: 'NSE', symbol_token: '' });
      setShowAddSymbol(false);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add symbol');
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
      await axios.post(`${API}/run-analysis`);
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
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card data-testid="watchlist-card" className="bg-white/90 backdrop-blur border-slate-200 hover:shadow-xl transition-all duration-300">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-semibold text-slate-700">Watchlist</CardTitle>
                <TrendingUp className="w-5 h-5 text-blue-600" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-4xl font-bold text-blue-600" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>
                {status.watchlist_symbols || 0}
              </p>
              <p className="text-sm text-slate-500 mt-1">Symbols being monitored</p>
            </CardContent>
          </Card>

          <Card data-testid="analyses-card" className="bg-white/90 backdrop-blur border-slate-200 hover:shadow-xl transition-all duration-300">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-semibold text-slate-700">Total Analyses</CardTitle>
                <BarChart3 className="w-5 h-5 text-indigo-600" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-4xl font-bold text-indigo-600" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>
                {status.total_analyses || 0}
              </p>
              <p className="text-sm text-slate-500 mt-1">Completed analyses</p>
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
              <p className="text-4xl font-bold text-green-600" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>
                {config?.schedule_minutes || 0}m
              </p>
              <p className="text-sm text-slate-500 mt-1">Analysis interval</p>
            </CardContent>
          </Card>
        </div>

        {/* Main Tabs */}
        <Tabs defaultValue="control" className="space-y-6">
          <TabsList className="bg-white/90 backdrop-blur border border-slate-200 p-1">
            <TabsTrigger value="control" data-testid="control-tab" className="data-[state=active]:bg-blue-600 data-[state=active]:text-white">
              <Settings className="w-4 h-4 mr-2" />
              Control Panel
            </TabsTrigger>
            <TabsTrigger value="watchlist" data-testid="watchlist-tab" className="data-[state=active]:bg-blue-600 data-[state=active]:text-white">
              <TrendingUp className="w-4 h-4 mr-2" />
              Watchlist
            </TabsTrigger>
            <TabsTrigger value="logs" data-testid="logs-tab" className="data-[state=active]:bg-blue-600 data-[state=active]:text-white">
              <Eye className="w-4 h-4 mr-2" />
              Analysis Logs
            </TabsTrigger>
          </TabsList>

          {/* Control Panel */}
          <TabsContent value="control" className="space-y-6">
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bot className="w-5 h-5 text-blue-600" />
                  Bot Control
                </CardTitle>
                <CardDescription>Activate or deactivate the trading bot</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex items-center justify-between p-4 rounded-lg bg-slate-50">
                  <div>
                    <Label className="text-base font-semibold text-slate-700">Bot Status</Label>
                    <p className="text-sm text-slate-500 mt-1">Enable or disable automated analysis</p>
                  </div>
                  <Switch
                    data-testid="bot-toggle"
                    checked={config?.is_active || false}
                    onCheckedChange={(checked) => updateConfig({ is_active: checked })}
                    className="data-[state=checked]:bg-green-600"
                  />
                </div>

                <Separator />

                <div className="space-y-4">
                  <Label className="text-base font-semibold text-slate-700">Schedule Frequency</Label>
                  <div className="flex items-center gap-4">
                    <Slider
                      data-testid="schedule-slider"
                      value={[config?.schedule_minutes || 30]}
                      onValueChange={([value]) => updateConfig({ schedule_minutes: value })}
                      min={5}
                      max={180}
                      step={5}
                      className="flex-1"
                    />
                    <span className="text-lg font-bold text-blue-600 min-w-[80px] text-right">
                      {config?.schedule_minutes || 30} min
                    </span>
                  </div>
                  <p className="text-sm text-slate-500">Bot will analyze watchlist every {config?.schedule_minutes || 30} minutes</p>
                </div>

                <div className="flex gap-3">
                  <Button
                    data-testid="run-now-btn"
                    onClick={triggerAnalysis}
                    className="flex-1 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white"
                  >
                    <Play className="w-4 h-4 mr-2" />
                    Run Analysis Now
                  </Button>
                  <Button
                    data-testid="refresh-btn"
                    onClick={fetchData}
                    variant="outline"
                    className="border-slate-300 hover:bg-slate-50"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* LLM Configuration */}
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Brain className="w-5 h-5 text-indigo-600" />
                  LLM Configuration
                </CardTitle>
                <CardDescription>Configure AI model for market analysis</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>LLM Provider</Label>
                    <Select
                      data-testid="llm-provider-select"
                      value={config?.llm_provider || 'emergent'}
                      onValueChange={(value) => updateConfig({ llm_provider: value })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="emergent">Emergent LLM Key</SelectItem>
                        <SelectItem value="openai">OpenAI</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Model</Label>
                    <Select
                      data-testid="llm-model-select"
                      value={config?.llm_model || 'gpt-4o-mini'}
                      onValueChange={(value) => updateConfig({ llm_model: value })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gpt-4o-mini">GPT-4o Mini</SelectItem>
                        <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                        <SelectItem value="gpt-5">GPT-5</SelectItem>
                        <SelectItem value="o1">O1</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {config?.llm_provider === 'openai' && (
                  <div className="space-y-2">
                    <Label>OpenAI API Key</Label>
                    <Input
                      data-testid="openai-key-input"
                      type="password"
                      placeholder="sk-..."
                      value={config?.openai_api_key || ''}
                      onChange={(e) => updateConfig({ openai_api_key: e.target.value })}
                      className="font-mono text-sm"
                    />
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Analysis Parameters */}
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <CardTitle>Analysis Parameters</CardTitle>
                <CardDescription>Customize trading signal criteria</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>P/E Ratio Threshold</Label>
                    <Input
                      data-testid="pe-ratio-input"
                      type="number"
                      value={config?.analysis_params?.pe_ratio_threshold || 25}
                      onChange={(e) => updateConfig({
                        analysis_params: { ...config.analysis_params, pe_ratio_threshold: parseInt(e.target.value) }
                      })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Volume Spike %</Label>
                    <Input
                      data-testid="volume-spike-input"
                      type="number"
                      value={config?.analysis_params?.volume_spike_percentage || 50}
                      onChange={(e) => updateConfig({
                        analysis_params: { ...config.analysis_params, volume_spike_percentage: parseInt(e.target.value) }
                      })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>RSI Overbought</Label>
                    <Input
                      data-testid="rsi-overbought-input"
                      type="number"
                      value={config?.analysis_params?.rsi_overbought || 70}
                      onChange={(e) => updateConfig({
                        analysis_params: { ...config.analysis_params, rsi_overbought: parseInt(e.target.value) }
                      })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>RSI Oversold</Label>
                    <Input
                      data-testid="rsi-oversold-input"
                      type="number"
                      value={config?.analysis_params?.rsi_oversold || 30}
                      onChange={(e) => updateConfig({
                        analysis_params: { ...config.analysis_params, rsi_oversold: parseInt(e.target.value) }
                      })}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Telegram Configuration */}
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bell className="w-5 h-5 text-yellow-600" />
                  Telegram Notifications
                </CardTitle>
                <CardDescription>Configure alerts for trading signals</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between p-4 rounded-lg bg-slate-50">
                  <Label>Enable Notifications</Label>
                  <Switch
                    data-testid="notifications-toggle"
                    checked={config?.enable_notifications || false}
                    onCheckedChange={(checked) => updateConfig({ enable_notifications: checked })}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Bot Token</Label>
                  <Input
                    data-testid="telegram-token-input"
                    type="password"
                    placeholder="123456:ABC-DEF..."
                    value={config?.telegram_bot_token || ''}
                    onChange={(e) => updateConfig({ telegram_bot_token: e.target.value })}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Chat IDs (comma separated)</Label>
                  <Input
                    data-testid="telegram-chat-ids-input"
                    placeholder="123456789, 987654321"
                    value={config?.telegram_chat_ids?.join(', ') || ''}
                    onChange={(e) => updateConfig({
                      telegram_chat_ids: e.target.value.split(',').map(id => id.trim()).filter(Boolean)
                    })}
                  />
                </div>

                <Dialog>
                  <DialogTrigger asChild>
                    <Button variant="outline" className="w-full" data-testid="test-telegram-btn">
                      Test Telegram Notification
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Test Telegram</DialogTitle>
                      <DialogDescription>Send a test notification to verify setup</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 pt-4">
                      <div className="space-y-2">
                        <Label>Bot Token</Label>
                        <Input
                          placeholder="Bot token"
                          value={testTelegram.bot_token}
                          onChange={(e) => setTestTelegram({ ...testTelegram, bot_token: e.target.value })}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Chat ID</Label>
                        <Input
                          placeholder="Chat ID"
                          value={testTelegram.chat_ids[0]}
                          onChange={(e) => setTestTelegram({ ...testTelegram, chat_ids: [e.target.value] })}
                        />
                      </div>
                      <Button onClick={testTelegramNotification} className="w-full">
                        Send Test Message
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Watchlist */}
          <TabsContent value="watchlist">
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Watchlist</CardTitle>
                    <CardDescription>Manage symbols for AI analysis</CardDescription>
                  </div>
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
                        <Button data-testid="confirm-add-symbol-btn" onClick={addSymbol} className="w-full">
                          Add to Watchlist
                        </Button>
                      </div>
                    </DialogContent>
                  </Dialog>
                </div>
              </CardHeader>
              <CardContent>
                {watchlist.length === 0 ? (
                  <div className="text-center py-12">
                    <TrendingUp className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-500 text-lg mb-2">No symbols in watchlist</p>
                    <p className="text-slate-400 text-sm">Add stocks or ETFs to start analysis</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {watchlist.map((item) => (
                      <div
                        key={item.id}
                        data-testid={`watchlist-item-${item.symbol}`}
                        className="flex items-center justify-between p-4 rounded-lg bg-slate-50 hover:bg-slate-100 transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center">
                            <TrendingUp className="w-5 h-5 text-white" />
                          </div>
                          <div>
                            <p className="font-semibold text-slate-800">{item.symbol}</p>
                            <p className="text-sm text-slate-500">{item.exchange} • Token: {item.symbol_token}</p>
                          </div>
                        </div>
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
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Logs */}
          <TabsContent value="logs">
            <Card className="bg-white/90 backdrop-blur border-slate-200">
              <CardHeader>
                <CardTitle>Analysis Logs</CardTitle>
                <CardDescription>Recent LLM analysis results</CardDescription>
              </CardHeader>
              <CardContent>
                {logs.length === 0 ? (
                  <div className="text-center py-12">
                    <BarChart3 className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-500 text-lg mb-2">No analyses yet</p>
                    <p className="text-slate-400 text-sm">Trigger an analysis to see results</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {logs.map((log) => (
                      <div
                        key={log.id}
                        data-testid={`log-${log.id}`}
                        className="p-4 rounded-lg border border-slate-200 bg-white hover:shadow-md transition-shadow"
                      >
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <Badge
                              data-testid={`signal-badge-${log.id}`}
                              className={`${
                                log.signal === 'BUY'
                                  ? 'bg-green-100 text-green-800'
                                  : log.signal === 'SELL'
                                  ? 'bg-red-100 text-red-800'
                                  : 'bg-slate-100 text-slate-800'
                              }`}
                            >
                              {log.signal || 'N/A'}
                            </Badge>
                            <span className="font-semibold text-slate-800">{log.symbol}</span>
                          </div>
                          <span className="text-xs text-slate-500">
                            {new Date(log.timestamp).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-sm text-slate-600 mb-2">{log.analysis_summary}</p>
                        <details className="text-xs text-slate-500">
                          <summary className="cursor-pointer hover:text-slate-700">View full analysis</summary>
                          <div className="mt-2 p-3 bg-slate-50 rounded border border-slate-200">
                            <pre className="whitespace-pre-wrap">{log.llm_response}</pre>
                          </div>
                        </details>
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
