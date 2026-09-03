/** Typed client for the Casa Radar backend.
 *
 * Paths are always relative: in dev Vite proxies /api to uvicorn, in production
 * Vercel rewrites it to the Python function. No base URL, no env variable.
 * There is no session: every endpoint is public.
 *
 * M0 shape: one endpoint. The read cache and the optimistic writes arrive with
 * the dashboard (M4), mirrored from food-plan-maker's api/cache.ts.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`)
  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    // /api/health answers 503 with a meaningful body; anything else with a
    // `detail` carries a message written for the user.
    if (path === '/health' && payload) {
      return payload as T
    }
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : `Errore ${response.status}`
    throw new ApiError(detail, response.status)
  }

  return payload as T
}

export interface Health {
  status: 'ok' | 'degraded'
  environment: string
  database: 'ok' | 'unreachable' | 'not_configured'
  detail: string | null
}

export const api = {
  health: () => request<Health>('/health'),
}
