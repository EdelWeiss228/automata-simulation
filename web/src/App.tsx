import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  getToken,
  setToken,
  withToken,
  type ReportFile,
  type RunDetail,
  type RunSummary,
} from './api'

const numberFormat = new Intl.NumberFormat('ru-RU')

const statusLabels: Record<string, string> = {
  completed: 'завершён',
  running: 'в работе',
  failed: 'ошибка',
  pending: 'ожидает',
}

function formatNumber(value: number): string {
  return numberFormat.format(value || 0)
}

function formatTime(unix: number): string {
  return unix ? new Date(unix * 1000).toLocaleString('ru-RU') : '—'
}

function statusBadge(status: string) {
  return <span className={`badge ${status}`}>{statusLabels[status] ?? status}</span>
}

export default function App() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [token, setTokenValue] = useState(getToken())
  const [tokenRevision, setTokenRevision] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [reports, setReports] = useState<ReportFile[]>([])

  const refresh = useCallback(async () => {
    try {
      const data = await api<{ runs: RunSummary[] }>('/api/runs')
      setRuns(data.runs ?? [])
      setError('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    if (!selected) {
      setDetail(null)
      setReports([])
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const run = await api<RunDetail>(`/api/runs/${encodeURIComponent(selected)}`)
        const reportList = await api<{ reports: ReportFile[] }>(
          `/api/runs/${encodeURIComponent(selected)}/reports`,
        )
        if (!cancelled) {
          setDetail(run)
          setReports(reportList.reports ?? [])
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : String(caught))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selected, tokenRevision])

  const totals = useMemo(
    () => ({
      total: runs.length,
      completed: runs.filter((run) => run.status === 'completed').length,
      running: runs.filter((run) => run.status === 'running').length,
      interactions: runs.reduce((sum, run) => sum + run.interactions, 0),
    }),
    [runs],
  )

  function applyToken() {
    setToken(token)
    setTokenRevision((revision) => revision + 1)
    void refresh()
  }

  return (
    <>
      <header>
        <span className={`dot ${error ? 'err' : 'ok'}`} />
        <div>
          <h1>automata v3</h1>
          <div className="sub">
            {loading ? 'загрузка прогонов…' : `${totals.total} прогонов · данные из манифестов`}
          </div>
        </div>
        <div className="spacer" />
        <input
          type="password"
          value={token}
          placeholder="токен доступа (если задан)"
          autoComplete="off"
          onChange={(event) => setTokenValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') applyToken()
          }}
        />
        <button onClick={applyToken}>Применить</button>
        <button onClick={() => void refresh()}>Обновить</button>
      </header>

      <main>
        {error && <div className="error visible">{error}</div>}

        <div className="cards">
          <div className="card">
            <div className="label">Всего прогонов</div>
            <div className="value">{totals.total}</div>
          </div>
          <div className="card">
            <div className="label">Завершено</div>
            <div className="value">{totals.completed}</div>
          </div>
          <div className="card">
            <div className="label">В работе</div>
            <div className="value">{totals.running}</div>
          </div>
          <div className="card">
            <div className="label">Взаимодействий</div>
            <div className="value">{formatNumber(totals.interactions)}</div>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th>№</th>
              <th>Сценарий</th>
              <th>Статус</th>
              <th>Прогресс</th>
              <th className="num">Дни</th>
              <th className="num">Контакты</th>
              <th className="num">Успех</th>
              <th className="num">Отказ</th>
              <th>Хеш</th>
              <th className="num">Время, с</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 && (
              <tr>
                <td colSpan={10} className="empty">
                  {loading ? 'Загрузка…' : 'Прогонов пока нет'}
                </td>
              </tr>
            )}
            {runs.map((run) => (
              <tr
                key={run.run_number}
                className={selected === String(run.run_number) ? 'selected' : ''}
                onClick={() => setSelected(String(run.run_number))}
              >
                <td className="num">{run.run_number}</td>
                <td>{run.scenario_name}</td>
                <td>{statusBadge(run.status)}</td>
                <td>
                  <div className="progress" title={`${Math.round(run.progress * 100)}%`}>
                    <span style={{ width: `${Math.round(run.progress * 100)}%` }} />
                  </div>
                </td>
                <td className="num">
                  {run.days_completed} / {run.days_total}
                </td>
                <td className="num">{formatNumber(run.interactions)}</td>
                <td className="num">{formatNumber(run.successes)}</td>
                <td className="num">{formatNumber(run.refusals)}</td>
                <td>
                  <span className="hash">{run.final_hash}</span>
                </td>
                <td className="num">{Number(run.wall_seconds || 0).toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {selected && detail && (
          <section className="detail visible">
            <h2>
              {detail.run.run_number} · {detail.run.scenario_name}
            </h2>
            <div className="detail-grid">
              <div className="panel">
                <pre>{JSON.stringify(detail.manifest, null, 2)}</pre>
              </div>
              <div className="panel reports">
                <div className="sub" style={{ marginBottom: 8 }}>
                  обновлено {formatTime(detail.run.updated_unix)}
                </div>
                {reports.length === 0 && <div className="empty">Отчётов пока нет</div>}
                {reports.map((report) => (
                  <a key={report.name} href={withToken(report.url)} target="_blank" rel="noreferrer">
                    {report.name} <span className="hash">({formatNumber(report.bytes)} Б)</span>
                  </a>
                ))}
              </div>
            </div>
          </section>
        )}

        {selected && !detail && <div className="empty">Загрузка деталей…</div>}
      </main>
    </>
  )
}
