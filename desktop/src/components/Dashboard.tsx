/**
 * Dashboard Component
 *
 * Main dashboard layout with signal table, alerts, and scanner stats.
 */

import { useEffect } from 'react';
import { useStore } from '../lib/store';
import SignalTable from './SignalTable';
import AlertFeed from './AlertFeed';
import ScannerStats from './ScannerStats';
import { RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import styles from './Dashboard.module.css';

export default function Dashboard() {
  const { fetchSignals, fetchAlerts, isLoading, selectedScanner, setSelectedScanner } = useStore();

  useEffect(() => {
    fetchSignals();
    fetchAlerts();

    // Auto-refresh every 10 seconds
    const interval = setInterval(() => {
      fetchSignals();
      fetchAlerts();
    }, 10000);

    return () => clearInterval(interval);
  }, [fetchSignals, fetchAlerts]);

  const scannerTypes = [
    { id: null, name: 'All Scanners' },
    { id: 'momentum', name: 'Momentum' },
    { id: 'breakout', name: 'Breakout' },
    { id: 'reversal', name: 'Reversal' },
    { id: 'options_flow', name: 'Options Flow' },
    { id: 'squeeze', name: 'Squeeze' },
    { id: 'gamma', name: 'Gamma' },
    { id: 'mtf', name: 'Multi-TF' },
  ];

  return (
    <div className={styles.dashboardWrapper}>
      {/* Top Bar - Scanner Filters */}
      <div className={styles.topBar}>
        <div className={styles.filterGroup}>
          {scannerTypes.map((scanner) => (
            <button
              key={scanner.id || 'all'}
              onClick={() => setSelectedScanner(scanner.id)}
              className={clsx(
                styles.filterButton,
                selectedScanner === scanner.id
                  ? styles.filterButtonActive
                  : styles.filterButtonInactive
              )}
            >
              {scanner.name}
            </button>
          ))}
        </div>

        <button
          onClick={() => fetchSignals()}
          disabled={isLoading}
          className={clsx('btn-secondary', styles.refreshButton)}
        >
          <RefreshCw className={clsx('w-4 h-4', isLoading && 'animate-spin')} />
          Refresh
        </button>
      </div>

      {/* Main Content Grid */}
      <div className={styles.contentGrid}>
        {/* Left Column - Signal Table */}
        <div className={styles.leftColumn}>
          <SignalTable />
        </div>

        {/* Right Column - Alerts & Stats */}
        <div className={styles.rightColumn}>
          <div className={styles.alertSection}>
            <AlertFeed />
          </div>
          <div className={styles.statsSection}>
            <ScannerStats />
          </div>
        </div>
      </div>
    </div>
  );
}
