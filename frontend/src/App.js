import React, { useState, useEffect } from 'react';
import '@/App.css';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import { Activity, Bot, Settings, TrendingUp, BarChart3, Bell, Plus, Trash2, Play, RefreshCw, Brain, Wallet, Edit2, Send } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
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
  const [portfolio, setPortfolio] = useState({ holdings: [], positions: [] });
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [newItem, setNewItem] = useState({ symbol: '', exchange: 'NSE', symbol_token: '', action: 'hold' });
  const [notificationMessage, setNotificationMessage] = useState('');

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const [statusRes, configRes, watchlistRes, portfolioRes, logsRes] = await Promise.all([
        axios.get(`${API}/status`),
        axios.get(`${API}/config`),
        axios.get(`${API}/watchlist`),
        axios.get(`${API}/portfolio`),
        axios.get(`${API}/logs?limit=20`)
      ]);
      
      setStatus(statusRes.data);
      setConfig(configRes.data);
      setWatchlist(watchlistRes.data);
      setPortfolio(portfolioRes.data);
      setLogs(logsRes.data);
      setLoading(false);
    } catch (error) {
      console.error('Error:', error);
      toast.error('Failed to fetch data');
      setLoading(false);
    }
  };

  const updateConfig = async (updates) => {
    try {
      await axios.put(`${API}/config`, { ...config, ...updates });
      setConfig({ ...config, ...updates });
      toast.success('Configuration updated');
      fetchData();
    } catch (error) {
      toast.error('Failed to update');
    }
  };

  const addItem = async () => {
    if (!newItem.symbol || !newItem.symbol_token) {
      toast.error('Enter symbol and token');
      return;
    }
    try {
      await axios.post(`${API}/watchlist`, newItem);
      toast.success('Added successfully');
      setNewItem({ symbol: '', exchange: 'NSE', symbol_token: '', action: 'hold' });
      setShowAddDialog(false);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add');
    }
  };

  const updateItem = async () => {
    try {
      await axios.put(`${API}/watchlist/${editingItem.symbol}`, editingItem);
      toast.success('Updated successfully');
      setShowEditDialog(false);
      setEditingItem(null);
      fetchData();
    } catch (error) {
      toast.error('Failed to update');
    }
  };

  const deleteItem = async (symbol) => {
    try {
      await axios.delete(`${API}/watchlist/${symbol}`);
      toast.success('Removed successfully');
      fetchData();
    } catch (error) {
      toast.error('Failed to remove');
    }
  };

  const sendNotification = async () => {
    if (!notificationMessage) {
      toast.error('Enter message');
      return;
    }
    try {
      await axios.post(`${API}/send-notification`, { message: notificationMessage });
      toast.success('Notification sent!');
      setNotificationMessage('');
    } catch (error) {
      toast.error('Failed to send');
    }
  };

  const triggerBot = async () => {
    try {
      await axios.post(`${API}/run-bot`);
      toast.success('Bot triggered! Check logs shortly.');
      setTimeout(fetchData, 3000);
    } catch (error) {
      toast.error('Failed to trigger bot');
    }
  };

  const formatCurrency = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(value);

  const calculatePortfolioValue = () => {
    return portfolio.holdings.reduce((sum, h) => sum + (parseFloat(h.ltp || 0) * parseInt(h.quantity || 0)), 0);
  };

  // Merge portfolio holdings with watchlist
  const mergedItems = [...watchlist];
  portfolio.holdings.forEach(holding => {
    const exists = watchlist.find(w => w.symbol === holding.tradingsymbol);
    if (!exists) {
      mergedItems.push({
        symbol: holding.tradingsymbol,
        exchange: holding.exchange,
        symbol_token: holding.symboltoken || '',
        action: 'hold',
        quantity: parseInt(holding.quantity || 0),
        avg_price: parseFloat(holding.averageprice || 0),
        id: `portfolio_${holding.tradingsymbol}`
      });
    }
  });

  if (loading) {
    return (
      <div className=\"min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50\">
        <div className=\"text-center\">
          <RefreshCw className=\"w-12 h-12 animate-spin text-blue-600 mx-auto mb-4\" />
          <p className=\"text-slate-600 text-lg\">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className=\"min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50\">
      <Toaster position=\"top-right\" richColors />
      
      <header className=\"bg-white/80 backdrop-blur-lg border-b border-slate-200 sticky top-0 z-50\">
        <div className=\"max-w-7xl mx-auto px-6 py-4\">
          <div className=\"flex items-center justify-between\">
            <div className=\"flex items-center gap-3\">
              <div className=\"w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center\">
                <Bot className=\"w-6 h-6 text-white\" />
              </div>
              <div>
                <h1 className=\"text-2xl font-bold text-slate-800\" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>AI Trading Bot</h1>
                <p className=\"text-sm text-slate-500\">Auto-Invest System</p>
              </div>
            </div>
            <div className=\"flex items-center gap-4\">
              <div className=\"flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100\">
                <Activity className={`w-4 h-4 ${status.bot_active ? 'text-green-500 animate-pulse' : 'text-slate-400'}`} />
                <span className=\"text-sm font-medium\">{status.bot_active ? 'Active' : 'Inactive'}</span>
              </div>
              <div className=\"flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100\">
                <Bot className={`w-4 h-4 ${status.angel_one_connected ? 'text-yellow-500' : 'text-slate-400'}`} />
                <span className=\"text-sm font-medium\">{status.angel_one_connected ? 'Connected' : 'Disconnected'}</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className=\"max-w-7xl mx-auto px-6 py-8\">
        <div className=\"grid grid-cols-1 md:grid-cols-4 gap-6 mb-8\">
          <Card className=\"bg-white/90 backdrop-blur\">
            <CardHeader className=\"pb-3\">
              <CardTitle className=\"text-lg flex items-center gap-2\"><Wallet className=\"w-5 h-5 text-green-600\" />Portfolio</CardTitle>
            </CardHeader>
            <CardContent>
              <p className=\"text-3xl font-bold text-green-600\" style={{ fontFamily: 'Space Grotesk' }}>{formatCurrency(calculatePortfolioValue())}</p>
              <p className=\"text-sm text-slate-500\">{portfolio.holdings.length} holdings</p>
            </CardContent>
          </Card>
          <Card className=\"bg-white/90\">
            <CardHeader className=\"pb-3\"><CardTitle className=\"text-lg\">Watchlist</CardTitle></CardHeader>
            <CardContent>
              <p className=\"text-3xl font-bold text-blue-600\" style={{ fontFamily: 'Space Grotesk' }}>{watchlist.length}</p>
              <p className=\"text-sm text-slate-500\">Items</p>
            </CardContent>
          </Card>
          <Card className=\"bg-white/90\">
            <CardHeader className=\"pb-3\"><CardTitle className=\"text-lg\">Analyses</CardTitle></CardHeader>
            <CardContent>
              <p className=\"text-3xl font-bold text-indigo-600\" style={{ fontFamily: 'Space Grotesk' }}>{status.total_analyses || 0}</p>
            </CardContent>
          </Card>
          <Card className=\"bg-white/90\">
            <CardHeader className=\"pb-3\"><CardTitle className=\"text-lg\">Schedule</CardTitle></CardHeader>
            <CardContent>
              <p className=\"text-3xl font-bold text-green-600\" style={{ fontFamily: 'Space Grotesk' }}>{config?.schedule_minutes || 0}m</p>
            </CardContent>
          </Card>
        </div>

        <Tabs defaultValue=\"watchlist\" className=\"space-y-6\">
          <TabsList className=\"bg-white/90 backdrop-blur border p-1\">
            <TabsTrigger value=\"watchlist\"><TrendingUp className=\"w-4 h-4 mr-2\" />Watchlist & Strategy</TabsTrigger>
            <TabsTrigger value=\"control\"><Settings className=\"w-4 h-4 mr-2\" />Control Panel</TabsTrigger>
            <TabsTrigger value=\"notifications\"><Bell className=\"w-4 h-4 mr-2\" />Notifications</TabsTrigger>
            <TabsTrigger value=\"logs\"><BarChart3 className=\"w-4 h-4 mr-2\" />Logs</TabsTrigger>
          </TabsList>

          {/* Watchlist Tab */}
          <TabsContent value=\"watchlist\">
            <Card className=\"bg-white/90\">
              <CardHeader>
                <div className=\"flex items-center justify-between\">
                  <div>
                    <CardTitle>Watchlist & Trading Strategy</CardTitle>
                    <CardDescription>Portfolio items + watchlist with action settings</CardDescription>
                  </div>
                  <Button onClick={() => setShowAddDialog(true)}><Plus className=\"w-4 h-4 mr-2\" />Add Symbol</Button>
                </div>
              </CardHeader>
              <CardContent>
                {mergedItems.length === 0 ? (
                  <div className=\"text-center py-12\">
                    <TrendingUp className=\"w-16 h-16 text-slate-300 mx-auto mb-4\" />
                    <p className=\"text-slate-500\">No items yet</p>
                  </div>
                ) : (
                  <div className=\"space-y-3\">
                    {mergedItems.map((item) => {
                      const holding = portfolio.holdings.find(h => h.tradingsymbol === item.symbol);
                      const ltp = holding ? parseFloat(holding.ltp || 0) : 0;
                      const avgPrice = item.avg_price || (holding ? parseFloat(holding.averageprice || 0) : 0);
                      const qty = item.quantity || (holding ? parseInt(holding.quantity || 0) : 0);
                      const pnl = avgPrice > 0 ? ((ltp - avgPrice) / avgPrice) * 100 : 0;

                      return (
                        <div key={item.id || item.symbol} className=\"p-4 rounded-lg border bg-white\">
                          <div className=\"flex items-center justify-between mb-3\">
                            <div className=\"flex-1\">
                              <div className=\"flex items-center gap-2\">
                                <h3 className=\"font-bold text-lg\">{item.symbol}</h3>
                                <Badge variant={item.action === 'sip' ? 'default' : item.action === 'buy' ? 'secondary' : item.action === 'sell' ? 'destructive' : 'outline'}>
                                  {item.action.toUpperCase()}
                                </Badge>
                                {holding && <Badge className=\"bg-green-100 text-green-800\">In Portfolio</Badge>}
                              </div>
                              <p className=\"text-sm text-slate-500\">{item.exchange} • {item.symbol_token}</p>
                            </div>
                            <div className=\"flex gap-2\">
                              <Button variant=\"ghost\" size=\"icon\" onClick={() => { setEditingItem(item); setShowEditDialog(true); }}>
                                <Edit2 className=\"w-4 h-4\" />
                              </Button>
                              <Button variant=\"ghost\" size=\"icon\" onClick={() => deleteItem(item.symbol)} className=\"text-red-600\">
                                <Trash2 className=\"w-4 h-4\" />
                              </Button>
                            </div>
                          </div>
                          {holding && (
                            <div className=\"grid grid-cols-4 gap-4 text-sm border-t pt-3\">
                              <div><p className=\"text-slate-500\">Qty</p><p className=\"font-semibold\">{qty}</p></div>
                              <div><p className=\"text-slate-500\">Avg</p><p className=\"font-semibold\">{formatCurrency(avgPrice)}</p></div>
                              <div><p className=\"text-slate-500\">LTP</p><p className=\"font-semibold\">{formatCurrency(ltp)}</p></div>
                              <div><p className=\"text-slate-500\">P&L</p><p className={`font-semibold ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>{pnl.toFixed(2)}%</p></div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Control Panel */}
          <TabsContent value=\"control\" className=\"space-y-6\">
            <Card className=\"bg-white/90\">
              <CardHeader><CardTitle>Bot Control</CardTitle></CardHeader>
              <CardContent className=\"space-y-6\">
                <div className=\"flex items-center justify-between p-4 rounded-lg bg-slate-50\">
                  <div><Label className=\"font-semibold\">Bot Active</Label></div>
                  <Switch checked={config?.is_active || false} onCheckedChange={(c) => updateConfig({ is_active: c })} />
                </div>
                <div className=\"flex items-center justify-between p-4 rounded-lg bg-yellow-50 border border-yellow-200\">
                  <div><Label className=\"font-semibold text-yellow-800\">Auto Execute Trades</Label><p className=\"text-sm text-yellow-700\">\u26a0\ufe0f Will execute real orders</p></div>
                  <Switch checked={config?.auto_execute_trades || false} onCheckedChange={(c) => updateConfig({ auto_execute_trades: c })} />
                </div>
                <Separator />
                <div className=\"space-y-4\">
                  <Label className=\"font-semibold\">Schedule (minutes)</Label>
                  <div className=\"flex items-center gap-4\">
                    <Slider value={[config?.schedule_minutes || 30]} onValueChange={([v]) => updateConfig({ schedule_minutes: v })} min={5} max={180} step={5} className=\"flex-1\" />
                    <span className=\"text-lg font-bold text-blue-600 min-w-[80px] text-right\">{config?.schedule_minutes || 30} min</span>
                  </div>
                </div>
                <div className=\"flex gap-3\">
                  <Button onClick={triggerBot} className=\"flex-1 bg-gradient-to-r from-blue-600 to-indigo-600\"><Play className=\"w-4 h-4 mr-2\" />Run Now</Button>
                  <Button onClick={fetchData} variant=\"outline\"><RefreshCw className=\"w-4 h-4\" /></Button>
                </div>
              </CardContent>
            </Card>

            <Card className=\"bg-white/90\">
              <CardHeader><CardTitle className=\"flex items-center gap-2\"><Brain className=\"w-5 h-5\" />LLM Configuration</CardTitle></CardHeader>
              <CardContent className=\"space-y-4\">
                <div className=\"grid grid-cols-2 gap-4\">
                  <div className=\"space-y-2\">
                    <Label>Provider</Label>
                    <Select value={config?.llm_provider || 'emergent'} onValueChange={(v) => updateConfig({ llm_provider: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value=\"emergent\">Emergent LLM</SelectItem><SelectItem value=\"openai\">OpenAI</SelectItem></SelectContent>
                    </Select>
                  </div>
                  <div className=\"space-y-2\">
                    <Label>Model</Label>
                    <Select value={config?.llm_model || 'gpt-4o-mini'} onValueChange={(v) => updateConfig({ llm_model: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value=\"gpt-4o-mini\">GPT-4o Mini</SelectItem><SelectItem value=\"gpt-4o\">GPT-4o</SelectItem><SelectItem value=\"gpt-5\">GPT-5</SelectItem></SelectContent>
                    </Select>
                  </div>
                </div>
                {config?.llm_provider === 'openai' && (
                  <Input type=\"password\" placeholder=\"OpenAI API Key\" value={config?.openai_api_key || ''} onChange={(e) => updateConfig({ openai_api_key: e.target.value })} />
                )}
              </CardContent>
            </Card>

            <Card className=\"bg-white/90\">
              <CardHeader><CardTitle>Analysis Parameters</CardTitle><CardDescription>Tell LLM what to consider (free text)</CardDescription></CardHeader>
              <CardContent>
                <Textarea 
                  rows={4} 
                  placeholder=\"e.g., Consider P/E ratio below 25, RSI oversold conditions, volume spike above 50%, resistance levels, market sentiment...\"
                  value={config?.analysis_parameters || ''}
                  onChange={(e) => updateConfig({ analysis_parameters: e.target.value })}
                  className=\"w-full\"
                />
              </CardContent>
            </Card>

            <Card className=\"bg-white/90\">
              <CardHeader><CardTitle>Telegram</CardTitle></CardHeader>
              <CardContent className=\"space-y-4\">
                <div className=\"flex items-center justify-between p-4 rounded-lg bg-slate-50\">
                  <Label>Enable Notifications</Label>
                  <Switch checked={config?.enable_notifications || false} onCheckedChange={(c) => updateConfig({ enable_notifications: c })} />
                </div>
                <Input placeholder=\"Bot Token\" type=\"password\" value={config?.telegram_bot_token || ''} onChange={(e) => updateConfig({ telegram_bot_token: e.target.value })} />
                <Input placeholder=\"Chat IDs (comma separated)\" value={config?.telegram_chat_ids?.join(', ') || ''} onChange={(e) => updateConfig({ telegram_chat_ids: e.target.value.split(',').map(id => id.trim()).filter(Boolean) })} />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Notifications Tab */}
          <TabsContent value=\"notifications\">
            <Card className=\"bg-white/90\">
              <CardHeader><CardTitle className=\"flex items-center gap-2\"><Bell className=\"w-5 h-5 text-yellow-600\" />Send Notification</CardTitle><CardDescription>Trigger manual Telegram notification</CardDescription></CardHeader>
              <CardContent className=\"space-y-4\">
                <Textarea 
                  rows={6}
                  placeholder=\"Enter your notification message...\"
                  value={notificationMessage}
                  onChange={(e) => setNotificationMessage(e.target.value)}
                  className=\"w-full\"
                />
                <Button onClick={sendNotification} className=\"w-full\"><Send className=\"w-4 h-4 mr-2\" />Send Notification</Button>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Logs Tab */}
          <TabsContent value=\"logs\">
            <Card className=\"bg-white/90\">
              <CardHeader><CardTitle>Analysis Logs</CardTitle><CardDescription>Recent bot decisions and actions</CardDescription></CardHeader>
              <CardContent>
                {logs.length === 0 ? (
                  <div className=\"text-center py-12\"><BarChart3 className=\"w-16 h-16 text-slate-300 mx-auto mb-4\" /><p className=\"text-slate-500\">No logs yet</p></div>
                ) : (
                  <div className=\"space-y-4\">
                    {logs.map((log) => (
                      <div key={log.id} className=\"p-4 rounded-lg border bg-white\">
                        <div className=\"flex items-start justify-between mb-2\">
                          <div className=\"flex items-center gap-3\">
                            <Badge className={log.executed ? 'bg-green-100 text-green-800' : 'bg-slate-100'}>{log.llm_decision}</Badge>
                            <span className=\"font-semibold\">{log.symbol}</span>
                            <Badge variant=\"outline\">{log.action.toUpperCase()}</Badge>
                            {log.executed && <Badge className=\"bg-blue-100 text-blue-800\">EXECUTED</Badge>}
                          </div>
                          <span className=\"text-xs text-slate-500\">{new Date(log.timestamp).toLocaleString()}</span>
                        </div>
                        {log.order_id && <p className=\"text-xs text-slate-600 mb-2\">Order ID: {log.order_id}</p>}
                        {log.error && <p className=\"text-xs text-red-600\">Error: {log.error}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>

      {/* Add Item Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add Symbol</DialogTitle></DialogHeader>
          <div className=\"space-y-4 pt-4\">
            <Input placeholder=\"Symbol (e.g., RELIANCE)\" value={newItem.symbol} onChange={(e) => setNewItem({...newItem, symbol: e.target.value})} />
            <Select value={newItem.exchange} onValueChange={(v) => setNewItem({...newItem, exchange: v})}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value=\"NSE\">NSE</SelectItem><SelectItem value=\"BSE\">BSE</SelectItem></SelectContent>
            </Select>
            <Input placeholder=\"Symbol Token\" value={newItem.symbol_token} onChange={(e) => setNewItem({...newItem, symbol_token: e.target.value})} />
            <Select value={newItem.action} onValueChange={(v) => setNewItem({...newItem, action: v})}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value=\"hold\">Hold</SelectItem><SelectItem value=\"sip\">SIP</SelectItem><SelectItem value=\"buy\">Buy</SelectItem><SelectItem value=\"sell\">Sell</SelectItem></SelectContent>
            </Select>
            <Button onClick={addItem} className=\"w-full\">Add to Watchlist</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Item Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className=\"max-w-2xl\">
          <DialogHeader><DialogTitle>Edit: {editingItem?.symbol}</DialogTitle></DialogHeader>
          {editingItem && (
            <div className=\"space-y-4 pt-4\">
              <div className=\"space-y-2\">
                <Label>Action</Label>
                <Select value={editingItem.action} onValueChange={(v) => setEditingItem({...editingItem, action: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value=\"hold\">Hold</SelectItem><SelectItem value=\"sip\">SIP</SelectItem><SelectItem value=\"buy\">Buy</SelectItem><SelectItem value=\"sell\">Sell</SelectItem></SelectContent>
                </Select>
              </div>
              {editingItem.action === 'sip' && (
                <>
                  <div className=\"space-y-2\"><Label>SIP Amount (₹)</Label><Input type=\"number\" value={editingItem.sip_amount || 0} onChange={(e) => setEditingItem({...editingItem, sip_amount: parseFloat(e.target.value)})} /></div>
                  <div className=\"space-y-2\"><Label>Frequency (days)</Label><Input type=\"number\" value={editingItem.sip_frequency_days || 30} onChange={(e) => setEditingItem({...editingItem, sip_frequency_days: parseInt(e.target.value)})} /></div>
                </>
              )}
              {editingItem.action === 'buy' && (
                <div className=\"space-y-2\"><Label>Quantity</Label><Input type=\"number\" value={editingItem.quantity || 1} onChange={(e) => setEditingItem({...editingItem, quantity: parseInt(e.target.value)})} /></div>
              )}
              <div className=\"space-y-2\"><Label>Notes</Label><Textarea rows={3} value={editingItem.notes || ''} onChange={(e) => setEditingItem({...editingItem, notes: e.target.value})} /></div>
              <Button onClick={updateItem} className=\"w-full\">Save Changes</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default App;
