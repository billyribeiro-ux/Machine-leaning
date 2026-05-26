<script lang="ts">
  import { page } from '$app/stores';
</script>
<div class="flex min-h-screen items-center justify-center" style="background: oklch(0.08 0.005 260); color: oklch(0.95 0.005 260);">
  <div class="text-center space-y-4">
    <h1 class="text-6xl font-bold font-mono" style="color: oklch(0.65 0.22 25);">{page.status}</h1>
    <p class="text-lg" style="color: oklch(0.72 0.008 260);">{page.error?.message ?? 'Something went wrong'}</p>
    <a href="/" class="inline-block px-6 py-2 rounded-md text-sm font-medium" style="background: oklch(0.14 0.010 260); border: 1px solid oklch(0.28 0.010 260);">Go Home</a>
  </div>
</div>
