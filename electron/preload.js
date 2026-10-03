const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("assistBall", {
  openAssistant: () => ipcRenderer.invoke("open-assistant"),
  getScreenshot: () => ipcRenderer.invoke("get-screenshot"),
  getSuggestions: () => ipcRenderer.invoke("get-suggestions"),
  ask: (question, history) => ipcRenderer.invoke("ask", { question, history }),
  askStream: (question, history) => ipcRenderer.invoke("ask-stream", { question, history }),
  onStreamToken: (callback) => {
    const listener = (_event, token) => callback(token);
    ipcRenderer.on("ask-stream-token", listener);
    return () => ipcRenderer.removeListener("ask-stream-token", listener);
  },
  backendStatus: () => ipcRenderer.invoke("backend-status"),
  closeChat: () => ipcRenderer.invoke("close-chat"),
  recapture: () => ipcRenderer.invoke("recapture"),
  startBallDrag: (screenX, screenY) => ipcRenderer.invoke("start-ball-drag", { screenX, screenY }),
  moveBall: (screenX, screenY) => ipcRenderer.invoke("move-ball", { screenX, screenY }),
  endBallDrag: () => ipcRenderer.invoke("end-ball-drag"),
});
