import {readFile, writeFile} from "node:fs/promises";
import {join} from "node:path";
const [profile, output, appUrl] = process.argv.slice(2);
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let port;
for (let i=0;i<100;i++) {
  try { port = Number((await readFile(join(profile,"DevToolsActivePort"),"utf8")).split("\n")[0]); if(port) break; } catch {}
  await pause(200);
}
if (!port) throw new Error("Chrome debugging endpoint did not start.");
const tabs = await (await fetch("http://127.0.0.1:"+port+"/json/list")).json();
const target = tabs.find(t => t.type === "page" && t.url === "about:blank");
if (!target) throw new Error("The isolated blank test page was not found.");
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject) => { socket.addEventListener("open",resolve,{once:true}); socket.addEventListener("error",reject,{once:true}); });
let sequence=0;
const pending = new Map();
socket.addEventListener("message",event => {
  const message=JSON.parse(event.data), handler=pending.get(message.id);
  if(handler) { pending.delete(message.id); clearTimeout(handler.timer); message.error ? handler.reject(new Error(JSON.stringify(message.error))) : handler.resolve(message.result); }
});
function send(method,params={}) {
  const id=++sequence;
  return new Promise((resolve,reject) => {
    const timer=setTimeout(()=>{ pending.delete(id); reject(new Error("CDP timeout: "+method)); },30000);
    pending.set(id,{resolve,reject,timer}); socket.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression) {
  const data=await send("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true,userGesture:true});
  if(data.exceptionDetails) throw new Error(data.exceptionDetails.text+" "+(data.exceptionDetails.exception?.description || ""));
  return data.result.value;
}
try {
  await send("Page.enable");
  await send("Page.navigate",{url:appUrl});
  let state;
  for(let i=0;i<100;i++) {
    state=await evaluate("({title:document.title,connected:document.getElementById('connectionText')?.textContent,generateDisabled:document.getElementById('generate')?.disabled,audioCount:document.querySelectorAll('audio').length,error:document.getElementById('error')?.textContent})");
    if(state.connected==="Студия подключена" && state.audioCount>0) break;
    await pause(200);
  }
  if(state.connected!=="Студия подключена" || state.generateDisabled!==false || state.audioCount<1 || state.error) throw new Error("UI state failed: "+JSON.stringify(state));
  await evaluate("document.getElementById('example').click()");
  const form=await evaluate("({style:document.getElementById('style').value,instrumental:document.getElementById('instrumental').checked,lyricsHidden:document.getElementById('lyricsFields').hidden,duration:document.getElementById('duration').value,cot:document.getElementById('cot').value})");
  if(!form.style || !form.instrumental || !form.lyricsHidden || form.duration!=="20" || form.cot!=="off") throw new Error("Example form failed: "+JSON.stringify(form));
  const audio=await evaluate("(async()=>{const a=document.querySelector('audio');a.muted=true;a.load();await new Promise((resolve,reject)=>{if(a.readyState>=1)return resolve();a.addEventListener('loadedmetadata',resolve,{once:true});a.addEventListener('error',()=>reject(new Error('Audio load failed')),{once:true});setTimeout(()=>reject(new Error('Audio metadata timeout')),15000);});await a.play();await new Promise(r=>setTimeout(r,400));const result={duration:a.duration,currentTime:a.currentTime,paused:a.paused,readyState:a.readyState};a.pause();return result;})()");
  if(audio.paused || audio.currentTime<=0 || !Number.isFinite(audio.duration) || audio.duration<=0) throw new Error("Audio playback failed: "+JSON.stringify(audio));
  const screenshot=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:true});
  await writeFile(join(output,"windows-ui.png"),Buffer.from(screenshot.data,"base64"));
  await writeFile(join(output,"ui-check.json"),JSON.stringify({passed:true,state,form,audio,url:appUrl,checkedAt:new Date().toISOString()},null,2));
  console.log(JSON.stringify({passed:true,audio,screenshot:join(output,"windows-ui.png")}));
} finally {
  try { await send("Browser.close"); } catch {}
  socket.close();
}
