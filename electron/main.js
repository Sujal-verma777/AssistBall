const { app, BrowserWindow, ipcMain, desktopCapturer, screen } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn, spawnSync } = require("child_process");

let mainWindow;
let chatWindow;
let latestScreenshot = null;
let dragState = null;
let backendProcess = null;
let backendReady = false;

const BALL_SIZE = 72;
const CHAT_WIDTH = 420;
const CHAT_HEIGHT = 680;
const BACKEND_HOST = process.env.ASSISTBALL_BACKEND_HOST || "127.0.0.1";
const BACKEND_PORT = Number(process.env.ASSISTBALL_BACKEND_PORT || 8000);
const BACKEND_BASE_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}`;

function getBackendDir() {
  if (app.isPackaged) return path.join(process.resourcesPath, "backend");
  return path.join(__dirname, "..", "backend");
}


function readDotEnv(filePath) {
  const values = {};
  try {
    const content = fs.readFileSync(filePath, "utf8");
    for (const rawLine of content.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#") || !line.includes("=")) continue;
      const idx = line.indexOf("=");
      const key = line.slice(0, idx).trim();
      let value = line.slice(idx + 1).trim();
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      values[key] = value;
    }
  } catch (_) {}
  return values;
}

function getApiKey() {
  return process.env.ASSISTBALL_API_KEY || readDotEnv(path.join(getBackendDir(), ".env")).APP_API_KEY || "";
}

function commandExists(command) {
  try {
    const result = spawnSync(command, ["--version"], {
      stdio: "ignore",
      windowsHide: true,
    });
    return result.status === 0 || result.error == null;
  } catch (_) {
    return false;
  }
}

function getPythonCommandConfig() {
  if (process.env.ASSISTBALL_PYTHON) {
    return { command: process.env.ASSISTBALL_PYTHON, args: [] };
  }

  const backendDir = getBackendDir();
  if (process.platform === "win32") {
    const venvPython = path.join(backendDir, "venv", "Scripts", "python.exe");
    if (fs.existsSync(venvPython)) return { command: venvPython, args: [] };
    if (commandExists("py")) return { command: "py", args: ["-3"] };
    return { command: "python", args: [] };
  }

  const venvPython = path.join(backendDir, "venv", "bin", "python");
  if (fs.existsSync(venvPython)) return { command: venvPython, args: [] };
  if (commandExists("python3")) return { command: "python3", args: [] };
  return { command: "python", args: [] };
}

function getPackagedBackendExecutable() {
  const candidates = process.platform === "win32"
    ? [path.join(process.resourcesPath, "backend-dist", "AssistBallBackend.exe")]
    : [path.join(process.resourcesPath, "backend-dist", "AssistBallBackend")];
  return candidates.find((candidate) => fs.existsSync(candidate));
}

function startBackend() {
  if (backendProcess || backendReady) return;

  const backendDir = getBackendDir();
  const packagedExecutable = getPackagedBackendExecutable();
  let command;
  let args;
  let cwd = backendDir;

  if (packagedExecutable) {
    command = packagedExecutable;
    args = [];
    cwd = path.dirname(packagedExecutable);
  } else {
    const pythonConfig = getPythonCommandConfig();
    command = pythonConfig.command;
    args = [...pythonConfig.args, "-m", "uvicorn", "app.main:app", "--host", BACKEND_HOST, "--port", String(BACKEND_PORT)];
  }

  const envFile = path.join(backendDir, ".env");
  const envValues = readDotEnv(envFile);
  const childEnv = {
    ...process.env,
    ...envValues,
    PYTHONUNBUFFERED: "1",
  };

  backendProcess = spawn(command, args, {
    cwd,
    env: childEnv,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  backendProcess.stdout?.on("data", (data) => console.log(`[AssistBall backend] ${data.toString().trimEnd()}`));
  backendProcess.stderr?.on("data", (data) => console.error(`[AssistBall backend] ${data.toString().trimEnd()}`));
  backendProcess.on("error", (error) => {
    console.error("Failed to start AssistBall backend:", error);
    backendProcess = null;
  });
  backendProcess.on("exit", (code, signal) => {
    console.log(`AssistBall backend exited (code=${code}, signal=${signal})`);
    backendProcess = null;
    backendReady = false;
  });
}

async function waitForBackend(timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${BACKEND_BASE_URL}/health`);
      if (response.ok) {
        backendReady = true;
        return true;
      }
    } catch (_) {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return false;
}

