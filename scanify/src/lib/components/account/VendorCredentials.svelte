<script lang="ts">
  interface VendorSummary {
    vendor_id: string;
    display_name: string;
    auth_type: string;
    status: string;
    required_fields: string[];
    optional_fields: string[];
    has_stored_credential: boolean;
    env_configured: boolean;
    rotation_count: number;
    last_updated: string | null;
    docs_url: string;
  }

  interface Props {
    class?: string;
  }

  let { class: className = '' }: Props = $props();

  const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  let adminToken = $state('');
  let tokenInput = $state('');
  let vendors = $state<VendorSummary[]>([]);
  let loading = $state(false);
  let error = $state('');
  let expandedVendor = $state<string | null>(null);
  let fieldInputs = $state<Record<string, string>>({});
  let saving = $state<string | null>(null);
  let saveMessage = $state<Record<string, { text: string; ok: boolean }>>({});
  let testing = $state<string | null>(null);

  $effect(() => {
    const stored = localStorage.getItem('scanify_admin_token');
    if (stored) {
      adminToken = stored;
    }
  });

  $effect(() => {
    if (adminToken) {
      fetchVendors();
    }
  });

  function setToken() {
    if (!tokenInput.trim()) return;
    adminToken = tokenInput.trim();
    localStorage.setItem('scanify_admin_token', adminToken);
    tokenInput = '';
  }

  function clearToken() {
    adminToken = '';
    localStorage.removeItem('scanify_admin_token');
    vendors = [];
  }

  async function fetchVendors() {
    loading = true;
    error = '';
    try {
      const res = await fetch(`${API_BASE}/api/admin/credentials/vendors`, {
        headers: { 'X-Scanify-Admin-Token': adminToken },
      });
      if (!res.ok) {
        if (res.status === 403) {
          error = 'Invalid admin token.';
          adminToken = '';
          localStorage.removeItem('scanify_admin_token');
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      vendors = await res.json();
    } catch (e: any) {
      error = e.message || 'Failed to fetch vendors';
    } finally {
      loading = false;
    }
  }

  function toggleExpand(vendorId: string) {
    if (expandedVendor === vendorId) {
      expandedVendor = null;
      fieldInputs = {};
    } else {
      expandedVendor = vendorId;
      fieldInputs = {};
    }
  }

  async function saveCredential(vendorId: string, requiredFields: string[], optionalFields: string[]) {
    const fields: Record<string, string> = {};
    for (const f of [...requiredFields, ...optionalFields]) {
      if (fieldInputs[f]?.trim()) {
        fields[f] = fieldInputs[f].trim();
      }
    }
    if (Object.keys(fields).length === 0) return;

    saving = vendorId;
    saveMessage = {};
    try {
      const res = await fetch(`${API_BASE}/api/admin/credentials/vendors/${vendorId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-Scanify-Admin-Token': adminToken,
        },
        body: JSON.stringify({ fields, notes: '' }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      saveMessage[vendorId] = { text: 'Saved', ok: true };
      fieldInputs = {};
      await fetchVendors();
    } catch (e: any) {
      saveMessage[vendorId] = { text: e.message, ok: false };
    } finally {
      saving = null;
    }
  }

  async function deleteCredential(vendorId: string) {
    saving = vendorId;
    try {
      const res = await fetch(`${API_BASE}/api/admin/credentials/vendors/${vendorId}`, {
        method: 'DELETE',
        headers: { 'X-Scanify-Admin-Token': adminToken },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      saveMessage[vendorId] = { text: 'Deleted', ok: true };
      expandedVendor = null;
      await fetchVendors();
    } catch (e: any) {
      saveMessage[vendorId] = { text: e.message, ok: false };
    } finally {
      saving = null;
    }
  }

  async function testConnection(vendorId: string) {
    testing = vendorId;
    saveMessage = {};
    const testUrls: Record<string, string> = {
      fmp: '/api/v3/profile/AAPL',
      polygon: '/v2/aggs/ticker/AAPL/prev',
      tradier: '/v1/markets/quotes?symbols=AAPL',
    };

    try {
      const detailRes = await fetch(`${API_BASE}/api/admin/credentials/vendors/${vendorId}`, {
        headers: { 'X-Scanify-Admin-Token': adminToken },
      });
      if (!detailRes.ok) throw new Error('Could not get vendor detail');
      const detail = await detailRes.json();
      if (!detail.is_ready) {
        saveMessage[vendorId] = { text: 'Missing required fields', ok: false };
        return;
      }
      saveMessage[vendorId] = { text: 'Connected', ok: true };
    } catch (e: any) {
      saveMessage[vendorId] = { text: e.message || 'Test failed', ok: false };
    } finally {
      testing = null;
    }
  }

  function statusColor(status: string): string {
    switch (status) {
      case 'active': return 'var(--bullish)';
      case 'not_configured': return 'var(--text-disabled)';
      case 'expired': return 'var(--warning)';
      case 'revoked': return 'var(--bearish)';
      default: return 'var(--text-tertiary)';
    }
  }

  function statusLabel(status: string): string {
    switch (status) {
      case 'active': return 'Active';
      case 'not_configured': return 'Not Configured';
      case 'expired': return 'Expired';
      case 'revoked': return 'Revoked';
      default: return status;
    }
  }

  function formatFieldName(field: string): string {
    return field.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }
</script>

<div class="vendor-root {className}">
  <!-- Section header -->
  <div class="section-header">
    <h2 class="title">Data Vendor API Keys</h2>
    <p class="subtitle">Manage API keys for market data providers</p>
  </div>

  <!-- Admin token gate -->
  {#if !adminToken}
    <div class="token-gate">
      <div class="token-card panel">
        <div class="token-icon-box">
          <svg xmlns="http://www.w3.org/2000/svg" class="token-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
          </svg>
        </div>
        <h3 class="token-title">Admin Token Required</h3>
        <p class="token-desc">Enter your SCANIFY_ADMIN_TOKEN to manage vendor credentials.</p>
        <div class="token-input-row">
          <input
            type="password"
            bind:value={tokenInput}
            placeholder="Paste admin token..."
            class="token-input"
            onkeydown={(e) => e.key === 'Enter' && setToken()}
          />
          <button class="token-btn" onclick={setToken}>Connect</button>
        </div>
        {#if error}
          <p class="token-error">{error}</p>
        {/if}
      </div>
    </div>
  {:else}
    <!-- Connected toolbar -->
    <div class="toolbar">
      <div class="toolbar-left">
        <span class="connected-dot"></span>
        <span class="connected-label">Connected</span>
      </div>
      <div class="toolbar-right">
        <button class="toolbar-btn" onclick={fetchVendors}>Refresh</button>
        <button class="toolbar-btn toolbar-btn-dim" onclick={clearToken}>Disconnect</button>
      </div>
    </div>

    {#if error}
      <div class="error-bar">{error}</div>
    {/if}

    {#if loading && vendors.length === 0}
      <div class="loading-state">Loading vendors...</div>
    {:else}
      <!-- Vendor list -->
      <div class="vendor-list">
        {#each vendors as vendor (vendor.vendor_id)}
          {@const isExpanded = expandedVendor === vendor.vendor_id}
          {@const msg = saveMessage[vendor.vendor_id]}
          <div class="vendor-card panel" class:vendor-card-active={vendor.has_stored_credential || vendor.env_configured}>
            <!-- Card header (clickable) -->
            <button class="vendor-header" onclick={() => toggleExpand(vendor.vendor_id)}>
              <div class="vendor-info">
                <div class="vendor-name-row">
                  <span class="vendor-name">{vendor.display_name}</span>
                  <span class="vendor-status" style:color={statusColor(vendor.status)}>
                    {statusLabel(vendor.status)}
                  </span>
                </div>
                <div class="vendor-meta">
                  <span class="vendor-id">{vendor.vendor_id}</span>
                  <span class="vendor-dot">·</span>
                  <span class="vendor-auth">{vendor.auth_type}</span>
                  {#if vendor.last_updated}
                    <span class="vendor-dot">·</span>
                    <span class="vendor-updated">Updated {vendor.last_updated.slice(0, 10)}</span>
                  {/if}
                </div>
              </div>
              <svg
                xmlns="http://www.w3.org/2000/svg"
                class="chevron"
                class:chevron-open={isExpanded}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
              >
                <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            <!-- Expanded content -->
            {#if isExpanded}
              <div class="vendor-body">
                <!-- Required fields -->
                {#if vendor.required_fields.length > 0}
                  <div class="field-section">
                    <span class="field-section-label">Required</span>
                    {#each vendor.required_fields as field (field)}
                      <div class="field-row">
                        <label class="field-name" for="field-{vendor.vendor_id}-{field}">{formatFieldName(field)}</label>
                        <input
                          id="field-{vendor.vendor_id}-{field}"
                          type="password"
                          placeholder={vendor.has_stored_credential ? '••••••••  (stored)' : `Enter ${field}...`}
                          class="field-input"
                          bind:value={fieldInputs[field]}
                        />
                      </div>
                    {/each}
                  </div>
                {/if}

                <!-- Optional fields -->
                {#if vendor.optional_fields.length > 0}
                  <div class="field-section">
                    <span class="field-section-label">Optional</span>
                    {#each vendor.optional_fields as field (field)}
                      <div class="field-row">
                        <label class="field-name" for="field-{vendor.vendor_id}-{field}">{formatFieldName(field)}</label>
                        <input
                          id="field-{vendor.vendor_id}-{field}"
                          type="text"
                          placeholder={`Enter ${field}...`}
                          class="field-input"
                          bind:value={fieldInputs[field]}
                        />
                      </div>
                    {/each}
                  </div>
                {/if}

                <!-- Env var hint -->
                {#if vendor.env_configured}
                  <div class="env-hint">
                    <svg xmlns="http://www.w3.org/2000/svg" class="env-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>Also configured via environment variable</span>
                  </div>
                {/if}

                <!-- Status message -->
                {#if msg}
                  <div class="status-msg" class:status-ok={msg.ok} class:status-err={!msg.ok}>
                    {msg.text}
                  </div>
                {/if}

                <!-- Action buttons -->
                <div class="vendor-actions">
                  <div class="actions-left">
                    <button
                      class="action-btn action-save"
                      onclick={() => saveCredential(vendor.vendor_id, vendor.required_fields, vendor.optional_fields)}
                      disabled={saving === vendor.vendor_id}
                    >
                      {saving === vendor.vendor_id ? 'Saving...' : 'Save Key'}
                    </button>
                    {#if vendor.has_stored_credential}
                      <button
                        class="action-btn action-test"
                        onclick={() => testConnection(vendor.vendor_id)}
                        disabled={testing === vendor.vendor_id}
                      >
                        {testing === vendor.vendor_id ? 'Testing...' : 'Test'}
                      </button>
                    {/if}
                  </div>
                  <div class="actions-right">
                    {#if vendor.docs_url}
                      <a href={vendor.docs_url} target="_blank" rel="noopener noreferrer" class="action-link">
                        Docs
                      </a>
                    {/if}
                    {#if vendor.has_stored_credential}
                      <button
                        class="action-btn action-delete"
                        onclick={() => deleteCredential(vendor.vendor_id)}
                      >
                        Remove
                      </button>
                    {/if}
                  </div>
                </div>
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .vendor-root {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .section-header {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .title {
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--text-primary);
  }

  .subtitle {
    font-size: var(--text-sm);
    color: var(--text-tertiary);
  }

  /* Token gate */
  .token-gate {
    display: flex;
    justify-content: center;
    padding: 40px 0;
  }

  .token-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    padding: 32px;
    max-width: 400px;
    width: 100%;
    text-align: center;
  }

  .token-icon-box {
    width: 48px;
    height: 48px;
    border-radius: var(--radius-xl);
    background: var(--bg-base);
    border: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .token-icon {
    width: 24px;
    height: 24px;
    color: var(--accent);
  }

  .token-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .token-desc {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    line-height: 1.5;
  }

  .token-input-row {
    display: flex;
    gap: 8px;
    width: 100%;
  }

  .token-input {
    flex: 1;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    background: var(--bg-base);
    padding: 8px 12px;
    font-size: var(--text-xs);
    color: var(--text-primary);
    outline: none;
  }

  .token-input:focus {
    border-color: var(--accent-dim);
    box-shadow: 0 0 0 2px oklch(0.45 0.12 250 / 0.2);
  }

  .token-btn {
    border-radius: var(--radius-md);
    background: var(--accent);
    color: white;
    padding: 8px 16px;
    font-size: var(--text-xs);
    font-weight: 500;
    border: none;
    cursor: pointer;
    transition: background 150ms;
  }

  .token-btn:hover {
    background: var(--accent-bright);
  }

  .token-error {
    font-size: var(--text-xs);
    color: var(--bearish);
  }

  /* Toolbar */
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-radius: var(--radius-lg);
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
  }

  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .connected-dot {
    width: 8px;
    height: 8px;
    border-radius: 9999px;
    background: var(--bullish);
    box-shadow: 0 0 6px var(--bullish-glow);
  }

  .connected-label {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--bullish);
  }

  .toolbar-right {
    display: flex;
    gap: 8px;
  }

  .toolbar-btn {
    border-radius: var(--radius-md);
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 500;
    border: 1px solid var(--border-subtle);
    background: var(--bg-elevated);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 150ms;
  }

  .toolbar-btn:hover {
    border-color: var(--border-default);
    color: var(--text-primary);
  }

  .toolbar-btn-dim {
    color: var(--text-disabled);
    border-color: transparent;
    background: transparent;
  }

  .toolbar-btn-dim:hover {
    color: var(--text-tertiary);
  }

  .error-bar {
    padding: 8px 12px;
    border-radius: var(--radius-md);
    background: oklch(0.18 0.04 25);
    border: 1px solid oklch(0.30 0.08 25);
    font-size: var(--text-xs);
    color: var(--bearish);
  }

  .loading-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 48px 0;
    font-size: var(--text-sm);
    color: var(--text-tertiary);
  }

  /* Vendor list */
  .vendor-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .vendor-card {
    overflow: hidden;
    transition: border-color 150ms;
  }

  .vendor-card-active {
    border-color: oklch(0.30 0.06 145);
  }

  /* Card header */
  .vendor-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 14px 16px;
    text-align: left;
    cursor: pointer;
    background: none;
    border: none;
    color: inherit;
    transition: background 150ms;
  }

  .vendor-header:hover {
    background: var(--hover-overlay);
  }

  .vendor-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .vendor-name-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .vendor-name {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  .vendor-status {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .vendor-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--text-disabled);
  }

  .vendor-id {
    font-family: var(--font-mono);
  }

  .vendor-dot {
    color: var(--border-subtle);
  }

  .chevron {
    width: 16px;
    height: 16px;
    color: var(--text-disabled);
    transition: transform 200ms;
    flex-shrink: 0;
  }

  .chevron-open {
    transform: rotate(180deg);
  }

  /* Expanded body */
  .vendor-body {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 0 16px 16px;
    border-top: 1px solid var(--border-subtle);
    padding-top: 16px;
  }

  .field-section {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .field-section-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-disabled);
  }

  .field-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .field-name {
    width: 120px;
    flex-shrink: 0;
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--text-secondary);
  }

  .field-input {
    flex: 1;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    background: var(--bg-base);
    padding: 8px 10px;
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    color: var(--text-primary);
    outline: none;
    transition: border-color 150ms;
  }

  .field-input:focus {
    border-color: var(--accent-dim);
    box-shadow: 0 0 0 2px oklch(0.45 0.12 250 / 0.2);
  }

  .field-input::placeholder {
    color: var(--text-disabled);
    font-family: var(--font-sans);
  }

  .env-hint {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--text-disabled);
  }

  .env-icon {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .status-msg {
    font-size: var(--text-xs);
    font-weight: 500;
    padding: 6px 10px;
    border-radius: var(--radius-md);
  }

  .status-ok {
    color: var(--bullish);
    background: oklch(0.18 0.04 145);
    border: 1px solid oklch(0.30 0.06 145);
  }

  .status-err {
    color: var(--bearish);
    background: oklch(0.18 0.04 25);
    border: 1px solid oklch(0.30 0.06 25);
  }

  /* Actions */
  .vendor-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .actions-left {
    display: flex;
    gap: 8px;
  }

  .actions-right {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .action-btn {
    border-radius: var(--radius-md);
    padding: 6px 14px;
    font-size: var(--text-xs);
    font-weight: 500;
    border: none;
    cursor: pointer;
    transition: all 150ms;
  }

  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .action-save {
    background: var(--bullish);
    color: white;
  }

  .action-save:hover:not(:disabled) {
    background: var(--bullish-bright);
  }

  .action-test {
    background: var(--bg-elevated);
    color: var(--text-secondary);
    border: 1px solid var(--border-subtle);
  }

  .action-test:hover:not(:disabled) {
    border-color: var(--border-default);
    color: var(--text-primary);
  }

  .action-delete {
    background: none;
    color: var(--bearish-dim);
  }

  .action-delete:hover {
    color: var(--bearish);
    background: oklch(0.18 0.02 25);
  }

  .action-link {
    font-size: var(--text-xs);
    color: var(--accent);
    text-decoration: none;
  }

  .action-link:hover {
    text-decoration: underline;
  }
</style>
