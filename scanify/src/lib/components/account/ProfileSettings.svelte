<!--
  ProfileSettings.svelte
  User profile form with avatar placeholder, name, email, timezone,
  and a change password section.
-->
<script lang="ts">
  interface Profile {
    name: string;
    email: string;
    timezone: string;
  }

  interface ProfileSettingsProps {
    /** User profile data (bindable). */
    profile: Profile;
    /** Additional CSS classes. */
    class?: string;
  }

  let {
    profile = $bindable(),
    class: className = '',
  }: ProfileSettingsProps = $props();

  let currentPassword = $state('');
  let newPassword = $state('');
  let confirmPassword = $state('');
  let showPasswordSection = $state(false);
  let saveMessage = $state('');

  /** Available timezone options. */
  const timezones = [
    { value: 'America/New_York',    label: 'Eastern Time (ET)' },
    { value: 'America/Chicago',     label: 'Central Time (CT)' },
    { value: 'America/Denver',      label: 'Mountain Time (MT)' },
    { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
    { value: 'America/Anchorage',   label: 'Alaska Time (AKT)' },
    { value: 'Pacific/Honolulu',    label: 'Hawaii Time (HT)' },
    { value: 'Europe/London',       label: 'GMT / London' },
    { value: 'Europe/Berlin',       label: 'CET / Berlin' },
    { value: 'Asia/Tokyo',          label: 'JST / Tokyo' },
    { value: 'Asia/Shanghai',       label: 'CST / Shanghai' },
    { value: 'Asia/Kolkata',        label: 'IST / Mumbai' },
    { value: 'Australia/Sydney',    label: 'AEST / Sydney' },
  ];

  /** First letter of user name for avatar. */
  let avatarInitial = $derived(
    profile.name ? profile.name.charAt(0).toUpperCase() : 'U'
  );

  let passwordsMatch = $derived(
    newPassword.length > 0 && newPassword === confirmPassword
  );

  let passwordError = $derived(
    confirmPassword.length > 0 && newPassword !== confirmPassword
      ? 'Passwords do not match'
      : ''
  );

  function handleSave(): void {
    saveMessage = 'Profile saved successfully';
    setTimeout(() => { saveMessage = ''; }, 3000);
  }

  function handlePasswordChange(): void {
    if (!passwordsMatch) return;
    // Reset fields after save
    currentPassword = '';
    newPassword = '';
    confirmPassword = '';
    showPasswordSection = false;
    saveMessage = 'Password updated successfully';
    setTimeout(() => { saveMessage = ''; }, 3000);
  }
</script>

<div class="profile-root {className}">
  <!-- Section header -->
  <div class="section-header">
    <h2 class="section-title">Profile Settings</h2>
    <p class="section-subtitle">Manage your account information</p>
  </div>

  <!-- Profile form -->
  <div class="card">
    <!-- Avatar + Name row -->
    <div class="avatar-row">
      <!-- Avatar placeholder -->
      <div class="avatar-group">
        <div class="avatar-circle">
          {avatarInitial}
        </div>
        <button class="avatar-change-btn">
          Change
        </button>
      </div>

      <!-- Name and email fields -->
      <div class="fields-column">
        <!-- Name -->
        <div class="field-group">
          <label for="profile-name" class="field-label">
            Display Name
          </label>
          <input
            id="profile-name"
            type="text"
            bind:value={profile.name}
            placeholder="Your name"
            class="text-input"
          />
        </div>

        <!-- Email (disabled) -->
        <div class="field-group">
          <label for="profile-email" class="field-label">
            Email Address
          </label>
          <input
            id="profile-email"
            type="email"
            value={profile.email}
            disabled
            class="text-input text-input--disabled"
          />
          <span class="field-hint">
            Contact support to change your email address
          </span>
        </div>
      </div>
    </div>

    <!-- Timezone -->
    <div class="field-group">
      <label for="profile-timezone" class="field-label">
        Timezone
      </label>
      <select
        id="profile-timezone"
        bind:value={profile.timezone}
        class="select-input"
      >
        {#each timezones as tz (tz.value)}
          <option value={tz.value}>{tz.label}</option>
        {/each}
      </select>
    </div>

    <!-- Save button + message -->
    <div class="save-row">
      {#if saveMessage}
        <span class="save-message">{saveMessage}</span>
      {:else}
        <span></span>
      {/if}
      <button
        class="btn-primary"
        onclick={handleSave}
      >
        Save Changes
      </button>
    </div>
  </div>

  <!-- Change Password Section -->
  <div class="card card--password">
    <div class="password-header">
      <div>
        <h3 class="password-title">Change Password</h3>
        <p class="password-subtitle">Update your account password</p>
      </div>
      {#if !showPasswordSection}
        <button
          class="btn-outline"
          onclick={() => { showPasswordSection = true; }}
        >
          Change Password
        </button>
      {/if}
    </div>

    {#if showPasswordSection}
      <div class="password-fields">
        <!-- Current password -->
        <div class="field-group">
          <label for="current-pw" class="field-label">
            Current Password
          </label>
          <input
            id="current-pw"
            type="password"
            bind:value={currentPassword}
            placeholder="Enter current password"
            class="text-input"
          />
        </div>

        <!-- New password -->
        <div class="field-group">
          <label for="new-pw" class="field-label">
            New Password
          </label>
          <input
            id="new-pw"
            type="password"
            bind:value={newPassword}
            placeholder="Enter new password"
            class="text-input"
          />
        </div>

        <!-- Confirm password -->
        <div class="field-group">
          <label for="confirm-pw" class="field-label">
            Confirm New Password
          </label>
          <input
            id="confirm-pw"
            type="password"
            bind:value={confirmPassword}
            placeholder="Confirm new password"
            class="text-input"
            class:input-error={!!passwordError}
          />
          {#if passwordError}
            <span class="error-text">{passwordError}</span>
          {/if}
        </div>

        <!-- Password actions -->
        <div class="password-actions">
          <button
            class="btn-cancel"
            onclick={() => {
              showPasswordSection = false;
              currentPassword = '';
              newPassword = '';
              confirmPassword = '';
            }}
          >
            Cancel
          </button>
          <button
            class="btn-update-password"
            class:btn-update-password--disabled={!passwordsMatch || currentPassword.length === 0}
            disabled={!passwordsMatch || currentPassword.length === 0}
            onclick={handlePasswordChange}
          >
            Update Password
          </button>
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  /* ── Root layout ── */
  .profile-root {
    display: flex;
    flex-direction: column;
    gap: 2rem; /* gap-8 */
  }

  /* ── Section header ── */
  .section-header {
    display: flex;
    flex-direction: column;
    gap: 0.25rem; /* gap-1 */
  }

  .section-title {
    font-size: 1.125rem; /* text-lg */
    line-height: 1.75rem;
    font-weight: 600; /* font-semibold */
    color: oklch(0.90 0 0);
  }

  .section-subtitle {
    font-size: 0.875rem; /* text-sm */
    line-height: 1.25rem;
    color: oklch(0.55 0 0);
  }

  /* ── Card panels ── */
  .card {
    display: flex;
    flex-direction: column;
    gap: 1.5rem; /* gap-6 */
    border-radius: var(--radius-xl, 0.75rem);
    border: 1px solid oklch(0.20 0 0);
    background-color: oklch(0.13 0 0);
    padding: 1.5rem; /* p-6 */
  }

  .card--password {
    gap: 1rem; /* gap-4 */
  }

  /* ── Avatar row ── */
  .avatar-row {
    display: flex;
    align-items: flex-start;
    gap: 1.25rem; /* gap-5 */
  }

  .avatar-group {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem; /* gap-2 */
  }

  .avatar-circle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 4rem; /* w-16 */
    height: 4rem; /* h-16 */
    border-radius: var(--radius-full, 9999px);
    background-color: oklch(0.20 0.04 250);
    border: 2px solid oklch(0.30 0.08 250);
    font-size: 1.25rem; /* text-xl */
    font-weight: 700; /* font-bold */
    color: oklch(0.70 0.12 250);
    user-select: none;
  }

  .avatar-change-btn {
    font-size: 11px; /* text-[11px] */
    font-weight: 500; /* font-medium */
    color: oklch(0.55 0.10 250);
    transition: color 150ms ease;
    cursor: pointer;
    background: transparent;
    border: none;
    padding: 0;
  }

  .avatar-change-btn:hover {
    color: oklch(0.65 0.12 250);
  }

  /* ── Fields column ── */
  .fields-column {
    display: flex;
    flex-direction: column;
    gap: 1rem; /* gap-4 */
    flex: 1;
  }

  /* ── Field group ── */
  .field-group {
    display: flex;
    flex-direction: column;
    gap: 0.375rem; /* gap-1.5 */
  }

  .field-label {
    font-size: 0.75rem; /* text-xs */
    line-height: 1rem;
    font-weight: 500; /* font-medium */
    color: oklch(0.65 0 0);
  }

  .field-hint {
    font-size: 11px; /* text-[11px] */
    color: oklch(0.42 0 0);
  }

  /* ── Text input ── */
  .text-input {
    width: 100%;
    border-radius: var(--radius-lg, 0.5rem);
    border: 1px solid oklch(0.24 0 0);
    background-color: oklch(0.11 0 0);
    padding: 0.5rem 0.75rem; /* px-3 py-2 */
    font-size: 0.875rem; /* text-sm */
    line-height: 1.25rem;
    color: oklch(0.88 0 0);
    outline: none;
    transition: all 150ms ease;
  }

  .text-input::placeholder {
    color: oklch(0.40 0 0);
  }

  .text-input:focus {
    border-color: oklch(0.45 0.12 250);
    box-shadow: 0 0 0 2px oklch(0.45 0.12 250 / 0.3);
  }

  .text-input--disabled {
    border-color: oklch(0.20 0 0);
    background-color: oklch(0.10 0 0);
    color: oklch(0.50 0 0);
    cursor: not-allowed;
    opacity: 0.6;
  }

  /* ── Input error state (via Svelte class: directive) ── */
  .text-input.input-error {
    border-color: oklch(0.50 0.16 25);
  }

  .text-input.input-error:focus {
    border-color: oklch(0.50 0.16 25);
    box-shadow: 0 0 0 2px oklch(0.50 0.16 25 / 0.3);
  }

  .error-text {
    font-size: 11px; /* text-[11px] */
    color: oklch(0.60 0.16 25);
  }

  /* ── Select input ── */
  .select-input {
    width: 100%;
    border-radius: var(--radius-lg, 0.5rem);
    border: 1px solid oklch(0.24 0 0);
    background-color: oklch(0.11 0 0);
    padding: 0.5rem 0.75rem; /* px-3 py-2 */
    font-size: 0.875rem; /* text-sm */
    line-height: 1.25rem;
    color: oklch(0.88 0 0);
    outline: none;
    transition: all 150ms ease;
    cursor: pointer;
  }

  .select-input:focus {
    border-color: oklch(0.45 0.12 250);
    box-shadow: 0 0 0 2px oklch(0.45 0.12 250 / 0.3);
  }

  /* ── Save row ── */
  .save-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 0.5rem; /* pt-2 */
  }

  .save-message {
    font-size: 0.75rem; /* text-xs */
    font-weight: 500; /* font-medium */
    color: oklch(0.60 0.12 145);
  }

  /* ── Primary button ── */
  .btn-primary {
    border-radius: var(--radius-lg, 0.5rem);
    background-color: oklch(0.55 0.15 145);
    padding: 0.5rem 1.25rem; /* px-5 py-2 */
    font-size: 0.875rem; /* text-sm */
    font-weight: 500; /* font-medium */
    color: white;
    box-shadow: 0 1px 2px oklch(0.55 0.15 145 / 0.25);
    transition: all 150ms ease;
    cursor: pointer;
    border: none;
  }

  .btn-primary:hover {
    background-color: oklch(0.60 0.16 145);
  }

  .btn-primary:active {
    background-color: oklch(0.50 0.14 145);
  }

  /* ── Password header ── */
  .password-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .password-title {
    font-size: 0.875rem; /* text-sm */
    line-height: 1.25rem;
    font-weight: 600; /* font-semibold */
    color: oklch(0.85 0 0);
  }

  .password-subtitle {
    font-size: 0.75rem; /* text-xs */
    line-height: 1rem;
    color: oklch(0.50 0 0);
    margin-top: 2px; /* mt-0.5 */
  }

  /* ── Outline button ── */
  .btn-outline {
    padding: 0.375rem 0.75rem; /* px-3 py-1.5 */
    border-radius: var(--radius-lg, 0.5rem);
    border: 1px solid oklch(0.28 0 0);
    background: transparent;
    font-size: 0.75rem; /* text-xs */
    font-weight: 500; /* font-medium */
    color: oklch(0.70 0 0);
    transition: color 150ms ease, background-color 150ms ease;
    cursor: pointer;
  }

  .btn-outline:hover {
    background-color: oklch(0.17 0 0);
    color: oklch(0.80 0 0);
  }

  /* ── Password fields wrapper ── */
  .password-fields {
    display: flex;
    flex-direction: column;
    gap: 1rem; /* gap-4 */
    padding-top: 0.5rem; /* pt-2 */
  }

  /* ── Password actions row ── */
  .password-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.75rem; /* gap-3 */
    padding-top: 0.25rem; /* pt-1 */
  }

  /* ── Cancel button ── */
  .btn-cancel {
    padding: 0.375rem 0.75rem; /* px-3 py-1.5 */
    border-radius: var(--radius-lg, 0.5rem);
    background: transparent;
    font-size: 0.75rem; /* text-xs */
    font-weight: 500; /* font-medium */
    color: oklch(0.60 0 0);
    transition: color 150ms ease;
    cursor: pointer;
    border: none;
  }

  .btn-cancel:hover {
    color: oklch(0.80 0 0);
  }

  /* ── Update password button ── */
  .btn-update-password {
    padding: 0.5rem 1rem; /* px-4 py-2 */
    border-radius: var(--radius-lg, 0.5rem);
    font-size: 0.875rem; /* text-sm */
    font-weight: 500; /* font-medium */
    border: none;
    cursor: pointer;
    transition: all 150ms ease;
    background-color: oklch(0.55 0.15 145);
    color: white;
    box-shadow: 0 1px 2px oklch(0.55 0.15 145 / 0.25);
  }

  .btn-update-password:hover {
    background-color: oklch(0.60 0.16 145);
  }

  .btn-update-password--disabled {
    background-color: oklch(0.20 0 0);
    color: oklch(0.40 0 0);
    cursor: not-allowed;
    box-shadow: none;
  }

  .btn-update-password--disabled:hover {
    background-color: oklch(0.20 0 0);
  }
</style>
