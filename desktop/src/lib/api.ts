/**
 * Scanify API Client
 *
 * Handles all communication with the Scanify backend API.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

export interface Signal {
  id: string;
  symbol: string;
  scanner_type: string;
  direction: 'LONG' | 'SHORT' | 'NEUTRAL';
  confidence: number;
  entry_price?: number;
  stop_loss?: number;
  targets: number[];
  risk_reward?: number;
  timeframe: string;
  timestamp: string;
  metadata: Record<string, unknown>;
  is_delayed: boolean;
  delay_seconds: number;
}

export interface Alert {
  id: string;
  type: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  symbol?: string;
  scanner_type?: string;
  message: string;
  direction?: string;
  confidence?: number;
  created_at: string;
  expires_at?: string;
  read: boolean;
}

export interface ScannerStats {
  scanner_type: string;
  signals_today: number;
  accuracy_7d?: number;
  avg_confidence: number;
  top_symbol?: string;
}

export interface SystemStatus {
  system: {
    status: string;
    version: string;
    uptime_seconds: number;
    timestamp: string;
  };
  scanners: Array<{
    name: string;
    status: string;
    signals_generated: number;
    avg_scan_time_ms: number;
  }>;
  markets: Array<{
    market: string;
    status: string;
  }>;
  signals_today: number;
  active_users: number;
}

export interface User {
  id: string;
  email: string;
  username?: string;
  tier: string;
  is_active: boolean;
}

class ScanifyAPI {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('scanify_token', token);
    } else {
      localStorage.removeItem('scanify_token');
    }
  }

  getToken(): string | null {
    if (!this.token) {
      this.token = localStorage.getItem('scanify_token');
    }
    return this.token;
  }

  private async fetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.headers as Record<string, string>,
    };

    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // Auth
  async login(email: string, password: string) {
    const data = await this.fetch<{
      access_token: string;
      refresh_token: string;
      user: User;
    }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async register(email: string, password: string, username?: string) {
    const data = await this.fetch<{
      access_token: string;
      user: User;
    }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, username }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async getProfile() {
    return this.fetch<User & { features: Record<string, unknown> }>('/api/auth/me');
  }

  logout() {
    this.setToken(null);
  }

  // Signals
  async getSignals(params?: {
    page?: number;
    page_size?: number;
    scanner_type?: string;
    symbol?: string;
    min_confidence?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString());
    if (params?.scanner_type) searchParams.set('scanner_type', params.scanner_type);
    if (params?.symbol) searchParams.set('symbol', params.symbol);
    if (params?.min_confidence) searchParams.set('min_confidence', params.min_confidence.toString());

    const query = searchParams.toString();
    return this.fetch<{
      signals: Signal[];
      total: number;
      page: number;
      has_more: boolean;
      is_realtime: boolean;
    }>(`/api/signals/latest${query ? `?${query}` : ''}`);
  }

  async getScannerStats() {
    return this.fetch<ScannerStats[]>('/api/signals/scanners');
  }

  // Alerts
  async getAlerts(params?: { page?: number; unread_only?: boolean }) {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.unread_only) searchParams.set('unread_only', 'true');

    const query = searchParams.toString();
    return this.fetch<Alert[]>(`/api/alerts${query ? `?${query}` : ''}`);
  }

  async getAlertCount() {
    return this.fetch<{ total: number; unread: number; critical: number }>('/api/alerts/count');
  }

  // Status
  async getStatus() {
    return this.fetch<SystemStatus>('/api/status/');
  }

  async getHealth() {
    return this.fetch<{ status: string }>('/health');
  }

  // WebSocket connection
  createWebSocket(onMessage: (data: unknown) => void, onError?: (error: Event) => void): WebSocket | null {
    const token = this.getToken();
    if (!token) {
      console.error('No token available for WebSocket connection');
      return null;
    }

    const ws = new WebSocket(`${WS_BASE}/ws/signals?token=${token}`);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      onError?.(error);
    };

    ws.onclose = () => {
      console.log('WebSocket connection closed');
    };

    return ws;
  }
}

export const api = new ScanifyAPI();
