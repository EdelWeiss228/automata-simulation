export interface RunSummary {
  directory: string
  run_id: string
  run_number: number
  scenario_name: string
  status: string
  days_completed: number
  days_total: number
  progress: number
  interactions: number
  successes: number
  failures: number
  refusals: number
  rotations: number
  semesters: number
  final_hash: string
  wall_seconds: number
  updated_unix: number
  updated_at: string
}

export interface RunDetail {
  run: RunSummary
  manifest: Record<string, string>
}

export interface ReportFile {
  name: string
  bytes: number
  url: string
}

const TOKEN_KEY = 'automata-token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(token: string): void {
  const trimmed = token.trim()
  if (trimmed) {
    localStorage.setItem(TOKEN_KEY, trimmed)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function authQuery(): string {
  const token = getToken().trim()
  return token ? `?token=${encodeURIComponent(token)}` : ''
}

export function withToken(url: string): string {
  const token = getToken().trim()
  if (!token) return url
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
}

export async function api<T>(path: string): Promise<T> {
  const response = await fetch(path + authQuery(), { cache: 'no-store' })
  if (response.status === 401) {
    throw new Error('Нужен токен доступа — введите его в поле справа сверху')
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}
