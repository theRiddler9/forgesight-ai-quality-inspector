import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const frontendRoot = resolve(import.meta.dirname, '..');
const repoRoot = resolve(frontendRoot, '../..');
const localPython = resolve(repoRoot, '.tools/python/python.exe');
const python = process.env.FORGESIGHT_PYTHON ?? (existsSync(localPython) ? localPython : 'python');

export class LocalServers {
  readonly runDir = resolve(repoRoot, '.tools/playwright-runs', `${Date.now()}-${process.pid}`);
  readonly dbPath = resolve(this.runDir, 'audit.sqlite3');
  private backend?: ChildProcess;
  private preview?: ChildProcess;
  private output = '';

  async start(): Promise<void> {
    mkdirSync(this.runDir, { recursive: true });
    await this.startBackend();
    this.preview = this.launch(process.execPath, [
      resolve(frontendRoot, 'node_modules/vite/bin/vite.js'),
      'preview', '--configLoader', 'runner', '--host', '127.0.0.1', '--port', '4173', '--strictPort',
    ], frontendRoot);
    await this.waitFor('http://127.0.0.1:4173/api/v1/health', this.preview);
  }

  async startBackend(): Promise<void> {
    this.backend = this.launch(python, ['-m', 'software.backend'], repoRoot, {
      FORGESIGHT_DB_PATH: this.dbPath,
      FORGESIGHT_API_HOST: '127.0.0.1',
      FORGESIGHT_API_PORT: '8000',
    });
    await this.waitFor('http://127.0.0.1:8000/health', this.backend);
  }

  async stopBackend(): Promise<void> {
    const child = this.backend;
    if (!child || child.exitCode !== null || child.signalCode !== null) return;
    const exited = new Promise<void>(resolve => child.once('exit', () => resolve()));
    child.kill();
    await exited;
  }

  private launch(executable: string, args: string[], cwd: string, env: Record<string, string> = {}): ChildProcess {
    const child = spawn(executable, args, { cwd, env: { ...process.env, ...env }, windowsHide: true });
    child.stdout?.on('data', data => { this.output += String(data).slice(-2000); });
    child.stderr?.on('data', data => { this.output += String(data).slice(-2000); });
    return child;
  }

  private async waitFor(url: string, child: ChildProcess): Promise<void> {
    const deadline = Date.now() + 15_000;
    while (Date.now() < deadline) {
      if (child.exitCode !== null) throw new Error(`test server exited: ${this.output.slice(-2000)}`);
      try {
        const response = await fetch(url);
        if (response.ok) return;
      } catch { /* startup is still in progress */ }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error(`test server did not start: ${this.output.slice(-2000)}`);
  }

  async stop(): Promise<void> {
    if (this.preview && this.preview.exitCode === null) this.preview.kill();
    await this.stopBackend();
  }
}
