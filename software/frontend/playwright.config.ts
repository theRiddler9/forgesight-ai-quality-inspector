import { existsSync } from 'node:fs';
import { defineConfig } from '@playwright/test';

const installedBrowser = [
  process.env.FORGESIGHT_BROWSER,
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
].find((candidate): candidate is string => Boolean(candidate && existsSync(candidate)));

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    browserName: 'chromium',
    launchOptions: installedBrowser ? { executablePath: installedBrowser } : {},
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  outputDir: './test-results',
});
