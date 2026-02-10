// ---------------------------------------------------------------------------
// WebSocket message processor — off-main-thread batching worker
//
// Receives raw WebSocket messages, buffers them, and flushes in batches
// at ~60 fps (16 ms intervals) to reduce main-thread pressure.
// ---------------------------------------------------------------------------

/// <reference lib="webworker" />
declare const self: DedicatedWorkerGlobalScope;

interface RawMessage {
  type: string;
  payload: unknown;
  timestamp: number;
}

interface ProcessedBatch {
  type: 'batch';
  messages: RawMessage[];
  processedAt: number;
}

let buffer: RawMessage[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
const BATCH_INTERVAL = 16; // ~60 fps

/**
 * Flush all buffered messages as a single batch to the main thread.
 */
function flush(): void {
  if (buffer.length === 0) return;

  const batch: ProcessedBatch = {
    type: 'batch',
    messages: [...buffer],
    processedAt: Date.now(),
  };

  self.postMessage(batch);
  buffer = [];
  flushTimer = null;
}

self.onmessage = (event: MessageEvent) => {
  const { type, data } = event.data as { type: string; data: unknown };

  if (type === 'message') {
    const parsed: RawMessage =
      typeof data === 'string' ? (JSON.parse(data) as RawMessage) : (data as RawMessage);

    buffer.push({
      ...parsed,
      timestamp: parsed.timestamp ?? Date.now(),
    });

    if (!flushTimer) {
      flushTimer = setTimeout(flush, BATCH_INTERVAL);
    }
  } else if (type === 'flush') {
    flush();
  }
};

export {};
