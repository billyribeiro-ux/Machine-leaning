// ---------------------------------------------------------------------------
// Auth store – Svelte 5 rune-based reactive state
// ---------------------------------------------------------------------------

import { browser } from '$app/environment';

export interface User {
  id: string;
  email: string;
  name: string;
  tier: 'free' | 'pro' | 'elite' | 'institutional';
  avatarUrl?: string;
}

export type AuthTier = User['tier'];

/** Token pair returned by the auth API. */
interface TokenPair {
  accessToken: string;
  refreshToken: string;
  expiresAt: number; // epoch ms
}

function createAuthStore() {
  // ---- reactive state ----
  let user = $state<User | null>(null);
  let isLoading = $state(false);
  let error = $state<string | null>(null);
  let tokens = $state<TokenPair | null>(null);
  let lastRefresh = $state<number>(0);

  // ---- derived ----
  let isAuthenticated = $derived(user !== null && tokens !== null);
  let tier = $derived<AuthTier>(user?.tier ?? 'free');
  let isTokenExpired = $derived(
    tokens !== null ? Date.now() >= tokens.expiresAt : true
  );
  let initials = $derived(
    user
      ? user.name
          .split(' ')
          .map((p) => p[0])
          .join('')
          .toUpperCase()
          .slice(0, 2)
      : ''
  );

  // ---- helpers ----

  function setTokensFromStorage(): void {
    if (!browser) return;
    try {
      const raw = localStorage.getItem('scanify:auth:tokens');
      if (raw) {
        tokens = JSON.parse(raw) as TokenPair;
      }
    } catch {
      tokens = null;
    }
  }

  function persistTokens(pair: TokenPair | null): void {
    if (!browser) return;
    if (pair) {
      localStorage.setItem('scanify:auth:tokens', JSON.stringify(pair));
    } else {
      localStorage.removeItem('scanify:auth:tokens');
    }
  }

  // ---- actions ----

  /**
   * Authenticate with email + password.
   * In a real implementation this would call the backend API.
   */
  async function login(email: string, password: string): Promise<boolean> {
    isLoading = true;
    error = null;

    try {
      // Simulated API call – replace with real fetch
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error((body as Record<string, string>).message ?? 'Login failed');
      }

      const data = (await response.json()) as { user: User; tokens: TokenPair };
      user = data.user;
      tokens = data.tokens;
      persistTokens(data.tokens);
      lastRefresh = Date.now();
      return true;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unknown error';
      return false;
    } finally {
      isLoading = false;
    }
  }

  /** End the current session and clear all stored credentials. */
  async function logout(): Promise<void> {
    isLoading = true;
    try {
      if (tokens) {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${tokens.accessToken}`,
          },
        }).catch(() => {
          /* best-effort */
        });
      }
    } finally {
      user = null;
      tokens = null;
      error = null;
      persistTokens(null);
      isLoading = false;
    }
  }

  /** Silently refresh the access token using the stored refresh token. */
  async function refreshToken(): Promise<boolean> {
    if (!tokens?.refreshToken) return false;

    try {
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refreshToken: tokens.refreshToken }),
      });

      if (!response.ok) {
        // Refresh failed – force logout
        await logout();
        return false;
      }

      const data = (await response.json()) as TokenPair;
      tokens = data;
      persistTokens(data);
      lastRefresh = Date.now();
      return true;
    } catch {
      await logout();
      return false;
    }
  }

  /** Update the current user's profile fields. */
  async function updateProfile(
    updates: Partial<Pick<User, 'name' | 'avatarUrl'>>
  ): Promise<boolean> {
    if (!user || !tokens) return false;

    isLoading = true;
    error = null;

    try {
      const response = await fetch('/api/auth/profile', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${tokens.accessToken}`,
        },
        body: JSON.stringify(updates),
      });

      if (!response.ok) {
        throw new Error('Profile update failed');
      }

      const data = (await response.json()) as User;
      user = data;
      return true;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unknown error';
      return false;
    } finally {
      isLoading = false;
    }
  }

  /** Attempt to restore a session from persisted tokens on app boot. */
  async function initialize(): Promise<void> {
    setTokensFromStorage();
    if (!tokens) return;

    isLoading = true;
    try {
      const response = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${tokens.accessToken}` },
      });

      if (response.ok) {
        user = (await response.json()) as User;
        lastRefresh = Date.now();
      } else {
        // Token may be expired – try refresh
        const refreshed = await refreshToken();
        if (refreshed) {
          const retry = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${tokens!.accessToken}` },
          });
          if (retry.ok) {
            user = (await retry.json()) as User;
          }
        }
      }
    } catch {
      // Network error – leave unauthenticated
    } finally {
      isLoading = false;
    }
  }

  // ---- public API ----
  return {
    // reactive getters
    get user() {
      return user;
    },
    get isAuthenticated() {
      return isAuthenticated;
    },
    get isLoading() {
      return isLoading;
    },
    get error() {
      return error;
    },
    get tier() {
      return tier;
    },
    get isTokenExpired() {
      return isTokenExpired;
    },
    get initials() {
      return initials;
    },
    get lastRefresh() {
      return lastRefresh;
    },
    get accessToken() {
      return tokens?.accessToken ?? null;
    },

    // actions
    login,
    logout,
    refreshToken,
    updateProfile,
    initialize,
  };
}

export const authStore = createAuthStore();
