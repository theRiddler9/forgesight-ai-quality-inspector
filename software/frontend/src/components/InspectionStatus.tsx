import type { InspectionEvent } from '../types';

const palette = {
  PASS: 'border-emerald-400 bg-emerald-400/10 text-emerald-200',
  FAIL: 'border-rose-400 bg-rose-400/10 text-rose-200',
  RECHECK: 'border-amber-400 bg-amber-400/10 text-amber-200',
};

export default function InspectionStatus({ event, connected, busy = false }: { event: InspectionEvent | null; connected: boolean; busy?: boolean }) {
  if (!connected) return <div role="status" className="rounded-2xl border border-slate-500 bg-slate-700/50 p-8 text-center text-2xl font-bold text-slate-100">Disconnected · current result unknown</div>;
  if (busy) return <div role="status" className="rounded-2xl border border-sky-500/70 bg-sky-500/10 p-8 text-center text-2xl font-bold text-sky-100">Inspection in progress · result pending</div>;
  if (!event) return <div role="status" className="rounded-2xl border border-sky-500/70 bg-sky-500/10 p-8 text-center text-2xl font-bold text-sky-100">Ready for a replay inspection</div>;
  return <div role="status" className={`rounded-2xl border-2 p-7 text-center ${palette[event.result]}`}>
    <div className="text-xs font-bold uppercase tracking-[0.3em]">Latest simulated inspection</div>
    <div className="mt-2 text-6xl font-black tracking-tight">{event.result}</div>
    <div className="mt-2 text-lg">{event.decision_reasons.join(' · ')}</div>
    <div className="mt-3 text-sm opacity-85">{new Date(event.timestamp).toLocaleString()} · {event.latency_ms.total.toFixed(1)} ms local software timing</div>
  </div>;
}
