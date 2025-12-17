/**
 * Alert Feed Component
 *
 * Real-time alert notifications with priority highlighting.
 */

import { useStore } from '../lib/store';
import { Bell, AlertTriangle, AlertCircle, Info, ArrowUp, ArrowDown } from 'lucide-react';
import { format } from 'date-fns';
import clsx from 'clsx';

export default function AlertFeed() {
  const { alerts } = useStore();

  const getPriorityIcon = (priority: string) => {
    switch (priority) {
      case 'critical':
        return <AlertTriangle className="w-4 h-4 text-red-500" />;
      case 'high':
        return <AlertCircle className="w-4 h-4 text-orange-500" />;
      case 'medium':
        return <Bell className="w-4 h-4 text-yellow-500" />;
      default:
        return <Info className="w-4 h-4 text-blue-500" />;
    }
  };

  const getPriorityStyle = (priority: string) => {
    switch (priority) {
      case 'critical':
        return 'border-l-red-500 bg-red-900/10';
      case 'high':
        return 'border-l-orange-500 bg-orange-900/10';
      case 'medium':
        return 'border-l-yellow-500 bg-yellow-900/10';
      default:
        return 'border-l-blue-500 bg-blue-900/10';
    }
  };

  return (
    <div className="card h-full flex flex-col">
      <div className="card-header flex items-center justify-between">
        <span>Live Alerts</span>
        <span className="badge badge-info">{alerts.length}</span>
      </div>

      <div className="flex-1 overflow-auto space-y-2">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={clsx(
              'p-3 rounded-lg border-l-4 animate-slide-in',
              getPriorityStyle(alert.priority)
            )}
          >
            <div className="flex items-start gap-2">
              {getPriorityIcon(alert.priority)}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  {alert.symbol && (
                    <span className="font-semibold text-white">{alert.symbol}</span>
                  )}
                  {alert.direction && (
                    <span className={clsx(
                      'flex items-center gap-0.5 text-xs font-medium',
                      alert.direction === 'LONG' ? 'text-green-400' : 'text-red-400'
                    )}>
                      {alert.direction === 'LONG' ? (
                        <ArrowUp className="w-3 h-3" />
                      ) : (
                        <ArrowDown className="w-3 h-3" />
                      )}
                      {alert.direction}
                    </span>
                  )}
                  {alert.confidence && (
                    <span className="text-xs text-gray-400">
                      {alert.confidence.toFixed(0)}%
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-300 truncate">{alert.message}</p>
                <div className="flex items-center gap-2 mt-1">
                  {alert.scanner_type && (
                    <span className="text-xs text-scanify-primary">
                      {alert.scanner_type.replace('_', ' ')}
                    </span>
                  )}
                  <span className="text-xs text-gray-500">
                    {format(new Date(alert.created_at), 'HH:mm:ss')}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}

        {alerts.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <Bell className="w-8 h-8 mb-2 opacity-50" />
            <p className="text-sm">No alerts yet</p>
          </div>
        )}
      </div>
    </div>
  );
}
