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
import styles from './page.module.css';

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
      <div className={styles.loadingScreen}>
        <div className={styles.loadingSpinner} />
      </div>
    );
  }

  return (
    <div className={styles.dashboardPage}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerLogo}>
          <div className={styles.headerLogoIcon}>
            <Activity className={styles.headerLogoIconImg} />
          </div>
          <span className={styles.headerLogoText}>Scanify</span>
        </div>

        <div className={styles.headerRight}>
          {isConnected ? (
            <div className={styles.statusOnline}>
              <Wifi className={styles.statusOnlineIcon} />
              <span>Live</span>
            </div>
          ) : (
            <div className={styles.statusOffline}>
              <WifiOff className={styles.statusOfflineIcon} />
              <span>Offline</span>
            </div>
          )}

          {!isRealtime && (
            <span className={styles.delayedBadge}>
              Delayed
            </span>
          )}

          <div className={styles.userInfo}>
            <span className={styles.userEmail}>{user?.email}</span>
            <span className={styles.userTier}>{user?.tier}</span>
          </div>

          <button onClick={handleLogout} className={styles.logoutButton}>
            <LogOut className={styles.logoutIcon} />
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className={styles.main}>
        {/* Scanner Filter */}
        <div className={styles.filterBar}>
          <div className={styles.scannerTabs}>
            {scannerTypes.map((scanner) => (
              <button
                key={scanner.id || 'all'}
                onClick={() => setSelectedScanner(scanner.id)}
                className={clsx(
                  styles.scannerTab,
                  selectedScanner === scanner.id
                    ? styles.scannerTabActive
                    : styles.scannerTabInactive
                )}
              >
                {scanner.name}
              </button>
            ))}
          </div>

          <button onClick={fetchData} className={`btn-secondary ${styles.refreshButton}`}>
            <RefreshCw className={styles.refreshIcon} />
            Refresh
          </button>
        </div>

        {/* Content Grid */}
        <div className={styles.contentGrid}>
          {/* Signals Table */}
          <div className={`card ${styles.signalsPanel}`}>
            <div className={styles.panelHeader}>
              <h2 className={styles.panelTitle}>Live Signals</h2>
              <span className={styles.signalCount}>{signals.length} signals</span>
            </div>

            <div className={styles.tableWrapper}>
              <table className={styles.signalsTable}>
                <thead className={styles.tableHead}>
                  <tr>
                    <th className={styles.tableHeadCell}>Time</th>
                    <th className={styles.tableHeadCell}>Symbol</th>
                    <th className={styles.tableHeadCell}>Scanner</th>
                    <th className={styles.tableHeadCell}>Direction</th>
                    <th className={styles.tableHeadCell}>Confidence</th>
                    <th className={styles.tableHeadCell}>Entry</th>
                    <th className={styles.tableHeadCell}>R:R</th>
                  </tr>
                </thead>
                <tbody>
                  {signals.map((signal) => (
                    <tr key={signal.id} className={styles.signalRow}>
                      <td className={styles.timeCell}>
                        <div className={styles.timeCellInner}>
                          <Clock className={styles.timeIcon} />
                          {format(new Date(signal.timestamp), 'HH:mm:ss')}
                        </div>
                      </td>
                      <td className={styles.symbolCell}>{signal.symbol}</td>
                      <td className={styles.scannerCell}>
                        <span className={`badge ${styles.scannerBadge}`}>
                          {signal.scanner_type.replace('_', ' ')}
                        </span>
                      </td>
                      <td className={styles.directionCell}>
                        <div className={clsx(
                          styles.directionInner,
                          signal.direction === 'LONG' ? styles.directionLong : signal.direction === 'SHORT' ? styles.directionShort : styles.directionNeutral
                        )}>
                          {signal.direction === 'LONG' ? <ArrowUp className={styles.directionIcon} /> : signal.direction === 'SHORT' ? <ArrowDown className={styles.directionIcon} /> : <Minus className={styles.directionIcon} />}
                          {signal.direction}
                        </div>
                      </td>
                      <td className={styles.confidenceCell}>
                        <div className={styles.confidenceInner}>
                          <div className={styles.confidenceBarBg}>
                            <div
                              className={signal.confidence >= 85 ? styles.confidenceBarHigh : signal.confidence >= 70 ? styles.confidenceBarMed : styles.confidenceBarLow}
                              style={{ width: `${signal.confidence}%` }}
                            />
                          </div>
                          <span className={styles.confidenceText}>{signal.confidence.toFixed(0)}%</span>
                        </div>
                      </td>
                      <td className={styles.entryCell}>${signal.entry_price?.toFixed(2) || '-'}</td>
                      <td className={styles.rrCell}>
                        {signal.risk_reward ? `${signal.risk_reward.toFixed(1)}:1` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {signals.length === 0 && (
                <div className={styles.emptyState}>
                  <Activity className={styles.emptyIcon} />
                  <p>No signals yet</p>
                </div>
              )}
            </div>
          </div>

          {/* Alerts */}
          <div className={`card ${styles.alertsPanel}`}>
            <div className={styles.panelHeader}>
              <h2 className={styles.panelTitle}>Alerts</h2>
              <span className={`badge ${styles.alertsBadge}`}>{alerts.length}</span>
            </div>

            <div className={styles.alertsList}>
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className={clsx(
                    styles.alertItem,
                    alert.priority === 'critical' ? styles.alertCritical :
                    alert.priority === 'high' ? styles.alertHigh :
                    styles.alertNormal
                  )}
                >
                  <div className={styles.alertHeader}>
                    <Bell className={styles.alertBellIcon} />
                    {alert.symbol && <span className={styles.alertSymbol}>{alert.symbol}</span>}
                  </div>
                  <p className={styles.alertMessage}>{alert.message}</p>
                  <span className={styles.alertTime}>
                    {format(new Date(alert.created_at), 'HH:mm:ss')}
                  </span>
                </div>
              ))}

              {alerts.length === 0 && (
                <div className={styles.alertsEmpty}>
                  <Bell className={styles.alertsEmptyIcon} />
                  <p className={styles.alertsEmptyText}>No alerts</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
