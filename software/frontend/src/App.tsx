import { useCallback, useEffect, useState } from 'react';
import { Bar, BarChart, Tooltip, XAxis, YAxis } from 'recharts';
import { api, websocketUrl } from './api';
import InspectionStatus from './components/InspectionStatus';
import type { Decision, Health, HistoryResponse, InspectionEvent, Metrics, Review } from './types';

const scenarioLabel = (name: string) => name.replaceAll('_', ' ');
const timestamp = (value: string) => new Date(value).toLocaleString();
const checkText = (value: boolean | null) => value === null ? 'Not evaluated' : value ? 'Pass' : 'Fail';
const STATUS_COLORS: Record<Decision, string> = { PASS: 'text-emerald-300', FAIL: 'text-rose-300', RECHECK: 'text-amber-300' };
const detectorMode = (event: InspectionEvent) => event.model.purpose === 'adapter_test_fixture'
  ? 'ONNX adapter test fixture · no validated defect judgment'
  : event.model.purpose === 'trained_unverified' ? 'Unverified trained model · no validated defect judgment'
  : event.model.purpose === 'trained_validated' ? 'Trained ONNX model · validate against approved evidence'
  : 'Scenario-driven detector · simulated';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="rounded-2xl border border-slate-700 bg-slate-900/85 p-5 shadow-xl shadow-black/10">
    <h2 className="mb-4 text-lg font-bold tracking-wide text-slate-100">{title}</h2>{children}
  </section>;
}

