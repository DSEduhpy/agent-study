const assert = require("assert");
const vscode = require("vscode");
const manifest = require("../package.json");

suite("Study Agent activation", () => {
  test("activates and registers the dashboard command", async () => {
    const extension = vscode.extensions.getExtension("study-agent.study-agent-vscode");
    assert.ok(extension);
    await vscode.commands.executeCommand("studyAgent.openDashboard");
    assert.ok(extension.isActive);
    const commands = await vscode.commands.getCommands(true);
    for (const command of [
      "studyAgent.openDashboard",
      "studyAgent.startStudy",
      "studyAgent.askTutor",
      "studyAgent.showReviews",
      "studyAgent.openCurriculum"
    ]) assert.ok(commands.includes(command));
  });

  test("declares the sidebar as a webview contribution", () => {
    const sidebar = manifest.contributes.views.studyAgent.find(item => item.id === "studyAgent.sidebar");
    assert.ok(sidebar, "sidebar view contribution must exist");
    assert.strictEqual(sidebar.type, "webview", "sidebar must be declared as a webview to match the WebviewViewProvider registration");
  });
});