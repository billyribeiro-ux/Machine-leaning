<script lang="ts">
	interface Tab {
		id: string;
		label: string;
		icon?: string;
	}

	interface Props {
		tabs?: Tab[];
		activeTab?: string;
		class?: string;
		ontabchange?: (tabId: string) => void;
	}

	let {
		tabs = [],
		activeTab = $bindable(''),
		class: className = '',
		ontabchange
	}: Props = $props();

	let tabRefs: HTMLButtonElement[] = $state([]);
	let indicatorStyle = $state('');

	function updateIndicator() {
		const activeIndex = tabs.findIndex((t) => t.id === activeTab);
		if (activeIndex >= 0 && tabRefs[activeIndex]) {
			const el = tabRefs[activeIndex];
			indicatorStyle = `width: ${el.offsetWidth}px; transform: translateX(${el.offsetLeft}px);`;
		}
	}

	function selectTab(tabId: string) {
		activeTab = tabId;
		ontabchange?.(tabId);
		// Defer indicator update to next tick so DOM is updated
		requestAnimationFrame(updateIndicator);
	}

	function handleKeydown(e: KeyboardEvent, index: number) {
		let newIndex = index;
		if (e.key === 'ArrowRight') {
			e.preventDefault();
			newIndex = (index + 1) % tabs.length;
		} else if (e.key === 'ArrowLeft') {
			e.preventDefault();
			newIndex = (index - 1 + tabs.length) % tabs.length;
		} else if (e.key === 'Home') {
			e.preventDefault();
			newIndex = 0;
		} else if (e.key === 'End') {
			e.preventDefault();
			newIndex = tabs.length - 1;
		} else {
			return;
		}

		selectTab(tabs[newIndex].id);
		tabRefs[newIndex]?.focus();
	}

	// Initialize active tab if not set
	$effect(() => {
		if (!activeTab && tabs.length > 0) {
			activeTab = tabs[0].id;
		}
	});

	// Update indicator when activeTab or tabs change
	$effect(() => {
		// Read these to track them
		activeTab;
		tabs;
		requestAnimationFrame(updateIndicator);
	});
</script>

<div class="tabs-container {className}" role="tablist" aria-orientation="horizontal">
	<div class="tabs-list">
		{#each tabs as tab, i (tab.id)}
			<button
				bind:this={tabRefs[i]}
				type="button"
				role="tab"
				id="tab-{tab.id}"
				aria-selected={activeTab === tab.id}
				aria-controls="tabpanel-{tab.id}"
				tabindex={activeTab === tab.id ? 0 : -1}
				class="tab-button"
				class:is-active={activeTab === tab.id}
				onclick={() => selectTab(tab.id)}
				onkeydown={(e) => handleKeydown(e, i)}
			>
				{#if tab.icon}
					<span class="tab-icon">{tab.icon}</span>
				{/if}
				{tab.label}
			</button>
		{/each}
	</div>

	<!-- Animated underline indicator -->
	<div
		class="tab-indicator"
		style={indicatorStyle}
	></div>
</div>

<style>
	.tabs-container {
		position: relative;
	}

	.tabs-list {
		display: flex;
		border-bottom: 1px solid oklch(0.22 0 0);
	}

	.tab-button {
		position: relative;
		display: flex;
		align-items: center;
		gap: 8px;
		padding-inline: 16px;
		padding-block: 10px;
		font-size: var(--text-sm);
		font-weight: 500;
		transition: color 150ms;
		outline: none;
		color: oklch(0.50 0 0);
	}

	.tab-button:hover {
		color: oklch(0.70 0 0);
	}

	.tab-button.is-active {
		color: oklch(0.90 0 0);
	}

	.tab-icon {
		font-size: var(--text-base);
		line-height: 1;
	}

	.tab-indicator {
		position: absolute;
		bottom: 0;
		left: 0;
		height: 2px;
		background-color: oklch(0.55 0.15 145);
		transition: all 200ms ease-out;
	}
</style>
