<script lang="ts">
  import VendorCredentials from '$lib/components/account/VendorCredentials.svelte';
</script>

<svelte:head>
  <title>Vendor API Keys - Scanify</title>
</svelte:head>

<div class="page-layout">
  <div class="page-header">
    <div class="header-left">
      <a href="/settings" class="back-link">
        <svg xmlns="http://www.w3.org/2000/svg" class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Settings
      </a>
    </div>
  </div>
  <div class="page-body">
    <VendorCredentials />
  </div>
</div>

<style>
  .page-layout {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: auto;
  }

  .page-header {
    display: flex;
    align-items: center;
    padding: 12px 20px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .back-link {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    text-decoration: none;
    transition: color 150ms;
  }

  .back-link:hover {
    color: var(--text-primary);
  }

  .back-icon {
    width: 14px;
    height: 14px;
  }

  .page-body {
    padding: 24px 20px;
    max-width: 720px;
  }
</style>
