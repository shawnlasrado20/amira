import { PipecatClient } from "@pipecat-ai/client-js";
import { WebSocketTransport } from "@pipecat-ai/websocket-transport";

const API = (import.meta.env.VITE_API_URL || "http://localhost:7860").replace(/\/$/, "");
const MAX_CALL_MS = 3 * 60 * 1000;

const opening = "Thank you for calling Cake N More. This is Lina. How can I help you today?";
let client;
let tick;
let callLimit;
let started;
let live = false;
let connecting = false;
let muted = false;
let userPart;
let botPart;
let statusReset;

const $ = (id) => document.getElementById(id);
const demo = $("demo");
const talk = $("talk");
const mute = $("mute");
const badge = $("badge");
const transcript = $("transcript");
const placeholder = $("placeholder");
const error = $("error");
const statusTitle = $("status-title");
const statusHelp = $("status-help");

function assistantConfig() {
  return {
    assistant: {
      name: "Lina",
      voice: "gu-IN-diya",
      firstMessage: opening,
      systemPrompt: "You represent Cake N More. Be warm, concise and helpful. Ask one question at a time. This is a prototype: never claim an order, payment, delivery or custom design is confirmed. Collect order-request details one item at a time, read them back, and say the team will confirm. Speak prices naturally as dirhams, never as AED or UAE dirhams. Do not dump full menus or price lists; narrow the customer choice first.",
    },
    company: {
      name: "Cake N More",
      industry: "Patisserie and cake shop",
      website: "https://cakenmore.com/",
      locationHours: "Use the attached Cake N More knowledge base.",
      servicesPolicies: "Use the attached Cake N More knowledge base as the only source of product, price, location, promotion and ordering facts.",
    },
    abilities: { answerQuestions: { qa: "Answer only from the attached Cake N More knowledge base. If a fact is missing or marked uncertain, offer human confirmation." } },
    knowledgeBase: [],
  };
}

function addLine(who, text, partial = false) {
  const row = document.createElement("p");
  row.className = `line ${who === "user" ? "you" : ""}`;
  const label = document.createElement("b");
  label.textContent = who === "user" ? "You:" : "Lina:";
  const content = document.createElement("span");
  content.textContent = text;
  content.style.opacity = partial ? 0.6 : 1;
  row.append(label, content);
  transcript.appendChild(row);
  transcript.scrollTop = transcript.scrollHeight;
  return content;
}

function updateTranscript(who, data) {
  let text = String(data?.text || "").replace(/^\s*\[\[show:\s*\w+\s*\]\]\s*/i, "").trim();
  if (who === "bot") {
    // RTVI observes the raw streamed LLM text before the server-side TTS cleaner.
    // Mirror that cleaner here so transcript-only artifacts such as "WeWe" never show.
    text = text.replace(/^(we|i|you|yes|sure|absolutely|the|our|that)(?:\1|\s+\1)\b/i, "$1");
  }
  if (!text) return;
  const final = data?.final !== false;
  const current = who === "user" ? userPart : botPart;
  if (!current) {
    const content = addLine(who, text, !final);
    if (who === "user") userPart = content;
    else botPart = content;
  } else {
    current.textContent = text;
    current.style.opacity = final ? 1 : 0.6;
  }
  if (final) {
    if (who === "user") userPart = undefined;
    else botPart = undefined;
  }
}

function moment(title, help) {
  clearTimeout(statusReset);
  statusTitle.textContent = title;
  statusHelp.textContent = help;
  statusReset = setTimeout(() => {
    statusTitle.textContent = "Call in progress";
    statusHelp.textContent = "Speak naturally—Lina will respond when you pause.";
  }, 1800);
}

