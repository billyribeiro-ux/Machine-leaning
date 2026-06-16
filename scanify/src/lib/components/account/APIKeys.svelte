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

<div class="api-keys-wrapper {className}">
  <!-- Section header -->
  <div class="section-header">
    <div class="section-header-text">
      <h2 class="section-title">API Keys</h2>
      <p class="section-subtitle">Manage your programmatic access keys</p>
    </div>
    <button
      class="generate-btn"
      onclick={() => { showGenerateForm = !showGenerateForm; }}
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="12" y1="5" x2="12" y2="19" />
        <line x1="5" y1="12" x2="19" y2="12" />
      </svg>
      Generate New Key
    </button>
  </div>

  <!-- Generate form (collapsible) -->
  {#if showGenerateForm}
    <div class="generate-form">
      <div class="form-field">
        <label for="new-key-name" class="form-label">
          Key Name
        </label>
        <input
          id="new-key-name"
          type="text"
          bind:value={newKeyName}
          placeholder="e.g., Production Server, Local Dev"
          class="form-input"
        />
      </div>
      <div class="form-actions">
        <button
          class="cancel-btn"
          onclick={() => { showGenerateForm = false; newKeyName = ''; }}
        >
          Cancel
        </button>
        <button
          class="submit-btn"
          class:submit-btn-disabled={!newKeyName.trim()}
          class:submit-btn-enabled={!!newKeyName.trim()}
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
    <div class="empty-state">
      <div class="empty-icon-wrapper">
        <svg xmlns="http://www.w3.org/2000/svg" class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
        </svg>
      </div>
      <div class="empty-text">
        <p class="empty-title">No API keys yet</p>
        <p class="empty-subtitle">Generate one to get started.</p>
      </div>
    </div>
  {:else}
    <!-- Keys table -->
    <div class="table-wrapper">
      <table class="keys-table">
        <thead>
          <tr class="table-header-row">
            <th class="th-left">Name</th>
            <th class="th-left">Key</th>
            <th class="th-left">Created</th>
            <th class="th-left">Last Used</th>
            <th class="th-center">Status</th>
            <th class="th-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {#each keys as key, i (key.id)}
            <tr class="table-row" class:row-even={i % 2 === 0} class:row-odd={i % 2 !== 0}>
              <!-- Name -->
              <td class="table-cell">
                <span class="key-name">{key.name}</span>
              </td>

              <!-- Masked key -->
              <td class="table-cell">
                <code class="masked-key">
                  {key.maskedKey}
                </code>
              </td>

              <!-- Created -->
              <td class="table-cell cell-muted">
                {formatDate(key.createdAt)}
              </td>

              <!-- Last used -->
              <td class="table-cell cell-muted">
                {formatDate(key.lastUsed)}
              </td>

              <!-- Status toggle -->
              <td class="table-cell cell-center">
                <button
                  type="button"
                  role="switch"
                  aria-checked={key.isActive}
                  class="toggle-switch"
                  class:toggle-active={key.isActive}
                  class:toggle-inactive={!key.isActive}
                  onclick={() => toggleKeyActive(key)}
                  title={key.isActive ? 'Active - click to deactivate' : 'Inactive - click to activate'}
                >
                  <span
                    class="toggle-thumb"
                    class:thumb-on={key.isActive}
                    class:thumb-off={!key.isActive}
                  ></span>
                </button>
              </td>

              <!-- Delete action -->
              <td class="table-cell cell-right">
                {#if confirmDeleteId === key.id}
                  <div class="confirm-delete-row">
                    <span class="confirm-label">Delete?</span>
                    <button
                      class="confirm-btn"
                      onclick={() => handleDelete(key.id)}
                    >
                      Confirm
                    </button>
                    <button
                      class="confirm-cancel-btn"
                      onclick={cancelDelete}
                    >
                      Cancel
                    </button>
                  </div>
                {:else}
                  <button
                    class="delete-btn"
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
    <p class="key-count">
      {keys.length} API key{keys.length !== 1 ? 's' : ''} &middot;
      {keys.filter(k => k.isActive).length} active
    </p>
  {/if}
</div>

<style>
  /* ── Wrapper ── */
  .api-keys-wrapper {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  /* ── Section header ── */
  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .section-header-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .section-title {
    font-size: var(--text-lg);
    font-weight: 600;
    color: oklch(0.90 0 0);
  }

  .section-subtitle {
    font-size: var(--text-sm);
    color: oklch(0.55 0 0);
  }

  /* ── Generate button ── */
  .generate-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-inline: 16px;
    padding-block: 8px;
    border-radius: var(--radius-lg);
    background-color: oklch(0.55 0.15 145);
    font-size: var(--text-sm);
    font-weight: 500;
    color: white;
    box-shadow: 0 1px 2px oklch(0.55 0.15 145 / 0.25);
    transition: all 150ms;
    cursor: pointer;
    border: none;
  }

  .generate-btn:hover {
    background-color: oklch(0.60 0.16 145);
  }

  /* ── Icon sizes ── */
  .icon-sm {
    width: 16px;
    height: 16px;
  }

  /* ── Generate form ── */
  .generate-form {
    display: flex;
    align-items: flex-end;
    gap: 12px;
    border-radius: var(--radius-xl);
    border: 1px solid oklch(0.22 0 0);
    background-color: oklch(0.13 0 0);
    padding: 16px;
  }

  .form-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
  }

  .form-label {
    font-size: var(--text-xs);
    font-weight: 500;
    color: oklch(0.65 0 0);
  }

  .form-input {
    width: 100%;
    border-radius: var(--radius-lg);
    border: 1px solid oklch(0.24 0 0);
    background-color: oklch(0.11 0 0);
    padding-inline: 12px;
    padding-block: 8px;
    font-size: var(--text-sm);
    color: oklch(0.88 0 0);
    outline: none;
    transition: all 150ms;
  }

  .form-input::placeholder {
    color: oklch(0.40 0 0);
  }

  .form-input:focus {
    border-color: oklch(0.45 0.12 250);
    box-shadow: 0 0 0 2px oklch(0.45 0.12 250 / 0.3);
  }

  .form-actions {
    display: flex;
    gap: 8px;
  }

  .cancel-btn {
    padding-inline: 12px;
    padding-block: 8px;
    border-radius: var(--radius-lg);
    font-size: var(--text-xs);
    font-weight: 500;
    background-color: transparent;
    color: oklch(0.60 0 0);
    transition: color 150ms, background-color 150ms, border-color 150ms;
    cursor: pointer;
    border: none;
  }

  .cancel-btn:hover {
    color: oklch(0.80 0 0);
  }

  .submit-btn {
    padding-inline: 16px;
    padding-block: 8px;
    border-radius: var(--radius-lg);
    font-size: var(--text-xs);
    font-weight: 500;
    border: none;
    cursor: pointer;
    transition: all 150ms;
  }

  .submit-btn-enabled {
    background-color: oklch(0.55 0.15 145);
    color: white;
  }

  .submit-btn-enabled:hover {
    background-color: oklch(0.60 0.16 145);
  }

  .submit-btn-disabled {
    background-color: oklch(0.20 0 0);
    color: oklch(0.40 0 0);
    cursor: not-allowed;
  }

  /* ── Empty state ── */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding-block: 64px;
    border-radius: var(--radius-xl);
    border: 1px dashed oklch(0.22 0 0);
    background-color: oklch(0.11 0 0);
  }

  .empty-icon-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    border-radius: var(--radius-full);
    background-color: oklch(0.16 0 0);
  }

  .empty-icon {
    width: 24px;
    height: 24px;
    color: oklch(0.40 0 0);
  }

  .empty-text {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }

  .empty-title {
    font-size: var(--text-sm);
    font-weight: 500;
    color: oklch(0.70 0 0);
  }

  .empty-subtitle {
    font-size: var(--text-xs);
    color: oklch(0.45 0 0);
  }

  /* ── Table ── */
  .table-wrapper {
    overflow-x: auto;
    border-radius: var(--radius-xl);
    border: 1px solid oklch(0.20 0 0);
  }

  .keys-table {
    width: 100%;
    font-size: var(--text-xs);
  }

  .table-header-row {
    border-bottom: 1px solid oklch(0.20 0 0);
    background-color: oklch(0.11 0 0);
  }

  .th-left,
  .th-center,
  .th-right {
    padding-inline: 16px;
    padding-block: 12px;
    font-weight: 500;
    color: oklch(0.60 0 0);
  }

  .th-left {
    text-align: left;
  }

  .th-center {
    text-align: center;
  }

  .th-right {
    text-align: right;
  }

  .table-row {
    border-bottom: 1px solid oklch(0.16 0 0);
    transition: color 150ms, background-color 150ms, border-color 150ms;
  }

  .table-row:hover {
    background-color: oklch(0.15 0 0);
  }

  .row-even {
    background-color: oklch(0.12 0 0);
  }

  .row-odd {
    background-color: oklch(0.13 0 0);
  }

  .table-cell {
    padding-inline: 16px;
    padding-block: 12px;
  }

  .cell-muted {
    color: oklch(0.60 0 0);
  }

  .cell-center {
    text-align: center;
  }

  .cell-right {
    text-align: right;
  }

  .key-name {
    font-weight: 500;
    color: oklch(0.80 0 0);
  }

  .masked-key {
    font-family: var(--font-mono);
    color: oklch(0.60 0 0);
    background-color: oklch(0.10 0 0);
    padding-inline: 8px;
    padding-block: 2px;
    border-radius: var(--radius-DEFAULT);
    font-size: 11px;
  }

  /* ── Toggle switch ── */
  .toggle-switch {
    position: relative;
    display: inline-flex;
    height: 20px;
    width: 36px;
    flex-shrink: 0;
    align-items: center;
    border-radius: var(--radius-full);
    transition: color 150ms, background-color 150ms, border-color 150ms;
    cursor: pointer;
    border: none;
  }

  .toggle-active {
    background-color: oklch(0.55 0.15 145);
  }

  .toggle-inactive {
    background-color: oklch(0.24 0 0);
  }

  .toggle-thumb {
    display: inline-block;
    height: 14px;
    width: 14px;
    border-radius: var(--radius-full);
    background-color: white;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
    transition: transform 200ms;
  }

  .thumb-on {
    transform: translateX(18px);
  }

  .thumb-off {
    transform: translateX(2px);
  }

  /* ── Delete actions ── */
  .confirm-delete-row {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
  }

  .confirm-label {
    font-size: 11px;
    color: oklch(0.60 0.14 25);
  }

  .confirm-btn {
    padding-inline: 8px;
    padding-block: 4px;
    border-radius: var(--radius-DEFAULT);
    font-size: 11px;
    font-weight: 500;
    background-color: oklch(0.50 0.18 25);
    color: white;
    transition: color 150ms, background-color 150ms, border-color 150ms;
    cursor: pointer;
    border: none;
  }

  .confirm-btn:hover {
    background-color: oklch(0.55 0.19 25);
  }

  .confirm-cancel-btn {
    padding-inline: 8px;
    padding-block: 4px;
    border-radius: var(--radius-DEFAULT);
    font-size: 11px;
    font-weight: 500;
    color: oklch(0.60 0 0);
    transition: color 150ms, background-color 150ms, border-color 150ms;
    cursor: pointer;
    border: none;
    background-color: transparent;
  }

  .confirm-cancel-btn:hover {
    color: oklch(0.80 0 0);
  }

  .delete-btn {
    padding-inline: 8px;
    padding-block: 4px;
    border-radius: var(--radius-DEFAULT);
    font-size: 11px;
    font-weight: 500;
    color: oklch(0.55 0.10 25);
    transition: color 150ms, background-color 150ms, border-color 150ms;
    cursor: pointer;
    border: none;
    background-color: transparent;
  }

  .delete-btn:hover {
    color: oklch(0.65 0.16 25);
    background-color: oklch(0.18 0.02 25);
  }

  /* ── Key count summary ── */
  .key-count {
    font-size: 11px;
    color: oklch(0.42 0 0);
  }
</style>
