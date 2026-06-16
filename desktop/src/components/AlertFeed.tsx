/**
 * Alert Feed Component
 *
 * Real-time alert notifications with priority highlighting.
 */

import { useStore } from '../lib/store';
import { Bell, AlertTriangle, AlertCircle, Info, ArrowUp, ArrowDown } from 'lucide-react';
import { format } from 'date-fns';
import clsx from 'clsx';
import styles from './AlertFeed.module.css';

export default function AlertFeed() {
  const { alerts } = useStore();

  const getPriorityIcon = (priority: string) => {
    switch (priority) {
      case 'critical':
        return <AlertTriangle className={clsx(styles.priorityIcon, styles.priorityCritical)} />;
      case 'high':
        return <AlertCircle className={clsx(styles.priorityIcon, styles.priorityHigh)} />;
      case 'medium':
        return <Bell className={clsx(styles.priorityIcon, styles.priorityMedium)} />;
      default:
        return <Info className={clsx(styles.priorityIcon, styles.priorityLow)} />;
    }
  };

  const getPriorityStyle = (priority: string) => {
    switch (priority) {
      case 'critical':
        return styles.alertCritical;
      case 'high':
        return styles.alertHigh;
      case 'medium':
        return styles.alertMedium;
      default:
        return styles.alertLow;
    }
  };

  return (
    <div className={clsx('card', styles.alertCard)}>
      <div className={clsx('card-header', styles.headerRow)}>
        <span>Live Alerts</span>
        <span className="badge badge-info">{alerts.length}</span>
      </div>

      <div className={styles.alertList}>
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={clsx(styles.alertItem, getPriorityStyle(alert.priority))}
          >
            <div className={styles.alertBody}>
              {getPriorityIcon(alert.priority)}
              <div className={styles.alertContent}>
                <div className={styles.alertMeta}>
                  {alert.symbol && (
                    <span className={styles.alertSymbol}>{alert.symbol}</span>
                  )}
                  {alert.direction && (
                    <span className={clsx(
                      styles.alertDirection,
                      alert.direction === 'LONG' ? styles.directionLong : styles.directionShort
                    )}>
                      {alert.direction === 'LONG' ? (
                        <ArrowUp className={styles.directionIcon} />
                      ) : (
                        <ArrowDown className={styles.directionIcon} />
                      )}
                      {alert.direction}
                    </span>
                  )}
                  {alert.confidence && (
                    <span className={styles.alertConfidence}>
                      {alert.confidence.toFixed(0)}%
                    </span>
                  )}
                </div>
                <p className={styles.alertMessage}>{alert.message}</p>
                <div className={styles.alertFooter}>
                  {alert.scanner_type && (
                    <span className={styles.alertScanner}>
                      {alert.scanner_type.replace('_', ' ')}
                    </span>
                  )}
                  <span className={styles.alertTime}>
                    {format(new Date(alert.created_at), 'HH:mm:ss')}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}

        {alerts.length === 0 && (
          <div className={styles.emptyState}>
            <Bell className={styles.emptyIcon} />
            <p className={styles.emptyText}>No alerts yet</p>
          </div>
        )}
      </div>
    </div>
  );
}
