/**
 * Header Component
 *
 * Top navigation bar with status indicators and user menu.
 */

import { Activity, Wifi, WifiOff, User, LogOut, Settings } from 'lucide-react';
import { useStore } from '../lib/store';

export default function Header() {
  const { user, status, isConnected, logout } = useStore();

  const marketStatus = status?.markets.find(m => m.market === 'US');
  const isMarketOpen = marketStatus?.status === 'open';

  return (
    <header className="h-14 bg-scanify-dark-800 border-b border-scanify-dark-600 flex items-center justify-between px-4">
      {/* Logo & Title */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-gradient-to-br from-scanify-primary to-scanify-secondary rounded-lg flex items-center justify-center">
          <Activity className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-white">Scanify</h1>
        </div>
      </div>

      {/* Status Indicators */}
      <div className="flex items-center gap-6">
        {/* Market Status */}
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isMarketOpen ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
          <span className="text-sm text-gray-400">
            US Market: <span className={isMarketOpen ? 'text-green-400' : 'text-gray-500'}>
              {isMarketOpen ? 'Open' : 'Closed'}
            </span>
          </span>
        </div>

        {/* Scanner Status */}
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-scanify-primary" />
          <span className="text-sm text-gray-400">
            Signals Today: <span className="text-white font-medium">{status?.signals_today || 0}</span>
          </span>
        </div>

        {/* Connection Status */}
        <div className="flex items-center gap-2">
          {isConnected ? (
            <>
              <Wifi className="w-4 h-4 text-green-500" />
              <span className="text-sm text-green-400">Live</span>
            </>
          ) : (
            <>
              <WifiOff className="w-4 h-4 text-gray-500" />
              <span className="text-sm text-gray-500">Disconnected</span>
            </>
          )}
        </div>

        {/* Separator */}
        <div className="w-px h-6 bg-scanify-dark-600" />

        {/* User Menu */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-scanify-dark-700 rounded-full flex items-center justify-center">
              <User className="w-4 h-4 text-gray-400" />
            </div>
            <div className="text-sm">
              <div className="text-white">{user?.username || user?.email}</div>
              <div className="text-xs text-scanify-primary capitalize">{user?.tier}</div>
            </div>
          </div>

          <button
            onClick={logout}
            className="p-2 hover:bg-scanify-dark-700 rounded-lg transition-colors"
            title="Logout"
          >
            <LogOut className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>
    </header>
  );
}
