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
		if (align === 'center') return 'align-center';
		if (align === 'right') return 'align-right';
		return 'align-left';
	}

	function getSortIndicator(column: ColumnDef): string {
		if (!column.sortable) return '';
		if (sortBy !== column.id) return ' △';
		return sortDirection === 'asc' ? ' ▲' : ' ▼';
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
	class="grid-wrapper {className}"
	tabindex="0"
	onkeydown={handleKeydown}
	role="grid"
	aria-rowcount={rows.length}
	aria-colcount={columns.length}
>
	<!-- Fixed header -->
	<div
		class="grid-header"
		style="height: {headerHeight}px; min-width: {totalWidth}px;"
		role="row"
	>
		{#each columns as column, colIdx (column.id)}
			<div
				class="header-cell {getAlignClass(column.align)} {column.sortable ? 'sortable' : ''} {colIdx === 0 ? 'sticky-col header-sticky-col' : ''}"
				style="width: {column.width}px; height: {headerHeight}px;"
				role="columnheader"
				aria-sort={sortBy === column.id ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
				onclick={() => handleColumnSort(column)}
				onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleColumnSort(column); }}
			>
				<span class="cell-truncate">
					{column.label}{getSortIndicator(column)}
				</span>
			</div>
		{/each}
	</div>

	<!-- Scrollable body with virtual scrolling -->
	<div
		class="grid-body"
		bind:this={scrollContainer}
		onscroll={handleScroll}
		role="rowgroup"
	>
		<div
			class="grid-scroll-area"
			style="height: {totalHeight}px; min-width: {totalWidth}px;"
		>
			{#each visibleRows as { row, index, top } (index)}
				<div
					class="grid-row {index % 2 === 0 ? 'row-even' : 'row-odd'} {selectedIndex === index ? 'row-selected' : ''} {onRowClick ? 'row-clickable' : ''}"
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
							class="grid-cell {getAlignClass(column.align)} {colIdx === 0 ? 'sticky-col' : ''}"
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

<style>
	.grid-wrapper {
		position: relative;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		border-radius: var(--radius-lg);
		border: 1px solid oklch(0.25 0.005 270);
		background-color: oklch(0.13 0.005 270);
	}

	.grid-header {
		position: sticky;
		top: 0;
		z-index: 20;
		display: flex;
		flex-shrink: 0;
		border-bottom: 1px solid oklch(0.25 0.005 270);
		background-color: oklch(0.15 0.005 270);
	}

	.header-cell {
		display: flex;
		flex-shrink: 0;
		align-items: center;
		padding-inline: 12px;
		font-size: var(--text-xs);
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: oklch(0.55 0 0);
	}

	.header-cell.sortable {
		cursor: pointer;
		user-select: none;
		transition: color 150ms;
	}

	.header-cell.sortable:hover {
		color: oklch(0.75 0 0);
	}

	.header-sticky-col {
		background-color: oklch(0.15 0.005 270);
	}

	.sticky-col {
		position: sticky;
		left: 0;
		z-index: 10;
		background-color: inherit;
	}

	/* Header sticky column needs higher z-index */
	.grid-header .sticky-col {
		z-index: 30;
	}

	.cell-truncate {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.grid-body {
		flex: 1;
		overflow: auto;
	}

	.grid-scroll-area {
		position: relative;
	}

	.grid-row {
		position: absolute;
		left: 0;
		right: 0;
		display: flex;
		align-items: center;
		border-bottom: 1px solid oklch(0.18 0.005 270);
		transition: background-color 75ms;
	}

	.row-even {
		background-color: oklch(0.13 0.005 270);
	}

	.row-odd {
		background-color: oklch(0.14 0.003 270);
	}

	.row-selected {
		background-color: oklch(0.20 0.02 250);
		border-left: 2px solid oklch(0.55 0.15 250);
	}

	.row-clickable {
		cursor: pointer;
	}

	.grid-row:hover {
		background-color: oklch(0.18 0.01 250);
	}

	.grid-cell {
		display: flex;
		flex-shrink: 0;
		align-items: center;
		overflow: hidden;
		padding-inline: 12px;
	}

	/* Alignment variants */
	.align-left {
		justify-content: flex-start;
		text-align: left;
	}

	.align-center {
		justify-content: center;
		text-align: center;
	}

	.align-right {
		justify-content: flex-end;
		text-align: right;
	}
</style>
