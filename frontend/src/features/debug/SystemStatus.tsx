import { useEffect, useState } from 'react'

import { api, type Health } from '../../api/client'

/** Diagnostics screen, reachable only at /_stato — not linked from the app.
 *
 * /api/health returns `detail` only when something is wrong, so a healthy
 * system publishes nothing about itself here.
 */

type Probe =
  | { state: 'loading' }
  | { state: 'loaded'; health: Health }
  | { state: 'failed'; message: string }

export function SystemStatus() {
  const [probe, setProbe] = useState<Probe>({ state: 'loading' })

  useEffect(() => {
    let active = true

    api
      .health()
      .then((health) => {
        if (active) setProbe({ state: 'loaded', health })
      })
      .catch((error: unknown) => {
        if (active) {
          setProbe({
            state: 'failed',
            message: error instanceof Error ? error.message : 'Errore sconosciuto',
          })
        }
      })

    return () => {
      active = false
    }
  }, [])

  return (
    <div className="min-h-full bg-bg-app px-5 py-8 sm:px-6">
      <div className="mx-auto flex w-full max-w-[520px] flex-col gap-5">
        <div className="flex items-center gap-2">
          <span className="size-3 rounded-pill bg-brand" aria-hidden />
          <span className="text-lg font-extrabold">Casa Radar</span>
        </div>

        <section className="rounded-card border border-border-subtle bg-surface-card p-5">
          <h1 className="text-xl font-bold">Stato del sistema</h1>
          <p className="mt-1 text-xs text-text-secondary">
            Pagina di diagnostica · non raggiungibile dall'app
          </p>

          <div className="mt-5 flex flex-col gap-2">
            <StatusRow label="Frontend" value="ok" detail="React · Vite · Tailwind" />
            <ApiRows probe={probe} />
          </div>
        </section>
      </div>
    </div>
  )
}

function ApiRows({ probe }: { probe: Probe }) {
  if (probe.state === 'loading') {
    return (
      <>
        <StatusRow label="API" value="pending" detail="Verifico…" />
        <StatusRow label="Database" value="pending" detail="Verifico…" />
      </>
    )
  }

  if (probe.state === 'failed') {
    return (
      <>
        <StatusRow label="API" value="error" detail={probe.message} />
        <StatusRow label="Database" value="pending" detail="Non verificabile" />
      </>
    )
  }

  const { health } = probe
  const databaseLabels: Record<Health['database'], string> = {
    ok: 'Connesso',
    unreachable: 'Non raggiungibile',
    not_configured: 'DATABASE_URL non configurata',
  }

  return (
    <>
      <StatusRow label="API" value="ok" detail={`FastAPI · ambiente ${health.environment}`} />
      <StatusRow
        label="Database"
        value={health.database === 'ok' ? 'ok' : 'error'}
        detail={databaseLabels[health.database]}
      />
      {health.database !== 'ok' && health.detail ? (
        <p className="mt-1 rounded-card-sm bg-surface-muted px-3 py-2.5 text-xs text-text-secondary">
          {health.detail}
        </p>
      ) : null}
    </>
  )
}

type Value = 'ok' | 'error' | 'pending'

function StatusRow({ label, value, detail }: { label: string; value: Value; detail: string }) {
  return (
    <div className="flex items-center gap-3 rounded-card-sm border border-border-hairline px-3 py-2.5">
      <StatusDot value={value} />
      <span className="text-sm font-bold">{label}</span>
      <span className="ml-auto truncate text-xs text-text-secondary" title={detail}>
        {detail}
      </span>
    </div>
  )
}

function StatusDot({ value }: { value: Value }) {
  const classes: Record<Value, string> = {
    ok: 'bg-success-bg text-success',
    error: 'bg-danger-bg text-danger',
    pending: 'bg-surface-muted text-text-tertiary',
  }
  const labels: Record<Value, string> = { ok: 'ok', error: 'errore', pending: 'in corso' }

  return (
    <span
      className={`grid size-6 shrink-0 place-items-center rounded-pill ${classes[value]}`}
      role="img"
      aria-label={labels[value]}
    >
      {value === 'ok' ? <CheckIcon /> : value === 'error' ? <CloseIcon /> : <Dot />}
    </span>
  )
}

function CheckIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 15 15" fill="none" aria-hidden>
      <path
        d="M3 8.2 6 11.2 12 4.4"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 15 15" fill="none" aria-hidden>
      <path d="M4 4l7 7M11 4l-7 7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  )
}

function Dot() {
  return <span className="size-1.5 rounded-pill bg-current" />
}
