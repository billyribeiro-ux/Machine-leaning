<!--
  GEXProfile.svelte
  Horizontal bar chart in SVG showing Gamma Exposure (GEX) profile.
  Positive GEX green, negative red. Current price marker line.
-->
<script lang="ts">
  import { formatPrice } from '$lib/utils/format';

  interface GEXEntry {
    strike: number;
    gex: number;
  }

  interface Props {
    data: GEXEntry[];
    currentPrice?: number;
    class?: string;
  }

  let {
    data = [],
    currentPrice,
    class: className = ''
  }: Props = $props();

  const SVG_WIDTH = 500;
  const ROW_HEIGHT = 22;
  const LABEL_WIDTH = 60;
  const BAR_AREA_WIDTH = SVG_WIDTH - LABEL_WIDTH - 20;
  const BAR_CENTER_X = LABEL_WIDTH + BAR_AREA_WIDTH / 2;
  const PADDING_TOP = 28;
  const PADDING_BOTTOM = 10;

  let sortedData = $derived(
    [...data].sort((a, b) => a.strike - b.strike)
  );

  let svgHeight = $derived(
    Math.max(100, sortedData.length * ROW_HEIGHT + PADDING_TOP + PADDING_BOTTOM)
  );

  let maxAbsGex = $derived(
    sortedData.length > 0 ? Math.max(...sortedData.map((d) => Math.abs(d.gex)), 0.001) : 1
  );

  let currentPriceIdx = $derived.by(() => {
    if (currentPrice == null || sortedData.length === 0) return -1;
    let closest = 0;
    let minDist = Math.abs(sortedData[0].strike - currentPrice);
    for (let i = 1; i < sortedData.length; i++) {
      const dist = Math.abs(sortedData[i].strike - currentPrice);
      if (dist < minDist) {
        minDist = dist;
        closest = i;
      }
    }
    return closest;
  });

  function barWidth(gex: number): number {
    return (Math.abs(gex) / maxAbsGex) * (BAR_AREA_WIDTH / 2);
  }

  function barX(gex: number): number {
    if (gex >= 0) return BAR_CENTER_X;
    return BAR_CENTER_X - barWidth(gex);
  }

  function barColor(gex: number): string {
    if (gex > 0) {
      const intensity = Math.min(1, Math.abs(gex) / maxAbsGex);
      const lightness = 0.30 + intensity * 0.25;
      const chroma = 0.06 + intensity * 0.12;
      return `oklch(${lightness} ${chroma} 155)`;
    } else {
      const intensity = Math.min(1, Math.abs(gex) / maxAbsGex);
      const lightness = 0.28 + intensity * 0.22;
      const chroma = 0.06 + intensity * 0.14;
      return `oklch(${lightness} ${chroma} 25)`;
    }
  }

  function formatGex(val: number): string {
    const sign = val > 0 ? '+' : '';
    if (Math.abs(val) >= 1_000_000_000) return sign + (val / 1_000_000_000).toFixed(1) + 'B';
    if (Math.abs(val) >= 1_000_000) return sign + (val / 1_000_000).toFixed(1) + 'M';
    if (Math.abs(val) >= 1_000) return sign + (val / 1_000).toFixed(0) + 'K';
    return sign + val.toFixed(0);
  }

  let hoveredIdx = $state<number | null>(null);
</script>

