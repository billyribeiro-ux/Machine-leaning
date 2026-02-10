// ---------------------------------------------------------------------------
// WebSocket store – Svelte 5 rune-based reactive state
// ---------------------------------------------------------------------------

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

export interface WebSocketMessage {
  channel: string;
  event: string;
  data: unknown;
  receivedAt: number;
}

export interface ChannelSubscription {
  channel: string;
  subscribedAt: number;
  messageCount: number;
}

export interface WebSocketConfig {
  url: string;
  /** Maximum reconnection attempts before giving up. */
  maxReconnectAttempts: number;
  /** Base delay in ms between reconnection attempts (doubled each attempt). */
  reconnectBaseDelay: number;
  /** Maximum delay cap in ms. */
  reconnectMaxDelay: number;
  /** Interval in ms for sending ping frames to measure latency. */
  pingInterval: number;
  /** Protocols to request during the WS handshake. */
  protocols?: string[];
}

const DEFAULT_CONFIG: WebSocketConfig = {
  url: '',
  maxReconnectAttempts: 10,
  reconnectBaseDelay: 1000,
  reconnectMaxDelay: 30000,
  pingInterval: 15000,
  protocols: undefined,
};

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createWebSocketStore() {
  // ---- reactive state ----
  let connectionState = $state<ConnectionState>('disconnected');
  let messageCount = $state(0);
  let lastMessageTimestamp = $state<number | null>(null);
  let latency = $state<number>(0);
  let subscriptions = $state<Map<string, ChannelSubscription>>(new Map());
  let reconnectAttempt = $state(0);
  let error = $state<string | null>(null);
  let config = $state<WebSocketConfig>({ ...DEFAULT_CONFIG });
  let lastMessage = $state<WebSocketMessage | null>(null);

  // Private, non-reactive references
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let pingSentAt = 0;
  let messageHandlers: Map<string, Set<(msg: WebSocketMessage) => void>> = new Map();

  // ---- derived ----
  let isConnected = $derived(connectionState === 'connected');
  let isReconnecting = $derived(connectionState === 'reconnecting');
  let channelCount = $derived(subscriptions.size);
  let subscribedChannels = $derived([...subscriptions.keys()]);

  // ---- internal helpers ----

  function clearTimers(): void {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (pingTimer) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
  }

  function startPing(): void {
    if (pingTimer) clearInterval(pingTimer);
    pingTimer = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        pingSentAt = Date.now();
        socket.send(JSON.stringify({ event: '__ping', data: pingSentAt }));
      }
    }, config.pingInterval);
  }

  function scheduleReconnect(): void {
    if (reconnectAttempt >= config.maxReconnectAttempts) {
      connectionState = 'disconnected';
      error = `Reconnection failed after ${config.maxReconnectAttempts} attempts`;
      return;
    }

    connectionState = 'reconnecting';
    const delay = Math.min(
      config.reconnectBaseDelay * Math.pow(2, reconnectAttempt),
      config.reconnectMaxDelay
    );
    reconnectAttempt++;

    reconnectTimer = setTimeout(() => {
      connectInternal();
    }, delay);
  }

  function handleOpen(): void {
    connectionState = 'connected';
    reconnectAttempt = 0;
    error = null;
    startPing();

    // Resubscribe to all channels after reconnect
    for (const channel of subscriptions.keys()) {
      sendRaw({ event: 'subscribe', channel });
    }
  }

  function handleClose(ev: CloseEvent): void {
    clearTimers();
    socket = null;

    if (ev.code === 1000 || ev.code === 1001) {
      // Normal closure
      connectionState = 'disconnected';
    } else {
      scheduleReconnect();
    }
  }

  function handleError(): void {
    error = 'WebSocket error';
  }

  function handleMessage(ev: MessageEvent): void {
    messageCount++;
    lastMessageTimestamp = Date.now();

    let parsed: { event?: string; channel?: string; data?: unknown };
    try {
      parsed = JSON.parse(ev.data as string);
    } catch {
      return;
    }

    // Handle pong for latency measurement
    if (parsed.event === '__pong') {
      latency = Date.now() - pingSentAt;
      return;
    }

    const msg: WebSocketMessage = {
      channel: parsed.channel ?? '',
      event: parsed.event ?? 'message',
      data: parsed.data,
      receivedAt: Date.now(),
    };

    lastMessage = msg;

    // Update per-channel stats
    const sub = subscriptions.get(msg.channel);
    if (sub) {
      sub.messageCount++;
      subscriptions = new Map(subscriptions);
    }

    // Notify registered handlers
    const channelHandlers = messageHandlers.get(msg.channel);
    if (channelHandlers) {
      for (const handler of channelHandlers) {
        try {
          handler(msg);
        } catch {
          // Swallow handler errors
        }
      }
    }

    // Also notify wildcard handlers
    const wildcardHandlers = messageHandlers.get('*');
    if (wildcardHandlers) {
      for (const handler of wildcardHandlers) {
        try {
          handler(msg);
        } catch {
          // Swallow handler errors
        }
      }
    }
  }

  function sendRaw(data: unknown): void {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(data));
    }
  }

  function connectInternal(): void {
    if (socket) {
      socket.onopen = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close();
      }
    }

    connectionState = 'connecting';
    error = null;

    try {
      socket = config.protocols
        ? new WebSocket(config.url, config.protocols)
        : new WebSocket(config.url);

      socket.onopen = handleOpen;
      socket.onclose = handleClose;
      socket.onerror = handleError;
      socket.onmessage = handleMessage;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Connection failed';
      scheduleReconnect();
    }
  }

  // ---- public actions ----

  /** Open a WebSocket connection with the given configuration. */
  function connect(url: string, options?: Partial<Omit<WebSocketConfig, 'url'>>): void {
    config = { ...DEFAULT_CONFIG, ...options, url };
    reconnectAttempt = 0;
    connectInternal();
  }

  /** Gracefully close the connection and stop reconnection. */
  function disconnect(): void {
    clearTimers();
    reconnectAttempt = config.maxReconnectAttempts; // prevent auto-reconnect
    if (socket) {
      socket.onclose = null; // prevent reconnect handler
      socket.close(1000, 'Client disconnect');
      socket = null;
    }
    connectionState = 'disconnected';
  }

  /** Subscribe to a named channel. */
  function subscribe(channel: string): void {
    if (!subscriptions.has(channel)) {
      subscriptions.set(channel, {
        channel,
        subscribedAt: Date.now(),
        messageCount: 0,
      });
      subscriptions = new Map(subscriptions);
    }
    sendRaw({ event: 'subscribe', channel });
  }

  /** Unsubscribe from a named channel. */
  function unsubscribe(channel: string): void {
    subscriptions.delete(channel);
    subscriptions = new Map(subscriptions);
    sendRaw({ event: 'unsubscribe', channel });
    messageHandlers.delete(channel);
  }

  /** Send a typed message on a channel. */
  function send(channel: string, event: string, data: unknown): void {
    sendRaw({ channel, event, data });
  }

  /**
   * Register a callback for messages on a specific channel.
   * Use '*' for a wildcard that receives all messages.
   * Returns an unsubscribe function.
   */
  function onMessage(
    channel: string,
    handler: (msg: WebSocketMessage) => void
  ): () => void {
    if (!messageHandlers.has(channel)) {
      messageHandlers.set(channel, new Set());
    }
    messageHandlers.get(channel)!.add(handler);
    return () => {
      messageHandlers.get(channel)?.delete(handler);
    };
  }

  /** Force a reconnection attempt now. */
  function reconnect(): void {
    clearTimers();
    reconnectAttempt = 0;
    connectInternal();
  }

  /** Reset all counters and state. */
  function reset(): void {
    disconnect();
    messageCount = 0;
    lastMessageTimestamp = null;
    latency = 0;
    subscriptions = new Map();
    lastMessage = null;
    error = null;
    messageHandlers = new Map();
  }

  // ---- public API ----
  return {
    // reactive getters
    get connectionState() {
      return connectionState;
    },
    get isConnected() {
      return isConnected;
    },
    get isReconnecting() {
      return isReconnecting;
    },
    get messageCount() {
      return messageCount;
    },
    get lastMessageTimestamp() {
      return lastMessageTimestamp;
    },
    get latency() {
      return latency;
    },
    get subscriptions() {
      return subscriptions;
    },
    get channelCount() {
      return channelCount;
    },
    get subscribedChannels() {
      return subscribedChannels;
    },
    get reconnectAttempt() {
      return reconnectAttempt;
    },
    get error() {
      return error;
    },
    get lastMessage() {
      return lastMessage;
    },

    // actions
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    send,
    onMessage,
    reconnect,
    reset,
  };
}

export const wsStore = createWebSocketStore();
