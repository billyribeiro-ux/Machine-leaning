<script lang="ts">
	interface TreemapNode {
		name: string;
		value: number;
		change: number;
		children?: TreemapNode[];
	}

	interface Props {
		data: TreemapNode[];
		height?: number;
	}

	let { data, height = 400 }: Props = $props();

	let containerEl: HTMLDivElement | undefined = $state(undefined);
	let containerWidth = $state(600);
	let hoveredNode = $state<TreemapNode | null>(null);
	let mouseX = $state(0);
	let mouseY = $state(0);

	// Observe container width
	$effect(() => {
		if (!containerEl) return;
		const observer = new ResizeObserver((entries) => {
			for (const entry of entries) {
				containerWidth = entry.contentRect.width;
			}
		});
		observer.observe(containerEl);
		return () => observer.disconnect();
	});

	interface LayoutRect {
		x: number;
		y: number;
		w: number;
		h: number;
		node: TreemapNode;
		children?: LayoutRect[];
	}

	// Squarified treemap layout algorithm
	function squarify(
		nodes: TreemapNode[],
		x: number,
		y: number,
		w: number,
		h: number
	): LayoutRect[] {
		if (nodes.length === 0 || w <= 0 || h <= 0) return [];

		const totalValue = nodes.reduce((s, n) => s + Math.max(n.value, 0), 0);
		if (totalValue <= 0) return [];

		const sorted = [...nodes].sort((a, b) => b.value - a.value);
		const rects: LayoutRect[] = [];

		let cx = x;
		let cy = y;
		let cw = w;
		let ch = h;

		let remaining = [...sorted];

		while (remaining.length > 0) {
			const isHorizontal = cw >= ch;
			const side = isHorizontal ? ch : cw;
			const remTotal = remaining.reduce((s, n) => s + Math.max(n.value, 0), 0);

			// Find best row
			let row: TreemapNode[] = [];
			let rowTotal = 0;
			let bestAspect = Infinity;

			for (let i = 0; i < remaining.length; i++) {
				const candidate = [...row, remaining[i]];
				const candidateTotal = rowTotal + Math.max(remaining[i].value, 0);
				const rowLength = (candidateTotal / remTotal) * (isHorizontal ? cw : ch);

				// Worst aspect ratio in this row
				let worstAspect = 0;
				for (const node of candidate) {
					const nodeArea = (Math.max(node.value, 0) / candidateTotal) * side;
					const aspect =
						rowLength > 0 && nodeArea > 0
							? Math.max(rowLength / nodeArea, nodeArea / rowLength)
							: Infinity;
					worstAspect = Math.max(worstAspect, aspect);
				}

				if (worstAspect <= bestAspect) {
					row = candidate;
					rowTotal = candidateTotal;
					bestAspect = worstAspect;
				} else {
					break;
				}
			}

			// Lay out the row
			const rowFraction = remTotal > 0 ? rowTotal / remTotal : 0;
			const rowSize = isHorizontal ? cw * rowFraction : ch * rowFraction;

			let offset = 0;
			for (const node of row) {
				const nodeFraction = rowTotal > 0 ? Math.max(node.value, 0) / rowTotal : 0;
				const nodeSize = side * nodeFraction;

				const rect: LayoutRect = isHorizontal
					? {
							x: cx,
							y: cy + offset,
							w: rowSize,
							h: nodeSize,
							node
						}
					: {
							x: cx + offset,
							y: cy,
							w: nodeSize,
							h: rowSize,
							node
						};

				// Recurse for children
				if (node.children && node.children.length > 0 && rect.w > 40 && rect.h > 30) {
					const headerH = 16;
					const pad = 2;
					rect.children = squarify(
						node.children,
						rect.x + pad,
						rect.y + headerH,
						rect.w - pad * 2,
						rect.h - headerH - pad
					);
				}

				rects.push(rect);
				offset += nodeSize;
			}

			// Update remaining area
			if (isHorizontal) {
				cx += rowSize;
				cw -= rowSize;
			} else {
				cy += rowSize;
				ch -= rowSize;
			}

			remaining = remaining.slice(row.length);
		}

		return rects;
	}

	let layout = $derived(squarify(data, 0, 0, containerWidth, height));

	function getColor(change: number): string {
		const clamped = Math.max(-10, Math.min(10, change));
		if (clamped > 0) {
			const t = clamped / 10;
			const lightness = 0.22 + t * 0.15;
			const chroma = t * 0.14;
			return `oklch(${lightness} ${chroma} 145)`;
		} else if (clamped < 0) {
			const t = -clamped / 10;
			const lightness = 0.22 + t * 0.13;
			const chroma = t * 0.15;
			return `oklch(${lightness} ${chroma} 25)`;
		}
		return 'oklch(0.20 0 0)';
	}

	function getTextColor(change: number): string {
		const clamped = Math.max(-10, Math.min(10, change));
		if (clamped > 0) return 'oklch(0.85 0.12 145)';
		if (clamped < 0) return 'oklch(0.82 0.14 25)';
		return 'oklch(0.70 0 0)';
	}

	function handleHover(e: MouseEvent, node: TreemapNode) {
		hoveredNode = node;
		if (containerEl) {
			const rect = containerEl.getBoundingClientRect();
			mouseX = e.clientX - rect.left;
			mouseY = e.clientY - rect.top;
		}
	}

	function handleLeave() {
		hoveredNode = null;
	}

	function shouldShowText(rect: LayoutRect): boolean {
		return rect.w > 35 && rect.h > 22;
	}

	function shouldShowChange(rect: LayoutRect): boolean {
		return rect.w > 50 && rect.h > 34;
	}

	function truncateText(text: string, maxWidth: number): string {
		const approxChars = Math.floor(maxWidth / 7);
		if (text.length <= approxChars) return text;
		return text.slice(0, Math.max(1, approxChars - 1)) + '\u2026';
	}
