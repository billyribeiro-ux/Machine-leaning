<!--
  SubscriptionManager.svelte
  Plan comparison grid with tier details, feature checkmarks,
  current plan badge, and upgrade buttons.
  Elite plan is highlighted as the recommended option.
-->
<script lang="ts">
  type Tier = 'free' | 'pro' | 'elite' | 'institutional';

  interface PlanFeature {
    label: string;
    free: boolean;
    pro: boolean;
    elite: boolean;
    institutional: boolean;
  }

  interface PlanInfo {
    id: Tier;
    name: string;
    price: string;
    period: string;
    tagline: string;
    highlights: string[];
    recommended: boolean;
  }

  interface SubscriptionManagerProps {
    /** Current subscription tier. */
    currentTier: Tier;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    currentTier,
    class: className = '',
  }: SubscriptionManagerProps = $props();

  const plans: PlanInfo[] = [
    {
      id: 'free',
      name: 'Free',
      price: '$0',
      period: 'forever',
      tagline: 'Get started with basic scanning',
      highlights: ['3 scans', '15-min delayed data', 'Basic signals'],
      recommended: false,
    },
    {
      id: 'pro',
      name: 'Pro',
      price: '$29',
      period: '/mo',
      tagline: 'Real-time data for active traders',
      highlights: ['Unlimited scans', 'Real-time data', 'All signals', 'Alert system'],
      recommended: false,
    },
    {
      id: 'elite',
      name: 'Elite',
      price: '$79',
      period: '/mo',
      tagline: 'Professional-grade trading intelligence',
      highlights: ['Options flow', 'Dark pool data', 'Institutional signals', 'API access'],
      recommended: true,
    },
    {
      id: 'institutional',
      name: 'Institutional',
      price: '$299',
      period: '/mo',
      tagline: 'Enterprise-level for teams and funds',
      highlights: ['Multi-seat licenses', 'Priority support', 'Custom scans', 'Dedicated infra'],
      recommended: false,
    },
  ];

  const features: PlanFeature[] = [
    { label: 'Stock scanner',            free: true,  pro: true,  elite: true,  institutional: true },
    { label: 'Number of scans',          free: false, pro: true,  elite: true,  institutional: true },
    { label: 'Real-time data',           free: false, pro: true,  elite: true,  institutional: true },
    { label: 'Advanced signals',         free: false, pro: true,  elite: true,  institutional: true },
    { label: 'Custom alerts',            free: false, pro: true,  elite: true,  institutional: true },
    { label: 'Options flow',             free: false, pro: false, elite: true,  institutional: true },
    { label: 'Dark pool data',           free: false, pro: false, elite: true,  institutional: true },
    { label: 'Institutional signals',    free: false, pro: false, elite: true,  institutional: true },
    { label: 'API access',               free: false, pro: false, elite: true,  institutional: true },
    { label: 'Multi-seat licenses',      free: false, pro: false, elite: false, institutional: true },
    { label: 'Priority support',         free: false, pro: false, elite: false, institutional: true },
    { label: 'Custom scan builder',      free: false, pro: false, elite: false, institutional: true },
    { label: 'Dedicated infrastructure', free: false, pro: false, elite: false, institutional: true },
  ];

  const tierOrder: Tier[] = ['free', 'pro', 'elite', 'institutional'];

  function featureForTier(feature: PlanFeature, tier: Tier): boolean {
    return feature[tier];
  }

  function isCurrent(tier: Tier): boolean {
    return currentTier === tier;
  }

  function isDowngrade(tier: Tier): boolean {
    return tierOrder.indexOf(tier) < tierOrder.indexOf(currentTier);
  }
</script>

