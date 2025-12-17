'use client';

/**
 * Dashboard Page
 */

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api, Signal, Alert, User } from '@/lib/api';
import {
  Activity, LogOut, RefreshCw, ArrowUp, ArrowDown, Minus,
  Bell, Clock, Target, Wifi, WifiOff
} from 'lucide-react';
import { format } from 'date-fns';
import clsx from 'clsx';

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isConnected, setIsConnected] = useState(false);
  const [selectedScanner, setSelectedScanner] = useState<string | null>(null);
  const [isRealtime, setIsRealtime] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [signalsData, alertsData] = await Promise.all([
        api.getSignals({ scanner_type: selectedScanner || undefined }),
        api.getAlerts().catch(() => []),
      ]);
      setSignals(signalsData.signals);
      setIsRealtime(signalsData.is_realtime);
      setAlerts(alertsData);
    } catch (err) {
      console.error('Failed to fetch data:', err);
    }
  }, [selectedScanner]);

  useEffect(() => {
    // Check auth
    const token = api.getToken();
    if (!token) {
      router.push('/login');
      return;
    }

    // Fetch profile
    api.getProfile()
      .then(setUser)
      .catch(() => {
        api.logout();
        router.push('/login');
      });

    // Fetch initial data
    fetchData().finally(() => setIsLoading(false));

    // Set up polling
    const interval = setInterval(fetchData, 10000);

    // Set up WebSocket
    const ws = api.createWebSocket((data: unknown) => {
      const msg = data as { type: string; data: Signal | Alert };
      if (msg.type === 'signal') {
        setSignals(prev => [msg.data as Signal, ...prev.slice(0, 99)]);
      } else if (msg.type === 'alert') {
        setAlerts(prev => [msg.data as Alert, ...prev.slice(0, 49)]);
      }
    });

    if (ws) {
      ws.onopen = () => setIsConnected(true);
      ws.onclose = () => setIsConnected(false);
    }

    return () => {
      clearInterval(interval);
      ws?.close();
    };
  }, [router, fetchData]);

  const handleLogout = () => {
    api.logout();
    router.push('/login');
  };

  const scannerTypes = [
    { id: null, name: 'All' },
    { id: 'momentum', name: 'Momentum' },
    { id: 'breakout', name: 'Breakout' },
    { id: 'reversal', name: 'Reversal' },
    { id: 'options_flow', name: 'Options' },
    { id: 'squeeze', name: 'Squeeze' },
  ];

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-scanify-primary/30 border-t-scanify-primary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="h-14 bg-scanify-dark-800 border-b border-scanify-dark-600 flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-gradient-to-br from-scanify-primary to-scanify-secondary rounded-lg flex items-center justify-center">
            <Activity className="w-5 h-5 text-white" />
          </div>
          <span className="text-lg font-bold text-white">Scanify</span>
        </div>

        <div className="flex items-center gap-4">
          {isConnected ? (
            <div className="flex items-center gap-1 text-green-400 text-sm">
              <Wifi className="w-4 h-4" />
              <span>Live</span>
            </div>
          ) : (
            <div className="flex items-center gap-1 text-gray-500 text-sm">
              <WifiOff className="w-4 h-4" />
              <span>Offline</span>
            </div>
          )}

          {!isRealtime && (
            <span className="text-xs text-yellow-500 bg-yellow-900/30 px-2 py-1 rounded">
              Delayed
            </span>
          )}

          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-400">{user?.email}</span>
            <span className="text-scanify-primary capitalize">{user?.tier}</span>
          </div>

          <button onClick={handleLogout} className="p-2 hover:bg-scanify-dark-700 rounded-lg">
            <LogOut className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 p-4 overflow-hidden flex flex-col gap-4">
        {/* Scanner Filter */}
        <div className="flex items-center justify-between">
          <div className="flex gap-2">
            {scannerTypes.map((scanner) => (
              <button
                key={scanner.id || 'all'}
                onClick={() => setSelectedScanner(scanner.id)}
                className={clsx(
                  'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                  selectedScanner === scanner.id
                    ? 'bg-scanify-primary text-white'
                    : 'bg-scanify-dark-700 text-gray-400 hover:bg-scanify-dark-600'
                )}
              >
                {scanner.name}
              </button>
            ))}
          </div>

          <button onClick={fetchData} className="btn-secondary flex items-center gap-2">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>

        {/* Content Grid */}
        <div className="flex-1 grid grid-cols-12 gap-4 min-h-0">
          {/* Signals Table */}
          <div className="col-span-8 card overflow-hidden flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-400 uppercase">Live Signals</h2>
              <span className="text-scanify-primary text-sm">{signals.length} signals</span>
            </div>

            <div className="flex-1 overflow-auto">
              <table className="w-full">
                <thead className="sticky top-0 bg-scanify-dark-800">
                  <tr className="text-left text-xs text-gray-500 uppercase">
                    <th className="pb-2 pr-4">Time</th>
                    <th className="pb-2 pr-4">Symbol</th>
                    <th className="pb-2 pr-4">Scanner</th>
                    <th className="pb-2 pr-4">Direction</th>
                    <th className="pb-2 pr-4">Confidence</th>
                    <th className="pb-2 pr-4">Entry</th>
                    <th className="pb-2">R:R</th>
                  </tr>
                </thead>
                <tbody>
                  {signals.map((signal) => (
                    <tr key={signal.id} className="border-b border-scanify-dark-700 hover:bg-scanify-dark-700/50">
                      <td className="py-3 pr-4 text-sm text-gray-400">
                        <div className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {format(new Date(signal.timestamp), 'HH:mm:ss')}
                        </div>
                      </td>
                      <td className="py-3 pr-4 font-semibold text-white">{signal.symbol}</td>
                      <td className="py-3 pr-4">
                        <span className="badge bg-scanify-dark-600 text-gray-300">
                          {signal.scanner_type.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="py-3 pr-4">
                        <div className={clsx(
                          'flex items-center gap-1 font-medium',
                          signal.direction === 'LONG' ? 'text-green-400' : signal.direction === 'SHORT' ? 'text-red-400' : 'text-gray-400'
                        )}>
                          {signal.direction === 'LONG' ? <ArrowUp className="w-4 h-4" /> : signal.direction === 'SHORT' ? <ArrowDown className="w-4 h-4" /> : <Minus className="w-4 h-4" />}
                          {signal.direction}
                        </div>
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <div className="w-12 h-1.5 bg-scanify-dark-600 rounded-full overflow-hidden">
                            <div
                              className={clsx('h-full', signal.confidence >= 85 ? 'bg-green-500' : signal.confidence >= 70 ? 'bg-yellow-500' : 'bg-gray-500')}
                              style={{ width: `${signal.confidence}%` }}
                            />
                          </div>
                          <span className="text-sm">{signal.confidence.toFixed(0)}%</span>
                        </div>
                      </td>
                      <td className="py-3 pr-4 text-sm">${signal.entry_price?.toFixed(2) || '-'}</td>
                      <td className="py-3 text-sm">
                        {signal.risk_reward ? `${signal.risk_reward.toFixed(1)}:1` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {signals.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                  <Activity className="w-8 h-8 mb-2 opacity-50" />
                  <p>No signals yet</p>
                </div>
              )}
            </div>
          </div>

          {/* Alerts */}
          <div className="col-span-4 card overflow-hidden flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-400 uppercase">Alerts</h2>
              <span className="badge bg-cyan-900/50 text-cyan-400">{alerts.length}</span>
            </div>

            <div className="flex-1 overflow-auto space-y-2">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className={clsx(
                    'p-3 rounded-lg border-l-4',
                    alert.priority === 'critical' ? 'border-l-red-500 bg-red-900/10' :
                    alert.priority === 'high' ? 'border-l-orange-500 bg-orange-900/10' :
                    'border-l-blue-500 bg-blue-900/10'
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Bell className="w-4 h-4 text-gray-400" />
                    {alert.symbol && <span className="font-semibold text-white">{alert.symbol}</span>}
                  </div>
                  <p className="text-sm text-gray-300">{alert.message}</p>
                  <span className="text-xs text-gray-500">
                    {format(new Date(alert.created_at), 'HH:mm:ss')}
                  </span>
                </div>
              ))}

              {alerts.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-gray-500">
                  <Bell className="w-8 h-8 mb-2 opacity-50" />
                  <p className="text-sm">No alerts</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
