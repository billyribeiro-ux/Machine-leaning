// ---------------------------------------------------------------------------
// Audio utilities — procedural sounds via the Web Audio API
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Global sound configuration. */
export interface SoundConfig {
  /** Master volume level (0 – 1). */
  volume: number;
  /** Whether sound playback is enabled. */
  enabled: boolean;
}

// ---------------------------------------------------------------------------
// Module-level state
// ---------------------------------------------------------------------------

let audioCtx: AudioContext | null = null;

const config: SoundConfig = {
  volume: 0.5,
  enabled: true,
};

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

/**
 * Lazily initialise (or resume) the shared AudioContext.
 *
 * Returns `null` when the Web Audio API is unavailable (e.g. SSR).
 */
function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined' || typeof AudioContext === 'undefined') {
    return null;
  }

  if (!audioCtx) {
    audioCtx = new AudioContext();
  }

  // Chrome (and other browsers) suspend the context until a user gesture.
  if (audioCtx.state === 'suspended') {
    void audioCtx.resume();
  }

  return audioCtx;
}

/**
 * Play a short tone via an OscillatorNode.
 *
 * @param frequency  Base frequency in Hz.
 * @param type       Oscillator waveform type.
 * @param durationMs Length of the tone in milliseconds.
 * @param rampTo     Optional second frequency for a pitch sweep.
 */
function playTone(
  frequency: number,
  type: OscillatorType,
  durationMs: number,
  rampTo?: number,
): void {
  if (!config.enabled) return;

  const ctx = getAudioContext();
  if (!ctx) return;

  const now = ctx.currentTime;
  const duration = durationMs / 1000;

  // Oscillator
  const osc = ctx.createOscillator();
  osc.type = type;
  osc.frequency.setValueAtTime(frequency, now);
  if (rampTo !== undefined) {
    osc.frequency.exponentialRampToValueAtTime(rampTo, now + duration);
  }

  // Gain envelope: quick attack, smooth release.
  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0, now);
  gain.gain.linearRampToValueAtTime(config.volume, now + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.001, now + duration);

  // Connect graph.
  osc.connect(gain);
  gain.connect(ctx.destination);

  osc.start(now);
  osc.stop(now + duration);
}

/**
 * Play two consecutive tones (a "double-beep" pattern).
 */
function playDoubleTone(
  freq1: number,
  freq2: number,
  type: OscillatorType,
  toneDurationMs: number,
  gapMs: number,
): void {
  if (!config.enabled) return;

  const ctx = getAudioContext();
  if (!ctx) return;

  const now = ctx.currentTime;
  const toneDur = toneDurationMs / 1000;
  const gap = gapMs / 1000;

  // -- First tone --
  const osc1 = ctx.createOscillator();
  osc1.type = type;
  osc1.frequency.setValueAtTime(freq1, now);

  const gain1 = ctx.createGain();
  gain1.gain.setValueAtTime(0, now);
  gain1.gain.linearRampToValueAtTime(config.volume, now + 0.01);
  gain1.gain.exponentialRampToValueAtTime(0.001, now + toneDur);

  osc1.connect(gain1);
  gain1.connect(ctx.destination);
  osc1.start(now);
  osc1.stop(now + toneDur);

  // -- Second tone --
  const startTwo = now + toneDur + gap;

  const osc2 = ctx.createOscillator();
  osc2.type = type;
  osc2.frequency.setValueAtTime(freq2, startTwo);

  const gain2 = ctx.createGain();
  gain2.gain.setValueAtTime(0, startTwo);
  gain2.gain.linearRampToValueAtTime(config.volume, startTwo + 0.01);
  gain2.gain.exponentialRampToValueAtTime(0.001, startTwo + toneDur);

  osc2.connect(gain2);
  gain2.connect(ctx.destination);
  osc2.start(startTwo);
  osc2.stop(startTwo + toneDur);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Play an audible cue indicating a bullish or bearish signal.
 *
 * - **Bullish**: ascending double-beep (C5 -> E5) — optimistic.
 * - **Bearish**: descending double-beep (E5 -> C5) — cautionary.
 */
export function playSignalSound(direction: 'bullish' | 'bearish'): void {
  const C5 = 523.25;
  const E5 = 659.25;

  if (direction === 'bullish') {
    playDoubleTone(C5, E5, 'sine', 100, 50);
  } else {
    playDoubleTone(E5, C5, 'sine', 100, 50);
  }
}

/**
 * Play a generic notification chime — a short triangle-wave ping.
 */
export function playNotificationSound(): void {
  playTone(880, 'triangle', 150);
}

/**
 * Set the master volume for all procedural sounds.
 *
 * @param volume  A value between 0 (silent) and 1 (full volume).
 */
export function setMasterVolume(volume: number): void {
  config.volume = Math.max(0, Math.min(1, volume));
}

/**
 * Mute or unmute all sounds.
 */
export function setMuted(muted: boolean): void {
  config.enabled = !muted;
}
