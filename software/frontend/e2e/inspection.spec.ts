import { expect, test } from '@playwright/test';
import { LocalServers } from './servers';

test.describe.configure({ mode: 'serial' });
const servers = new LocalServers();
test.beforeAll(async () => { await servers.start(); });
test.afterAll(async () => { await servers.stop(); });

test('opens the rendered operator console and connects to the local backend', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Operator inspection console' })).toBeVisible();
  await expect(page.getByText('Connected to local backend')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run clean part' })).toBeEnabled();
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
    if (event.faults.length) await expect(detail).toContainText(event.faults[0]);

    await page.reload();
    await expect(page.getByRole('button', { name: `View inspection ${event.event_id}` })).toBeVisible();
    await page.getByRole('button', { name: `View inspection ${event.event_id}` }).click();
    await expect(detail).toContainText(`ID: ${event.event_id}`);
  });
}
