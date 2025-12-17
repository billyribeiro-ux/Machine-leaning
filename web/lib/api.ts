/**
 * Scanify API Client (Web)
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

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
  is_delayed: boolean;
}

export interface Alert {
  id: string;
  type: string;
  priority: string;
  symbol?: string;
  message: string;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  username?: string;
  tier: string;
  is_active: boolean;
  features?: Record<string, unknown>;
}

class ScanifyAPI {
  private token: string | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('scanify_token');
    }
  }

  setToken(token: string | null) {
    this.token = token;
    if (typeof window !== 'undefined') {
      if (token) {
        localStorage.setItem('scanify_token', token);
      } else {
        localStorage.removeItem('scanify_token');
      }
    }
  }

  getToken() {
    return this.token;
  }

  private async fetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${API_URL}${endpoint}`, {
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
    const data = await this.fetch<{ access_token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async register(email: string, password: string, username?: string) {
    const data = await this.fetch<{ access_token: string; user: User }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, username }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async getProfile() {
    return this.fetch<User>('/api/auth/me');
  }

  logout() {
    this.setToken(null);
  }

  // Signals
  async getSignals(params?: { scanner_type?: string; min_confidence?: number }) {
    const searchParams = new URLSearchParams();
    if (params?.scanner_type) searchParams.set('scanner_type', params.scanner_type);
    if (params?.min_confidence) searchParams.set('min_confidence', params.min_confidence.toString());
    const query = searchParams.toString();
    return this.fetch<{ signals: Signal[]; is_realtime: boolean }>(`/api/signals/latest${query ? `?${query}` : ''}`);
  }

  async getAlerts() {
    return this.fetch<Alert[]>('/api/alerts');
  }

  async getStatus() {
    return this.fetch<{ signals_today: number; markets: Array<{ market: string; status: string }> }>('/api/status/');
  }

  // WebSocket
  createWebSocket(onMessage: (data: unknown) => void): WebSocket | null {
    if (!this.token) return null;
    const ws = new WebSocket(`${WS_URL}/ws/signals?token=${this.token}`);
    ws.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch (e) {
        console.error('WS parse error:', e);
      }
    };
    return ws;
  }
}

export const api = new ScanifyAPI();
