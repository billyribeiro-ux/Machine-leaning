/**
 * Scanner Stats Component
 *
 * Overview of scanner performance and activity.
 */

import { useStore } from '../lib/store';
import { BarChart3, TrendingUp, Zap, Target } from 'lucide-react';

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
      color: 'text-scanify-accent',
    },
    {
      label: 'Active Scanners',
      value: `${activeCount}/${scanners.length}`,
      icon: BarChart3,
      color: 'text-green-400',
    },
    {
      label: 'Avg Scan Time',
      value: `${avgScanTime.toFixed(0)}ms`,
      icon: TrendingUp,
      color: 'text-yellow-400',
    },
    {
      label: 'Active Users',
      value: status?.active_users?.toString() || '0',
      icon: Target,
      color: 'text-purple-400',
    },
  ];

  return (
    <div className="card h-full">
      <div className="card-header">Scanner Performance</div>

      <div className="grid grid-cols-2 gap-3">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="bg-scanify-dark-700 rounded-lg p-3"
          >
            <div className="flex items-center gap-2 mb-1">
              <stat.icon className={`w-4 h-4 ${stat.color}`} />
              <span className="text-xs text-gray-500">{stat.label}</span>
            </div>
            <div className={`text-xl font-bold ${stat.color}`}>
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Mini scanner list */}
      <div className="mt-3 space-y-1">
        {scanners.slice(0, 4).map((scanner) => (
          <div
            key={scanner.name}
            className="flex items-center justify-between text-sm py-1"
          >
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${
                scanner.status === 'running' ? 'bg-green-500' : 'bg-gray-500'
              }`} />
              <span className="text-gray-400 capitalize">{scanner.name}</span>
            </div>
            <span className="text-gray-500">{scanner.signals_generated}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
