import * as vscode from "vscode";
import { CoreClient, CoreResponse } from "./coreClient";

type Dashboard = { firstLessonId?: string | null; resumeSessionId?: string | null; resumeLessonId?: string | null };
type Exercise = { id: string; subject: string; topic: string; question: string; expectedAnswer: string; explanation: string; professionalContext: string; exerciseType: string; difficulty: string; options: string[]; knowledgeNodeId?: string | null };
type ExerciseResponse = { sessionId: string; exercise: Exercise };

/**
 * Get the workspace root folder, or undefined if no folder is open.
 * Uses only vscode.workspace.workspaceFolders, never workspaceFile or process.cwd().
 */
function getWorkspaceRoot(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  const paths = folders?.map(folder => folder.uri.fsPath) ?? [];

  console.log("[Study Agent] workspaceFolders:", folders);
  console.log("[Study Agent] workspace paths:", paths);
  console.log("[Study Agent] workspace resolution:", paths[0] ?? "<none>");

  return paths[0];
}

export function activate(context: vscode.ExtensionContext): void {
  const root = getWorkspaceRoot();
  console.log("[Study Agent] workspace resolution (activate):", root ?? "<none>");
  console.log("[Study Agent] activate()", {
    extensionPath: context.extensionUri.fsPath,
    entryPoint: context.asAbsolutePath("out/extension.js"),
    workspaceRoot: root ?? "<none>"
  });

  const view = new StudyAgentView(root);
  const workspaceChanged = vscode.workspace.onDidChangeWorkspaceFolders(() => {
    console.log("[Study Agent] workspace folders changed");
    view.refreshWorkspace();
  });

  context.subscriptions.push(
    view,
    workspaceChanged,
    vscode.window.registerWebviewViewProvider("studyAgent.sidebar", view),
    vscode.commands.registerCommand("studyAgent.openDashboard", () => view.show("dashboard")),
    vscode.commands.registerCommand("studyAgent.startStudy", () => view.show("dashboard")),
    vscode.commands.registerCommand("studyAgent.askTutor", () => view.show("tutor")),
    vscode.commands.registerCommand("studyAgent.showReviews", () => view.show("reviews")),
    vscode.commands.registerCommand("studyAgent.openCurriculum", () => view.show("curriculum"))
  );
}

class StudyAgentView implements vscode.WebviewViewProvider, vscode.Disposable {
  private view: vscode.WebviewView | undefined;
  private mode = "dashboard";
  private sessionId = "";
  private exercise: Exercise | undefined;
  private client: CoreClient | undefined;
  private clientRoot: string | undefined;

  constructor(initialRoot?: string) {
    this.clientRoot = initialRoot;
  }

  show(mode: string): void {
    this.mode = mode;
    void this.render();
  }

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    console.log("[Study Agent] resolveWebviewView", {
      hasWorkspace: Boolean(vscode.workspace.workspaceFolders?.length)
    });

    view.webview.options = {
      enableScripts: true
    };

    view.webview.onDidReceiveMessage(
      message => void this.handle(message)
    );

