/**
 * Signal Table Component
 *
 * Displays trading signals in a sortable, filterable table.
 */

import { useState } from 'react';
import { useStore } from '../lib/store';
import { ArrowUp, ArrowDown, Minus, Clock, Target, AlertTriangle } from 'lucide-react';
import { format } from 'date-fns';
import clsx from 'clsx';
import styles from './SignalTable.module.css';

type SortField = 'timestamp' | 'confidence' | 'symbol';
type SortDirection = 'asc' | 'desc';

export default function SignalTable() {
  const { signals } = useStore();
  const [sortField, setSortField] = useState<SortField>('timestamp');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const sortedSignals = [...signals].sort((a, b) => {
    let comparison = 0;
    switch (sortField) {
      case 'timestamp':
        comparison = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
        break;
      case 'confidence':
        comparison = a.confidence - b.confidence;
        break;
      case 'symbol':
        comparison = a.symbol.localeCompare(b.symbol);
        break;
    }
    return sortDirection === 'asc' ? comparison : -comparison;
  });

  const DirectionIcon = ({ direction }: { direction: string }) => {
    switch (direction) {
      case 'LONG':
        return <ArrowUp className={styles.directionIconUp} />;
      case 'SHORT':
        return <ArrowDown className={styles.directionIconDown} />;
      default:
        return <Minus className={styles.directionIconNeutral} />;
    }
  };

  const getConfidenceBarClass = (confidence: number) => {
    if (confidence >= 85) return styles.confidenceHigh;
    if (confidence >= 70) return styles.confidenceMedium;
    return styles.confidenceLow;
  };

  const getConfidenceTextClass = (confidence: number) => {
    if (confidence >= 85) return styles.confidenceTextHigh;
    if (confidence >= 70) return styles.confidenceTextMedium;
    return styles.confidenceTextLow;
  };

  const getScannerBadgeClass = (type: string) => {
    const classMap: Record<string, string> = {
      momentum: styles.scannerMomentum,
      breakout: styles.scannerBreakout,
      reversal: styles.scannerReversal,
      options_flow: styles.scannerOptionsFlow,
      squeeze: styles.scannerSqueeze,
      gamma: styles.scannerGamma,
      mtf: styles.scannerMtf,
    };
    return classMap[type] || styles.scannerDefault;
  };

  return (
    <div className={clsx('card', styles.tableCard)}>
      <div className={clsx('card-header', styles.headerRow)}>
        <span>Live Signals</span>
        <span className={styles.signalCountLabel}>{signals.length} signals</span>
      </div>

      <div className={styles.scrollArea}>
        <table className={styles.table}>
          <thead className={styles.tableHead}>
            <tr>
              <th
                className={clsx(styles.columnHeader, styles.columnHeaderSortable)}
                onClick={() => handleSort('timestamp')}
              >
                Time {sortField === 'timestamp' && (sortDirection === 'desc' ? '↓' : '↑')}
              </th>
              <th
                className={clsx(styles.columnHeader, styles.columnHeaderSortable)}
                onClick={() => handleSort('symbol')}
              >
                Symbol {sortField === 'symbol' && (sortDirection === 'desc' ? '↓' : '↑')}
              </th>
              <th className={styles.columnHeader}>Scanner</th>
              <th className={styles.columnHeader}>Direction</th>
              <th
                className={clsx(styles.columnHeader, styles.columnHeaderSortable)}
                onClick={() => handleSort('confidence')}
              >
                Confidence {sortField === 'confidence' && (sortDirection === 'desc' ? '↓' : '↑')}
              </th>
              <th className={styles.columnHeader}>Entry</th>
              <th className={styles.columnHeader}>Targets</th>
              <th className={clsx(styles.columnHeader, styles.columnHeaderLast)}>R:R</th>
            </tr>
          </thead>
          <tbody>
            {sortedSignals.map((signal) => (
              <tr key={signal.id} className="table-row">
                <td className={styles.timeCell}>
                  <div className={styles.timeContent}>
                    <Clock className={styles.timeIcon} />
                    {format(new Date(signal.timestamp), 'HH:mm:ss')}
                    {signal.is_delayed && (
                      <span className={styles.delayedLabel} title={`Delayed ${signal.delay_seconds}s`}>
                        (D)
                      </span>
                    )}
                  </div>
                </td>
                <td className={styles.symbolCell}>
                  {signal.symbol}
                </td>
                <td className={styles.scannerCell}>
                  <span className={clsx('badge', styles.scannerBadge, getScannerBadgeClass(signal.scanner_type))}>
                    {signal.scanner_type.replace('_', ' ')}
                  </span>
                </td>
                <td className={styles.directionCell}>
                  <div className={clsx(
                    styles.directionContent,
                    signal.direction === 'LONG' ? styles.directionLong : signal.direction === 'SHORT' ? styles.directionShort : styles.directionNeutral
                  )}>
                    <DirectionIcon direction={signal.direction} />
                    {signal.direction}
                  </div>
                </td>
                <td className={styles.confidenceCell}>
                  <div className={styles.confidenceContent}>
                    <div className={styles.confidenceBarTrack}>
                      <div
                        className={clsx(styles.confidenceBarFill, getConfidenceBarClass(signal.confidence))}
                        style={{ width: `${signal.confidence}%` }}
                      />
                    </div>
                    <span className={clsx(styles.confidenceValue, getConfidenceTextClass(signal.confidence))}>
                      {signal.confidence.toFixed(0)}%
                    </span>
                  </div>
                </td>
                <td className={styles.entryCell}>
                  ${signal.entry_price?.toFixed(2) || '-'}
                </td>
                <td className={styles.targetsCell}>
                  <div className={styles.targetsContent}>
                    <Target className={styles.targetsIcon} />
                    {signal.targets.length > 0 ? (
                      <span className={styles.targetsValue}>
                        ${signal.targets[0]?.toFixed(2)}
                        {signal.targets.length > 1 && ` +${signal.targets.length - 1}`}
                      </span>
                    ) : (
                      <span className={styles.targetsEmpty}>-</span>
                    )}
                  </div>
                </td>
                <td className={styles.rrCell}>
                  {signal.risk_reward ? (
                    <span className={
                      signal.risk_reward >= 2 ? styles.rrGood : signal.risk_reward >= 1.5 ? styles.rrOk : styles.rrLow
                    }>
                      {signal.risk_reward.toFixed(1)}:1
                    </span>
                  ) : (
                    <span className={styles.rrEmpty}>-</span>
                  )}
                </td>
              </tr>
            ))}
            {signals.length === 0 && (
              <tr>
                <td colSpan={8} className={styles.emptyState}>
                  <AlertTriangle className={styles.emptyIcon} />
                  No signals yet. Waiting for scanner data...
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
