import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test, type Page, type WebSocketRoute } from '@playwright/test';
import { LocalServers } from './servers';

test.describe.configure({ mode: 'serial' });
const servers = new LocalServers();
test.beforeAll(async () => { await servers.start(); });
test.afterAll(async () => { await servers.stop(); });

async function captureEvidence(page: Page, name: string): Promise<void> {
  if (process.env.FORGESIGHT_CAPTURE_EVIDENCE !== '1') return;
  const directory = resolve(import.meta.dirname, '../../../evidence/recorded-image-slice');
  mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: resolve(directory, `${name}.png`), fullPage: true });
}

test('opens the rendered operator console and connects to the local backend', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Operator inspection console' })).toBeVisible();
  await expect(page.getByText('Connected to local backend')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run clean part' })).toBeEnabled();
});

test('empty history is clear and a failed replay never looks successful', async ({ page }) => {
  await page.goto('/');
  const history = page.getByRole('heading', { name: 'Inspection history' }).locator('..');
  await expect(history).toContainText('No inspections yet');
  const metrics = page.getByRole('heading', { name: 'Result distribution' }).locator('..');
  await expect(metrics.getByText('total', { exact: true }).locator('..')).toContainText('0');

  let release: () => void = () => {};
  await page.route('**/api/v1/inspections/replay', async route => {
    await new Promise<void>(resolve => { release = resolve; });
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'inspection unavailable' }) });
  });
  const request = page.waitForRequest('**/api/v1/inspections/replay');
  await page.getByRole('button', { name: 'Run clean part' }).click();
  await request;
  await expect(page.getByRole('status')).toContainText('Inspection in progress');
  release();
  await expect(page.getByRole('alert')).toContainText('inspection unavailable');
  await expect(page.getByRole('status')).not.toContainText('PASS');
  await expect(history).toContainText('No inspections yet');
});

const scenarios = [
  { name: 'clean_part', result: 'PASS' },
  { name: 'heavy_burr', result: 'FAIL' },
  { name: 'uncertain_burr', result: 'RECHECK' },
  { name: 'missing_hole', result: 'FAIL' },
  { name: 'no_part', result: 'RECHECK' },
  { name: 'capture_fault', result: 'RECHECK' },
] as const;

for (const { name, result } of scenarios) {
  test(`${name} travels through the rendered HMI and persistent history`, async ({ page }) => {
    const label = name.replaceAll('_', ' ');
    await page.goto('/');
    const trigger = page.getByRole('button', { name: `Run ${label}` });
    await expect(trigger).toBeEnabled();
    const replayResponse = page.waitForResponse(response =>
      response.url().endsWith('/api/v1/inspections/replay') && response.request().method() === 'POST',
    );
    await trigger.click();
    const response = await replayResponse;
    expect(response.status()).toBe(200);
    const { event } = await response.json() as { event: {
      event_id: string; result: string; decision_reasons: string[];
      image: { input_uri: string | null }; faults: string[];
    } };
    expect(event.result).toBe(result);
    await expect(page.getByRole('status').getByText(result, { exact: true })).toBeVisible();
    await expect(page.getByRole('status')).toContainText(event.decision_reasons[0]);
    if (['clean_part', 'heavy_burr', 'uncertain_burr', 'capture_fault'].includes(name)) await captureEvidence(page, name);
    await expect(page.getByText('Poka-Yoke geometry')).toBeVisible();
    if (name === 'capture_fault') {
      await expect(page.getByText(/No image captured/)).toBeVisible();
    } else {
      await expect(page.getByRole('img', { name: `Synthetic fixture for ${label}` })).toBeVisible();
    }
    const row = page.locator('table tbody tr').filter({ hasText: label });
    await expect(row).toContainText(result);
    await row.getByRole('button', { name: `View inspection ${event.event_id}` }).click();
    const detail = page.getByRole('heading', { name: 'Inspection detail' }).locator('..');
    await expect(detail).toContainText(`ID: ${event.event_id}`);
    await expect(detail).toContainText(`Decision reason: ${event.decision_reasons.join('; ')}`);
    await expect(detail).toContainText('Detector:');
    await expect(detail).toContainText('Timing:');
    await expect(detail).toContainText('Geometry checks:');
    await expect(detail).toContainText('Simulation: synthetic fixture, scenario-driven detector, mock I/O');
    if (name === 'uncertain_burr') await captureEvidence(page, 'inspection-detail');
    if (event.faults.length) {
      await expect(detail).toContainText(event.faults[0]);
      await expect(page.getByRole('heading', { name: 'System health' }).locator('..')).toContainText(`Current fault: ${event.faults[0]}`);
    }

    await page.reload();
    await expect(page.getByRole('button', { name: `View inspection ${event.event_id}` })).toBeVisible();
    await page.getByRole('button', { name: `View inspection ${event.event_id}` }).click();
    await expect(detail).toContainText(`ID: ${event.event_id}`);
  });
}

