import {readFile,writeFile} from "node:fs/promises";
import {join} from "node:path";
const [profile,output,appUrl]=process.argv.slice(2);
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let port;
for(let i=0;i<100;i++){try{port=Number((await readFile(join(profile,"DevToolsActivePort"),"utf8")).split("\n")[0]);if(port)break;}catch{}await pause(200);}
if(!port)throw new Error("Chrome did not start.");
const tabs=await(await fetch("http://127.0.0.1:"+port+"/json/list")).json();
const target=tabs.find(t=>t.type==="page"&&t.url==="about:blank");
if(!target)throw new Error("Isolated test page missing.");
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener("open",resolve,{once:true});socket.addEventListener("error",reject,{once:true});});
let sequence=0,synthRequests=0;
const pending=new Map();
socket.addEventListener("message",event=>{
 const message=JSON.parse(event.data);
 if(message.method==="Network.requestWillBeSent"&&message.params.request.method==="POST"&&new URL(message.params.request.url).pathname==="/synth")synthRequests++;
 const handler=pending.get(message.id);
 if(handler){pending.delete(message.id);clearTimeout(handler.timer);message.error?handler.reject(new Error(JSON.stringify(message.error))):handler.resolve(message.result);}
});
function send(method,params={}){const id=++sequence;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error("CDP timeout: "+method));},30000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const data=await send("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true,userGesture:true});if(data.exceptionDetails)throw new Error(data.exceptionDetails.exception?.description||data.exceptionDetails.text);return data.result.value;}
function assert(condition,message){if(!condition)throw new Error(message);}
async function click(selector){
 const point=await evaluate("(()=>{const el=document.querySelector("+JSON.stringify(selector)+");if(!el)throw new Error('Missing click target');el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()");
 await send("Input.dispatchMouseEvent",{type:"mousePressed",button:"left",clickCount:1,...point});
 await send("Input.dispatchMouseEvent",{type:"mouseReleased",button:"left",clickCount:1,...point});
}
async function edit(text){await click("#style");await evaluate("document.getElementById('style').select()");await send("Input.insertText",{text});}
async function style(){return evaluate("document.getElementById('style').value");}
const checks=[];
try{
 await send("Network.enable");await send("Page.enable");await send("Page.navigate",{url:appUrl});
 for(let i=0;i<100;i++){if(await evaluate("!!document.querySelector('[data-tag-id=rock]')"))break;await pause(100);}
 assert(await evaluate("document.querySelectorAll('.tag-category').length===5"),"Five categories missing");
 await edit("My handmade intro");
 await click('[data-tag-id="rock"]');let value=await style();
 assert(value==="My handmade intro, rock","Tag did not preserve manual text");checks.push("real click appends while preserving manual text");
 await click('[data-tag-id="rock"]');assert(await style()===value,"Repeated tag duplicated");checks.push("repeated click is idempotent");
 await edit("My note; ROCK");await click('[data-tag-id="rock"]');assert(await style()==="My note; ROCK","Case-insensitive dedup failed");checks.push("case-insensitive manual dedup");
 await click("#styleCategory-sounds");await click('[data-tag-id="piano"]');
 assert(await style()==="My note; ROCK, piano","Instrument append failed");
 await edit("Loose notes\nLo-fi hip-hop; PIANO");await click('[data-tag-id="piano"]');assert(await style()==="Loose notes\nLo-fi hip-hop; PIANO","Manual multi-line text changed");
 await click("#styleCategory-genres");await click('[data-tag-id="lofi"]');assert(await style()==="Loose notes\nLo-fi hip-hop; PIANO","Punctuation-normalized dedup failed");checks.push("manual editing and hyphen-aware dedup");
 await edit("piano, custom ending");await click("#styleCategory-sounds");assert(await evaluate("document.querySelector('[data-tag-id=piano]').classList.contains('selected')"),"Selection did not follow editing");checks.push("selected state follows manual editing");
 await evaluate("document.getElementById('instrumental').checked=false;document.getElementById('instrumental').dispatchEvent(new Event('input',{bubbles:true}))");
 const randomValues=[];
 for(let i=0;i<12;i++){await click("#randomStyle");randomValues.push(await style());}
 assert(new Set(randomValues).size>=10,"Random descriptions lack variety");
 assert(randomValues.every(s=>s.includes("vocals")&&!s.includes("no vocals")&&s.split(",").length>=6),"Random vocal recipe invalid");
 checks.push("12 varied coherent vocal recipes");
 await click("#instrumental");await click("#randomStyle");const instrumental=await style();
 assert(instrumental.includes("instrumental, no vocals")&&!/female|male|rap vocals/.test(instrumental),"Instrumental random recipe conflicts with vocals");checks.push("random respects instrumental mode");
 await click("#styleCategory-vocals");await click('[data-tag-id="novocals"]');assert(await style()===instrumental,"Existing no-vocals token duplicated");checks.push("vocal tag dedup");
 const longText="x".repeat(1999);await edit(longText);await click("#styleCategory-sounds");await click('[data-tag-id="piano"]');assert(await style()===longText,"Long manual text was truncated");checks.push("maximum-length guard preserves manual input");
 await edit("My preserved text");await click("#styleCategory-genres");await click('[data-tag-id="jazz"]');const persisted=await style();
 await send("Page.reload");
 for(let i=0;i<100;i++){if(await evaluate("document.getElementById('style')?.value==="+JSON.stringify(persisted)))break;await pause(100);}
 assert(await style()===persisted,"Style did not persist across reload");checks.push("tagged manual text survives reload");
 await click("#randomStyle");await click("#styleCategory-genres");await evaluate("window.scrollTo(0,0)");
 const desktop=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:true});await writeFile(join(output,"tags-desktop.png"),Buffer.from(desktop.data,"base64"));
 await send("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await pause(100);await evaluate("window.scrollTo(0,0)");
 assert(await evaluate("document.documentElement.scrollWidth<=window.innerWidth"),"Mobile layout overflows horizontally");checks.push("390px mobile layout without horizontal overflow");
 await click("#styleCategory-moods");await click('[data-tag-id="calm"]');
 await click("#styleCategory-features");await click('[data-tag-id="reverb"]');
 const mobile=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:true});await writeFile(join(output,"tags-mobile.png"),Buffer.from(mobile.data,"base64"));
 assert(synthRequests===0,"UI controls submitted a generation request");
 checks.push("no /synth requests or new audio generation");
 const report={passed:true,checks,randomValues,instrumental,synthRequests,url:appUrl,checkedAt:new Date().toISOString()};
 await writeFile(join(output,"tags-check.json"),JSON.stringify(report,null,2));console.log(JSON.stringify({passed:true,checks,synthRequests}));
}finally{try{await send("Browser.close");}catch{}socket.close();}
