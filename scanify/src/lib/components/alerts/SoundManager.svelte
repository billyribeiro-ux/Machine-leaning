<!--
  SoundManager.svelte
  Compact audio control: speaker icon, volume slider, mute toggle.
  Horizontal layout, small form factor.
-->
<script lang="ts">
  interface SoundManagerProps {
    /** Whether sound is enabled (bindable). */
    enabled: boolean;
    /** Volume level 0-1 (bindable). */
    volume: number;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    enabled = $bindable(true),
    volume = $bindable(0.7),
    class: className = '',
  }: SoundManagerProps = $props();

  /** Volume percentage for display. */
  let volumePercent = $derived(Math.round(volume * 100));

  /** Effective volume (0 when muted). */
  let effectiveVolume = $derived(enabled ? volume : 0);

  /** Icon state based on volume and enabled. */
  let iconState = $derived<'muted' | 'low' | 'medium' | 'high'>(
    !enabled || volume === 0 ? 'muted' :
    volume < 0.33 ? 'low' :
    volume < 0.66 ? 'medium' :
    'high'
  );

  /** Store volume before muting so we can restore it. */
  let volumeBeforeMute = $state(0.7);

  function toggleMute(): void {
    if (enabled) {
      volumeBeforeMute = volume;
      enabled = false;
    } else {
      enabled = true;
      if (volume === 0) {
        volume = volumeBeforeMute || 0.5;
      }
    }
  }

  function handleVolumeInput(e: Event): void {
    const target = e.target as HTMLInputElement;
    volume = parseFloat(target.value);
    if (volume > 0 && !enabled) {
      enabled = true;
    }
    if (volume === 0) {
      enabled = false;
    }
  }
</script>

<div
  class="flex items-center gap-2 {className}"
  role="group"
  aria-label="Sound controls"
>
  <!-- Speaker icon / mute toggle -->
  <button
    class="
      flex items-center justify-center
      w-7 h-7 rounded-md
      border-none bg-transparent
      text-[oklch(0.55_0_0)] hover:text-[oklch(0.80_0_0)]
      hover:bg-[oklch(0.20_0_0)]
      transition-colors duration-150 cursor-pointer
    "
    onclick={toggleMute}
    aria-label={enabled ? 'Mute sound' : 'Unmute sound'}
    title={enabled ? `Volume: ${volumePercent}%` : 'Muted'}
  >
    {#if iconState === 'muted'}
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
        <line x1="23" y1="9" x2="17" y2="15" />
        <line x1="17" y1="9" x2="23" y2="15" />
      </svg>
    {:else if iconState === 'low'}
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
      </svg>
    {:else if iconState === 'medium'}
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
        <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
      </svg>
    {:else}
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
        <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
      </svg>
    {/if}
  </button>

  <!-- Volume slider -->
  <div class="relative flex items-center w-20">
    <input
      type="range"
      min="0"
      max="1"
      step="0.01"
      value={enabled ? volume : 0}
      oninput={handleVolumeInput}
      class="
        volume-slider w-full h-1 appearance-none rounded-full outline-none cursor-pointer
        bg-[oklch(0.22_0_0)]
      "
      style="background: linear-gradient(to right, oklch(0.50 0.12 250) 0%, oklch(0.50 0.12 250) {effectiveVolume * 100}%, oklch(0.22 0 0) {effectiveVolume * 100}%, oklch(0.22 0 0) 100%);"
      aria-label="Volume"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={enabled ? volumePercent : 0}
    />
  </div>

  <!-- Volume level indicator -->
  <span class="text-[10px] font-mono tabular-nums w-7 text-right text-[oklch(0.50_0_0)]">
    {enabled ? volumePercent : 0}%
  </span>
</div>

<style>
  .volume-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: oklch(0.80 0 0);
    border: 2px solid oklch(0.50 0.12 250);
    cursor: pointer;
    transition: background 150ms ease, transform 150ms ease;
  }

  .volume-slider::-webkit-slider-thumb:hover {
    background: oklch(0.90 0 0);
    transform: scale(1.15);
  }

  .volume-slider::-moz-range-thumb {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: oklch(0.80 0 0);
    border: 2px solid oklch(0.50 0.12 250);
    cursor: pointer;
  }

  .volume-slider::-moz-range-thumb:hover {
    background: oklch(0.90 0 0);
  }
</style>
