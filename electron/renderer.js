const ballView = document.getElementById("ballView");
const chatView = document.getElementById("chatView");
const ballButton = document.getElementById("ballButton");
const closeButton = document.getElementById("closeButton");
const minimizeButton = document.getElementById("minimizeButton");
const sendButton = document.getElementById("sendButton");
const recaptureButton = document.getElementById("recaptureButton");
const questionInput = document.getElementById("questionInput");
const messages = document.getElementById("messages");
const statusText = document.getElementById("statusText");
const suggestions = document.getElementById("suggestions");

const isChatMode = new URLSearchParams(window.location.search).get("mode") === "chat";
if (isChatMode) {
  ballView.classList.add("hidden");
  chatView.classList.remove("hidden");
  window.addEventListener("DOMContentLoaded", loadSuggestions);
}

let pointerId = null;
let dragStarted = false;
let conversationHistory = [];
let removeStreamListener = null;

ballButton?.addEventListener("pointerdown", async (event) => {
  if (event.button !== 0) return;
  pointerId = event.pointerId;
  dragStarted = false;
  ballButton.setPointerCapture(pointerId);
  await window.assistBall.startBallDrag(event.screenX, event.screenY);
});

ballButton?.addEventListener("pointermove", async (event) => {
  if (event.pointerId !== pointerId) return;
  if (!dragStarted && Math.hypot(event.movementX || 0, event.movementY || 0) > 2) {
    dragStarted = true;
    ballButton.classList.add("dragging");
  }
  if (dragStarted) await window.assistBall.moveBall(event.screenX, event.screenY);
});

ballButton?.addEventListener("pointerup", async (event) => {
  if (event.pointerId !== pointerId) return;
  if (ballButton.hasPointerCapture(pointerId)) ballButton.releasePointerCapture(pointerId);
  const result = await window.assistBall.endBallDrag();
  const shouldOpen = !result.moved && !dragStarted;
  pointerId = null;
  ballButton.classList.remove("dragging");
  if (shouldOpen) {
    const captureResult = await window.assistBall.openAssistant();
    if (!captureResult.ok) alert(`AssistBall could not capture the screen:\n${captureResult.message}`);
  }
  dragStarted = false;
});

ballButton?.addEventListener("pointercancel", async () => {
  await window.assistBall.endBallDrag();
  pointerId = null;
  dragStarted = false;
  ballButton.classList.remove("dragging");
});

closeButton?.addEventListener("click", () => window.assistBall.closeChat());
minimizeButton?.addEventListener("click", () => window.assistBall.closeChat());

recaptureButton?.addEventListener("click", async () => {
  statusText.textContent = "Capturing screen...";
  recaptureButton.disabled = true;
  sendButton.disabled = true;
  const result = await window.assistBall.recapture();
  recaptureButton.disabled = false;
  sendButton.disabled = false;
  if (result.ok) {
    conversationHistory = [];
    clearMessages();
    statusText.textContent = "Screen captured";
    await loadSuggestions();
  } else {
    statusText.textContent = "Capture failed";
    addMessage("ai", `I couldn't capture the screen: ${result.message}`);
  }
});

sendButton?.addEventListener("click", sendQuestion);
questionInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendQuestion();
  }
});

function clearMessages() {
  messages.innerHTML = `<div class="welcome"><div class="welcome-icon">✦</div><h2>How can I help?</h2><p>I captured your screen. Choose a suggestion or tell me what problem you're facing.</p></div>`;
}

function addMessage(type, text, streaming = false) {
  const welcome = messages.querySelector(".welcome");
  if (welcome) welcome.remove();
  const message = document.createElement("div");
  message.className = type === "user" ? "message user-message" : "message ai-message";
  message.textContent = text;
  if (streaming) message.dataset.streaming = "true";
  messages.appendChild(message);
  messages.scrollTop = messages.scrollHeight;
  return message;
}

function setSuggestions(items = []) {
  if (!suggestions) return;
  suggestions.innerHTML = "";
  const clean = Array.isArray(items) ? items.filter(Boolean).slice(0, 2) : [];
  if (!clean.length) {
    suggestions.classList.add("hidden");
    return;
  }
  suggestions.classList.remove("hidden");
  clean.forEach((item) => {
    const button = document.createElement("button");
    button.className = "suggestion-button";
    button.textContent = item;
    button.addEventListener("click", () => {
      questionInput.value = item;
      sendQuestion();
    });
    suggestions.appendChild(button);
  });
}

async function loadSuggestions() {
  if (!suggestions) return;
  suggestions.innerHTML = `<div class="suggestion-loading">Understanding your screen…</div>`;
  suggestions.classList.remove("hidden");
  statusText.textContent = "Understanding screen...";
  const result = await window.assistBall.getSuggestions();
  if (result.ok) {
    setSuggestions(result.suggestions);
    statusText.textContent = result.detected_app ? `Ready · ${result.detected_app}` : "Ready";
  } else {
    suggestions.classList.add("hidden");
    statusText.textContent = "Ready · type your question";
  }
}

async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question || sendButton.disabled) return;
  addMessage("user", question);
  questionInput.value = "";
  setSuggestions([]);
  sendButton.disabled = true;
  recaptureButton.disabled = true;
  statusText.textContent = "Thinking...";

  const historyForRequest = conversationHistory.slice(-10);
  const aiMessage = addMessage("ai", "", true);
  let streamedText = "";

  try {
    if (removeStreamListener) removeStreamListener();
    removeStreamListener = window.assistBall.onStreamToken((token) => {
      streamedText += token;
      aiMessage.textContent = streamedText;
      messages.scrollTop = messages.scrollHeight;
    });

    const result = await window.assistBall.askStream(question, historyForRequest);
    if (!result.ok) throw new Error(result.message);

    const answer = result.answer || streamedText || "The AI returned no answer.";
    aiMessage.textContent = answer;
    aiMessage.dataset.streaming = "false";
    conversationHistory.push({ role: "user", content: question });
    conversationHistory.push({ role: "assistant", content: answer });
    statusText.textContent = `Ready · ${result.provider || "AI"}`;
  } catch (error) {
    aiMessage.textContent = `Something went wrong: ${error.message}`;
    statusText.textContent = "Error";
  } finally {
    if (removeStreamListener) {
      removeStreamListener();
      removeStreamListener = null;
    }
    sendButton.disabled = false;
    recaptureButton.disabled = false;
  }
}