export default function App() {
  const [connected, setConnected] = useState(false);
  const [current, setCurrent] = useState<InspectionEvent | null>(null);
  const [history, setHistory] = useState<HistoryResponse>({ items: [], total: 0, limit: 20, offset: 0 });
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [scenarios, setScenarios] = useState<string[]>([]);
  const [filter, setFilter] = useState<Decision | 'ALL'>('ALL');
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<InspectionEvent | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [reviewer, setReviewer] = useState('');
  const [reviewResult, setReviewResult] = useState<Decision>('FAIL');
  const [reviewNote, setReviewNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshHistory = useCallback(async () => setHistory(await api.history(filter, page)), [filter, page]);
  const refreshSummary = useCallback(async () => {
    const [summary, status] = await Promise.all([api.metrics(), api.health()]);
    setMetrics(summary); setHealth(status);
  }, []);

  useEffect(() => {
    let active = true;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | undefined;
    const connect = () => {
      if (!active) return;
      socket = new WebSocket(websocketUrl());
      socket.onopen = () => {
        if (!active) return;
        setConnected(true);
        setError(null);
        void Promise.all([refreshHistory(), refreshSummary()]).catch((err: Error) => setError(err.message));
      };
      socket.onmessage = message => {
        try {
          const envelope = JSON.parse(message.data) as { event: string; data: InspectionEvent };
          if (envelope.event !== 'inspection_event' || !active) return;
          setCurrent(envelope.data);
          void Promise.all([refreshHistory(), refreshSummary()]).catch((err: Error) => setError(err.message));
        } catch { setError('Invalid live event received'); }
      };
      socket.onclose = () => {
        if (!active) return;
        setConnected(false);
        setCurrent(null); // an old PASS must never look live
        retry = setTimeout(connect, 600);
      };
      socket.onerror = () => socket?.close();
    };
    void api.scenarios().then(setScenarios).catch((err: Error) => setError(err.message));
    void Promise.all([refreshHistory(), refreshSummary()]).catch((err: Error) => setError(err.message));
    connect();
    return () => { active = false; if (retry) clearTimeout(retry); socket?.close(); };
  }, [refreshHistory, refreshSummary]);

  async function runScenario(name: string) {
    setBusy(true); setError(null);
    try {
      const response = await api.replay(name);
      setCurrent(response.event);
      await Promise.all([refreshHistory(), refreshSummary()]);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function viewInspection(id: string) {
    try {
      const [detail, reviewItems] = await Promise.all([api.detail(id), api.reviews(id)]);
      setSelected(detail); setReviews(reviewItems); setError(null);
    } catch (err) { setError((err as Error).message); }
  }

  async function submitReview() {
    if (!selected) return;
    try {
      await api.review(selected.event_id, reviewer.trim(), reviewResult, reviewNote.trim());
      setReviews(await api.reviews(selected.event_id));
      setReviewNote(''); setError(null);
    } catch (err) { setError((err as Error).message); }
  }

  const chartData = metrics ? (['PASS', 'FAIL', 'RECHECK'] as Decision[]).map(name => ({ name, count: metrics[name] })) : [];
  return <main className="mx-auto max-w-[1500px] px-4 py-5 md:px-7">
    <header className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-slate-700 pb-5">
      <div><div className="text-xs font-semibold uppercase tracking-[0.35em] text-cyan-300">ForgeSight · Stage 2 virtual prototype</div><h1 className="mt-1 text-3xl font-black tracking-tight md:text-4xl">Operator inspection console</h1></div>
      <div className={`rounded-full border px-4 py-2 text-sm font-bold ${connected ? 'border-emerald-400 bg-emerald-400/10 text-emerald-200' : 'border-slate-500 bg-slate-700 text-slate-100'}`} aria-live="polite">{connected ? '● Connected to local backend' : '● Disconnected · reconnecting'}</div>
    </header>

    <div className="mb-5 grid gap-2 sm:grid-cols-3">
      <div className="rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-4 py-3 text-sm font-semibold text-cyan-100">{current && !current.simulation.synthetic_fixture ? 'Local image · source hash recorded' : 'Synthetic fixtures · no factory images'}</div>
      <div className="rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-4 py-3 text-sm font-semibold text-cyan-100">{current ? detectorMode(current) : 'Scenario-driven detector · no trained model'}</div>
      <div className="rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-4 py-3 text-sm font-semibold text-cyan-100">Mock I/O · no physical indicators</div>
    </div>
    {error && <div role="alert" className="mb-5 rounded-xl border border-rose-400 bg-rose-400/10 p-4 text-rose-100">{error}</div>}

    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(340px,1fr)]">
      <div className="space-y-5">
        <InspectionStatus event={current} connected={connected} busy={busy} />
        <Section title="Recorded inspection replay">
          <p className="mb-4 text-sm text-slate-300">Run one deterministic local scenario. Geometry is checked from pixels; burr confidence comes from scenario metadata.</p>
          <div className="flex flex-wrap gap-2">{scenarios.map(name => <button key={name} disabled={!connected || busy} onClick={() => void runScenario(name)} className="min-h-12 rounded-xl border border-sky-500 bg-sky-600/20 px-4 py-2 font-semibold capitalize text-sky-100 hover:bg-sky-600/40">Run {scenarioLabel(name)}</button>)}</div>
        </Section>
        <Section title="Latest frame and checks">
          {connected && current ? <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(230px,1fr)]">
            <div className="flex min-h-56 items-center justify-center overflow-hidden rounded-xl bg-slate-950">
              {!current.simulation.synthetic_fixture ? <span className="p-5 text-center text-slate-300">No stored preview for local image · inspect source hash in detail</span> : current.scenario === 'capture_fault' ? <span className="p-5 text-center text-amber-200">No image captured · simulated camera fault</span> : <img className="max-h-72 w-full object-contain" src={api.fixture(current.scenario)} alt={`Synthetic fixture for ${scenarioLabel(current.scenario)}`} />}
            </div>
            <div className="space-y-2 text-sm">
              <div className="font-semibold text-slate-200">Poka-Yoke geometry</div>
              {Object.entries(current.poka_yoke).filter(([key]) => key !== 'reasons').map(([key, value]) => <div key={key} className="flex justify-between gap-3 border-b border-slate-700 py-1"><span className="capitalize text-slate-400">{key.replaceAll('_', ' ')}</span><span>{checkText(value as boolean | null)}</span></div>)}
              <div className="pt-2 text-slate-300">Detector: {current.defects.length ? `${current.defects[0].type} (${(current.defects[0].confidence * 100).toFixed(0)}% ${current.simulation.scenario_driven_detector ? 'simulated confidence' : 'ONNX output confidence'})` : 'No detector output'}</div>
            </div>
          </div> : <p className="text-slate-400">{connected ? 'Run a scenario to see its recorded frame.' : 'Current frame unavailable while disconnected.'}</p>}
        </Section>
        <Section title="Inspection history">
          <div className="mb-4 flex items-center gap-3"><label htmlFor="result-filter" className="text-sm text-slate-300">Result</label><select id="result-filter" value={filter} onChange={e => { setFilter(e.target.value as Decision | 'ALL'); setPage(0); }} className="min-h-11 rounded-lg border border-slate-600 bg-slate-800 px-3"><option>ALL</option><option>PASS</option><option>FAIL</option><option>RECHECK</option></select><span className="ml-auto text-sm text-slate-400">{history.total} records</span></div>
          <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b border-slate-600 text-slate-400"><tr><th className="pb-2">Time</th><th className="pb-2">Result</th><th className="pb-2">Scenario</th><th className="pb-2">Detail</th></tr></thead><tbody>{history.items.map(item => <tr key={item.event_id} className="border-b border-slate-800"><td className="py-3 pr-3 whitespace-nowrap">{timestamp(item.timestamp)}</td><td className={`pr-3 font-bold ${STATUS_COLORS[item.result]}`}>{item.result}</td><td className="pr-3 capitalize">{scenarioLabel(item.scenario)}</td><td><button onClick={() => void viewInspection(item.event_id)} className="min-h-11 rounded-lg px-3 font-semibold text-cyan-300 hover:bg-slate-800" aria-label={`View inspection ${item.event_id}`}>View</button></td></tr>)}{history.items.length === 0 && <tr><td colSpan={4} className="py-6 text-center text-slate-400">No inspections yet</td></tr>}</tbody></table></div>
          <div className="mt-4 flex items-center justify-end gap-3"><button disabled={page === 0} onClick={() => setPage(page - 1)} className="min-h-11 rounded-lg border border-slate-600 px-3">Previous</button><span className="text-sm">Page {page + 1}</span><button disabled={(page + 1) * 20 >= history.total} onClick={() => setPage(page + 1)} className="min-h-11 rounded-lg border border-slate-600 px-3">Next</button></div>
        </Section>
      </div>

      <div className="space-y-5">
        <Section title="System health"><div className="grid gap-2 text-sm"><div>Backend: <strong>{connected ? 'connected' : 'disconnected / unknown'}</strong></div><div>Frame source: <strong>{connected ? health?.frame_source ?? 'unknown' : 'unknown'}</strong></div><div>Detector mode: <strong>{connected ? health?.detector ?? 'unknown' : 'unknown'}</strong></div><div>I/O mode: <strong>{connected ? health?.io ?? 'unknown' : 'unknown'}</strong></div><div>Current fault: <strong>{!connected ? 'connection unavailable' : !current ? 'unknown; select an inspection' : current.faults.join(', ') || 'none reported'}</strong></div><div>Mock outputs: <strong>{connected && health ? `Green: ${health.mock_io_state.green ? 'on' : 'off'} · Red: ${health.mock_io_state.red ? 'on' : 'off'} · Amber: ${health.mock_io_state.amber ? 'on' : 'off'} · Buzzer: ${health.mock_io_state.buzzer ? 'on' : 'off'} · Ring light: ${health.mock_io_state.ring_light_pwm}%` : 'unknown while disconnected'}</strong></div></div></Section>
        <Section title="Result distribution"><div className="grid grid-cols-4 gap-2 text-center">{(['total', 'PASS', 'FAIL', 'RECHECK'] as const).map(key => <div key={key} className="rounded-lg bg-slate-800 p-3"><div className="text-2xl font-black">{metrics?.[key] ?? '—'}</div><div className="text-xs text-slate-400">{key}</div></div>)}</div><div className="mt-3 overflow-x-auto"><BarChart width={330} height={145} data={chartData}><XAxis dataKey="name" stroke="#94a3b8" fontSize={11} /><YAxis stroke="#94a3b8" allowDecimals={false} fontSize={11} /><Tooltip /><Bar dataKey="count" fill="#38bdf8" radius={[4, 4, 0, 0]} /></BarChart></div><p className="text-sm text-slate-400">Average local software timing: {metrics?.average_latency_ms?.toFixed(1) ?? '—'} ms. This is not Orange Pi latency.</p></Section>
        <Section title="Inspection detail">
          {selected ? <div className="space-y-3 text-sm">
            <div className="flex justify-between gap-3"><strong className={STATUS_COLORS[selected.result]}>{selected.result}</strong><span>{timestamp(selected.timestamp)}</span></div>
            <div className="break-all text-xs text-slate-400">ID: {selected.event_id}</div>
            <div><strong>Decision reason:</strong> {selected.decision_reasons.join('; ')}</div>
            <div><strong>Geometry checks:</strong><ul className="ml-5 list-disc">{Object.entries(selected.poka_yoke).filter(([key]) => key !== 'reasons').map(([key, value]) => <li key={key}>{key.replaceAll('_', ' ')}: {checkText(value as boolean | null)}</li>)}</ul>{selected.poka_yoke.reasons.length > 0 && <div>Geometry reasons: {selected.poka_yoke.reasons.join('; ')}</div>}</div>
            <div><strong>Image reference:</strong> {selected.image.input_uri} · SHA-256 {selected.image.sha256 ?? 'unavailable'}</div>
            <div><strong>Detector:</strong> {selected.model.name} ({selected.model.runtime}); confidence {selected.defects[0]?.confidence?.toFixed(2) ?? 'none'}</div>
            <div><strong>Detection mode:</strong> {detectorMode(selected)}</div>
            <div><strong>Simulation:</strong> {[selected.simulation.synthetic_fixture && 'synthetic fixture', selected.simulation.scenario_driven_detector && 'scenario-driven detector', selected.simulation.test_model && 'test-only ONNX graph', selected.simulation.mock_io && 'mock I/O'].filter(Boolean).join(', ')}</div>
            <div><strong>Faults:</strong> {selected.faults.join(', ') || 'none'}</div>
            <div><strong>Configuration:</strong> {selected.configuration_version}</div>
            <div><strong>Timing:</strong> {Object.entries(selected.latency_ms).map(([key, value]) => `${key} ${value.toFixed(1)} ms`).join(' · ')}</div>
            <div><strong>Reviews:</strong> {reviews.length ? reviews.map(r => `${r.corrected_result} by ${r.reviewer_id} (${r.note})`).join('; ') : 'none'}</div>
            <div className="border-t border-slate-700 pt-3"><div className="mb-2 font-semibold">Append operator review</div><div className="grid gap-2"><input aria-label="Reviewer ID" value={reviewer} onChange={e => setReviewer(e.target.value)} maxLength={80} placeholder="Reviewer ID" className="min-h-11 rounded-lg border border-slate-600 bg-slate-800 px-3" /><select aria-label="Corrected result" value={reviewResult} onChange={e => setReviewResult(e.target.value as Decision)} className="min-h-11 rounded-lg border border-slate-600 bg-slate-800 px-3"><option>PASS</option><option>FAIL</option><option>RECHECK</option></select><textarea aria-label="Review note" value={reviewNote} onChange={e => setReviewNote(e.target.value)} maxLength={1000} placeholder="Reason for correction" className="rounded-lg border border-slate-600 bg-slate-800 p-3" /><button disabled={!connected || !reviewer.trim() || !reviewNote.trim()} onClick={() => void submitReview()} className="min-h-11 rounded-lg bg-cyan-600 px-3 font-bold">Save review</button></div></div>
          </div> : <p className="text-slate-400">Select a history row to inspect the full event and review trail.</p>}
        </Section>
      </div>
    </div>
    <footer className="mt-7 border-t border-slate-800 pt-4 text-xs text-slate-500">Stage 2 virtual validation only. Recorded replay uses synthetic fixtures and simulated burr decisions. ONNX events identify their model provenance. No physical camera, GPIO, isolation verification, or Orange Pi benchmark is connected.</footer>
  </main>;
}