</script>

<div class="relative w-full" bind:this={containerEl}>
	<svg
		width={containerWidth}
		{height}
		viewBox="0 0 {containerWidth} {height}"
		class="select-none"
		role="img"
		aria-label="Treemap Chart"
	>
		{#each layout as rect}
			<!-- Parent cell -->
			<rect
				x={rect.x + 0.5}
				y={rect.y + 0.5}
				width={Math.max(0, rect.w - 1)}
				height={Math.max(0, rect.h - 1)}
				fill={getColor(rect.node.change)}
				stroke="oklch(0.12 0 0)"
				stroke-width="1"
				rx="3"
				class="cursor-pointer transition-[filter] duration-100"
				opacity={hoveredNode && hoveredNode !== rect.node ? 0.75 : 1}
				onmouseenter={(e) => handleHover(e, rect.node)}
				onmousemove={(e) => handleHover(e, rect.node)}
				onmouseleave={handleLeave}
			/>

			{#if rect.children && rect.children.length > 0}
				<!-- Parent label -->
				{#if rect.w > 50 && rect.h > 20}
					<text
						x={rect.x + 4}
						y={rect.y + 11}
						class="text-[9px] font-semibold fill-[oklch(0.70_0_0)] pointer-events-none"
					>
						{truncateText(rect.node.name, rect.w - 8)}
					</text>
				{/if}

				<!-- Child cells -->
				{#each rect.children as child}
					<rect
						x={child.x + 0.5}
						y={child.y + 0.5}
						width={Math.max(0, child.w - 1)}
						height={Math.max(0, child.h - 1)}
						fill={getColor(child.node.change)}
						stroke="oklch(0.15 0 0)"
						stroke-width="0.5"
						rx="2"
						class="cursor-pointer transition-[filter] duration-100"
						opacity={hoveredNode && hoveredNode !== child.node ? 0.75 : 1}
						onmouseenter={(e) => handleHover(e, child.node)}
						onmousemove={(e) => handleHover(e, child.node)}
						onmouseleave={handleLeave}
					/>

					{#if shouldShowText(child)}
						<text
							x={child.x + child.w / 2}
							y={child.y + child.h / 2 - (shouldShowChange(child) ? 5 : 0)}
							text-anchor="middle"
							dominant-baseline="middle"
							fill={getTextColor(child.node.change)}
							class="text-[10px] font-bold pointer-events-none"
						>
							{truncateText(child.node.name, child.w - 6)}
						</text>
					{/if}
					{#if shouldShowChange(child)}
						<text
							x={child.x + child.w / 2}
							y={child.y + child.h / 2 + 8}
							text-anchor="middle"
							dominant-baseline="middle"
							fill={getTextColor(child.node.change)}
							class="text-[9px] font-mono pointer-events-none"
							opacity="0.8"
						>
							{child.node.change >= 0 ? '+' : ''}{child.node.change.toFixed(2)}%
						</text>
					{/if}
				{/each}
			{:else}
				<!-- Leaf node text -->
				{#if shouldShowText(rect)}
					<text
						x={rect.x + rect.w / 2}
						y={rect.y + rect.h / 2 - (shouldShowChange(rect) ? 5 : 0)}
						text-anchor="middle"
						dominant-baseline="middle"
						fill={getTextColor(rect.node.change)}
						class="text-[11px] font-bold pointer-events-none"
					>
						{truncateText(rect.node.name, rect.w - 6)}
					</text>
				{/if}
				{#if shouldShowChange(rect)}
					<text
						x={rect.x + rect.w / 2}
						y={rect.y + rect.h / 2 + 9}
						text-anchor="middle"
						dominant-baseline="middle"
						fill={getTextColor(rect.node.change)}
						class="text-[10px] font-mono pointer-events-none"
						opacity="0.8"
					>
						{rect.node.change >= 0 ? '+' : ''}{rect.node.change.toFixed(2)}%
					</text>
				{/if}
			{/if}
		{/each}
	</svg>

	<!-- Tooltip -->
	{#if hoveredNode}
		<div
			class="pointer-events-none absolute z-50 rounded-lg border border-[oklch(0.25_0_0)]
				bg-[oklch(0.14_0_0/0.94)] px-3 py-2 shadow-xl backdrop-blur-sm"
			style="left: {Math.min(mouseX + 14, containerWidth - 160)}px;
				top: {Math.max(mouseY - 55, 4)}px;"
		>
			<div class="text-xs font-semibold text-[oklch(0.85_0_0)] mb-1">
				{hoveredNode.name}
			</div>
			<div class="flex flex-col gap-0.5 text-[10px] font-mono">
				<div class="flex items-center gap-3">
					<span class="text-[oklch(0.50_0_0)]">Value</span>
					<span class="text-[oklch(0.80_0_0)] ml-auto">
						{hoveredNode.value.toLocaleString()}
					</span>
				</div>
				<div class="flex items-center gap-3">
					<span class="text-[oklch(0.50_0_0)]">Change</span>
					<span
						class="ml-auto {hoveredNode.change >= 0
							? 'text-[oklch(0.75_0.15_145)]'
							: 'text-[oklch(0.70_0.16_25)]'}"
					>
						{hoveredNode.change >= 0 ? '+' : ''}{hoveredNode.change.toFixed(2)}%
					</span>
				</div>
			</div>
		</div>
	{/if}
</div>