test('history filters, metrics, health, and append-only review match stored inspections', async ({ page }) => {
  await page.goto('/');
  const history = page.getByRole('heading', { name: 'Inspection history' }).locator('..');
  const metrics = page.getByRole('heading', { name: 'Result distribution' }).locator('..');
  await expect(history).toContainText('6 records');
  for (const [label, count] of [['total', '6'], ['PASS', '1'], ['FAIL', '2'], ['RECHECK', '3']]) {
    await expect(metrics.getByText(label, { exact: true }).first().locator('..')).toContainText(count);
  }
  await expect(metrics.locator('.recharts-bar-rectangle')).toHaveCount(3);
  const health = page.getByRole('heading', { name: 'System health' }).locator('..');
  await expect(health).toContainText('Backend: connected');
  await expect(health).toContainText('Detector mode: scenario-driven simulation');
  await expect(health).toContainText('I/O mode: mock');
  await expect(health).toContainText('Current fault: unknown; select an inspection');
  await expect(health).toContainText('Amber: on');
  await expect(health).toContainText('Ring light: 0%');
  await captureEvidence(page, 'history-metrics-health');

  await history.getByLabel('Result').selectOption('FAIL');
  await expect(history.locator('tbody tr')).toHaveCount(2);
  await expect(history).toContainText('2 records');
  await history.getByLabel('Result').selectOption('ALL');
  await expect(history.locator('tbody tr')).toHaveCount(6);
  await history.locator('tbody tr').filter({ hasText: 'uncertain burr' }).getByRole('button', { name: /View inspection/ }).click();
  const detail = page.getByRole('heading', { name: 'Inspection detail' }).locator('..');
  await expect(detail).toContainText('RECHECK');
  await detail.getByRole('textbox', { name: 'Reviewer ID' }).fill('demo-operator');
  await detail.getByLabel('Corrected result').selectOption('FAIL');
  await detail.getByRole('textbox', { name: 'Review note' }).fill('Manual burr review');
  await detail.getByRole('button', { name: 'Save review' }).click();
  await expect(detail).toContainText('FAIL by demo-operator (Manual burr review)');
  await expect(detail).toContainText('RECHECK');
  await captureEvidence(page, 'operator-review');
  await page.reload();
  await history.locator('tbody tr').filter({ hasText: 'uncertain burr' }).getByRole('button', { name: /View inspection/ }).click();
  await expect(detail).toContainText('FAIL by demo-operator (Manual burr review)');
  await expect(detail).toContainText('RECHECK');
});

test('history pagination preserves newest-first ordering without duplicates', async ({ page }) => {
  const created: string[] = [];
  for (let index = 0; index < 18; index++) {
    const response = await page.request.post('/api/v1/inspections/replay', { data: { scenario: 'clean_part' } });
    expect(response.ok()).toBeTruthy();
    created.push((await response.json()).event.event_id as string);
  }
  await page.goto('/');
  const history = page.getByRole('heading', { name: 'Inspection history' }).locator('..');
  await expect(history).toContainText('24 records');
  await expect(history.locator('tbody tr')).toHaveCount(20);
  await expect(history.locator('tbody tr').first().getByRole('button', { name: `View inspection ${created.at(-1)}` })).toBeVisible();
  await history.getByRole('button', { name: 'Next' }).click();
  await expect(history).toContainText('Page 2');
  await expect(history.locator('tbody tr')).toHaveCount(4);
  await expect(history.getByRole('button', { name: 'Next' })).toBeDisabled();
  await history.getByRole('button', { name: 'Previous' }).click();
  await expect(history.locator('tbody tr')).toHaveCount(20);
});

test('live WebSocket updates, disconnect safety, missed-event recovery, and idempotency', async ({ page }) => {
  let blocked = false;
  let active: WebSocketRoute | undefined;
  await page.routeWebSocket('**/ws/inspections', route => {
    if (blocked) route.close();
    else { active = route; route.connectToServer(); }
  });
  await page.goto('/');
  await expect(page.getByText('Connected to local backend')).toBeVisible();
  const clean = await page.request.post('/api/v1/inspections/replay', { data: { scenario: 'clean_part' } });
  expect(clean.ok()).toBeTruthy();
  await expect(page.getByRole('status').getByText('PASS', { exact: true })).toBeVisible();
  blocked = true;
  active?.close();
  await expect(page.getByRole('status')).toContainText('Disconnected');
  await expect(page.getByRole('status')).not.toContainText('PASS');
  const missedResponse = await page.request.post('/api/v1/inspections/replay', { data: { scenario: 'heavy_burr' } });
  const missed = (await missedResponse.json()).event as { event_id: string };
  await expect(page.getByRole('button', { name: `View inspection ${missed.event_id}` })).toHaveCount(0);
  blocked = false;
  await expect(page.getByText('Connected to local backend')).toBeVisible();
  await expect(page.getByRole('button', { name: `View inspection ${missed.event_id}` })).toBeVisible();
  const before = await page.request.get('/api/v1/inspections');
  const duplicate = await page.request.post('/api/v1/inspections/replay', { data: { scenario: 'clean_part', event_id: missed.event_id } });
  expect((await duplicate.json()).inserted).toBe(false);
  const after = await page.request.get('/api/v1/inspections');
  expect((await after.json()).total).toBe((await before.json()).total);
  await expect(page.getByRole('button', { name: `View inspection ${missed.event_id}` })).toHaveCount(1);
});

