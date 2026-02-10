// ---------------------------------------------------------------------------
// API client with interceptors, auth handling, and strong typing
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Configuration for the API client. */
export interface ApiConfig {
  /** Base URL for all requests (e.g. "https://api.scanify.io"). */
  readonly baseUrl: string;
  /** Default request timeout in milliseconds (default: 10 000). */
  readonly timeout: number;
}

/** Typed API response wrapper. */
export interface ApiResponse<T> {
  readonly data: T;
  readonly status: number;
  readonly ok: boolean;
}

/** Structured API error. */
export interface ApiError {
  readonly message: string;
  readonly status: number;
  readonly code?: string;
}

/** A request interceptor can mutate the RequestInit before it is sent. */
export type RequestInterceptor = (
  url: string,
  init: RequestInit,
) => RequestInit | Promise<RequestInit>;

/** A response interceptor can inspect / transform the Response. */
export type ResponseInterceptor = (
  response: Response,
) => Response | Promise<Response>;

/** The shape returned by {@link createApiClient}. */
export interface ApiClient {
  get<T>(path: string, params?: Record<string, string>): Promise<ApiResponse<T>>;
  post<T>(path: string, body?: unknown): Promise<ApiResponse<T>>;
  put<T>(path: string, body?: unknown): Promise<ApiResponse<T>>;
  delete<T>(path: string): Promise<ApiResponse<T>>;
  /** Append a request interceptor. Returns a dispose function. */
  addRequestInterceptor(interceptor: RequestInterceptor): () => void;
  /** Append a response interceptor. Returns a dispose function. */
  addResponseInterceptor(interceptor: ResponseInterceptor): () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Read the auth token from the `token` cookie (if present).
 * Returns `undefined` when running server-side or when the cookie is absent.
 */
function getAuthToken(): string | undefined {
  if (typeof document === 'undefined') return undefined;

  const match = document.cookie
    .split('; ')
    .find((row) => row.startsWith('token='));

  return match ? decodeURIComponent(match.split('=')[1] ?? '') : undefined;
}

/**
 * Type-guard that narrows `unknown` to {@link ApiError}.
 */
export function isApiError(value: unknown): value is ApiError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'message' in value &&
    'status' in value
  );
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Create a configured API client.
 *
 * ```ts
 * const api = createApiClient({ baseUrl: 'https://api.scanify.io', timeout: 8000 });
 * const { data } = await api.get<ScanResult[]>('/scans/momentum');
 * ```
 */
export function createApiClient(config: ApiConfig): ApiClient {
  let requestInterceptors: RequestInterceptor[] = [];
  let responseInterceptors: ResponseInterceptor[] = [];

  // -----------------------------------------------------------------------
  // Core request runner
  // -----------------------------------------------------------------------

  async function request<T>(
    method: string,
    path: string,
    body?: unknown,
    params?: Record<string, string>,
  ): Promise<ApiResponse<T>> {
    // Build URL.
    const base = config.baseUrl.replace(/\/+$/, '');
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    const url = new URL(`${base}${normalizedPath}`);

    if (params) {
      for (const [key, value] of Object.entries(params)) {
        url.searchParams.set(key, value);
      }
    }

    // Build RequestInit.
    let init: RequestInit = {
      method,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      credentials: 'include' as RequestCredentials,
    };

    // Attach auth token.
    const token = getAuthToken();
    if (token) {
      (init.headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
    }

    // Serialise body.
    if (body !== undefined && body !== null) {
      init.body = JSON.stringify(body);
    }

    // Apply request interceptors.
    for (const interceptor of requestInterceptors) {
      init = await interceptor(url.toString(), init);
    }

    // Execute with timeout.
    const controller = new AbortController();
    init.signal = controller.signal;

    const timeoutId = setTimeout(() => controller.abort(), config.timeout);

    let response: Response;

    try {
      response = await fetch(url.toString(), init);
    } catch (err) {
      clearTimeout(timeoutId);

      if (err instanceof DOMException && err.name === 'AbortError') {
        throw {
          message: `Request timed out after ${config.timeout}ms`,
          status: 0,
          code: 'TIMEOUT',
        } satisfies ApiError;
      }

      throw {
        message: err instanceof Error ? err.message : 'Network error',
        status: 0,
        code: 'NETWORK_ERROR',
      } satisfies ApiError;
    } finally {
      clearTimeout(timeoutId);
    }

    // Apply response interceptors.
    for (const interceptor of responseInterceptors) {
      response = await interceptor(response);
    }

    // Parse body.
    let data: T;

    const contentType = response.headers.get('content-type') ?? '';

    if (contentType.includes('application/json')) {
      try {
        data = (await response.json()) as T;
      } catch {
        data = null as T;
      }
    } else {
      // For non-JSON responses, attempt to read text and cast.
      const text = await response.text();
      data = text as unknown as T;
    }

    // Throw structured error for non-2xx responses.
    if (!response.ok) {
      const errorBody = data as unknown as Record<string, unknown> | null;
      throw {
        message:
          (typeof errorBody === 'object' && errorBody !== null && typeof errorBody['message'] === 'string'
            ? errorBody['message']
            : response.statusText) || 'Request failed',
        status: response.status,
        code:
          typeof errorBody === 'object' && errorBody !== null && typeof errorBody['code'] === 'string'
            ? errorBody['code']
            : undefined,
      } satisfies ApiError;
    }

    return {
      data,
      status: response.status,
      ok: true,
    };
  }

  // -----------------------------------------------------------------------
  // Public methods
  // -----------------------------------------------------------------------

  function get<T>(
    path: string,
    params?: Record<string, string>,
  ): Promise<ApiResponse<T>> {
    return request<T>('GET', path, undefined, params);
  }

  function post<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
    return request<T>('POST', path, body);
  }

  function put<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
    return request<T>('PUT', path, body);
  }

  function del<T>(path: string): Promise<ApiResponse<T>> {
    return request<T>('DELETE', path);
  }

  function addRequestInterceptor(interceptor: RequestInterceptor): () => void {
    requestInterceptors.push(interceptor);
    return () => {
      requestInterceptors = requestInterceptors.filter((i) => i !== interceptor);
    };
  }

  function addResponseInterceptor(interceptor: ResponseInterceptor): () => void {
    responseInterceptors.push(interceptor);
    return () => {
      responseInterceptors = responseInterceptors.filter((i) => i !== interceptor);
    };
  }

  return {
    get,
    post,
    put,
    delete: del,
    addRequestInterceptor,
    addResponseInterceptor,
  };
}
