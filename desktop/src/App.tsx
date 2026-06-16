/**
 * Scanify Desktop App
 *
 * Main application component with routing and layout.
 */

import { useEffect } from 'react';
import { useStore } from './lib/store';
import Dashboard from './components/Dashboard';
import Login from './components/Login';
import Header from './components/Header';
import styles from './App.module.css';

function App() {
  const { isAuthenticated, fetchStatus, connectWebSocket } = useStore();

  useEffect(() => {
    // Fetch status on mount
    fetchStatus();

    // Reconnect WebSocket if authenticated
    if (isAuthenticated) {
      connectWebSocket();
    }

    // Refresh status periodically
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, [isAuthenticated, fetchStatus, connectWebSocket]);

  if (!isAuthenticated) {
    return <Login />;
  }

  return (
    <div className={styles.appLayout}>
      <Header />
      <main className={styles.mainContent}>
        <Dashboard />
      </main>
    </div>
  );
}

export default App;
