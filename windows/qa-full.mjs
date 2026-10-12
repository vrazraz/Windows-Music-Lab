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
const exceptions=[],requests=[],failures=[];
let sequence=0;
const pending = new Map();
socket.addEventListener("message",event => {
  const message=JSON.parse(event.data), handler=pending.get(message.id);
  if(message.method==='Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails);
  if(message.method==='Network.requestWillBeSent') requests.push({url:message.params.request.url,method:message.params.request.method});
  if(message.method==='Network.loadingFailed') failures.push(message.params);
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
  await send("Page.enable"); await send("Runtime.enable"); await send("Network.enable");
  await send("Emulation.setDeviceMetricsOverride",{width:1920,height:1080,deviceScaleFactor:1,mobile:false});
  await send("Page.navigate",{url:appUrl});
  let ready=false;
  for(let i=0;i<100;i++){
    ready=await evaluate("document.readyState!=='loading' && !!document.body.dataset.tab && !!window.HeresyArtist");
    if(ready)break; await pause(200);
  }
  if(!ready)throw new Error('Full UI did not initialize');
  const tabs=[];
  for(const name of ['create','write','post','artist','collection','train']){
    await evaluate(`document.querySelector('.topbar [data-tab="${name}"]').click()`);
    await pause(450);
    const state=await evaluate(`({tab:document.body.dataset.tab,title:document.title,localOnly:window.WINDOWS_FULL_PORT?.localOnly,selected:document.querySelector('.topbar [data-tab="${name}"]').getAttribute('aria-selected'),bodyWidth:document.body.scrollWidth,viewport:innerWidth,dialogs:[...document.querySelectorAll('[role="dialog"]')].filter(x=>x.getBoundingClientRect().width>0).length})`);
    if(state.tab!==name || state.selected!=='true' || !state.localOnly)throw new Error('Tab state failed '+JSON.stringify(state));
    const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,name+'.png'),Buffer.from(shot.data,'base64')); tabs.push(state);
  }
  const expectsWriter = process.argv[5] === '--writer-ready';
  let writer;
  for(let i=0;i<100;i++){
    writer=await evaluate("({configured:window.WINDOWS_FULL_PORT?.writerUrl,alias:window.WINDOWS_FULL_PORT?.writerModel,endpoint:document.getElementById('chatUrl')?.value,provider:document.getElementById('assistProvider')?.value,state:document.getElementById('assistLine')?.dataset.s,text:document.getElementById('assistLine')?.textContent})");
    if(!expectsWriter || writer.state==='ready')break;
    await pause(200);
  }
  if(expectsWriter && (writer.configured!=='http://127.0.0.1:41872' || writer.endpoint!==writer.configured || writer.provider!=='engine' || writer.state!=='ready' || !writer.text.includes('Windows-Music-Lab-Writer'))){
    throw new Error('Automatic local Writer UI readiness failed: '+JSON.stringify(writer));
  }
  const expectsArtist = process.argv.includes('--artist-ready');
  const artist=await evaluate("({painter:document.getElementById('arPainter')?.value,options:[...document.getElementById('arPainter').options].map(o=>({value:o.value,label:o.text,disabled:o.disabled})),resolution:document.getElementById('arResolution')?.value,sampling:document.getElementById('arSampSay')?.textContent})");
  if(expectsArtist && (artist.painter!=='sdxl' || !artist.options.some(o=>o.value==='sdxl' && !o.disabled))){
    throw new Error('Installed SDXL selection is not ready: '+JSON.stringify(artist));
  }
  const cloud=await evaluate("({providers:[...document.querySelectorAll('option')].filter(x=>/openrouter|cloud/i.test(x.value)).map(x=>({value:x.value,disabled:x.disabled,hidden:x.hidden})),boot:document.getElementById('bootSplash')?.textContent})");
  const external=requests.filter(x=>/^https?:/.test(x.url)&&!['127.0.0.1','localhost','[::1]'].includes(new URL(x.url).hostname));
  // The installed antivirus injects its own browser script; do not change its protection.
  const injected=external.filter(x=>new URL(x.url).hostname==='gc.kis.v2.scr.kaspersky-labs.com');
  const appExternal=external.filter(x=>!injected.includes(x));
  const result={passed:exceptions.length===0&&appExternal.length===0,tabs,writer,expectsWriter,artist,expectsArtist,cloud,exceptions,externalRequests:external,applicationExternalRequests:appExternal,antivirusInjectedRequests:injected,requests,failures,url:appUrl,checkedAt:new Date().toISOString(),inferenceJobs:0};
  await writeFile(join(output,'full-ui-check.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify({passed:result.passed,tabs:tabs.length,exceptions:exceptions.length,applicationExternalRequests:appExternal.length,antivirusInjectedRequests:injected.length,failures:failures.length}));
  if(!result.passed)throw new Error('UI runtime exception or external request; see full-ui-check.json');
}finally{
  try{await send('Browser.close')}catch{} socket.close();
}
