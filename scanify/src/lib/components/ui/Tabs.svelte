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

<div class="relative {className}" role="tablist" aria-orientation="horizontal">
	<div class="flex border-b border-[oklch(0.22_0_0)]">
		{#each tabs as tab, i (tab.id)}
			<button
				bind:this={tabRefs[i]}
				type="button"
				role="tab"
				id="tab-{tab.id}"
				aria-selected={activeTab === tab.id}
				aria-controls="tabpanel-{tab.id}"
				tabindex={activeTab === tab.id ? 0 : -1}
				class="relative flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors duration-150 outline-none
					{activeTab === tab.id
						? 'text-[oklch(0.90_0_0)]'
						: 'text-[oklch(0.50_0_0)] hover:text-[oklch(0.70_0_0)]'}"
				onclick={() => selectTab(tab.id)}
				onkeydown={(e) => handleKeydown(e, i)}
			>
				{#if tab.icon}
					<span class="text-base leading-none">{tab.icon}</span>
				{/if}
				{tab.label}
			</button>
		{/each}
	</div>

	<!-- Animated underline indicator -->
	<div
		class="absolute bottom-0 left-0 h-0.5 bg-[oklch(0.55_0.15_145)] transition-all duration-200 ease-out"
		style={indicatorStyle}
	></div>
</div>
