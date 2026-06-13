<!--
  SentimentGauge.svelte
  SVG semicircular gauge with color gradient arc from red (-100)
  through yellow (0) to green (+100), animated needle pointer,
  and value label in center.
-->
<script lang="ts">
  interface Props {
    value: number;
    label?: string;
    class?: string;
  }

  let {
    value,
    label = 'Sentiment',
    class: className = ''
  }: Props = $props();

  const WIDTH = 220;
  const HEIGHT = 130;
  const CX = 110;
  const CY = 110;
  const RADIUS = 85;
  const ARC_WIDTH = 12;
  const INNER_RADIUS = RADIUS - ARC_WIDTH;

  let clampedValue = $derived(Math.max(-100, Math.min(100, value)));

  // Map -100..+100 to 180..0 degrees (left to right arc)
  let needleAngleDeg = $derived(180 - ((clampedValue + 100) / 200) * 180);
  let needleAngleRad = $derived((needleAngleDeg * Math.PI) / 180);

  let needleX = $derived(CX + Math.cos(needleAngleRad) * (RADIUS - 6));
  let needleY = $derived(CY - Math.sin(needleAngleRad) * (RADIUS - 6));

  let sentimentLabel = $derived(
    clampedValue >= 60
      ? 'Extreme Greed'
      : clampedValue >= 25
        ? 'Greed'
        : clampedValue >= -25
          ? 'Neutral'
          : clampedValue >= -60
            ? 'Fear'
            : 'Extreme Fear'
  );

  let sentimentColor = $derived(
    clampedValue >= 60
      ? 'var(--bullish-bright)'
      : clampedValue >= 25
        ? 'var(--bullish)'
        : clampedValue >= -25
          ? 'var(--warning)'
          : clampedValue >= -60
            ? 'var(--bearish)'
            : 'var(--bearish-bright)'
  );

  function arcPath(startAngle: number, endAngle: number, r: number): string {
    const startRad = (startAngle * Math.PI) / 180;
    const endRad = (endAngle * Math.PI) / 180;
    const x1 = CX + Math.cos(startRad) * r;
    const y1 = CY - Math.sin(startRad) * r;
    const x2 = CX + Math.cos(endRad) * r;
    const y2 = CY - Math.sin(endRad) * r;
    const largeArc = Math.abs(endAngle - startAngle) > 180 ? 1 : 0;
    const sweep = endAngle < startAngle ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} ${sweep} ${x2} ${y2}`;
  }
</script>

<div class="gauge-wrapper {className}">
  <span class="gauge-label">{label}</span>

  <svg
    width={WIDTH}
    height={HEIGHT}
    viewBox="0 0 {WIDTH} {HEIGHT}"
    class="gauge-svg"
    role="img"
    aria-label="{label}: {clampedValue}"
  >
    <defs>
      <linearGradient id="sentiment-arc-gradient" x1="0" y1="0.5" x2="1" y2="0.5">
        <stop offset="0%" stop-color="oklch(0.58 0.18 25)" />
        <stop offset="30%" stop-color="oklch(0.72 0.16 60)" />
        <stop offset="50%" stop-color="oklch(0.80 0.16 85)" />
        <stop offset="70%" stop-color="oklch(0.72 0.16 120)" />
        <stop offset="100%" stop-color="oklch(0.64 0.16 155)" />
      </linearGradient>
    </defs>

    <!-- Background track arc -->
    <path
      d={arcPath(180, 0, RADIUS)}
      fill="none"
      stroke="oklch(0.18 0.02 260)"
      stroke-width={ARC_WIDTH}
      stroke-linecap="round"
    />

    <!-- Gradient arc -->
    <path
      d={arcPath(180, 0, RADIUS)}
      fill="none"
      stroke="url(#sentiment-arc-gradient)"
      stroke-width={ARC_WIDTH}
      stroke-linecap="round"
    />

    <!-- Tick marks -->
    {#each [-100, -50, 0, 50, 100] as tickVal}
      {@const tickAngle = (180 - ((tickVal + 100) / 200) * 180) * Math.PI / 180}
      {@const outerR = RADIUS + 6}
      {@const innerR = RADIUS + 2}
      <line
        x1={CX + Math.cos(tickAngle) * innerR}
        y1={CY - Math.sin(tickAngle) * innerR}
        x2={CX + Math.cos(tickAngle) * outerR}
        y2={CY - Math.sin(tickAngle) * outerR}
        stroke="oklch(0.40 0 0)"
        stroke-width="1.5"
      />
    {/each}

    <!-- Needle -->
    <line
      x1={CX}
      y1={CY}
      x2={needleX}
      y2={needleY}
      stroke={sentimentColor}
      stroke-width="2.5"
      stroke-linecap="round"
      style="transition: x2 0.6s cubic-bezier(0.16, 1, 0.3, 1), y2 0.6s cubic-bezier(0.16, 1, 0.3, 1);"
    />

    <!-- Needle hub -->
    <circle cx={CX} cy={CY} r="5" fill={sentimentColor} />
    <circle cx={CX} cy={CY} r="2.5" fill="oklch(0.14 0.02 260)" />

    <!-- Center value -->
    <text
      x={CX}
      y={CY - 22}
      text-anchor="middle"
      dominant-baseline="auto"
      class="gauge-value-text"
      fill={sentimentColor}
    >
      {clampedValue > 0 ? '+' : ''}{clampedValue.toFixed(0)}
    </text>

    <!-- Sentiment label -->
    <text
      x={CX}
      y={CY - 8}
      text-anchor="middle"
      dominant-baseline="hanging"
      class="gauge-sentiment-text"
      fill="oklch(0.55 0.01 260)"
    >
      {sentimentLabel}
    </text>

    <!-- Scale labels -->
    <text x="10" y={CY + 4} text-anchor="start" class="gauge-scale-text" fill="oklch(0.45 0 0)">-100</text>
    <text x={WIDTH - 10} y={CY + 4} text-anchor="end" class="gauge-scale-text" fill="oklch(0.45 0 0)">+100</text>
  </svg>
</div>

<style>
  .gauge-wrapper {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }

  .gauge-label {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .gauge-svg {
    user-select: none;
  }

  .gauge-value-text {
    font-size: 1.25rem;
    font-weight: 700;
    font-family: var(--font-mono);
  }

  .gauge-sentiment-text {
    font-size: 10px;
  }

  .gauge-scale-text {
    font-size: 9px;
    font-family: var(--font-mono);
  }
</style>
