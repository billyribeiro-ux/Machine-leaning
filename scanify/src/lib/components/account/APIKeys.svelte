<!--
  APIKeys.svelte
  API key management table with generation, deletion, and status toggling.
  Empty state when no keys exist.
-->
<script lang="ts">
  interface APIKey {
    id: string;
    name: string;
    maskedKey: string;
    createdAt: string;
    lastUsed: string;
    isActive: boolean;
  }

  interface APIKeysProps {
    /** List of API keys. */
    keys: APIKey[];
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    keys,
    class: className = '',
  }: APIKeysProps = $props();

  let showGenerateForm = $state(false);
  let newKeyName = $state('');
  let confirmDeleteId = $state<string | null>(null);

  /** Format ISO date to readable short form. */
  function formatDate(iso: string): string {
    if (!iso) return 'Never';
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return iso;
    }
  }

  function handleGenerate(): void {
    if (!newKeyName.trim()) return;
    // In a real app this would call an API endpoint
    newKeyName = '';
    showGenerateForm = false;
  }

  function handleDelete(id: string): void {
    if (confirmDeleteId === id) {
      // In a real app this would call an API endpoint
      confirmDeleteId = null;
    } else {
      confirmDeleteId = id;
    }
  }

  function cancelDelete(): void {
    confirmDeleteId = null;
  }

  function toggleKeyActive(key: APIKey): void {
    key.isActive = !key.isActive;
  }
</script>