async function backendRequest(endpoint, payload) {
  const ready = backendReady || await waitForBackend();
  if (!ready) throw new Error("AssistBall AI backend did not start. Check the backend setup and Python dependencies.");

  const response = await fetch(`${BACKEND_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": getApiKey(),
    },
    body: JSON.stringify(payload),
  });

  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch (_) { data = {}; }
  if (!response.ok) {
    throw new Error(data.detail || `Backend returned HTTP ${response.status}`);
  }
  return data;
}

async function requestSuggestions(screenshot) {
  return backendRequest("/suggest", {
    image_b64: screenshot.base64,
    media_type: screenshot.mime,
    session_id: `desktop-${process.pid}`,
  });
}

async function requestAnswer(question, screenshot, history) {
  return backendRequest("/ask", {
    query: question,
    image_b64: screenshot.base64,
    media_type: screenshot.mime,
    history: Array.isArray(history) ? history.slice(-10) : [],
    session_id: `desktop-${process.pid}`,
  });
}

async function requestAnswerStream(question, screenshot, history, onToken) {
  const ready = backendReady || await waitForBackend();
  if (!ready) throw new Error("AssistBall AI backend did not start.");

  const response = await fetch(`${BACKEND_BASE_URL}/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": getApiKey(),
    },
    body: JSON.stringify({
      query: question,
      image_b64: screenshot.base64,
      media_type: screenshot.mime,
      history: Array.isArray(history) ? history.slice(-10) : [],
      session_id: `desktop-${process.pid}`,
    }),
  });

  if (!response.ok || !response.body) {
    let detail = `Backend returned HTTP ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const event of events) {
      const lines = event.split(/\r?\n/);
      const eventName = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
      const dataLine = lines.find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      let data;
      try { data = JSON.parse(dataLine.slice(5).trim()); } catch (_) { continue; }

      if (eventName === "token" && data.token) onToken(data.token);
      if (eventName === "done") finalPayload = data;
      if (eventName === "error") throw new Error(data.error || "Streaming request failed.");
    }
  }

  return finalPayload || { answer: "", provider: "unknown" };
}

function createBallWindow() {
  mainWindow = new BrowserWindow({
    width: BALL_SIZE,
    height: BALL_SIZE,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.setAlwaysOnTop(true, "floating");
  mainWindow.loadFile(path.join(__dirname, "index.html"));
}

function showBall() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.show();
  mainWindow.setAlwaysOnTop(true, "floating");
}

function openChatWindow() {
  if (chatWindow && !chatWindow.isDestroyed()) {
    chatWindow.show();
    chatWindow.focus();
    return;
  }
  const bounds = mainWindow.getBounds();
  chatWindow = new BrowserWindow({
    width: CHAT_WIDTH,
    height: CHAT_HEIGHT,
    x: Math.max(10, bounds.x - CHAT_WIDTH + BALL_SIZE),
    y: Math.max(10, bounds.y - CHAT_HEIGHT + BALL_SIZE),
    minWidth: 340,
    minHeight: 500,
    frame: false,
    transparent: true,
    resizable: true,
    movable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: true,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  chatWindow.setAlwaysOnTop(true, "floating");
  chatWindow.loadFile(path.join(__dirname, "index.html"), { query: { mode: "chat" } });
  chatWindow.once("ready-to-show", () => { chatWindow.show(); chatWindow.focus(); });
  chatWindow.on("closed", () => { chatWindow = null; showBall(); });
}

async function captureFullScreen() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.size;
  const scale = primaryDisplay.scaleFactor || 1;
  const sources = await desktopCapturer.getSources({
    types: ["screen"],
    thumbnailSize: { width: Math.round(width * scale), height: Math.round(height * scale) },
    fetchWindowIcons: false,
  });
  if (!sources.length) throw new Error("No screen source was found.");
  const source = sources.find((s) => String(s.display_id) === String(primaryDisplay.id)) || sources[0];
  const image = source.thumbnail;
  if (image.isEmpty()) throw new Error("Electron returned an empty screenshot.");
  return image.toPNG();
}

ipcMain.handle("start-ball-drag", (_event, { screenX, screenY }) => {
  if (!mainWindow || mainWindow.isDestroyed()) return false;
  const bounds = mainWindow.getBounds();
  dragState = { offsetX: screenX - bounds.x, offsetY: screenY - bounds.y, startX: screenX, startY: screenY, moved: false };
  return true;
});

ipcMain.handle("move-ball", (_event, { screenX, screenY }) => {
  if (!mainWindow || mainWindow.isDestroyed() || !dragState) return false;
  if (!dragState.moved && Math.hypot(screenX - dragState.startX, screenY - dragState.startY) > 4) dragState.moved = true;
  mainWindow.setPosition(Math.round(screenX - dragState.offsetX), Math.round(screenY - dragState.offsetY), false);
  return true;
});

ipcMain.handle("end-ball-drag", () => {
  const moved = !!dragState?.moved;
  dragState = null;
  return { moved };
});

ipcMain.handle("open-assistant", async () => {
  try {
    mainWindow.hide();
    await new Promise((resolve) => setTimeout(resolve, 150));
    latestScreenshot = await captureFullScreen();
    openChatWindow();
    return { ok: true, message: "Screen captured successfully." };
  } catch (error) {
    console.error("Screenshot error:", error);
    showBall();
    return { ok: false, message: error.message };
  }
});

ipcMain.handle("get-screenshot", async () => {
  if (!latestScreenshot) return { ok: false, message: "No screenshot is available." };
  return { ok: true, base64: latestScreenshot.toString("base64"), mime: "image/png" };
});

ipcMain.handle("get-suggestions", async () => {
  try {
    if (!latestScreenshot) throw new Error("No screenshot is available.");
    const result = await requestSuggestions({ base64: latestScreenshot.toString("base64"), mime: "image/png" });
    return { ok: true, ...result };
  } catch (error) {
    console.error("Suggestion error:", error);
    return { ok: false, message: error.message };
  }
});

ipcMain.handle("ask", async (_event, { question, history }) => {
  try {
    if (!latestScreenshot) throw new Error("No screenshot is available.");
    const result = await requestAnswer(question, { base64: latestScreenshot.toString("base64"), mime: "image/png" }, history);
    return { ok: true, ...result };
  } catch (error) {
    console.error("Ask error:", error);
    return { ok: false, message: error.message };
  }
});

ipcMain.handle("ask-stream", async (event, { question, history }) => {
  try {
    if (!latestScreenshot) throw new Error("No screenshot is available.");
    const result = await requestAnswerStream(
      question,
      { base64: latestScreenshot.toString("base64"), mime: "image/png" },
      history,
      (token) => event.sender.send("ask-stream-token", token),
    );
    return { ok: true, ...result };
  } catch (error) {
    console.error("Stream error:", error);
    return { ok: false, message: error.message };
  }
});

ipcMain.handle("close-chat", () => {
  if (chatWindow && !chatWindow.isDestroyed()) chatWindow.close();
  else showBall();
  return { ok: true };
});

ipcMain.handle("recapture", async () => {
  try {
    if (chatWindow && !chatWindow.isDestroyed()) chatWindow.hide();
    await new Promise((resolve) => setTimeout(resolve, 150));
    latestScreenshot = await captureFullScreen();
    if (chatWindow && !chatWindow.isDestroyed()) { chatWindow.show(); chatWindow.focus(); }
    return { ok: true, message: "Screen recaptured." };
  } catch (error) {
    console.error("Recapture error:", error);
    if (chatWindow && !chatWindow.isDestroyed()) { chatWindow.show(); chatWindow.focus(); }
    return { ok: false, message: error.message };
  }
});

ipcMain.handle("backend-status", async () => ({
  ok: await waitForBackend(2000),
  url: BACKEND_BASE_URL,
}));

app.whenReady().then(async () => {
  startBackend();
  await waitForBackend();
  createBallWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createBallWindow(); });
});

app.on("window-all-closed", (event) => event.preventDefault());

app.on("before-quit", () => {
  if (backendProcess && !backendProcess.killed) {
    try { backendProcess.kill(); } catch (_) {}
    backendProcess = null;
  }
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.destroy();
  if (chatWindow && !chatWindow.isDestroyed()) chatWindow.destroy();
});
