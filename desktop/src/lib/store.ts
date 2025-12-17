/**
 * Scanify State Store
 *
 * Global state management using Zustand.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api, Signal, Alert, SystemStatus, User } from './api';

interface ScanifyState {
  // Auth
  user: User | null;
  isAuthenticated: boolean;

  // Data
  signals: Signal[];
  alerts: Alert[];
  status: SystemStatus | null;

  // UI State
  isLoading: boolean;
  error: string | null;
  selectedScanner: string | null;
  isConnected: boolean;

  // WebSocket
  ws: WebSocket | null;

  // Actions
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  fetchSignals: (params?: { scanner_type?: string; min_confidence?: number }) => Promise<void>;
  fetchAlerts: () => Promise<void>;
  fetchStatus: () => Promise<void>;
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;
  setSelectedScanner: (scanner: string | null) => void;
  addSignal: (signal: Signal) => void;
  addAlert: (alert: Alert) => void;
  clearError: () => void;
}

export const useStore = create<ScanifyState>()(
  persist(
    (set, get) => ({
      // Initial state
      user: null,
      isAuthenticated: false,
      signals: [],
      alerts: [],
      status: null,
      isLoading: false,
      error: null,
      selectedScanner: null,
      isConnected: false,
      ws: null,

      // Auth actions
      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null });
        try {
          const data = await api.login(email, password);
          set({
            user: data.user,
            isAuthenticated: true,
            isLoading: false
          });
          // Connect WebSocket after login
          get().connectWebSocket();
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Login failed',
            isLoading: false
          });
          throw error;
        }
      },

      logout: () => {
        api.logout();
        get().disconnectWebSocket();
        set({
          user: null,
          isAuthenticated: false,
          signals: [],
          alerts: []
        });
      },

      // Data fetching
      fetchSignals: async (params) => {
        set({ isLoading: true });
        try {
          const data = await api.getSignals({
            ...params,
            scanner_type: params?.scanner_type || get().selectedScanner || undefined,
          });
          set({ signals: data.signals, isLoading: false });
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Failed to fetch signals',
            isLoading: false
          });
        }
      },

      fetchAlerts: async () => {
        try {
          const alerts = await api.getAlerts();
          set({ alerts });
        } catch (error) {
          console.error('Failed to fetch alerts:', error);
        }
      },

      fetchStatus: async () => {
        try {
          const status = await api.getStatus();
          set({ status });
        } catch (error) {
          console.error('Failed to fetch status:', error);
        }
      },

      // WebSocket
      connectWebSocket: () => {
        const { ws: existingWs } = get();
        if (existingWs) {
          existingWs.close();
        }

        const ws = api.createWebSocket(
          (data: unknown) => {
            const message = data as { type: string; data: Signal | Alert };
            if (message.type === 'signal') {
              get().addSignal(message.data as Signal);
            } else if (message.type === 'alert') {
              get().addAlert(message.data as Alert);
            }
          },
          () => {
            set({ isConnected: false });
          }
        );

        if (ws) {
          ws.onopen = () => {
            set({ isConnected: true });
            // Subscribe to all scanners
            ws.send(JSON.stringify({
              type: 'subscribe',
              scanners: ['momentum', 'breakout', 'reversal', 'options_flow', 'squeeze', 'gamma', 'mtf'],
            }));
          };
          set({ ws });
        }
      },

      disconnectWebSocket: () => {
        const { ws } = get();
        if (ws) {
          ws.close();
          set({ ws: null, isConnected: false });
        }
      },

      // UI actions
      setSelectedScanner: (scanner: string | null) => {
        set({ selectedScanner: scanner });
        get().fetchSignals({ scanner_type: scanner || undefined });
      },

      addSignal: (signal: Signal) => {
        set(state => ({
          signals: [signal, ...state.signals.slice(0, 99)], // Keep last 100
        }));
      },

      addAlert: (alert: Alert) => {
        set(state => ({
          alerts: [alert, ...state.alerts.slice(0, 49)], // Keep last 50
        }));

        // Send desktop notification for high priority alerts
        if (alert.priority === 'critical' || alert.priority === 'high') {
          import('@tauri-apps/api/notification').then(({ sendNotification }) => {
            sendNotification({
              title: `${alert.priority.toUpperCase()}: ${alert.symbol || 'Alert'}`,
              body: alert.message,
            });
          }).catch(() => {
            // Not in Tauri environment
          });
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'scanify-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
