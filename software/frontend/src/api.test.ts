import { afterEach, expect, test, vi } from 'vitest';
import { api } from './api';

afterEach(() => vi.unstubAllGlobals());

async function failedRequest(body: unknown, status = 422): Promise<string> {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status, json: async () => body })));
  try {
    await api.scenarios();
    throw new Error('request unexpectedly succeeded');
  } catch (error) {
    return (error as Error).message;
  }
}

test('keeps ordinary string API errors readable', async () => {
  expect(await failedRequest({ detail: 'inspection unavailable' }, 503)).toBe('inspection unavailable');
});

test('formats FastAPI validation errors without object coercion', async () => {
  expect(await failedRequest({ detail: [
    { loc: ['body', 'scenario'], msg: 'Field required', type: 'missing' },
    { loc: ['query', 'version'], msg: 'Invalid version', type: 'value_error' },
  ] })).toBe('body.scenario: Field required; query.version: Invalid version');
});

test.each([{}, { detail: { private: 'object' } }, { detail: [null, {}] }])(
  'falls back to status for missing or unexpected detail %#', async body => {
    expect(await failedRequest(body)).toBe('Request failed (422)');
  },
);

test('falls back to status when error response is not JSON', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 502, json: async () => { throw new SyntaxError('invalid JSON'); } })));
  await expect(api.scenarios()).rejects.toThrow('Request failed (502)');
});
