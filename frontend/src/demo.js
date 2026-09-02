import { PipecatClient } from "@pipecat-ai/client-js";
import { DailyTransport } from "@pipecat-ai/daily-transport";

const API = (import.meta.env.VITE_API_URL || "http://localhost:7860").replace(/\/$/, "");
const MAX_CALL_MS = 3 * 60 * 1000;

const scenarios = [
  { id: "birthday", title: "Birthday cake", hint: "flavour, size & date", opening: "Thank you for calling Cake N More. This is Lina. Are you looking for a birthday cake or another sweet today?" },
  { id: "custom", title: "Custom design", hint: "occasion & inspiration", opening: "Thank you for calling Cake N More. This is Lina. Tell me a little about the custom cake you have in mind." },
  { id: "delivery", title: "Delivery", hint: "location & timing", opening: "Thank you for calling Cake N More. This is Lina. How can I help with your delivery enquiry?" },
];

let chosen = scenarios[0];
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
const box = $("scenarios");
const demo = $("demo");
const talk = $("talk");
const mute = $("mute");
const badge = $("badge");
const transcript = $("transcript");
const placeholder = $("placeholder");
const error = $("error");
const statusTitle = $("status-title");
const statusHelp = $("status-help");

function drawScenarios() {
  box.innerHTML = "";
  scenarios.forEach((scenario) => {
    const button = document.createElement("button");
    button.className = `scenario${scenario.id === chosen.id ? " active" : ""}`;
    button.innerHTML = `<b>${scenario.title}</b><span>${scenario.hint}</span>`;
    button.onclick = () => {
      if (live || connecting) return;
      chosen = scenario;
      drawScenarios();
    };
    box.appendChild(button);
  });
}

function assistantConfig() {
  return {
    assistant: {
      name: "Lina",
      voice: "gu-IN-diya",
      firstMessage: chosen.opening,
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
  const text = String(data?.text || "").replace(/^\s*\[\[show:\s*\w+\s*\]\]\s*/i, "").trim();
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

async function endCall(title = "Ready when you are", help = "Choose a journey, then start the call.") {
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
    transport: new DailyTransport(),
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
    await client.startBotAndConnect({
      endpoint: `${API}/start`,
      requestData: {
        transport: "daily",
        createDailyRoom: true,
        body: { language: "en", demoPreset: "cake-n-more", assistantConfig: assistantConfig() },
      },
    });
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
mute.onclick = async () => {
  if (!client) return;
  muted = !muted;
  await client.enableMic(!muted);
  mute.textContent = muted ? "Unmute" : "Mute";
  statusTitle.textContent = muted ? "Microphone muted" : "Call in progress";
  statusHelp.textContent = muted ? "Lina cannot hear you until you unmute." : "Speak naturally—Lina will respond when you pause.";
};

drawScenarios();
