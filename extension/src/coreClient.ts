import * as vscode from "vscode";
import { ChildProcessWithoutNullStreams, spawn } from "child_process";
import * as readline from "readline";
import * as path from "path";
import * as fs from "fs";
import { parseCoreResponse } from "./protocol";

export type CoreResponse<T> =
  | { ok: true; data: T }
  | { ok: false; error: { code: string; message: string } };

export class CoreClient implements vscode.Disposable {
  private process: ChildProcessWithoutNullStreams | undefined;
  private nextId = 1;
  private pending = new Map<
    number,
    { resolve: (value: CoreResponse<unknown>) => void; reject: (error: Error) => void }
  >();
  private readonly output = vscode.window.createOutputChannel("Study Agent");
  private disposed = false;

  constructor(private readonly root: string) { }

  public request<T>(operation: string, payload: Record<string, unknown> = {}): Promise<CoreResponse<T>> {
    this.ensureProcess();

    if (!this.process || this.process.killed) {
      return Promise.resolve({
        ok: false,
        error: {
          code: "CORE_UNAVAILABLE",
          message: "Não foi possível iniciar o processo backend do Study Agent."
        }
      });
    }

    const requestId = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(requestId, {
        resolve: resolve as (value: CoreResponse<unknown>) => void,
        reject
      });

      const message = JSON.stringify({ requestId, operation, payload });
      this.process!.stdin.write(`${message}\n`);
    });
  }

  public dispose(): void {
    if (this.disposed) return;
    this.disposed = true;

    this.failAllPendingRequests({
      code: "CORE_DISPOSED",
      message: "A extensão foi desativada."
    });

    if (this.process && !this.process.killed) {
      this.process.kill();
      this.process = undefined;
    }
    this.output.dispose();
  }

  private ensureProcess(): void {
    if (this.process && !this.process.killed) return;

    // Validação: src folder deve existir
    const srcPath = path.join(this.root, "src");
    if (!fs.existsSync(srcPath)) {
      this.output.appendLine(`[CoreClient Error] src folder não encontrado em: ${this.root}`);
      this.failAllPendingRequests({
        code: "SRC_NOT_FOUND",
        message: `Pasta 'src' não encontrada no workspace: ${this.root}`
      });
      return;
    }

    // Resolução estrita do executável Python (.venv local -> configuração do usuário -> fallback global)
    const venvPythonWin = path.join(this.root, ".venv", "Scripts", "python.exe");
    const venvPythonPosix = path.join(this.root, ".venv", "bin", "python");

    let pythonBinary = vscode.workspace.getConfiguration("studyAgent").get<string>("pythonPath", "").trim();

    if (!pythonBinary || pythonBinary === "python") {
      if (fs.existsSync(venvPythonWin)) {
        pythonBinary = venvPythonWin;
      } else if (fs.existsSync(venvPythonPosix)) {
        pythonBinary = venvPythonPosix;
      } else {
        pythonBinary = "python";
      }
    }

    this.output.appendLine(`[CoreClient] Workspace: ${this.root}`);
    this.output.appendLine(`[CoreClient] Python: ${pythonBinary}`);
    this.output.appendLine(`[CoreClient] PYTHONPATH: ${srcPath}`);

    try {
      this.process = spawn(pythonBinary, ["-m", "study_agent.application"], {
        cwd: this.root,
        env: { ...process.env, PYTHONPATH: srcPath },
        windowsHide: true
      });
    } catch (err) {
      this.output.appendLine(`[CoreClient Error] Falha ao disparar o spawn: ${String(err)}`);
      this.failAllPendingRequests({
        code: "PYTHON_SPAWN_FAILED",
        message: `Falha ao iniciar Python: ${String(err)}`
      });
      return;
    }

    const lines = readline.createInterface({ input: this.process.stdout });
    lines.on("line", line => this.handleLine(line));

    this.process.stderr.on("data", data => {
      const errMessage = data.toString();
      this.output.append(`[Python Stderr]: ${errMessage}`);
    });

    this.process.on("error", error => this.onProcessError(error));
    this.process.on("exit", (code) => this.onProcessExit(code));
    this.process.on("close", (code) => this.onProcessClose(code));
  }

  private failAllPendingRequests(error: { code: string; message: string }): void {
    for (const item of this.pending.values()) {
      item.resolve({
        ok: false,
        error
      });
    }
    this.pending.clear();
  }

  private onProcessError(error: Error): void {
    this.output.appendLine(`[CoreClient Process Error]: ${error.message}`);
    this.failAllPendingRequests({
      code: "CORE_UNAVAILABLE",
      message: `Erro no backend Python: ${error.message}`
    });
    this.process = undefined;
  }

  private onProcessExit(code: number | null): void {
    this.output.appendLine(`[CoreClient Exit]: Processo finalizado com código ${code}`);
    // Don't fail pending here; wait for close event on Windows
    // On Unix, exit usually comes before close
    if (!this.process || this.process.killed) {
      this.failAllPendingRequests({
        code: "CORE_DISCONNECTED",
        message: `O backend Python foi encerrado inesperadamente (código ${code ?? "desconhecido"}).`
      });
    }
  }

  private onProcessClose(code: number | null): void {
    this.output.appendLine(`[CoreClient Close]: Stream encerrado (código ${code})`);
    // This is the definitive event for cleanup on all platforms
    this.failAllPendingRequests({
      code: "CORE_DISCONNECTED",
      message: `O backend Python foi encerrado inesperadamente (código ${code ?? "desconhecido"}).`
    });
    this.process = undefined;
  }

  private handleLine(line: string): void {
    const message = parseCoreResponse(line);
    if (!message) {
      this.output.appendLine(`[CoreClient] Linha malformada ignorada: ${line}`);
      return;
    }

    const item = this.pending.get(message.requestId);
    if (!item) return;

    this.pending.delete(message.requestId);
    item.resolve(message);
  }
}