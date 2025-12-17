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
        return <ArrowUp className="w-4 h-4 text-green-500" />;
      case 'SHORT':
        return <ArrowDown className="w-4 h-4 text-red-500" />;
      default:
        return <Minus className="w-4 h-4 text-gray-500" />;
    }
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 85) return 'text-green-400';
    if (confidence >= 70) return 'text-yellow-400';
    return 'text-gray-400';
  };

  const getScannerBadgeColor = (type: string) => {
    const colors: Record<string, string> = {
      momentum: 'bg-blue-900/50 text-blue-400 border-blue-800',
      breakout: 'bg-purple-900/50 text-purple-400 border-purple-800',
      reversal: 'bg-orange-900/50 text-orange-400 border-orange-800',
      options_flow: 'bg-cyan-900/50 text-cyan-400 border-cyan-800',
      squeeze: 'bg-pink-900/50 text-pink-400 border-pink-800',
      gamma: 'bg-indigo-900/50 text-indigo-400 border-indigo-800',
      mtf: 'bg-emerald-900/50 text-emerald-400 border-emerald-800',
    };
    return colors[type] || 'bg-gray-900/50 text-gray-400 border-gray-800';
  };

  return (
    <div className="card h-full flex flex-col">
      <div className="card-header flex items-center justify-between">
        <span>Live Signals</span>
        <span className="text-scanify-primary">{signals.length} signals</span>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-scanify-dark-800">
            <tr className="text-left text-xs text-gray-500 uppercase">
              <th className="pb-2 pr-4 cursor-pointer hover:text-gray-300" onClick={() => handleSort('timestamp')}>
                Time {sortField === 'timestamp' && (sortDirection === 'desc' ? '↓' : '↑')}
              </th>
              <th className="pb-2 pr-4 cursor-pointer hover:text-gray-300" onClick={() => handleSort('symbol')}>
                Symbol {sortField === 'symbol' && (sortDirection === 'desc' ? '↓' : '↑')}
              </th>
              <th className="pb-2 pr-4">Scanner</th>
              <th className="pb-2 pr-4">Direction</th>
              <th className="pb-2 pr-4 cursor-pointer hover:text-gray-300" onClick={() => handleSort('confidence')}>
                Confidence {sortField === 'confidence' && (sortDirection === 'desc' ? '↓' : '↑')}
              </th>
              <th className="pb-2 pr-4">Entry</th>
              <th className="pb-2 pr-4">Targets</th>
              <th className="pb-2">R:R</th>
            </tr>
          </thead>
          <tbody>
            {sortedSignals.map((signal) => (
              <tr key={signal.id} className="table-row">
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-1 text-sm text-gray-400">
                    <Clock className="w-3 h-3" />
                    {format(new Date(signal.timestamp), 'HH:mm:ss')}
                    {signal.is_delayed && (
                      <span className="text-xs text-yellow-500" title={`Delayed ${signal.delay_seconds}s`}>
                        (D)
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-3 pr-4">
                  <span className="font-semibold text-white">{signal.symbol}</span>
                </td>
                <td className="py-3 pr-4">
                  <span className={clsx('badge border', getScannerBadgeColor(signal.scanner_type))}>
                    {signal.scanner_type.replace('_', ' ')}
                  </span>
                </td>
                <td className="py-3 pr-4">
                  <div className={clsx(
                    'flex items-center gap-1 font-medium',
                    signal.direction === 'LONG' ? 'text-green-400' : signal.direction === 'SHORT' ? 'text-red-400' : 'text-gray-400'
                  )}>
                    <DirectionIcon direction={signal.direction} />
                    {signal.direction}
                  </div>
                </td>
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 bg-scanify-dark-600 rounded-full overflow-hidden">
                      <div
                        className={clsx(
                          'h-full rounded-full',
                          signal.confidence >= 85 ? 'bg-green-500' : signal.confidence >= 70 ? 'bg-yellow-500' : 'bg-gray-500'
                        )}
                        style={{ width: `${signal.confidence}%` }}
                      />
                    </div>
                    <span className={clsx('text-sm font-medium', getConfidenceColor(signal.confidence))}>
                      {signal.confidence.toFixed(0)}%
                    </span>
                  </div>
                </td>
                <td className="py-3 pr-4">
                  <span className="text-sm text-white">
                    ${signal.entry_price?.toFixed(2) || '-'}
                  </span>
                </td>
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-1 text-sm">
                    <Target className="w-3 h-3 text-scanify-accent" />
                    {signal.targets.length > 0 ? (
                      <span className="text-scanify-accent">
                        ${signal.targets[0]?.toFixed(2)}
                        {signal.targets.length > 1 && ` +${signal.targets.length - 1}`}
                      </span>
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </div>
                </td>
                <td className="py-3">
                  {signal.risk_reward ? (
                    <span className={clsx(
                      'text-sm font-medium',
                      signal.risk_reward >= 2 ? 'text-green-400' : signal.risk_reward >= 1.5 ? 'text-yellow-400' : 'text-gray-400'
                    )}>
                      {signal.risk_reward.toFixed(1)}:1
                    </span>
                  ) : (
                    <span className="text-gray-500">-</span>
                  )}
                </td>
              </tr>
            ))}
            {signals.length === 0 && (
              <tr>
                <td colSpan={8} className="py-12 text-center text-gray-500">
                  <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-50" />
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
