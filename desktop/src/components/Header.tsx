/**
 * Header Component
 *
 * Top navigation bar with status indicators and user menu.
 */

import { Activity, Wifi, WifiOff, User, LogOut } from 'lucide-react';
import { useStore } from '../lib/store';
import styles from './Header.module.css';

export default function Header() {
  const { user, status, isConnected, logout } = useStore();

  const marketStatus = status?.markets.find(m => m.market === 'US');
  const isMarketOpen = marketStatus?.status === 'open';

  return (
    <header className={styles.headerBar}>
      {/* Logo & Title */}
      <div className={styles.logoGroup}>
        <div className={styles.logoBox}>
          <Activity className={styles.logoIcon} />
        </div>
        <div>
          <h1 className={styles.logoTitle}>Scanify</h1>
        </div>
      </div>

      {/* Status Indicators */}
      <div className={styles.statusGroup}>
        {/* Market Status */}
        <div className={styles.statusItem}>
          <div className={`${styles.marketDot} ${isMarketOpen ? styles.marketDotOpen : styles.marketDotClosed}`} />
          <span className={styles.statusLabel}>
            US Market: <span className={isMarketOpen ? styles.marketOpen : styles.marketClosed}>
              {isMarketOpen ? 'Open' : 'Closed'}
            </span>
          </span>
        </div>

        {/* Scanner Status */}
        <div className={styles.statusItem}>
          <Activity className={styles.scannerIcon} />
          <span className={styles.statusLabel}>
            Signals Today: <span className={styles.signalCount}>{status?.signals_today || 0}</span>
          </span>
        </div>

        {/* Connection Status */}
        <div className={styles.statusItem}>
          {isConnected ? (
            <>
              <Wifi className={styles.connectedIcon} />
              <span className={styles.connectedLabel}>Live</span>
            </>
          ) : (
            <>
              <WifiOff className={styles.disconnectedIcon} />
              <span className={styles.disconnectedLabel}>Disconnected</span>
            </>
          )}
        </div>

        {/* Separator */}
        <div className={styles.separator} />

        {/* User Menu */}
        <div className={styles.userMenu}>
          <div className={styles.userInfo}>
            <div className={styles.userAvatar}>
              <User className={styles.userAvatarIcon} />
            </div>
            <div className={styles.userDetails}>
              <div className={styles.userName}>{user?.username || user?.email}</div>
              <div className={styles.userTier}>{user?.tier}</div>
            </div>
          </div>

          <button
            onClick={logout}
            className={styles.logoutButton}
            title="Logout"
          >
            <LogOut className={styles.logoutIcon} />
          </button>
        </div>
      </div>
    </header>
  );
}