    void this.render();
  }

  refreshWorkspace(): void {
    void this.render();
  }

  dispose(): void {
    this.client?.dispose();
    this.client = undefined;
    this.view = undefined;
  }

  private syncClient(root: string | undefined): void {
    if (root === this.clientRoot && (root === undefined || this.client)) return;

    if (this.client) {
      console.log("[Study Agent] disposing CoreClient for workspace change", {
        previousRoot: this.clientRoot,
        nextRoot: root ?? "<none>"
      });
      this.client.dispose();
    }

    this.client = undefined;
    this.clientRoot = root;

    if (root) {
      console.log("[Study Agent] creating CoreClient", { workspaceRoot: root });
      this.client = new CoreClient(root);
    }
  }

  private async render(): Promise<void> {
    if (!this.view) return;

    const root = getWorkspaceRoot();
    console.log("[Study Agent] workspace resolution (render):", root ?? "<none>");
    this.syncClient(root);
    const client = this.client;

    if (!client) {
      this.view.webview.html = render(this.view.webview, "Study Agent", {
        ok: false,
        error: {
          code: "WORKSPACE_REQUIRED",
          message: "Abra a pasta do seu projeto Study Agent no VS Code para iniciar os estudos."
        }
      });
      return;
    }

    if (this.mode === "exercise" && this.exercise) {
      this.view.webview.html = render(this.view.webview, "Exercise", {
        ok: true,
        data: { type: "exercise", exercise: this.exercise }
      });
      return;
    }

    const operation = this.mode === "curriculum" ? "curriculum" : this.mode === "reviews" ? "reviews" : "dashboard";

    this.view.webview.html = render(this.view.webview, operation, { ok: true, data: { type: "loading" } });

    try {
      const response = await client.request(operation);
      this.view.webview.html = render(this.view.webview, this.mode, response);
    } catch (err) {
      this.view.webview.html = render(this.view.webview, "Error", {
        ok: false,
        error: { code: "CORE_ERROR", message: String(err) }
      });
    }
  }

  private async handle(message: { command: string; answer?: string; question?: string }): Promise<void> {
    const client = this.client;
    if (!client || !this.view) return;

    if (message.command === "refresh") return this.render();

    if (message.command === "start") {
      const dashboard = await client.request<Dashboard>("dashboard");
      if (!dashboard.ok || !dashboard.data.firstLessonId) return this.showError(dashboard);

      const lesson = await client.request<{ sessionId: string; state: string; content: string }>(
        "startLesson",
        {
          lessonId: dashboard.data.resumeLessonId || dashboard.data.firstLessonId,
          sessionId: dashboard.data.resumeSessionId || undefined
        }
      );

      if (!lesson.ok) return this.showError(lesson);

      this.sessionId = lesson.data.sessionId;
      this.view.webview.html = render(this.view.webview, "Lesson", lesson);
      return;
    }

    if (message.command === "practice") {
      const response = await client.request<ExerciseResponse>("startExercise", { sessionId: this.sessionId, topic: "" });
      if (!response.ok) return this.showError(response);

      this.sessionId = response.data.sessionId;
      this.exercise = response.data.exercise;
      this.mode = "exercise";
      return this.render();
    }

    if (message.command === "submit" && this.exercise) {
      this.view.webview.postMessage({ type: "submissionState", state: "loading" });
      const response = await client.request("submitAnswer", {
        ...this.exercise,
        exerciseId: this.exercise.id,
        answer: message.answer ?? ""
      });

      if (!response.ok) return this.showError(response);

      this.view.webview.html = render(this.view.webview, "Feedback", response);
      return;
    }

    if (message.command === "next") {
      const response = await client.request<ExerciseResponse>("startExercise", { sessionId: this.sessionId, topic: this.exercise?.topic ?? "" });
      if (!response.ok) return this.showError(response);

      this.exercise = response.data.exercise;
      this.mode = "exercise";
      return this.render();
    }

    if (message.command === "tutor" && message.question) {
      const response = await client.request("askTutor", { sessionId: this.sessionId, question: message.question });
      if (!response.ok) return this.showError(response);

      this.view.webview.html = render(this.view.webview, "Tutor", response);
    }
  }

  private showError(response: CoreResponse<unknown>): void {
    if (!response.ok && this.view) {
      this.view.webview.html = render(this.view.webview, "Error", response);
    }
  }
}

