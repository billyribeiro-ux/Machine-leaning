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

<div class="flex flex-col gap-8 {className}">
  <!-- Section header -->
  <div class="flex flex-col gap-1">
    <h2 class="text-lg font-semibold text-[oklch(0.90_0_0)]">Profile Settings</h2>
    <p class="text-sm text-[oklch(0.55_0_0)]">Manage your account information</p>
  </div>

  <!-- Profile form -->
  <div class="flex flex-col gap-6 rounded-xl border border-[oklch(0.20_0_0)] bg-[oklch(0.13_0_0)] p-6">
    <!-- Avatar + Name row -->
    <div class="flex items-start gap-5">
      <!-- Avatar placeholder -->
      <div class="flex flex-col items-center gap-2">
        <div
          class="
            flex items-center justify-center
            w-16 h-16 rounded-full
            bg-[oklch(0.20_0.04_250)]
            border-2 border-[oklch(0.30_0.08_250)]
            text-xl font-bold text-[oklch(0.70_0.12_250)]
            select-none
          "
        >
          {avatarInitial}
        </div>
        <button
          class="
            text-[11px] font-medium text-[oklch(0.55_0.10_250)]
            hover:text-[oklch(0.65_0.12_250)]
            transition-colors duration-150
            cursor-pointer bg-transparent border-none
          "
        >
          Change
        </button>
      </div>

      <!-- Name and email fields -->
      <div class="flex flex-col gap-4 flex-1">
        <!-- Name -->
        <div class="flex flex-col gap-1.5">
          <label for="profile-name" class="text-xs font-medium text-[oklch(0.65_0_0)]">
            Display Name
          </label>
          <input
            id="profile-name"
            type="text"
            bind:value={profile.name}
            placeholder="Your name"
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

        <!-- Email (disabled) -->
        <div class="flex flex-col gap-1.5">
          <label for="profile-email" class="text-xs font-medium text-[oklch(0.65_0_0)]">
            Email Address
          </label>
          <input
            id="profile-email"
            type="email"
            value={profile.email}
            disabled
            class="
              w-full rounded-lg border border-[oklch(0.20_0_0)]
              bg-[oklch(0.10_0_0)] px-3 py-2
              text-sm text-[oklch(0.50_0_0)]
              outline-none cursor-not-allowed opacity-60
            "
          />
          <span class="text-[11px] text-[oklch(0.42_0_0)]">
            Contact support to change your email address
          </span>
        </div>
      </div>
    </div>

    <!-- Timezone -->
    <div class="flex flex-col gap-1.5">
      <label for="profile-timezone" class="text-xs font-medium text-[oklch(0.65_0_0)]">
        Timezone
      </label>
      <select
        id="profile-timezone"
        bind:value={profile.timezone}
        class="
          w-full rounded-lg border border-[oklch(0.24_0_0)]
          bg-[oklch(0.11_0_0)] px-3 py-2
          text-sm text-[oklch(0.88_0_0)]
          outline-none transition-all duration-150
          focus:border-[oklch(0.45_0.12_250)]
          focus:ring-2 focus:ring-[oklch(0.45_0.12_250/0.3)]
          cursor-pointer
        "
      >
        {#each timezones as tz (tz.value)}
          <option value={tz.value}>{tz.label}</option>
        {/each}
      </select>
    </div>

    <!-- Save button + message -->
    <div class="flex items-center justify-between pt-2">
      {#if saveMessage}
        <span class="text-xs font-medium text-[oklch(0.60_0.12_145)]">{saveMessage}</span>
      {:else}
        <span></span>
      {/if}
      <button
        class="
          rounded-lg bg-[oklch(0.55_0.15_145)] px-5 py-2
          text-sm font-medium text-white
          shadow-sm shadow-[oklch(0.55_0.15_145/0.25)]
          transition-all duration-150
          hover:bg-[oklch(0.60_0.16_145)]
          active:bg-[oklch(0.50_0.14_145)]
          cursor-pointer border-none
        "
        onclick={handleSave}
      >
        Save Changes
      </button>
    </div>
  </div>

  <!-- Change Password Section -->
  <div class="flex flex-col gap-4 rounded-xl border border-[oklch(0.20_0_0)] bg-[oklch(0.13_0_0)] p-6">
    <div class="flex items-center justify-between">
      <div>
        <h3 class="text-sm font-semibold text-[oklch(0.85_0_0)]">Change Password</h3>
        <p class="text-xs text-[oklch(0.50_0_0)] mt-0.5">Update your account password</p>
      </div>
      {#if !showPasswordSection}
        <button
          class="
            px-3 py-1.5 rounded-lg
            border border-[oklch(0.28_0_0)]
            bg-transparent text-xs font-medium text-[oklch(0.70_0_0)]
            hover:bg-[oklch(0.17_0_0)] hover:text-[oklch(0.80_0_0)]
            transition-colors duration-150 cursor-pointer
          "
          onclick={() => { showPasswordSection = true; }}
        >
          Change Password
        </button>
      {/if}
    </div>

    {#if showPasswordSection}
      <div class="flex flex-col gap-4 pt-2">
        <!-- Current password -->
        <div class="flex flex-col gap-1.5">
          <label for="current-pw" class="text-xs font-medium text-[oklch(0.65_0_0)]">
            Current Password
          </label>
          <input
            id="current-pw"
            type="password"
            bind:value={currentPassword}
            placeholder="Enter current password"
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

        <!-- New password -->
        <div class="flex flex-col gap-1.5">
          <label for="new-pw" class="text-xs font-medium text-[oklch(0.65_0_0)]">
            New Password
          </label>
          <input
            id="new-pw"
            type="password"
            bind:value={newPassword}
            placeholder="Enter new password"
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

        <!-- Confirm password -->
        <div class="flex flex-col gap-1.5">
          <label for="confirm-pw" class="text-xs font-medium text-[oklch(0.65_0_0)]">
            Confirm New Password
          </label>
          <input
            id="confirm-pw"
            type="password"
            bind:value={confirmPassword}
            placeholder="Confirm new password"
            class="
              w-full rounded-lg border border-[oklch(0.24_0_0)]
              bg-[oklch(0.11_0_0)] px-3 py-2
              text-sm text-[oklch(0.88_0_0)]
              placeholder-[oklch(0.40_0_0)]
              outline-none transition-all duration-150
              focus:border-[oklch(0.45_0.12_250)]
              focus:ring-2 focus:ring-[oklch(0.45_0.12_250/0.3)]
              {passwordError ? 'border-[oklch(0.50_0.16_25)] focus:border-[oklch(0.50_0.16_25)] focus:ring-[oklch(0.50_0.16_25/0.3)]' : ''}
            "
          />
          {#if passwordError}
            <span class="text-[11px] text-[oklch(0.60_0.16_25)]">{passwordError}</span>
          {/if}
        </div>

        <!-- Password actions -->
        <div class="flex items-center justify-end gap-3 pt-1">
          <button
            class="
              px-3 py-1.5 rounded-lg
              bg-transparent text-xs font-medium text-[oklch(0.60_0_0)]
              hover:text-[oklch(0.80_0_0)]
              transition-colors duration-150 cursor-pointer border-none
            "
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
            class="
              px-4 py-2 rounded-lg text-sm font-medium
              border-none cursor-pointer transition-all duration-150
              {passwordsMatch && currentPassword.length > 0
                ? 'bg-[oklch(0.55_0.15_145)] hover:bg-[oklch(0.60_0.16_145)] text-white shadow-sm shadow-[oklch(0.55_0.15_145/0.25)]'
                : 'bg-[oklch(0.20_0_0)] text-[oklch(0.40_0_0)] cursor-not-allowed'}
            "
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
