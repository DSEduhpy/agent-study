const assert = require("assert");
const path = require("path");
const fs = require("fs");

let passed = 0, failed = 0;

function check(name, fn) {
    try {
        fn();
        console.log("  PASS: " + name);
        passed++;
    } catch (e) {
        console.log("  FAIL: " + name);
        console.log("    " + e.message);
        failed++;
    }
}

console.log("\n=== DEF-001: Workspace Resolution ===");
check("getWorkspaceRoot() exists", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/extension.ts"), "utf-8");
    assert(src.includes("function getWorkspaceRoot()"));
});

check("NO workspaceFile fallback", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/extension.ts"), "utf-8");
    assert(!src.includes("workspaceFile?.fsPath"));
});

check("NO process.cwd() fallback in activate", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/extension.ts"), "utf-8");
    const activate = src.substring(src.indexOf("export function activate"), src.indexOf("class StudyAgentView"));
    assert(!activate.includes("process.cwd()"));
});

console.log("\n=== DEF-001: Workspace Lifecycle & Observability ===");
check("Rechecks workspace folders during render", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/extension.ts"), "utf-8");
    assert(src.includes("const root = getWorkspaceRoot();"));
    assert(src.includes('workspace resolution (render)'));
});

check("Refreshes the view when workspace folders change", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/extension.ts"), "utf-8");
    assert(src.includes("onDidChangeWorkspaceFolders"));
    assert(src.includes("view.refreshWorkspace()"));
});

check("Logs the extension entry point for stale-bundle diagnosis", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/extension.ts"), "utf-8");
    assert(src.includes('context.asAbsolutePath("out/extension.js")'));
});

check("Uses the webview CSP source", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/extension.ts"), "utf-8");
    assert(src.includes("webview.cspSource"));
});

console.log("\n=== DEF-002 & DEF-006: Python Discovery ===");
check("Validates src folder", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/coreClient.ts"), "utf-8");
    assert(src.includes("SRC_NOT_FOUND"));
});

check("Logs workspace info", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/coreClient.ts"), "utf-8");
    assert(src.includes("[CoreClient] Workspace:"));
});

console.log("\n=== DEF-003 & DEF-005: Process Lifecycle ===");
check("Has process close handler", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/coreClient.ts"), "utf-8");
    assert(src.includes('on("close"'));
});

check("Has failAllPendingRequests", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/coreClient.ts"), "utf-8");
    assert(src.includes("failAllPendingRequests"));
});

check("Has disposed guard", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/coreClient.ts"), "utf-8");
    assert(src.includes("disposed"));
});

console.log("\n=== DEF-004: HTML Sanitization ===");
check("Has esc() function", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/extension.ts"), "utf-8");
    assert(src.includes("function esc(value: string)"));
});

check("Escapes all special chars", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/extension.ts"), "utf-8");
    assert(src.includes("&amp;"));
    assert(src.includes("&lt;"));
    assert(src.includes("&gt;"));
    assert(src.includes("&quot;"));
    assert(src.includes("&#39;"));
});

console.log("\n=== Manifest & Webview ===");
check("Sidebar type is webview", () => {
    const manifest = require("../package.json");
    const sidebar = manifest.contributes.views.studyAgent.find(v => v.id === "studyAgent.sidebar");
    assert(sidebar && sidebar.type === "webview");
});

check("Provider registered correctly", () => {
    const src = fs.readFileSync(path.join(__dirname, "../src/extension.ts"), "utf-8");
    assert(src.includes('registerWebviewViewProvider("studyAgent.sidebar"'));
});

console.log("\n=== Result ===");
console.log("PASS: " + passed + " | FAIL: " + failed);
process.exit(failed > 0 ? 1 : 0);