<div class="panel flex flex-col gap-3 p-4 {className}">
  <div class="flex items-center justify-between">
    <span class="text-sm font-semibold text-[var(--text-primary)]">GEX Profile</span>
    {#if currentPrice != null}
      <span class="mono-nums text-xs text-[var(--text-secondary)]">Spot: {formatPrice(currentPrice)}</span>
    {/if}
  </div>

  <div class="overflow-auto">
    <svg
      width={SVG_WIDTH}
      height={svgHeight}
      viewBox="0 0 {SVG_WIDTH} {svgHeight}"
      class="select-none w-full"
      style="min-width: {SVG_WIDTH}px;"
      role="img"
      aria-label="GEX Profile Chart"
    >
      <!-- Header labels -->
      <text
        x={LABEL_WIDTH - 4}
        y={14}
        text-anchor="end"
        class="text-[9px] font-mono"
        fill="oklch(0.50 0 0)"
      >
        Strike
      </text>
      <text
        x={BAR_CENTER_X}
        y={14}
        text-anchor="middle"
        class="text-[9px] font-mono"
        fill="oklch(0.50 0 0)"
      >
        0
      </text>
      <text
        x={BAR_CENTER_X - BAR_AREA_WIDTH / 2}
        y={14}
        text-anchor="start"
        class="text-[9px] font-mono"
        fill="oklch(0.45 0.12 25)"
      >
        -{formatGex(maxAbsGex)}
      </text>
      <text
        x={BAR_CENTER_X + BAR_AREA_WIDTH / 2}
        y={14}
        text-anchor="end"
        class="text-[9px] font-mono"
        fill="oklch(0.45 0.10 155)"
      >
        +{formatGex(maxAbsGex)}
      </text>

      <!-- Center line -->
      <line
        x1={BAR_CENTER_X}
        y1={PADDING_TOP}
        x2={BAR_CENTER_X}
        y2={svgHeight - PADDING_BOTTOM}
        stroke="oklch(0.28 0.01 260)"
        stroke-width="1"
        stroke-dasharray="3 3"
      />

      <!-- Bars -->
      {#each sortedData as entry, idx (entry.strike)}
        {@const y = PADDING_TOP + idx * ROW_HEIGHT}
        {@const isCurrentPrice = currentPriceIdx === idx}
        {@const isHovered = hoveredIdx === idx}

        <!-- Row background for current price -->
        {#if isCurrentPrice}
          <rect
            x="0"
            y={y}
            width={SVG_WIDTH}
            height={ROW_HEIGHT}
            fill="oklch(0.18 0.04 250 / 0.3)"
          />
        {/if}

        <!-- Hover background -->
        {#if isHovered}
          <rect
            x="0"
            y={y}
            width={SVG_WIDTH}
            height={ROW_HEIGHT}
            fill="oklch(0.22 0.01 260 / 0.4)"
          />
        {/if}

        <!-- Strike label -->
        <text
          x={LABEL_WIDTH - 4}
          y={y + ROW_HEIGHT / 2}
          text-anchor="end"
          dominant-baseline="middle"
          class="text-[9px] font-mono"
          fill={isCurrentPrice ? 'oklch(0.85 0.12 250)' : 'oklch(0.55 0 0)'}
        >
          {entry.strike}
        </text>

        <!-- GEX bar -->
        <rect
          x={barX(entry.gex)}
          y={y + 3}
          width={Math.max(1, barWidth(entry.gex))}
          height={ROW_HEIGHT - 6}
          fill={barColor(entry.gex)}
          rx="2"
          class="cursor-crosshair transition-opacity duration-100"
          opacity={hoveredIdx !== null && !isHovered ? 0.5 : 1}
          onmouseenter={() => (hoveredIdx = idx)}
          onmouseleave={() => (hoveredIdx = null)}
        />

        <!-- GEX value on hover -->
        {#if isHovered}
          <text
            x={entry.gex >= 0 ? barX(entry.gex) + barWidth(entry.gex) + 4 : barX(entry.gex) - 4}
            y={y + ROW_HEIGHT / 2}
            text-anchor={entry.gex >= 0 ? 'start' : 'end'}
            dominant-baseline="middle"
            class="text-[9px] font-mono font-bold"
            fill={entry.gex >= 0 ? 'oklch(0.75 0.14 155)' : 'oklch(0.70 0.16 25)'}
          >
            {formatGex(entry.gex)}
          </text>
        {/if}
      {/each}

      <!-- Current price marker line -->
      {#if currentPriceIdx >= 0}
        {@const cpY = PADDING_TOP + currentPriceIdx * ROW_HEIGHT + ROW_HEIGHT / 2}
        <line
          x1={LABEL_WIDTH}
          y1={cpY}
          x2={SVG_WIDTH - 10}
          y2={cpY}
          stroke="oklch(0.65 0.14 250)"
          stroke-width="1.5"
          stroke-dasharray="6 3"
        />
        <circle
          cx={LABEL_WIDTH + 2}
          cy={cpY}
          r="3"
          fill="oklch(0.65 0.14 250)"
        />
      {/if}
    </svg>
  </div>

  {#if data.length === 0}
    <div class="flex items-center justify-center h-32 text-sm text-[var(--text-tertiary)]">
      No GEX data available
    </div>
  {/if}
</div>
