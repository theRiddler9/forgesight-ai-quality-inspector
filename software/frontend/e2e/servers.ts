import { execFileSync, spawn, type ChildProcess } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { createServer } from 'node:net';
import { resolve } from 'node:path';

const frontendRoot = resolve(import.meta.dirname, '..');
const repoRoot = resolve(frontendRoot, '../..');
const localPython = resolve(repoRoot, '.tools/python/python.exe');
const python = process.env.FORGESIGHT_PYTHON ?? (existsSync(localPython) ? localPython : 'python');

export async function assertPortAvailable(port: number, service: string): Promise<void> {
  const probe = createServer();
  await new Promise<void>((resolve, reject) => {
    probe.once('error', error => {
      if ('code' in error && error.code === 'EADDRINUSE') {
        reject(new Error(`Cannot start ${service}: port ${port} is already in use`));
      } else {
        reject(error);
      }
    });
    probe.listen({ host: '127.0.0.1', port, exclusive: true }, () => {
      probe.close(error => error ? reject(error) : resolve());
    });
  });
}

export class LocalServers {
  readonly runDir = resolve(repoRoot, '.tools/playwright-runs', `${Date.now()}-${process.pid}`);
  readonly dbPath = resolve(this.runDir, 'audit.sqlite3');
  private backend?: ChildProcess;
  private preview?: ChildProcess;
  private output = new Map<ChildProcess, string>();

  async start(): Promise<void> {
    await assertPortAvailable(8000, 'backend');
    await assertPortAvailable(4173, 'frontend preview');
    mkdirSync(this.runDir, { recursive: true });
    if (process.env.FORGESIGHT_TEST_ONNX === '1') {
      execFileSync(python, ['-m', 'software.ml.fixture_model', resolve(this.runDir, 'onnx'), '--bundle'],
        { cwd: repoRoot, windowsHide: true });
    }
    await this.startBackend();
    await this.startPreview();
  }

  private async startPreview(): Promise<void> {
    await assertPortAvailable(4173, 'frontend preview');
    this.preview = this.launch(process.execPath, [
      resolve(frontendRoot, 'node_modules/vite/bin/vite.js'),
      'preview', '--configLoader', 'runner', '--host', '127.0.0.1', '--port', '4173', '--strictPort',
    ], frontendRoot);
    await this.waitFor('http://127.0.0.1:4173/api/v1/health', this.preview);
  }

  async startBackend(): Promise<void> {
    await assertPortAvailable(8000, 'backend');
    this.backend = this.launch(python, ['-m', 'software.backend'], repoRoot, {
      FORGESIGHT_DB_PATH: this.dbPath,
      FORGESIGHT_API_HOST: '127.0.0.1',
      FORGESIGHT_API_PORT: '8000',
      ...(process.env.FORGESIGHT_TEST_ONNX === '1' ? {
        FORGESIGHT_PROFILE_CATALOG: resolve(this.runDir, 'onnx/catalog'),
        FORGESIGHT_MODEL_MANIFEST: resolve(this.runDir, 'onnx/model-manifest.json'),
        FORGESIGHT_MODEL_ROOT: resolve(this.runDir, 'onnx/models'),
      } : {}),
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
    this.output.set(child, '');
    child.stdout?.on('data', data => { this.output.set(child, ((this.output.get(child) ?? '') + String(data)).slice(-2000)); });
    child.stderr?.on('data', data => { this.output.set(child, ((this.output.get(child) ?? '') + String(data)).slice(-2000)); });
    return child;
  }

  private async waitFor(url: string, child: ChildProcess): Promise<void> {
    const deadline = Date.now() + 15_000;
    while (Date.now() < deadline) {
      if (child.exitCode !== null) throw new Error(`test server exited: ${(this.output.get(child) ?? '').slice(-2000)}`);
      try {
        const response = await fetch(url);
        if (response.ok) return;
      } catch { /* startup is still in progress */ }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error(`test server did not start: ${(this.output.get(child) ?? '').slice(-2000)}`);
  }

  async stop(): Promise<void> {
    if (this.preview && this.preview.exitCode === null) this.preview.kill();
    await this.stopBackend();
  }
}
