<script lang="ts">
	import DataCell from './DataCell.svelte';

	export interface ColumnDef {
		id: string;
		label: string;
		width: number;
		type: 'price' | 'percent' | 'volume' | 'text' | 'signal' | 'sparkline' | 'timestamp' | 'ticker';
		sortable?: boolean;
		align?: 'left' | 'center' | 'right';
	}

	interface Props {
		columns: ColumnDef[];
		rows: Record<string, unknown>[];
		rowHeight?: number;
		onRowClick?: (row: Record<string, unknown>, index: number) => void;
		onSort?: (columnId: string, direction: 'asc' | 'desc') => void;
		sortBy?: string;
		sortDirection?: 'asc' | 'desc';
		class?: string;
	}

	let {
		columns,
		rows,
		rowHeight = 36,
		onRowClick,
		onSort,
		sortBy,
		sortDirection = 'asc',
		class: className = ''
	}: Props = $props();

	let scrollContainer: HTMLDivElement | undefined = $state();
	let scrollTop = $state(0);
	let containerHeight = $state(400);
	let selectedIndex = $state(-1);

	const headerHeight = 36;
	const overscan = 5;

	let totalHeight = $derived(rows.length * rowHeight);

	let visibleStart = $derived.by(() => {
		return Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
	});

	let visibleEnd = $derived.by(() => {
		const maxVisible = Math.ceil(containerHeight / rowHeight) + overscan * 2;
		return Math.min(rows.length, visibleStart + maxVisible);
	});

	let visibleRows = $derived.by(() => {
		const start = visibleStart;
		const end = visibleEnd;
		const result: { row: Record<string, unknown>; index: number; top: number }[] = [];
		for (let i = start; i < end; i++) {
			result.push({
				row: rows[i],
				index: i,
				top: i * rowHeight
			});
		}
		return result;
	});

	let totalWidth = $derived(columns.reduce((sum, col) => sum + col.width, 0));

	function handleScroll() {
		if (scrollContainer) {
			scrollTop = scrollContainer.scrollTop;
		}
	}

	function handleColumnSort(column: ColumnDef) {
		if (!column.sortable || !onSort) return;

		let newDirection: 'asc' | 'desc' = 'asc';
		if (sortBy === column.id) {
			newDirection = sortDirection === 'asc' ? 'desc' : 'asc';
		}
		onSort(column.id, newDirection);
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'j' || e.key === 'ArrowDown') {
			e.preventDefault();
			selectedIndex = Math.min(rows.length - 1, selectedIndex + 1);
			scrollToSelected();
		} else if (e.key === 'k' || e.key === 'ArrowUp') {
			e.preventDefault();
			selectedIndex = Math.max(0, selectedIndex - 1);
			scrollToSelected();
		} else if (e.key === 'Enter' && selectedIndex >= 0 && selectedIndex < rows.length) {
			e.preventDefault();
			onRowClick?.(rows[selectedIndex], selectedIndex);
		}
	}

	function scrollToSelected() {
		if (!scrollContainer) return;

		const rowTop = selectedIndex * rowHeight;
		const rowBottom = rowTop + rowHeight;
		const viewTop = scrollContainer.scrollTop;
		const viewBottom = viewTop + containerHeight - headerHeight;

		if (rowTop < viewTop) {
			scrollContainer.scrollTop = rowTop;
		} else if (rowBottom > viewBottom) {
			scrollContainer.scrollTop = rowBottom - containerHeight + headerHeight;
		}
	}

	function getAlignClass(align?: string): string {
		if (align === 'center') return 'justify-center text-center';
		if (align === 'right') return 'justify-end text-right';
		return 'justify-start text-left';
	}

	function getSortIndicator(column: ColumnDef): string {
		if (!column.sortable) return '';
		if (sortBy !== column.id) return ' \u25B3';
		return sortDirection === 'asc' ? ' \u25B2' : ' \u25BC';
	}

	$effect(() => {
		if (!scrollContainer) return;

		const observer = new ResizeObserver((entries) => {
			for (const entry of entries) {
				containerHeight = entry.contentRect.height;
			}
		});

		observer.observe(scrollContainer);

		return () => observer.disconnect();
	});
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class="relative flex flex-col overflow-hidden rounded-lg border border-[oklch(0.25_0.005_270)] bg-[oklch(0.13_0.005_270)] {className}"
	tabindex="0"
	onkeydown={handleKeydown}
	role="grid"
	aria-rowcount={rows.length}
	aria-colcount={columns.length}
>
	<!-- Fixed header -->
	<div
		class="sticky top-0 z-20 flex shrink-0 border-b border-[oklch(0.25_0.005_270)] bg-[oklch(0.15_0.005_270)]"
		style="height: {headerHeight}px; min-width: {totalWidth}px;"
		role="row"
	>
		{#each columns as column, colIdx (column.id)}
			<div
				class="flex shrink-0 items-center px-3 text-xs font-medium uppercase tracking-wider text-[oklch(0.55_0_0)] {getAlignClass(column.align)} {column.sortable ? 'cursor-pointer select-none hover:text-[oklch(0.75_0_0)] transition-colors' : ''} {colIdx === 0 ? 'sticky left-0 z-30 bg-[oklch(0.15_0.005_270)]' : ''}"
				style="width: {column.width}px; height: {headerHeight}px;"
				role="columnheader"
				aria-sort={sortBy === column.id ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
				onclick={() => handleColumnSort(column)}
				onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleColumnSort(column); }}
			>
				<span class="truncate">
					{column.label}{getSortIndicator(column)}
				</span>
			</div>
		{/each}
	</div>

	<!-- Scrollable body with virtual scrolling -->
	<div
		class="flex-1 overflow-auto"
		bind:this={scrollContainer}
		onscroll={handleScroll}
		role="rowgroup"
	>
		<div
			class="relative"
			style="height: {totalHeight}px; min-width: {totalWidth}px;"
		>
			{#each visibleRows as { row, index, top } (index)}
				<div
					class="absolute left-0 right-0 flex items-center border-b border-[oklch(0.18_0.005_270)] transition-colors duration-75
						{index % 2 === 0 ? 'bg-[oklch(0.13_0.005_270)]' : 'bg-[oklch(0.14_0.003_270)]'}
						{selectedIndex === index ? 'bg-[oklch(0.20_0.02_250)] border-l-2 border-l-[oklch(0.55_0.15_250)]' : ''}
						{onRowClick ? 'cursor-pointer' : ''}
						hover:bg-[oklch(0.18_0.01_250)]"
					style="height: {rowHeight}px; top: 0; transform: translateY({top}px);"
					role="row"
					aria-rowindex={index + 1}
					aria-selected={selectedIndex === index}
					onclick={() => {
						selectedIndex = index;
						onRowClick?.(row, index);
					}}
				>
					{#each columns as column, colIdx (column.id)}
						<div
							class="flex shrink-0 items-center overflow-hidden px-3 {getAlignClass(column.align)} {colIdx === 0 ? 'sticky left-0 z-10 bg-inherit' : ''}"
							style="width: {column.width}px; height: {rowHeight}px;"
							role="gridcell"
						>
							<DataCell
								type={column.type}
								value={row[column.id]}
								metadata={(row[column.id + '_meta'] as Record<string, unknown>) ?? {}}
							/>
						</div>
					{/each}
				</div>
			{/each}
		</div>
	</div>
</div>
