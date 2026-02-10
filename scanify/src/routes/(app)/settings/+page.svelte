<script lang="ts">
	const sections = [
		{ title: 'Profile', description: 'Manage your account details and personal information', href: '/settings/profile', icon: '👤' },
		{ title: 'Subscription', description: 'View your plan, billing, and upgrade options', href: '/settings/subscription', icon: '💳' },
		{ title: 'Appearance', description: 'Customize theme, layout density, and animations', href: '/settings/appearance', icon: '🎨' },
		{ title: 'Keyboard Shortcuts', description: 'View and customize keyboard shortcuts', href: '/settings/keyboard', icon: '⌨️' },
		{ title: 'API Keys', description: 'Manage API keys for programmatic access', href: '/settings/api', icon: '🔑' },
	];
</script>

<div class="flex h-full flex-col gap-4 p-4" style="color: oklch(0.95 0.005 260);">
	<h1 class="text-lg font-semibold">Settings</h1>

	<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
		{#each sections as section}
			<a href={section.href} class="group flex items-center gap-4 rounded-lg p-4 transition-colors" style="background: oklch(0.14 0.010 260); border: 1px solid oklch(0.20 0.008 260);">
				<div class="flex h-10 w-10 items-center justify-center rounded-lg text-lg" style="background: oklch(0.17 0.012 260);">
					{section.icon}
				</div>
				<div class="flex-1">
					<h3 class="text-sm font-semibold">{section.title}</h3>
					<p class="mt-0.5 text-xs" style="color: oklch(0.52 0.006 260);">{section.description}</p>
				</div>
				<span class="text-sm" style="color: oklch(0.38 0.004 260);">→</span>
			</a>
		{/each}
	</div>
</div>
