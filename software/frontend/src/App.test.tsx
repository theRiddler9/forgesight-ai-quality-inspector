import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import App from './App';

const event = {
  event_id: '7b4d47c8-083c-4baa-b86c-7a5b56cb463a', timestamp: '2026-10-17T08:00:00Z',
  scenario: 'clean_part', result: 'PASS', decision_reasons: ['clean'], defects: [], faults: [],
  poka_yoke: { part_present: true, position_ok: true, orientation_ok: null, hole_present: true, size_in_range: true, reasons: [] },
  latency_ms: { capture: 1, preprocess: 0, poka_yoke: 2, inference: 1, postprocess: 0, decision: 1, io: 0, total: 5 },
  model: { name: 'scenario-driven-burr-simulator', version: '1.0.0', runtime: 'mock', artifact_sha256: null },
  simulation: { synthetic_fixture: true, scenario_driven_detector: true, mock_io: true },
  image: { input_uri: 'fixtures/images/clean.png', sha256: '0'.repeat(64), evidence_uri: null, source_id: 'synthetic-recorded-v1' },
  configuration_version: 'virtual-profile-v1', mock_io_state: { green: true, red: false, amber: false, buzzer: false, ring_light_pwm: 100 },
};

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  close = vi.fn();
  constructor() { FakeSocket.instances.push(this); }
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeSocket);
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    if (url.includes('/scenarios')) return { ok: true, json: async () => ['clean_part', 'heavy_burr'] };
    if (url.includes('/metrics/summary')) return { ok: true, json: async () => ({ total: 1, PASS: 1, FAIL: 0, RECHECK: 0, average_latency_ms: 5 }) };
    if (url.includes('/api/v1/health')) return { ok: true, json: async () => ({ status: 'ok', detector: 'scenario-driven simulation', frame_source: 'synthetic recorded replay', io: 'mock', mock_io_state: event.mock_io_state }) };
    if (url.includes('/reviews')) return { ok: true, json: async () => [] };
    if (url.includes('/replay') && options?.method === 'POST') return { ok: true, json: async () => ({ event, inserted: true }) };
    if (url.includes('/inspections?')) return { ok: true, json: async () => ({ items: [event], total: 1, limit: 20, offset: 0 }) };
    return { ok: true, json: async () => event };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

test('shows simulation boundaries and result after connection and replay', async () => {
  render(<App />);
  expect(within(screen.getByRole('status')).getByText(/Disconnected/)).toBeInTheDocument();
  act(() => FakeSocket.instances[0].onopen?.());
  await screen.findByRole('button', { name: /Run clean part/i });
  fireEvent.click(screen.getByRole('button', { name: /Run clean part/i }));
  await waitFor(() => expect(within(screen.getByRole('status')).getByText('PASS', { exact: true })).toBeInTheDocument());
  expect(screen.getByText(/Scenario-driven detector/)).toBeInTheDocument();
  expect(screen.getByText(/Synthetic fixtures/)).toBeInTheDocument();
  expect(screen.getByText(/Mock I\/O/)).toBeInTheDocument();
});

test('disconnect hides current PASS and reconnect reloads history', async () => {
  render(<App />);
  const socket = FakeSocket.instances[0];
  act(() => socket.onopen?.());
  act(() => socket.onmessage?.({ data: JSON.stringify({ event: 'inspection_event', data: event }) }));
  await waitFor(() => expect(within(screen.getByRole('status')).getByText('PASS', { exact: true })).toBeInTheDocument());
  act(() => socket.onclose?.());
  await waitFor(() => expect(within(screen.getByRole('status')).getByText(/Disconnected/)).toBeInTheDocument());
  expect(within(screen.getByRole('status')).queryByText('PASS', { exact: true })).not.toBeInTheDocument();
  const callsBefore = vi.mocked(fetch).mock.calls.length;
  await waitFor(() => expect(FakeSocket.instances.length).toBeGreaterThan(1));
  act(() => FakeSocket.instances.at(-1)?.onopen?.());
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(callsBefore));
});

test.each([
  ['FAIL', 'heavy_burr'],
  ['RECHECK', 'uncertain_burr'],
  ['RECHECK', 'capture_fault'],
] as const)('live %s event from %s is visible, then cleared on disconnect', async (result, scenario) => {
  render(<App />);
  const socket = FakeSocket.instances[0];
  act(() => socket.onopen?.());
  act(() => socket.onmessage?.({ data: JSON.stringify({ event: 'inspection_event', data: { ...event, result, scenario } }) }));
  await waitFor(() => expect(within(screen.getByRole('status')).getByText(result, { exact: true })).toBeInTheDocument());
  act(() => socket.onclose?.());
  expect(within(screen.getByRole('status')).getByText(/Disconnected/)).toBeInTheDocument();
  expect(within(screen.getByRole('status')).queryByText(result, { exact: true })).not.toBeInTheDocument();
});

test('history selection shows decision details', async () => {
  render(<App />);
  act(() => FakeSocket.instances[0].onopen?.());
  await screen.findByRole('button', { name: /View inspection/i });
  fireEvent.click(screen.getByRole('button', { name: /View inspection/i }));
  expect(await screen.findByText(/Decision reason/)).toBeInTheDocument();
  expect(screen.getByText(/virtual-profile-v1/)).toBeInTheDocument();
});

test('connected health does not claim no fault before a current inspection exists', async () => {
  render(<App />);
  act(() => FakeSocket.instances[0].onopen?.());
  const health = screen.getByRole('heading', { name: 'System health' }).parentElement;
  await waitFor(() => expect(health).toHaveTextContent('Current fault: unknown; select an inspection'));
});

test('ONNX adapter fixture event is not presented as a validated burr detector', async () => {
  render(<App />);
  act(() => FakeSocket.instances[0].onopen?.());
  const fixture = { ...event, scenario: 'local_image', result: 'RECHECK',
    model: { name: 'adapter-test-constant', version: '0.0.1', runtime: 'onnx', artifact_sha256: 'a'.repeat(64), purpose: 'adapter_test_fixture' },
    simulation: { synthetic_fixture: false, scenario_driven_detector: false, mock_io: true, test_model: true },
    defects: [{ type: 'burr', confidence: 0.9, bbox_normalized: [0.3, 0.3, 0.2, 0.2] }],
    image: { ...event.image, input_uri: 'local-image:sha256:abc', source_id: 'local-upload' } };
  act(() => FakeSocket.instances[0].onmessage?.({ data: JSON.stringify({ event: 'inspection_event', data: fixture }) }));
  expect(await screen.findByText(/ONNX adapter test fixture/i)).toBeInTheDocument();
  expect(screen.getByText(/No stored preview for local image/i)).toBeInTheDocument();
});