<div class="flex flex-col gap-6 {className}">
  <!-- Section header -->
  <div class="flex items-center justify-between">
    <div class="flex flex-col gap-1">
      <h2 class="text-lg font-semibold text-[oklch(0.90_0_0)]">API Keys</h2>
      <p class="text-sm text-[oklch(0.55_0_0)]">Manage your programmatic access keys</p>
    </div>
    <button
      class="
        flex items-center gap-2 px-4 py-2 rounded-lg
        bg-[oklch(0.55_0.15_145)] hover:bg-[oklch(0.60_0.16_145)]
        text-sm font-medium text-white
        shadow-sm shadow-[oklch(0.55_0.15_145/0.25)]
        transition-all duration-150 cursor-pointer border-none
      "
      onclick={() => { showGenerateForm = !showGenerateForm; }}
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="12" y1="5" x2="12" y2="19" />
        <line x1="5" y1="12" x2="19" y2="12" />
      </svg>
      Generate New Key
    </button>
  </div>

  <!-- Generate form (collapsible) -->
  {#if showGenerateForm}
    <div class="flex items-end gap-3 rounded-xl border border-[oklch(0.22_0_0)] bg-[oklch(0.13_0_0)] p-4">
      <div class="flex flex-col gap-1.5 flex-1">
        <label for="new-key-name" class="text-xs font-medium text-[oklch(0.65_0_0)]">
          Key Name
        </label>
        <input
          id="new-key-name"
          type="text"
          bind:value={newKeyName}
          placeholder="e.g., Production Server, Local Dev"
          class="
            w-full rounded-lg border border-[oklch(0.24_0_0)]
            bg-[oklch(0.11_0_0)] px-3 py-2
            text-sm text-[oklch(0.88_0_0)]
            placeholder-[oklch(0.40_0_0)]
            outline-none transition-all duration-150
            focus:border-[oklch(0.45_0.12_250)]
            focus:ring-2 focus:ring-[oklch(0.45_0.12_250/0.3)]
          "
        />
      </div>
      <div class="flex gap-2">
        <button
          class="
            px-3 py-2 rounded-lg text-xs font-medium
            bg-transparent text-[oklch(0.60_0_0)] hover:text-[oklch(0.80_0_0)]
            transition-colors duration-150 cursor-pointer border-none
          "
          onclick={() => { showGenerateForm = false; newKeyName = ''; }}
        >
          Cancel
        </button>
        <button
          class="
            px-4 py-2 rounded-lg text-xs font-medium border-none cursor-pointer
            transition-all duration-150
            {newKeyName.trim()
              ? 'bg-[oklch(0.55_0.15_145)] hover:bg-[oklch(0.60_0.16_145)] text-white'
              : 'bg-[oklch(0.20_0_0)] text-[oklch(0.40_0_0)] cursor-not-allowed'}
          "
          disabled={!newKeyName.trim()}
          onclick={handleGenerate}
        >
          Generate
        </button>
      </div>
    </div>
  {/if}

  <!-- Keys table or empty state -->
  {#if keys.length === 0}
    <!-- Empty state -->
    <div class="flex flex-col items-center justify-center gap-4 py-16 rounded-xl border border-dashed border-[oklch(0.22_0_0)] bg-[oklch(0.11_0_0)]">
      <div class="flex items-center justify-center w-12 h-12 rounded-full bg-[oklch(0.16_0_0)]">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-[oklch(0.40_0_0)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
        </svg>
      </div>
      <div class="flex flex-col items-center gap-1">
        <p class="text-sm font-medium text-[oklch(0.70_0_0)]">No API keys yet</p>
        <p class="text-xs text-[oklch(0.45_0_0)]">Generate one to get started.</p>
      </div>
    </div>
  {:else}
    <!-- Keys table -->
    <div class="overflow-x-auto rounded-xl border border-[oklch(0.20_0_0)]">
      <table class="w-full text-xs">
        <thead>
          <tr class="border-b border-[oklch(0.20_0_0)] bg-[oklch(0.11_0_0)]">
            <th class="text-left px-4 py-3 font-medium text-[oklch(0.60_0_0)]">Name</th>
            <th class="text-left px-4 py-3 font-medium text-[oklch(0.60_0_0)]">Key</th>
            <th class="text-left px-4 py-3 font-medium text-[oklch(0.60_0_0)]">Created</th>
            <th class="text-left px-4 py-3 font-medium text-[oklch(0.60_0_0)]">Last Used</th>
            <th class="text-center px-4 py-3 font-medium text-[oklch(0.60_0_0)]">Status</th>
            <th class="text-right px-4 py-3 font-medium text-[oklch(0.60_0_0)]">Actions</th>
          </tr>
        </thead>
        <tbody>
          {#each keys as key, i (key.id)}
            <tr class="border-b border-[oklch(0.16_0_0)] {i % 2 === 0 ? 'bg-[oklch(0.12_0_0)]' : 'bg-[oklch(0.13_0_0)]'} hover:bg-[oklch(0.15_0_0)] transition-colors duration-100">
              <!-- Name -->
              <td class="px-4 py-3">
                <span class="font-medium text-[oklch(0.80_0_0)]">{key.name}</span>
              </td>

              <!-- Masked key -->
              <td class="px-4 py-3">
                <code class="font-mono text-[oklch(0.60_0_0)] bg-[oklch(0.10_0_0)] px-2 py-0.5 rounded text-[11px]">
                  {key.maskedKey}
                </code>
              </td>

              <!-- Created -->
              <td class="px-4 py-3 text-[oklch(0.60_0_0)]">
                {formatDate(key.createdAt)}
              </td>

              <!-- Last used -->
              <td class="px-4 py-3 text-[oklch(0.60_0_0)]">
                {formatDate(key.lastUsed)}
              </td>

              <!-- Status toggle -->
              <td class="px-4 py-3 text-center">
                <button
                  type="button"
                  role="switch"
                  aria-checked={key.isActive}
                  class="
                    relative inline-flex h-5 w-9 shrink-0 items-center rounded-full
                    transition-colors duration-200 cursor-pointer border-none
                    {key.isActive ? 'bg-[oklch(0.55_0.15_145)]' : 'bg-[oklch(0.24_0_0)]'}
                  "
                  onclick={() => toggleKeyActive(key)}
                  title={key.isActive ? 'Active - click to deactivate' : 'Inactive - click to activate'}
                >
                  <span
                    class="
                      inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm
                      transition-transform duration-200
                      {key.isActive ? 'translate-x-[18px]' : 'translate-x-0.5'}
                    "
                  ></span>
                </button>
              </td>

              <!-- Delete action -->
              <td class="px-4 py-3 text-right">
                {#if confirmDeleteId === key.id}
                  <div class="flex items-center justify-end gap-2">
                    <span class="text-[11px] text-[oklch(0.60_0.14_25)]">Delete?</span>
                    <button
                      class="
                        px-2 py-1 rounded text-[11px] font-medium
                        bg-[oklch(0.50_0.18_25)] hover:bg-[oklch(0.55_0.19_25)]
                        text-white transition-colors duration-150
                        cursor-pointer border-none
                      "
                      onclick={() => handleDelete(key.id)}
                    >
                      Confirm
                    </button>
                    <button
                      class="
                        px-2 py-1 rounded text-[11px] font-medium
                        text-[oklch(0.60_0_0)] hover:text-[oklch(0.80_0_0)]
                        transition-colors duration-150
                        cursor-pointer border-none bg-transparent
                      "
                      onclick={cancelDelete}
                    >
                      Cancel
                    </button>
                  </div>
                {:else}
                  <button
                    class="
                      px-2 py-1 rounded text-[11px] font-medium
                      text-[oklch(0.55_0.10_25)] hover:text-[oklch(0.65_0.16_25)]
                      hover:bg-[oklch(0.18_0.02_25)]
                      transition-colors duration-150
                      cursor-pointer border-none bg-transparent
                    "
                    onclick={() => handleDelete(key.id)}
                    title="Delete API key"
                  >
                    Delete
                  </button>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <!-- Key count summary -->
    <p class="text-[11px] text-[oklch(0.42_0_0)]">
      {keys.length} API key{keys.length !== 1 ? 's' : ''} &middot;
      {keys.filter(k => k.isActive).length} active
    </p>
  {/if}
</div>
