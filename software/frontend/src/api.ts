import type { Decision, Health, HistoryResponse, InspectionEvent, Metrics, Review } from './types';

function errorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') return detail.trim() || null;
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const messages = detail.slice(0, 3).map((item: unknown) => {
    if (!item || typeof item !== 'object' || !('msg' in item) || typeof item.msg !== 'string') return null;
    const location = 'loc' in item && Array.isArray(item.loc)
      ? item.loc.filter((part: unknown) => typeof part === 'number' || (typeof part === 'string' && /^[\w-]+$/.test(part))).join('.')
      : '';
    return `${location ? `${location}: ` : ''}${item.msg.slice(0, 200)}`;
  });
  return messages.every((message): message is string => Boolean(message)) ? messages.join('; ') : null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === 'object' && 'detail' in body) {
        message = errorDetail(body.detail) ?? message;
      }
    } catch { /* response may not be JSON */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  scenarios: () => request<string[]>('/api/v1/scenarios'),
  health: () => request<Health>('/api/v1/health'),
  metrics: () => request<Metrics>('/api/v1/metrics/summary'),
  history: (result: Decision | 'ALL', page: number) => {
    const params = new URLSearchParams({ limit: '20', offset: String(page * 20) });
    if (result !== 'ALL') params.set('result', result);
    return request<HistoryResponse>(`/api/v1/inspections?${params}`);
  },
  detail: (id: string) => request<InspectionEvent>(`/api/v1/inspections/${encodeURIComponent(id)}`),
  reviews: (id: string) => request<Review[]>(`/api/v1/inspections/${encodeURIComponent(id)}/reviews`),
  replay: (scenario: string) => request<{ event: InspectionEvent; inserted: boolean }>(
    '/api/v1/inspections/replay',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario }) },
  ),
  review: (id: string, reviewer_id: string, corrected_result: Decision, note: string) => request<Review>(
    `/api/v1/inspections/${encodeURIComponent(id)}/review`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reviewer_id, corrected_result, note }) },
  ),
  fixture: (scenario: string) => `/api/v1/fixtures/${encodeURIComponent(scenario)}`,
};

export function websocketUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/inspections`;
}
