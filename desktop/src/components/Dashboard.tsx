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
    <div className="h-full flex flex-col p-4 gap-4">
      {/* Top Bar - Scanner Filters */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {scannerTypes.map((scanner) => (
            <button
              key={scanner.id || 'all'}
              onClick={() => setSelectedScanner(scanner.id)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                selectedScanner === scanner.id
                  ? 'bg-scanify-primary text-white'
                  : 'bg-scanify-dark-700 text-gray-400 hover:bg-scanify-dark-600'
              }`}
            >
              {scanner.name}
            </button>
          ))}
        </div>

        <button
          onClick={() => fetchSignals()}
          disabled={isLoading}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Main Content Grid */}
      <div className="flex-1 grid grid-cols-12 gap-4 min-h-0">
        {/* Left Column - Signal Table */}
        <div className="col-span-8 flex flex-col min-h-0">
          <SignalTable />
        </div>

        {/* Right Column - Alerts & Stats */}
        <div className="col-span-4 flex flex-col gap-4 min-h-0">
          <div className="flex-1 min-h-0">
            <AlertFeed />
          </div>
          <div className="h-64">
            <ScannerStats />
          </div>
        </div>
      </div>
    </div>
  );
}
