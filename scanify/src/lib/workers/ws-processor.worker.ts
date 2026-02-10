// ---------------------------------------------------------------------------
// WebSocket Message Processor — Web Worker
// Scanify trading scanner
//
// Receives raw WebSocket messages, parses and transforms them, batches
// within ~16 ms windows (~60 fps), and posts processed batches to the
// main thread.  Handles message types: scan_result, market_data,
// options_flow, alert, heartbeat, error.
// ---------------------------------------------------------------------------

/// <reference lib="webworker" />
declare const self: DedicatedWorkerGlobalScope;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Raw inbound message wrapper. */
interface WSMessage {
  type: string;
  payload: unknown;
  timestamp: number;
}

/** Recognised WebSocket message categories. */
type WSMessageType =
  | 'scan_result'
  | 'market_data'
  | 'options_flow'
  | 'alert'
  | 'heartbeat'
  | 'error';

/** Individual processed message. */
interface ProcessedMessage {
  type: WSMessageType;
  data: unknown;
  receivedAt: number;
  processedAt: number;
  sequenceId: number;
}

/** Batch posted to the main thread. */
interface ProcessedBatch {
  type: 'batch';
  messages: ProcessedMessage[];
  batchTimestamp: number;
  messageCount: number;
}

/** Commands sent from the main thread. */
interface WorkerCommand {
  type: 'message' | 'configure' | 'flush' | 'reset';
  data?: unknown;
}

/** Worker configuration. */
interface WorkerConfig {
  batchInterval?: number;
  maxBatchSize?: number;
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let messageBuffer: ProcessedMessage[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let sequenceCounter = 0;
let BATCH_INTERVAL = 16;   // ~60 fps
let MAX_BATCH_SIZE = 500;

// ---------------------------------------------------------------------------
// Parsing & classification
// ---------------------------------------------------------------------------

function parseRawMessage(raw: unknown): WSMessage | null {
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      return {
        type: typeof parsed['type'] === 'string' ? parsed['type'] : 'unknown',
        payload: parsed['payload'] ?? parsed['data'] ?? parsed,
        timestamp:
          typeof parsed['timestamp'] === 'number'
            ? parsed['timestamp']
            : Date.now(),
      };
    } catch {
      return null;
    }
  }

  if (raw !== null && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    return {
      type: typeof obj['type'] === 'string' ? obj['type'] : 'unknown',
      payload: obj['payload'] ?? obj['data'] ?? obj,
      timestamp:
        typeof obj['timestamp'] === 'number' ? obj['timestamp'] : Date.now(),
    };
  }

  return null;
}

function classifyType(rawType: string): WSMessageType {
  const norm = rawType.toLowerCase().replace(/[_\-\s]/g, '');
  if (norm.includes('scan') || norm.includes('signal')) return 'scan_result';
  if (norm.includes('market') || norm.includes('quote') || norm.includes('tick')) return 'market_data';
  if (norm.includes('option') || norm.includes('flow')) return 'options_flow';
  if (norm.includes('alert') || norm.includes('notification')) return 'alert';
  if (norm.includes('heartbeat') || norm.includes('ping') || norm.includes('pong')) return 'heartbeat';
  if (norm.includes('error') || norm.includes('err')) return 'error';
  return 'market_data';
}

// ---------------------------------------------------------------------------
// Payload normalisation
// ---------------------------------------------------------------------------

function toNumber(v: unknown): number {
  if (typeof v === 'number') return v;
  if (typeof v === 'string') {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : 0;
  }
  return 0;
}