<div class="subscription-root {className}">
  <!-- Section header -->
  <div class="section-header">
    <h2 class="section-title">Subscription Plans</h2>
    <p class="section-subtitle">Choose the plan that fits your trading needs</p>
  </div>

  <!-- Plan cards grid -->
  <div class="plan-grid">
    {#each plans as plan (plan.id)}
      {@const current = isCurrent(plan.id)}
      {@const downgrade = isDowngrade(plan.id)}
      <div
        class="plan-card"
        class:plan-card--recommended={plan.recommended}
        class:plan-card--current={current}
      >
        <!-- Recommended badge -->
        {#if plan.recommended}
          <div class="recommended-badge-wrapper">
            <span class="recommended-badge">Recommended</span>
          </div>
        {/if}

        <!-- Plan name and price -->
        <div class="plan-header" class:plan-header--with-badge={plan.recommended}>
          <div class="plan-name-row">
            <h3 class="plan-name">{plan.name}</h3>
            {#if current}
              <span class="current-badge">Current</span>
            {/if}
          </div>
          <p class="plan-tagline">{plan.tagline}</p>
          <div class="plan-price-row">
            <span class="plan-price">{plan.price}</span>
            <span class="plan-period">{plan.period}</span>
          </div>
        </div>

        <!-- Highlights list -->
        <ul class="highlights-list">
          {#each plan.highlights as highlight}
            <li class="highlight-item">
              <svg xmlns="http://www.w3.org/2000/svg" class="check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              {highlight}
            </li>
          {/each}
        </ul>

        <!-- Action button -->
        {#if current}
          <button class="plan-btn plan-btn--current" disabled>
            Current Plan
          </button>
        {:else if downgrade}
          <button class="plan-btn plan-btn--downgrade">
            Downgrade
          </button>
        {:else}
          <button
            class="plan-btn plan-btn--upgrade"
            class:plan-btn--upgrade-recommended={plan.recommended}
            class:plan-btn--upgrade-default={!plan.recommended}
          >
            Upgrade to {plan.name}
          </button>
        {/if}
      </div>
    {/each}
  </div>

  <!-- Feature comparison table -->
  <div class="comparison-section">
    <h3 class="comparison-title">Feature Comparison</h3>
    <div class="comparison-table-wrapper">
      <table class="comparison-table">
        <thead>
          <tr class="comparison-thead-row">
            <th class="comparison-th comparison-th--feature">Feature</th>
            {#each plans as plan (plan.id)}
              <th class="comparison-th comparison-th--plan" class:comparison-th--active={isCurrent(plan.id)}>
                {plan.name}
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each features as feature, i (feature.label)}
            <tr class="comparison-row" class:comparison-row--even={i % 2 === 0} class:comparison-row--odd={i % 2 !== 0}>
              <td class="comparison-td comparison-td--label">{feature.label}</td>
              {#each tierOrder as tier}
                <td class="comparison-td comparison-td--value">
                  {#if featureForTier(feature, tier)}
                    <svg xmlns="http://www.w3.org/2000/svg" class="check-icon-table" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  {:else}
                    <span class="feature-dash">&mdash;</span>
                  {/if}
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
</div>

<style>
  /* ── Root layout ── */
  .subscription-root {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }

  /* ── Section header ── */
  .section-header {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .section-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: oklch(0.90 0 0);
  }

  .section-subtitle {
    font-size: 0.875rem;
    color: oklch(0.55 0 0);
  }

  /* ── Plan cards grid ── */
  .plan-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  @media (min-width: 768px) {
    .plan-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (min-width: 1280px) {
    .plan-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }

  /* ── Plan card ── */
  .plan-card {
    position: relative;
    display: flex;
    flex-direction: column;
    border-radius: 0.75rem;
    border: 1px solid oklch(0.22 0 0);
    padding: 1.25rem;
    background-color: oklch(0.12 0 0);
    transition: all 200ms;
  }

  .plan-card--recommended {
    border-color: oklch(0.45 0.15 250);
    background-color: oklch(0.14 0.01 250);
    box-shadow: 0 0 24px oklch(0.45 0.15 250 / 0.12);
  }

  .plan-card--current {
    outline: 2px solid oklch(0.55 0.15 145);
    outline-offset: 1px;
  }

  /* ── Recommended badge ── */
  .recommended-badge-wrapper {
    position: absolute;
    top: -0.75rem;
    left: 50%;
    transform: translateX(-50%);
  }

  .recommended-badge {
    display: inline-block;
    padding: 0.125rem 0.75rem;
    border-radius: 9999px;
    background-color: oklch(0.45 0.15 250);
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: white;
  }

  /* ── Plan header (name + price) ── */
  .plan-header {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .plan-header--with-badge {
    margin-top: 0.5rem;
  }

  .plan-name-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .plan-name {
    font-size: 1rem;
    font-weight: 700;
    color: oklch(0.88 0 0);
  }

  .current-badge {
    display: inline-flex;
    align-items: center;
    padding: 0.125rem 0.5rem;
    border-radius: 9999px;
    background-color: oklch(0.22 0.04 145);
    font-size: 10px;
    font-weight: 600;
    color: oklch(0.65 0.15 145);
  }

  .plan-tagline {
    font-size: 0.75rem;
    color: oklch(0.50 0 0);
  }

  .plan-price-row {
    display: flex;
    align-items: baseline;
    gap: 0.25rem;
    margin-top: 0.25rem;
  }

  .plan-price {
    font-size: 1.5rem;
    font-weight: 700;
    color: oklch(0.92 0 0);
  }

  .plan-period {
    font-size: 0.75rem;
    color: oklch(0.45 0 0);
  }

  /* ── Highlights list ── */
  .highlights-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    flex: 1;
    list-style: none;
    padding: 0;
    margin-top: 0;
  }

  .highlight-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.75rem;
    color: oklch(0.72 0 0);
  }

  .check-icon {
    width: 0.875rem;
    height: 0.875rem;
    flex-shrink: 0;
    color: oklch(0.55 0.15 145);
  }

  /* ── Action buttons ── */
  .plan-btn {
    width: 100%;
    padding: 0.625rem 0;
    border-radius: 0.5rem;
    font-size: 0.875rem;
  }

  .plan-btn--current {
    font-weight: 500;
    border: 1px solid oklch(0.30 0 0);
    background-color: oklch(0.16 0 0);
    color: oklch(0.55 0 0);
    cursor: default;
  }

  .plan-btn--downgrade {
    font-weight: 500;
    border: 1px solid oklch(0.28 0 0);
    background-color: transparent;
    color: oklch(0.60 0 0);
    transition: color 150ms, background-color 150ms;
    cursor: pointer;
  }

  .plan-btn--downgrade:hover {
    background-color: oklch(0.16 0 0);
  }

  .plan-btn--upgrade {
    font-weight: 600;
    border: none;
    cursor: pointer;
    transition: all 150ms;
    color: white;
  }

  .plan-btn--upgrade-recommended {
    background-color: oklch(0.50 0.15 250);
    box-shadow: 0 1px 2px oklch(0.50 0.15 250 / 0.3);
  }

  .plan-btn--upgrade-recommended:hover {
    background-color: oklch(0.55 0.16 250);
  }

  .plan-btn--upgrade-default {
    background-color: oklch(0.55 0.15 145);
    box-shadow: 0 1px 2px oklch(0.55 0.15 145 / 0.25);
  }

  .plan-btn--upgrade-default:hover {
    background-color: oklch(0.60 0.16 145);
  }

  /* ── Feature comparison section ── */
  .comparison-section {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .comparison-title {
    font-size: 0.875rem;
    font-weight: 600;
    color: oklch(0.80 0 0);
  }

  .comparison-table-wrapper {
    overflow-x: auto;
    border-radius: 0.5rem;
    border: 1px solid oklch(0.20 0 0);
  }

  .comparison-table {
    width: 100%;
    font-size: 0.75rem;
    border-collapse: collapse;
  }

  /* ── Table head ── */
  .comparison-thead-row {
    border-bottom: 1px solid oklch(0.20 0 0);
    background-color: oklch(0.11 0 0);
  }

  .comparison-th {
    padding: 0.75rem 1rem;
    font-weight: 500;
    color: oklch(0.60 0 0);
  }

  .comparison-th--feature {
    text-align: left;
  }

  .comparison-th--plan {
    text-align: center;
  }

  .comparison-th--active {
    color: oklch(0.65 0.15 145);
  }

  /* ── Table body rows ── */
  .comparison-row {
    border-bottom: 1px solid oklch(0.16 0 0);
  }

  .comparison-row--even {
    background-color: oklch(0.12 0 0);
  }

  .comparison-row--odd {
    background-color: oklch(0.13 0 0);
  }

  /* ── Table cells ── */
  .comparison-td {
    padding: 0.625rem 1rem;
  }

  .comparison-td--label {
    color: oklch(0.72 0 0);
  }

  .comparison-td--value {
    text-align: center;
  }

  .check-icon-table {
    width: 1rem;
    height: 1rem;
    margin-inline: auto;
    color: oklch(0.55 0.15 145);
  }

  .feature-dash {
    color: oklch(0.30 0 0);
  }
</style>
