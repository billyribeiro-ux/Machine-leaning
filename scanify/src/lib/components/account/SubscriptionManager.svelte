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

<div class="flex flex-col gap-8 {className}">
  <!-- Section header -->
  <div class="flex flex-col gap-1">
    <h2 class="text-lg font-semibold text-[oklch(0.90_0_0)]">Subscription Plans</h2>
    <p class="text-sm text-[oklch(0.55_0_0)]">Choose the plan that fits your trading needs</p>
  </div>

  <!-- Plan cards grid -->
  <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
    {#each plans as plan (plan.id)}
      {@const current = isCurrent(plan.id)}
      {@const downgrade = isDowngrade(plan.id)}
      <div
        class="
          relative flex flex-col rounded-xl border p-5 transition-all duration-200
          {plan.recommended
            ? 'border-[oklch(0.45_0.15_250)] bg-[oklch(0.14_0.01_250)] shadow-[0_0_24px_oklch(0.45_0.15_250/0.12)]'
            : 'border-[oklch(0.22_0_0)] bg-[oklch(0.12_0_0)]'}
          {current
            ? 'ring-2 ring-[oklch(0.55_0.15_145)] ring-offset-1 ring-offset-[oklch(0.10_0_0)]'
            : ''}
        "
      >
        <!-- Recommended badge -->
        {#if plan.recommended}
          <div class="absolute -top-3 left-1/2 -translate-x-1/2">
            <span class="inline-block px-3 py-0.5 rounded-full bg-[oklch(0.45_0.15_250)] text-[10px] font-bold uppercase tracking-widest text-white">
              Recommended
            </span>
          </div>
        {/if}

        <!-- Plan name and price -->
        <div class="flex flex-col gap-2 mb-4 {plan.recommended ? 'mt-2' : ''}">
          <div class="flex items-center gap-2">
            <h3 class="text-base font-bold text-[oklch(0.88_0_0)]">{plan.name}</h3>
            {#if current}
              <span class="inline-flex items-center px-2 py-0.5 rounded-full bg-[oklch(0.22_0.04_145)] text-[10px] font-semibold text-[oklch(0.65_0.15_145)]">
                Current
              </span>
            {/if}
          </div>
          <p class="text-xs text-[oklch(0.50_0_0)]">{plan.tagline}</p>
          <div class="flex items-baseline gap-1 mt-1">
            <span class="text-2xl font-bold text-[oklch(0.92_0_0)]">{plan.price}</span>
            <span class="text-xs text-[oklch(0.45_0_0)]">{plan.period}</span>
          </div>
        </div>

        <!-- Highlights list -->
        <ul class="flex flex-col gap-2 mb-6 flex-1">
          {#each plan.highlights as highlight}
            <li class="flex items-center gap-2 text-xs text-[oklch(0.72_0_0)]">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 shrink-0 text-[oklch(0.55_0.15_145)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              {highlight}
            </li>
          {/each}
        </ul>

        <!-- Action button -->
        {#if current}
          <button
            class="
              w-full py-2.5 rounded-lg text-sm font-medium
              border border-[oklch(0.30_0_0)] bg-[oklch(0.16_0_0)]
              text-[oklch(0.55_0_0)] cursor-default
            "
            disabled
          >
            Current Plan
          </button>
        {:else if downgrade}
          <button
            class="
              w-full py-2.5 rounded-lg text-sm font-medium
              border border-[oklch(0.28_0_0)] bg-transparent
              text-[oklch(0.60_0_0)] hover:bg-[oklch(0.16_0_0)]
              transition-colors duration-150 cursor-pointer
            "
          >
            Downgrade
          </button>
        {:else}
          <button
            class="
              w-full py-2.5 rounded-lg text-sm font-semibold
              border-none cursor-pointer transition-all duration-150
              {plan.recommended
                ? 'bg-[oklch(0.50_0.15_250)] hover:bg-[oklch(0.55_0.16_250)] text-white shadow-sm shadow-[oklch(0.50_0.15_250/0.3)]'
                : 'bg-[oklch(0.55_0.15_145)] hover:bg-[oklch(0.60_0.16_145)] text-white shadow-sm shadow-[oklch(0.55_0.15_145/0.25)]'}
            "
          >
            Upgrade to {plan.name}
          </button>
        {/if}
      </div>
    {/each}
  </div>

  <!-- Feature comparison table -->
  <div class="flex flex-col gap-3">
    <h3 class="text-sm font-semibold text-[oklch(0.80_0_0)]">Feature Comparison</h3>
    <div class="overflow-x-auto rounded-lg border border-[oklch(0.20_0_0)]">
      <table class="w-full text-xs">
        <thead>
          <tr class="border-b border-[oklch(0.20_0_0)] bg-[oklch(0.11_0_0)]">
            <th class="text-left px-4 py-3 font-medium text-[oklch(0.60_0_0)]">Feature</th>
            {#each plans as plan (plan.id)}
              <th class="text-center px-4 py-3 font-medium {isCurrent(plan.id) ? 'text-[oklch(0.65_0.15_145)]' : 'text-[oklch(0.60_0_0)]'}">
                {plan.name}
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each features as feature, i (feature.label)}
            <tr class="border-b border-[oklch(0.16_0_0)] {i % 2 === 0 ? 'bg-[oklch(0.12_0_0)]' : 'bg-[oklch(0.13_0_0)]'}">
              <td class="px-4 py-2.5 text-[oklch(0.72_0_0)]">{feature.label}</td>
              {#each tierOrder as tier}
                <td class="text-center px-4 py-2.5">
                  {#if featureForTier(feature, tier)}
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 mx-auto text-[oklch(0.55_0.15_145)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  {:else}
                    <span class="text-[oklch(0.30_0_0)]">&mdash;</span>
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
