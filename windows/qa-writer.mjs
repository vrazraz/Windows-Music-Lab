import {readFile, writeFile} from "node:fs/promises";
import {join} from "node:path";
const [profile, output, appUrl = "http://localhost:41868/"] = process.argv.slice(2);
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let port;
for (let i = 0; i < 100; i++) {
  try {port = Number((await readFile(join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]); if (port) break;} catch {}
  await pause(200);
}
if (!port) throw new Error("Owned headless Chrome did not start");
const tabs = await (await fetch("http://127.0.0.1:" + port + "/json/list")).json();
const target = tabs.find(t => t.type === "page" && t.url === "about:blank");
if (!target) throw new Error("Owned isolated blank page not found");
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {socket.addEventListener("open", resolve, {once: true}); socket.addEventListener("error", reject, {once: true});});
let sequence = 0;
const pending = new Map();
socket.addEventListener("message", event => {
  const message = JSON.parse(event.data), handler = pending.get(message.id);
  if (handler) {pending.delete(message.id); clearTimeout(handler.timer); message.error ? handler.reject(new Error(JSON.stringify(message.error))) : handler.resolve(message.result);}
});
function send(method, params = {}) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {pending.delete(id); reject(new Error("CDP timeout: " + method));}, 240000);
    pending.set(id, {resolve, reject, timer}); socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const data = await send("Runtime.evaluate", {expression, returnByValue: true, awaitPromise: true});
  if (data.exceptionDetails) throw new Error(data.exceptionDetails.exception?.description || data.exceptionDetails.text);
  return data.result.value;
}
const browserTask = async () => {
  if (!["localhost", "127.0.0.1"].includes(location.hostname) || location.port !== "41868") throw new Error("Expected local Studio origin");
  const models = await fetch("http://127.0.0.1:41872/v1/models").then(r => {if (!r.ok) throw new Error("models HTTP " + r.status); return r.json();});
  const response = await fetch("http://127.0.0.1:41872/v1/chat/completions", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({model: "Windows-Music-Lab-Writer", messages: [{role: "user", content: "Reply with the single word READY. This is a synthetic local test."}], max_tokens: 32, stream: false, temperature: 0})
  }).then(r => {if (!r.ok) throw new Error("completion HTTP " + r.status); return r.json();});
  const content = response.choices[0].message.content;
  if (!content.includes("READY")) throw new Error("Unexpected synthetic response");
  const chatUrl = document.getElementById("chatUrl"), provider = document.getElementById("assistProvider");
  if (!chatUrl || !provider) throw new Error("The real Studio Writer controls were not found");
  // This is a fresh owned test profile: only its local endpoint choice is saved.
  chatUrl.value = "http://127.0.0.1:41872";
  chatUrl.dispatchEvent(new Event("change", {bubbles: true}));
  provider.value = "engine";
  provider.dispatchEvent(new Event("change", {bubbles: true}));
  let uiWriter;
  for (let i = 0; i < 150; i++) {
    const line = document.getElementById("assistLine");
    uiWriter = {endpoint: chatUrl.value, provider: provider.value, state: line?.dataset.s, text: line?.textContent};
    if (uiWriter.state === "ready" && uiWriter.text.includes("Windows-Music-Lab-Writer")) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (uiWriter.state !== "ready" || !uiWriter.text.includes("Windows-Music-Lab-Writer")) throw new Error("Studio Writer status did not become ready: " + JSON.stringify(uiWriter));
  return {origin: location.origin, models, response, uiWriter, browserCorsPost: true, syntheticOnly: true};
};
try {
  await send("Page.enable");
  await send("Page.navigate", {url: appUrl});
  for (let i = 0; i < 100; i++) {
    if (await evaluate("document.readyState === 'complete' && location.protocol === 'http:'")) break;
    await pause(200);
  }
  const result = await evaluate("(" + browserTask.toString() + ")()");
  await writeFile(join(output, "browser-check.json"), JSON.stringify({schema_version: 1, passed: true, ...result, testedUtc: new Date().toISOString()}, null, 2));
  console.log(JSON.stringify({passed: true, origin: result.origin, browserCorsPost: true}));
} finally {
  try {await send("Browser.close");} catch {}
  socket.close();
}