function render(webview: vscode.Webview, title: string, response: CoreResponse<unknown>): string {
  const nonce = Math.random().toString(36).slice(2);
  const data = response.ok
    ? JSON.stringify(response.data)
    : JSON.stringify({ error: response.error.message, code: response.error.code });
  const csp = `default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';`;

  return `<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="${csp}"><style>${styles}</style></head><body><header><b>SA</b><div><strong>Study Agent</strong><small>${esc(title)}</small></div><button id="refresh" title="Refresh">Refresh</button></header><main id="app"></main><script nonce="${nonce}">const vscode=acquireVsCodeApi(),data=${data},root=document.getElementById('app'),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]||c)),post=(command,payload={})=>vscode.postMessage({command,...payload});if(data.error){root.innerHTML='<section class="error"><b>'+esc(data.code)+'</b><p>'+esc(data.error)+'</p></section>'}else if(data.type==='loading'){root.innerHTML='<p class="loading">Loading...</p>'}else if(data.dailyGoal){root.innerHTML='<section class="hero"><small>TODAY</small><h1>Make today count.</h1><strong class="score">'+data.dailyGoal.completed+' / '+data.dailyGoal.target+'</strong><p>exercises completed</p><div class="bar"><i style="width:'+Math.min(100,data.dailyGoal.completed/data.dailyGoal.target*100)+'%"></i></div></section><section class="grid"><article><small>REVIEWS</small><b>'+data.reviewCount+'</b><span>pending now</span></article><article><small>NEXT FOCUS</small><b>'+(data.recommendation?esc(data.recommendation.topic):'Start a topic')+'</b><span>'+(data.recommendation?esc(data.recommendation.reason):'Workspace ready')+'</span></article></section><button class="primary" id="start">Start studying</button>'}else if(data.type==='exercise'){const x=data.exercise;root.innerHTML='<section class="hero"><small>EXERCISE</small><h1>'+esc(x.subject)+' &rarr; '+esc(x.topic)+'</h1><span class="pill">'+esc(x.difficulty)+'</span><p class="context">'+esc(x.professionalContext)+'</p><h2>Question</h2><p>'+esc(x.question)+'</p><label for="answer">Your answer</label><textarea id="answer" aria-label="Your answer"></textarea><button class="primary" id="submit">Submit answer</button><button class="secondary" id="askExercise">Ask tutor</button></section>'}else if(data.evaluation){const x=data.evaluation;root.innerHTML='<section class="hero"><small>RESULT</small><h1>'+esc(x.status)+'</h1><p>'+esc(x.feedback)+'</p><h2>How to think</h2><p>'+esc(x.explanation||'Review the concept and try again.')+'</p>'+(x.misconception?'<p class="error">'+esc(x.misconception)+'</p>':'')+'<button class="primary" id="next">Next</button></section>'}else if(data.items){root.innerHTML='<section class="hero"><small>MEMORY LOOP</small><h1>Reviews that matter.</h1></section>'+data.items.map(x=>'<article class="row"><b>'+esc(x.concept)+'</b><span>'+esc(x.status)+'</span></article>').join('')}else if(data.concepts){root.innerHTML='<section class="hero"><small>KNOWLEDGE MAP</small><h1>Explore your curriculum.</h1></section>'+data.concepts.map(x=>'<article class="row"><b>'+esc(x.name)+'</b><span>'+esc(x.type)+'</span></article>').join('')}else if(data.content){root.innerHTML='<section class="hero"><small>'+esc(data.state)+'</small><h1>Study step</h1><pre>'+esc(data.content)+'</pre><button class="primary" id="practice">Practice</button><button class="secondary" id="askLesson">Ask tutor</button></section>'}else if(data.answer){root.innerHTML='<section class="hero"><small>TUTOR</small><h1>Let us work through it.</h1><p>'+esc(data.answer)+'</p><textarea id="question" aria-label="Tutor question" placeholder="Ask a question"></textarea><button class="primary" id="ask">Ask tutor</button></section>'}document.getElementById('refresh')?.addEventListener('click',()=>post('refresh'));document.getElementById('start')?.addEventListener('click',()=>post('start'));document.getElementById('practice')?.addEventListener('click',()=>post('practice'));document.getElementById('submit')?.addEventListener('click',()=>{const b=document.getElementById('submit');b.disabled=true;b.textContent='Evaluating...';post('submit',{answer:document.getElementById('answer').value})});document.getElementById('next')?.addEventListener('click',()=>post('next'));document.getElementById('ask')?.addEventListener('click',()=>post('tutor',{question:document.getElementById('question').value}));document.getElementById('askExercise')?.addEventListener('click',()=>post('tutor',{question:'I need help understanding this exercise.'}));document.getElementById('askLesson')?.addEventListener('click',()=>post('tutor',{question:'I need help with this lesson.'}));</script></body></html>`;
}

function esc(value: string): string { return value.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] ?? c)); }
const styles = `:root{--ink:#17211b;--muted:#66736b;--paper:#f4f1e8;--green:#205c4b;--coral:#d9674e;--line:#d8d8c9}*{box-sizing:border-box}body{margin:0;padding:18px;color:var(--ink);background:var(--paper);font:13px Georgia,serif}header{display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line);padding-bottom:14px}header>b{background:var(--coral);color:white;padding:8px;font:11px Arial}header strong{display:block;font-size:17px}small,label{font:10px Arial,sans-serif;letter-spacing:1px;text-transform:uppercase;color:var(--muted)}header button{margin-left:auto;border:1px solid var(--line);background:transparent;padding:5px 8px;color:var(--green);cursor:pointer}.hero{padding:25px 0 18px}.hero h1{font-size:26px;line-height:1.05;margin:8px 0 18px}.hero h2{font-size:16px;margin-top:22px}.score{font-size:28px}.bar{height:8px;background:#deded1;margin-top:14px}.bar i{display:block;height:100%;background:var(--green)}.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.grid article,.row{border:1px solid var(--line);padding:13px;background:#faf8f0}.grid b{display:block;font-size:19px;margin-top:9px}.grid span,.row span{display:block;color:var(--muted);font:11px Arial;margin-top:5px}.primary,.secondary{padding:11px 15px;margin:16px 8px 0 0;cursor:pointer;font:bold 11px Arial}.primary{border:0;background:var(--green);color:white}.secondary{border:1px solid var(--green);background:transparent;color:var(--green)}.pill{display:inline-block;padding:4px 7px;background:#dfe8df;color:var(--green);font:bold 10px Arial;text-transform:uppercase}.context{border-left:3px solid var(--coral);padding-left:10px;color:var(--muted)}textarea{display:block;width:100%;min-height:120px;border:1px solid var(--line);background:#faf8f0;padding:10px;margin-top:7px;font:14px Georgia;resize:vertical}pre{white-space:pre-wrap;line-height:1.5}.row{display:flex;justify-content:space-between;margin:7px 0}.error{border-left:3px solid var(--coral);padding:12px;background:#faf8f0}.loading{text-align:center;padding:50px;color:var(--muted)}`;

export function deactivate(): void { }