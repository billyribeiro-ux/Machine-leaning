/**
 * Scanner Stats Component
 *
 * Overview of scanner performance and activity.
 */

import { useStore } from '../lib/store';
import { BarChart3, TrendingUp, Zap, Target } from 'lucide-react';
import clsx from 'clsx';
import styles from './ScannerStats.module.css';

export default function ScannerStats() {
  const { status } = useStore();

  const scanners = status?.scanners || [];

  // Calculate totals
  const totalSignals = scanners.reduce((sum, s) => sum + s.signals_generated, 0);
  const avgScanTime = scanners.length > 0
    ? scanners.reduce((sum, s) => sum + s.avg_scan_time_ms, 0) / scanners.length
    : 0;
  const activeCount = scanners.filter(s => s.status === 'running').length;

  const stats = [
    {
      label: 'Total Signals',
      value: totalSignals.toLocaleString(),
      icon: Zap,
      colorClass: styles.colorCyan,
    },
    {
      label: 'Active Scanners',
      value: `${activeCount}/${scanners.length}`,
      icon: BarChart3,
      colorClass: styles.colorGreen,
    },
    {
      label: 'Avg Scan Time',
      value: `${avgScanTime.toFixed(0)}ms`,
      icon: TrendingUp,
      colorClass: styles.colorYellow,
    },
    {
      label: 'Active Users',
      value: status?.active_users?.toString() || '0',
      icon: Target,
      colorClass: styles.colorPurple,
    },
  ];

  return (
    <div className={clsx('card', styles.statsCard)}>
      <div className="card-header">Scanner Performance</div>

      <div className={styles.statsGrid}>
        {stats.map((stat) => (
          <div
            key={stat.label}
            className={styles.statBox}
          >
            <div className={styles.statHeader}>
              <stat.icon className={clsx(styles.statIcon, stat.colorClass)} />
              <span className={styles.statLabel}>{stat.label}</span>
            </div>
            <div className={clsx(styles.statValue, stat.colorClass)}>
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Mini scanner list */}
      <div className={styles.scannerList}>
        {scanners.slice(0, 4).map((scanner) => (
          <div
            key={scanner.name}
            className={styles.scannerRow}
          >
            <div className={styles.scannerInfo}>
              <div className={clsx(
                styles.scannerDot,
                scanner.status === 'running' ? styles.scannerDotRunning : styles.scannerDotStopped
              )} />
              <span className={styles.scannerName}>{scanner.name}</span>
            </div>
            <span className={styles.scannerSignals}>{scanner.signals_generated}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
