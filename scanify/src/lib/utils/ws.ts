// ---------------------------------------------------------------------------
// WebSocket manager with auto-reconnect and heartbeat
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Configuration for a {@link WebSocketManager} instance. */
export interface WSConfig {
  /** WebSocket endpoint URL (ws:// or wss://). */
  readonly url: string;
  /** Optional sub-protocols. */
  readonly protocols?: readonly string[];
  /** Whether to automatically reconnect on unexpected closure. */
  readonly reconnect: boolean;
  /** Maximum number of reconnect attempts before giving up. */
  readonly maxRetries: number;
  /** Initial backoff interval in milliseconds (default: 100). */
  readonly backoffMs: number;
  /** Ceiling for exponential backoff in milliseconds (default: 30 000). */
  readonly maxBackoffMs: number;
}

/** Structure for messages sent / received through the manager. */
export interface WSMessage {
  readonly type: string;
  readonly payload: unknown;
  readonly timestamp: number;
}

/** Connection lifecycle states. */
export type WSConnectionState =
  | 'connecting'
  | 'connected'
  | 'disconnecting'
  | 'disconnected'
  | 'reconnecting';

/** Callback signatures. */
export type WSMessageCallback = (message: WSMessage) => void;
export type WSStateCallback = (state: WSConnectionState) => void;
export type WSErrorCallback = (error: Event) => void;

// ---------------------------------------------------------------------------
// Default config
// ---------------------------------------------------------------------------

const DEFAULT_CONFIG: WSConfig = {
  url: '',
  protocols: undefined,
  reconnect: true,
  maxRetries: 10,
  backoffMs: 100,
  maxBackoffMs: 30_000,
};

/** Interval at which we send a heartbeat ping (ms). */
const HEARTBEAT_INTERVAL = 30_000;

// ---------------------------------------------------------------------------
// WebSocketManager class
// ---------------------------------------------------------------------------

/**
 * Managed WebSocket connection with:
 *
 * - Automatic reconnection using exponential backoff (100 ms -> max 30 s).
 * - Heartbeat / ping mechanism to keep the connection alive.
 * - Typed message and state-change callbacks.
 */
export class WebSocketManager {
  // -- Configuration -------------------------------------------------------
  private readonly config: WSConfig;

  // -- Runtime state -------------------------------------------------------
  private ws: WebSocket | null = null;
  private state: WSConnectionState = 'disconnected';
  private retryCount = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private manualClose = false;

  // -- Callbacks -----------------------------------------------------------
  private messageCallbacks: WSMessageCallback[] = [];
  private stateCallbacks: WSStateCallback[] = [];
  private errorCallbacks: WSErrorCallback[] = [];

  constructor(config: Partial<WSConfig> & Pick<WSConfig, 'url'>) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  // -----------------------------------------------------------------------
  // Public API
  // -----------------------------------------------------------------------

  /** Current connection state. */
  get connectionState(): WSConnectionState {
    return this.state;
  }

  /** Register a message handler. Returns a dispose function. */
  onMessage(cb: WSMessageCallback): () => void {
    this.messageCallbacks.push(cb);
    return () => {
      this.messageCallbacks = this.messageCallbacks.filter((c) => c !== cb);
    };
  }

  /** Register a state-change handler. Returns a dispose function. */
  onStateChange(cb: WSStateCallback): () => void {
    this.stateCallbacks.push(cb);
    return () => {
      this.stateCallbacks = this.stateCallbacks.filter((c) => c !== cb);
    };
  }

  /** Register an error handler. Returns a dispose function. */
  onError(cb: WSErrorCallback): () => void {
    this.errorCallbacks.push(cb);
    return () => {
      this.errorCallbacks = this.errorCallbacks.filter((c) => c !== cb);
    };
  }

  /**
   * Open the WebSocket connection.
   *
   * If already connected or connecting, this is a no-op.
   */
  connect(): void {
    if (this.ws && (this.state === 'connected' || this.state === 'connecting')) {
      return;
    }

    this.manualClose = false;
    this.createSocket();
  }

  /**
   * Gracefully close the WebSocket connection.
   *
   * Disables auto-reconnect for this closure.
   */
  disconnect(): void {
    this.manualClose = true;
    this.clearTimers();
    this.retryCount = 0;

    if (this.ws) {
      this.setState('disconnecting');
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }

    this.setState('disconnected');
  }