test('backend restart preserves reviews and safe disconnect status', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Run clean part' })).toBeEnabled();
  await page.getByRole('button', { name: 'Run clean part' }).click();
  await expect(page.getByRole('status').getByText('PASS', { exact: true })).toBeVisible();
  await servers.stopBackend();
  await expect(page.getByRole('status')).toContainText('Disconnected');
  await expect(page.getByRole('status')).not.toContainText('PASS');
  await servers.startBackend();
  await expect(page.getByText('Connected to local backend')).toBeVisible();
  const history = page.getByRole('heading', { name: 'Inspection history' }).locator('..');
  await history.getByLabel('Result').selectOption('RECHECK');
  await history.locator('tbody tr').filter({ hasText: 'uncertain burr' }).getByRole('button', { name: /View inspection/ }).click();
  const detail = page.getByRole('heading', { name: 'Inspection detail' }).locator('..');
  await expect(detail).toContainText('FAIL by demo-operator (Manual burr review)');
  await expect(detail).toContainText('RECHECK');
});

test('concurrent requests retain their own committed mock outputs', async ({ page }) => {
  const responses = await Promise.all([
    page.request.post('/api/v1/inspections/replay', { data: { scenario: 'clean_part' } }),
    page.request.post('/api/v1/inspections/replay', { data: { scenario: 'heavy_burr' } }),
  ]);
  const [clean, burr] = await Promise.all(responses.map(response => response.json()));
  expect(clean.event.mock_io_state.green).toBe(true);
  expect(clean.event.result).toBe('PASS');
  expect(burr.event.mock_io_state.red).toBe(true);
  expect(burr.event.result).toBe('FAIL');
  await page.goto('/');
  const history = page.getByRole('heading', { name: 'Inspection history' }).locator('..');
  await expect(history.getByRole('button', { name: `View inspection ${clean.event.event_id}` })).toBeVisible();
  await expect(history.getByRole('button', { name: `View inspection ${burr.event.event_id}` })).toBeVisible();
});

test('operator console fits desktop and narrow touchscreen viewports', async ({ page }) => {
  for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Operator inspection console' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Run clean part' })).toBeEnabled();
    const width = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, window: window.innerWidth }));
    expect(width.document).toBeLessThanOrEqual(width.window);
  }
});

test('replay controls are reachable and usable from the keyboard', async ({ page }) => {
  await page.goto('/');
  const firstScenario = page.getByRole('button', { name: 'Run capture fault' });
  await expect(firstScenario).toBeEnabled();
  await page.keyboard.press('Tab');
  await expect(firstScenario).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('status').getByText('RECHECK', { exact: true })).toBeVisible();
});

test('history controls keep one live WebSocket and fetch current selection', async ({ page }) => {
  let connections = 0;
  let closures = 0;
  let scenarioRequests = 0;
  const historyQueries: string[] = [];
  page.on('websocket', socket => {
    connections += 1;
    socket.on('close', () => { closures += 1; });
  });
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname === '/api/v1/scenarios') scenarioRequests += 1;
    if (url.pathname === '/api/v1/inspections') historyQueries.push(url.search);
  });
  await page.goto('/');
  await expect(page.getByText('Connected to local backend')).toBeVisible();
  expect(connections).toBe(1);
  const history = page.getByRole('heading', { name: 'Inspection history' }).locator('..');
  const filtered = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/v1/inspections' &&
    new URL(response.url()).searchParams.get('result') === 'FAIL',
  );
  await history.getByLabel('Result').selectOption('FAIL');
  const filteredTotal = (await filtered).json().then((body: { total: number }) => body.total);
  await expect(history).toContainText(`${await filteredTotal} records`);
  expect(connections).toBe(1);
  expect(closures).toBe(0);
  expect(scenarioRequests).toBe(1);

  await history.getByLabel('Result').selectOption('ALL');
  const created: string[] = [];
  for (let index = 0; index < 21; index++) {
    const response = await page.request.post('/api/v1/inspections/replay', { data: { scenario: 'clean_part' } });
    created.push((await response.json()).event.event_id as string);
  }
  await expect(history.getByRole('button', { name: `View inspection ${created.at(-1)}` })).toBeVisible();
  await expect(history.getByRole('button', { name: 'Next' })).toBeEnabled();
  const pageTwo = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname === '/api/v1/inspections' && url.searchParams.get('offset') === '20';
  });
  await history.getByRole('button', { name: 'Next' }).click();
  await pageTwo;
  await expect(history).toContainText('Page 2');
  expect(historyQueries.some(query => new URLSearchParams(query).get('offset') === '20')).toBe(true);
  expect(connections).toBe(1);
  expect(closures).toBe(0);
  expect(scenarioRequests).toBe(1);
  const live = await page.request.post('/api/v1/inspections/replay', { data: { scenario: 'heavy_burr' } });
  expect(live.ok()).toBeTruthy();
  await expect(page.getByRole('status').getByText('FAIL', { exact: true })).toBeVisible();
  expect(connections).toBe(1);
});