function transformPayload(type: WSMessageType, payload: unknown): unknown {
  if (!payload || typeof payload !== 'object') return payload;
  const p = payload as Record<string, unknown>;

  switch (type) {
    case 'market_data':
      return {
        symbol: p['symbol'] ?? p['s'] ?? '',
        last: toNumber(p['last'] ?? p['price'] ?? p['p']),
        bid: toNumber(p['bid'] ?? p['b']),
        ask: toNumber(p['ask'] ?? p['a']),
        volume: toNumber(p['volume'] ?? p['vol'] ?? p['v']),
        change: toNumber(p['change'] ?? p['chg']),
        changePercent: toNumber(p['changePercent'] ?? p['pct']),
        timestamp: p['timestamp'] ?? p['t'] ?? Date.now(),
      };

    case 'scan_result':
      return {
        scanId: p['scanId'] ?? p['scan_id'] ?? '',
        symbol: p['symbol'] ?? p['s'] ?? '',
        direction: p['direction'] ?? p['dir'] ?? 'neutral',
        strength: toNumber(p['strength'] ?? p['str'] ?? 1),
        name: p['name'] ?? p['signal'] ?? '',
        price: toNumber(p['price'] ?? p['p']),
        metadata: p['metadata'] ?? p['meta'] ?? {},
        timestamp: p['timestamp'] ?? p['t'] ?? Date.now(),
      };

    case 'options_flow':
      return {
        symbol: p['symbol'] ?? p['s'] ?? '',
        optionType: p['type'] ?? p['optionType'] ?? '',
        strike: toNumber(p['strike'] ?? p['k']),
        expiry: p['expiry'] ?? p['exp'] ?? '',
        premium: toNumber(p['premium'] ?? p['prem']),
        size: toNumber(p['size'] ?? p['qty']),
        side: p['side'] ?? '',
        sentiment: p['sentiment'] ?? '',
        timestamp: p['timestamp'] ?? p['t'] ?? Date.now(),
      };

    case 'alert':
      return {
        alertId: p['alertId'] ?? p['alert_id'] ?? p['id'] ?? '',
        message: p['message'] ?? p['msg'] ?? '',
        severity: p['severity'] ?? p['level'] ?? 'info',
        symbol: p['symbol'] ?? '',
        timestamp: p['timestamp'] ?? Date.now(),
      };

    case 'heartbeat':
      return { alive: true, serverTime: Date.now() };

    case 'error':
      return {
        code: p['code'] ?? 0,
        message: p['message'] ?? p['msg'] ?? p['error'] ?? 'Unknown error',
        timestamp: Date.now(),
      };

    default:
      return payload;
  }
}

// ---------------------------------------------------------------------------
// Batching
// ---------------------------------------------------------------------------

function enqueueMessage(msg: ProcessedMessage): void {
  messageBuffer.push(msg);

  if (messageBuffer.length >= MAX_BATCH_SIZE) {
    flushBatch();
    return;
  }

  if (flushTimer === null) {
    flushTimer = setTimeout(flushBatch, BATCH_INTERVAL);
  }
}

function flushBatch(): void {
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }

  if (messageBuffer.length === 0) return;

  const batch: ProcessedBatch = {
    type: 'batch',
    messages: messageBuffer,
    batchTimestamp: Date.now(),
    messageCount: messageBuffer.length,
  };

  self.postMessage(batch);
  messageBuffer = [];
}

// ---------------------------------------------------------------------------
// Worker message handler
// ---------------------------------------------------------------------------

self.onmessage = (event: MessageEvent<WorkerCommand>): void => {
  const { type, data } = event.data;

  switch (type) {
    case 'message': {
      const parsed = parseRawMessage(data);
      if (!parsed) return;

      const msgType = classifyType(parsed.type);

      // Heartbeats are acknowledged but not forwarded.
      if (msgType === 'heartbeat') {
        self.postMessage({ type: 'heartbeat_ack', timestamp: Date.now() });
        return;
      }

      const transformed = transformPayload(msgType, parsed.payload);

      const processed: ProcessedMessage = {
        type: msgType,
        data: transformed,
        receivedAt: parsed.timestamp,
        processedAt: Date.now(),
        sequenceId: sequenceCounter++,
      };

      enqueueMessage(processed);
      break;
    }

    case 'configure': {
      const cfg = data as WorkerConfig | undefined;
      if (cfg) {
        if (typeof cfg.batchInterval === 'number' && cfg.batchInterval > 0) {
          BATCH_INTERVAL = cfg.batchInterval;
        }
        if (typeof cfg.maxBatchSize === 'number' && cfg.maxBatchSize > 0) {
          MAX_BATCH_SIZE = cfg.maxBatchSize;
        }
      }
      self.postMessage({
        type: 'configured',
        config: { batchInterval: BATCH_INTERVAL, maxBatchSize: MAX_BATCH_SIZE },
      });
      break;
    }

    case 'flush': {
      flushBatch();
      break;
    }

    case 'reset': {
      messageBuffer = [];
      sequenceCounter = 0;
      if (flushTimer !== null) {
        clearTimeout(flushTimer);
        flushTimer = null;
      }
      self.postMessage({ type: 'reset_complete' });
      break;
    }
  }
};

// Signal readiness.
self.postMessage({ type: 'ready' });

export {};