function setLive(on) {
  live = on;
  demo.classList.toggle("live", on);
  badge.classList.toggle("live", on);
  badge.textContent = on ? "LIVE" : "STANDBY";
  talk.textContent = on ? "End call" : "Start live call";
  mute.style.display = on ? "block" : "none";
  if (on) {
    statusTitle.textContent = "Call in progress";
    statusHelp.textContent = "Speak naturally—Lina will respond when you pause.";
    started = Date.now();
    tick = setInterval(() => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      $("timer").textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    }, 1000);
    callLimit = setTimeout(() => endCall("Demo complete", "This preview is limited to three minutes."), MAX_CALL_MS);
  } else {
    clearInterval(tick);
    clearTimeout(callLimit);
    clearTimeout(statusReset);
    $("timer").textContent = "Ready";
  }
}

async function endCall(title = "Ready when you are", help = "Press start, allow microphone access and speak naturally.") {
  const active = client;
  client = undefined;
  if (active) await active.disconnect().catch(() => {});
  muted = false;
  mute.textContent = "Mute";
  setLive(false);
  statusTitle.textContent = title;
  statusHelp.textContent = help;
}

function createClient() {
  return new PipecatClient({
    transport: new WebSocketTransport(),
    enableCam: false,
    enableMic: true,
    callbacks: {
      onConnected: () => setLive(true),
      onDisconnected: () => {
        if (live) endCall();
      },
      onUserStartedSpeaking: () => moment("Listening", "Understanding your question…"),
      onBotStartedSpeaking: () => moment("Lina is answering", "You can speak again when she finishes."),
      onUserTranscript: (data) => updateTranscript("user", data),
      onBotTranscript: (data) => updateTranscript("bot", { text: data?.text || data, final: true }),
      onError: (data) => showError(data?.message || "The voice session encountered a problem."),
    },
  });
}

function showError(message) {
  statusTitle.textContent = "Could not start the call";
  statusHelp.textContent = "Please try again in a moment.";
  error.textContent = message;
  error.style.display = "block";
}

async function startCall() {
  if (live) return endCall();
  if (connecting) return;
  connecting = true;
  talk.disabled = true;
  talk.textContent = "Connecting…";
  statusTitle.textContent = "Opening a voice session";
  statusHelp.textContent = "Your browser may ask for microphone access.";
  error.style.display = "none";
  placeholder.style.display = "none";
  [...transcript.children].forEach((node) => { if (node !== placeholder) node.remove(); });
  userPart = undefined;
  botPart = undefined;
  try {
    client = createClient();
    const response = await fetch(`${API}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transport: "websocket",
        body: { language: "en", demoPreset: "cake-n-more", assistantConfig: assistantConfig() },
      }),
    });
    if (!response.ok) throw new Error(`Voice service returned ${response.status}`);
    const session = await response.json();
    if (!session.wsUrl) throw new Error("Voice service did not return a WebSocket URL");
    // The generic Pipecat runner sees Railway's private bind address and returns
    // wss://0.0.0.0:PORT. The public browser socket is on the Railway HTTPS origin.
    const publicWsUrl = `${API.replace(/^http/, "ws")}/ws-client`;
    await client.connect({ wsUrl: publicWsUrl });
  } catch (cause) {
    await endCall("Could not start the call", "Please try again in a moment.");
    showError(cause?.name === "NotAllowedError" ? "Please allow microphone access to try the demo." : (cause?.message || "The assistant is temporarily unavailable."));
    placeholder.style.display = "grid";
  } finally {
    connecting = false;
    talk.disabled = false;
    if (!live) talk.textContent = "Start live call";
  }
}

talk.onclick = startCall;
$("top-talk").onclick = () => {
  demo.scrollIntoView({ behavior: "smooth", block: "center" });
  if (!live && !connecting) startCall();
};
mute.onclick = async () => {
  if (!client) return;
  muted = !muted;
  await client.enableMic(!muted);
  mute.textContent = muted ? "Unmute" : "Mute";
  statusTitle.textContent = muted ? "Microphone muted" : "Call in progress";
  statusHelp.textContent = muted ? "Lina cannot hear you until you unmute." : "Speak naturally—Lina will respond when you pause.";
};