  /**
   * Send data over the WebSocket.
   *
   * Accepts a {@link WSMessage}, a plain string, or an `ArrayBuffer`.
   * Objects are JSON-serialised automatically.
   */
  send(data: WSMessage | string | ArrayBuffer): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WebSocketManager] Cannot send — socket is not open.');
      return;
    }

    if (typeof data === 'string' || data instanceof ArrayBuffer) {
      this.ws.send(data);
    } else {
      this.ws.send(JSON.stringify(data));
    }
  }

  // -----------------------------------------------------------------------
  // Internal helpers
  // -----------------------------------------------------------------------

  private createSocket(): void {
    this.setState('connecting');

    try {
      this.ws = this.config.protocols?.length
        ? new WebSocket(this.config.url, [...this.config.protocols])
        : new WebSocket(this.config.url);
    } catch (err) {
      console.error('[WebSocketManager] Failed to create WebSocket:', err);
      this.setState('disconnected');
      return;
    }

    this.ws.binaryType = 'arraybuffer';

    this.ws.addEventListener('open', this.handleOpen);
    this.ws.addEventListener('message', this.handleMessage);
    this.ws.addEventListener('close', this.handleClose);
    this.ws.addEventListener('error', this.handleError);
  }

  // -- Event handlers (arrow functions to preserve `this`) -----------------

  private handleOpen = (): void => {
    this.retryCount = 0;
    this.setState('connected');
    this.startHeartbeat();
  };

  private handleMessage = (event: MessageEvent): void => {
    let message: WSMessage;

    try {
      const parsed: unknown = typeof event.data === 'string'
        ? JSON.parse(event.data)
        : event.data;

      // If the parsed value looks like a WSMessage, use it directly.
      if (
        typeof parsed === 'object' &&
        parsed !== null &&
        'type' in parsed
      ) {
        const obj = parsed as Record<string, unknown>;
        message = {
          type: String(obj['type']),
          payload: obj['payload'] ?? null,
          timestamp: typeof obj['timestamp'] === 'number' ? obj['timestamp'] : Date.now(),
        };
      } else {
        message = { type: 'raw', payload: parsed, timestamp: Date.now() };
      }
    } catch {
      message = { type: 'raw', payload: event.data, timestamp: Date.now() };
    }

    // Respond to server-initiated pongs silently.
    if (message.type === 'pong') return;

    for (const cb of this.messageCallbacks) {
      try {
        cb(message);
      } catch (err) {
        console.error('[WebSocketManager] Message callback error:', err);
      }
    }
  };

  private handleClose = (event: CloseEvent): void => {
    this.stopHeartbeat();
    this.removeSocketListeners();

    if (this.manualClose) {
      this.setState('disconnected');
      return;
    }

    // Attempt reconnect if configured.
    if (
      this.config.reconnect &&
      this.retryCount < this.config.maxRetries &&
      event.code !== 1000
    ) {
      this.scheduleReconnect();
    } else {
      this.setState('disconnected');
    }
  };

  private handleError = (event: Event): void => {
    for (const cb of this.errorCallbacks) {
      try {
        cb(event);
      } catch (err) {
        console.error('[WebSocketManager] Error callback error:', err);
      }
    }
  };

  // -- Reconnect logic -----------------------------------------------------

  private scheduleReconnect(): void {
    this.setState('reconnecting');
    this.retryCount += 1;

    // Exponential backoff: base * 2^(retry-1), capped at maxBackoffMs.
    const delay = Math.min(
      this.config.backoffMs * Math.pow(2, this.retryCount - 1),
      this.config.maxBackoffMs,
    );

    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.createSocket();
    }, delay);
  }

  // -- Heartbeat -----------------------------------------------------------

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: 'ping', payload: null, timestamp: Date.now() });
    }, HEARTBEAT_INTERVAL);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  // -- State management ----------------------------------------------------

  private setState(next: WSConnectionState): void {
    if (this.state === next) return;
    this.state = next;

    for (const cb of this.stateCallbacks) {
      try {
        cb(next);
      } catch (err) {
        console.error('[WebSocketManager] State callback error:', err);
      }
    }
  }

  // -- Cleanup -------------------------------------------------------------

  private removeSocketListeners(): void {
    if (!this.ws) return;
    this.ws.removeEventListener('open', this.handleOpen);
    this.ws.removeEventListener('message', this.handleMessage);
    this.ws.removeEventListener('close', this.handleClose);
    this.ws.removeEventListener('error', this.handleError);
  }

  private clearTimers(): void {
    this.stopHeartbeat();
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
  }
}
