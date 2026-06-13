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
    { key: 'delta', label: 'Delta', symbol: 'Δ', min: -1, max: 1, description: 'Price sensitivity', hue: 155 },
    { key: 'gamma', label: 'Gamma', symbol: 'Γ', min: 0, max: 0.15, description: 'Delta rate of change', hue: 250 },
    { key: 'theta', label: 'Theta', symbol: 'Θ', min: -1, max: 0, description: 'Time decay per day', hue: 25 },
    { key: 'vega', label: 'Vega', symbol: 'ν', min: 0, max: 1, description: 'Volatility sensitivity', hue: 290 },
    { key: 'rho', label: 'Rho', symbol: 'ρ', min: -0.5, max: 0.5, description: 'Interest rate sensitivity', hue: 85 }
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

<div class="greeks-wrapper {className}">
  <span class="section-title">Options Greeks</span>

  <div class="greeks-grid">
    {#each greekDefs as def (def.key)}
      {@const val = greeks[def.key]}
      {@const normalized = normalizeValue(val, def.min, def.max)}

      <div class="panel greek-card">
        <!-- Header: symbol + label -->
        <div class="greek-header">
          <div class="greek-symbol-group">
            <span
              class="greek-symbol"
              style="color: {valueColor(normalized, def.hue)};"
            >
              {def.symbol}
            </span>
            <span class="greek-label">{def.label}</span>
          </div>
        </div>

        <!-- Value -->
        <div
          class="mono-nums greek-value"
          style="color: {valueColor(normalized, def.hue)};"
        >
          {formatGreek(val)}
        </div>

        <!-- Range bar -->
        <div class="range-section">
          <div class="range-bar-bg">
            <div
              class="range-bar-fill"
              style="width: {normalized * 100}%; background-color: {intensityColor(normalized, def.hue)};"
            ></div>
          </div>
          <div class="range-labels mono-nums">
            <span>{def.min}</span>
            <span>{def.max}</span>
          </div>
        </div>

        <!-- Description -->
        <span class="text-2xs greek-desc">{def.description}</span>
      </div>
    {/each}
  </div>
</div>

<style>
  .greeks-wrapper {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .section-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
    padding-inline: 4px;
  }

  .greeks-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }

  @media (min-width: 640px) {
    .greeks-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  @media (min-width: 1024px) {
    .greeks-grid {
      grid-template-columns: repeat(5, 1fr);
    }
  }

  .greek-card {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .greek-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .greek-symbol-group {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .greek-symbol {
    font-size: 1.125rem;
    font-weight: 700;
  }

  .greek-label {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--text-tertiary);
  }

  .greek-value {
    font-size: 1.25rem;
    font-weight: 700;
  }

  .range-section {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .range-bar-bg {
    width: 100%;
    height: 10px;
    border-radius: 9999px;
    background-color: var(--bg-void);
    overflow: hidden;
  }

  .range-bar-fill {
    height: 100%;
    border-radius: 9999px;
    transition: all 500ms;
  }

  .range-labels {
    display: flex;
    justify-content: space-between;
    font-size: 9px;
    color: var(--text-disabled);
  }

  .greek-desc {
    color: var(--text-tertiary);
  }
</style>
