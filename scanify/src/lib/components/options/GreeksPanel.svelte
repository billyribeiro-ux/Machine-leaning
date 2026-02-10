<!--
  GreeksPanel.svelte
  Dashboard of 5 Greek cards (delta, gamma, theta, vega, rho),
  each with value, label, and range bar.
  Color intensity based on magnitude.
-->
<script lang="ts">
  interface Greeks {
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
    rho: number;
  }

  interface Props {
    greeks: Greeks;
    class?: string;
  }

  let {
    greeks,
    class: className = ''
  }: Props = $props();

  interface GreekMeta {
    key: keyof Greeks;
    label: string;
    symbol: string;
    min: number;
    max: number;
    description: string;
    hue: number;
  }

  const greekDefs: GreekMeta[] = [
    { key: 'delta', label: 'Delta', symbol: '\u0394', min: -1, max: 1, description: 'Price sensitivity', hue: 155 },
    { key: 'gamma', label: 'Gamma', symbol: '\u0393', min: 0, max: 0.15, description: 'Delta rate of change', hue: 250 },
    { key: 'theta', label: 'Theta', symbol: '\u0398', min: -1, max: 0, description: 'Time decay per day', hue: 25 },
    { key: 'vega', label: 'Vega', symbol: '\u03BD', min: 0, max: 1, description: 'Volatility sensitivity', hue: 290 },
    { key: 'rho', label: 'Rho', symbol: '\u03C1', min: -0.5, max: 0.5, description: 'Interest rate sensitivity', hue: 85 }
  ];

  function normalizeValue(val: number, min: number, max: number): number {
    if (max === min) return 0.5;
    return Math.max(0, Math.min(1, (val - min) / (max - min)));
  }

  function intensityColor(normalized: number, hue: number): string {
    const lightness = 0.30 + normalized * 0.35;
    const chroma = 0.04 + normalized * 0.14;
    return `oklch(${lightness} ${chroma} ${hue})`;
  }

  function valueColor(normalized: number, hue: number): string {
    const lightness = 0.55 + normalized * 0.30;
    const chroma = 0.06 + normalized * 0.14;
    return `oklch(${lightness} ${chroma} ${hue})`;
  }

  function formatGreek(val: number): string {
    if (Math.abs(val) >= 1) return val.toFixed(3);
    return val.toFixed(4);
  }
</script>

<div class="flex flex-col gap-3 {className}">
  <span class="text-sm font-semibold text-[var(--text-primary)] px-1">Options Greeks</span>

  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
    {#each greekDefs as def (def.key)}
      {@const val = greeks[def.key]}
      {@const normalized = normalizeValue(val, def.min, def.max)}

      <div class="panel p-4 flex flex-col gap-3">
        <!-- Header: symbol + label -->
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5">
            <span
              class="text-lg font-bold"
              style="color: {valueColor(normalized, def.hue)};"
            >
              {def.symbol}
            </span>
            <span class="text-xs font-medium text-[var(--text-tertiary)]">{def.label}</span>
          </div>
        </div>

        <!-- Value -->
        <div
          class="mono-nums text-xl font-bold"
          style="color: {valueColor(normalized, def.hue)};"
        >
          {formatGreek(val)}
        </div>

        <!-- Range bar -->
        <div class="flex flex-col gap-1">
          <div class="w-full h-2.5 rounded-full bg-[var(--bg-void)] overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500"
              style="width: {normalized * 100}%; background-color: {intensityColor(normalized, def.hue)};"
            ></div>
          </div>
          <div class="flex justify-between text-[9px] mono-nums text-[var(--text-disabled)]">
            <span>{def.min}</span>
            <span>{def.max}</span>
          </div>
        </div>

        <!-- Description -->
        <span class="text-2xs text-[var(--text-tertiary)]">{def.description}</span>
      </div>
    {/each}
  </div>
</div>
