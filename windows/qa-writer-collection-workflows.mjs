import {readFile,writeFile,readdir} from 'node:fs/promises';
import {join} from 'node:path';
const cfg=JSON.parse((await readFile(process.argv[2],'utf8')).replace(/^\uFEFF/,''));
const {profile,output,appUrl,scope,take}=cfg;
const pinOnly=process.argv.includes('--pin-only');
if(!/^uiqa-[a-f0-9]+$/.test(scope)||!take.startsWith(scope+'-'))throw Error('Owned fixture scope required');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let port; for(let i=0;i<100;i++){try{port=Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);if(port)break;}catch{}await pause(200);}
const targets=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
const target=targets.find(t=>t.type==='page'&&t.url==='about:blank');if(!target)throw Error('Owned blank Chrome missing');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
let seq=0,navigationCount=0;const pending=new Map(),exceptions=[],requests=[],blocked=[],checks=[],downloads=[];
function send(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
ws.addEventListener('message',event=>{const m=JSON.parse(event.data),p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}
 if(m.method==='Runtime.exceptionThrown')exceptions.push(m.params.exceptionDetails);
 if(m.method==='Network.requestWillBeSent')requests.push({url:m.params.request.url,method:m.params.request.method,body:m.params.request.postData});
 if(m.method==='Browser.downloadWillBegin')downloads.push(m.params);
 if(m.method==='Page.frameNavigated'&&!m.params.frame.parentId)navigationCount++;
 if(m.method==='Fetch.requestPaused'){
  const r=m.params.request,u=new URL(r.url);let deny=/^\/(synth|transcribe)(\/|$)|^\/lab\/(stems|upscale|chain|listen|train\/|artist\/(draw|upscale))/.test(u.pathname);
  if(u.pathname==='/lab/trash'&&r.method==='POST'){let b;try{b=JSON.parse(r.postData||'{}');}catch{};deny ||= !b||!['move','restore'].includes(b.op)||(b.names||b.items?.map(x=>x.name)||[]).some(n=>!n.startsWith(scope+'-'));}
  if(u.pathname==='/library/delete')deny=true;
  if(deny){blocked.push({url:r.url,body:r.postData});send('Fetch.failRequest',{requestId:m.params.requestId,errorReason:'BlockedByClient'}).catch(()=>{});}else send('Fetch.continueRequest',{requestId:m.params.requestId}).catch(()=>{});
 }
});
async function ev(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
async function until(expr,label,limit=120){for(let i=0;i<limit;i++){if(await ev(expr))return;await pause(100);}throw Error('Not ready: '+label);}
async function click(sel){await ev(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});if(!e)throw Error('Missing '+${JSON.stringify(sel)});e.click();})()`);}
async function value(id,text,event='input'){await ev(`(()=>{const e=document.getElementById(${JSON.stringify(id)});if(!e)throw Error('Missing '+${JSON.stringify(id)});e.value=${JSON.stringify(text)};e.dispatchEvent(new Event(${JSON.stringify(event)},{bubbles:true}));})()`);}
async function modal(text){await until("!!document.querySelector('.hd-back:not(.is-leaving) .hd-yes')",'modal');if(text!==undefined)await ev(`document.querySelector('.hd-back:not(.is-leaving) .hd-input').value=${JSON.stringify(text)}`);await click('.hd-back:not(.is-leaving) .hd-yes');await pause(200);}
function check(name,data){checks.push({name,passed:true,data});}
async function shot(name){const s=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(join(output,name+'.png'),Buffer.from(s.data,'base64'));}
let failure=null,docId,collectionBefore,collectionAfter;
try{
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
 await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:join(output,'downloads'),eventsEnabled:true});
 await send('Emulation.setDeviceMetricsOverride',{width:1920,height:1080,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:appUrl});await until("document.readyState!=='loading'&&!!window.HeresyWriter&&!!document.body.dataset.tab",'Studio');
 await ev("document.getElementById('autoRun').checked=false;localStorage.setItem('yue2.autoRun','0')");
 const health=await(await fetch('http://127.0.0.1:41872/health')).json();if(!health.mock_ai)throw Error('Real Writer forbidden in mock validation');check('Mock AI isolation',health);
 if(!pinOnly){
 await click('.topbar [data-tab="write"]');await click('#wrNew');await until("!!window.HeresyWriter.openDoc()&&!document.getElementById('wrDoc').hidden",'new doc');
 docId=await ev('window.HeresyWriter.openDoc().id');
 const title='Own QA '+scope,lyrics='[Verse]\nOwn browser fixture first line\nOwn browser fixture second line';
 await value('wrTitle',title);await value('wrStyle','own piano,90 bpm');await value('wrLyrics',lyrics);await value('wrNotes','**Own bold note**\n\nOnly this fixture.');
 await until(`window.HeresyWriter.openDoc()?.title===${JSON.stringify(title)}&&window.HeresyWriter.openDoc()?.lyrics===${JSON.stringify(lyrics)}`,'debounced notebook save');
 const saved=await ev(`fetch('/lab/writer?scope=${scope}&id='+encodeURIComponent(${JSON.stringify(docId)})).then(r=>r.json())`);
 if(saved.lyrics!==lyrics||saved.notes!=='**Own bold note**\n\nOnly this fixture.')throw Error('Autosave persistence mismatch');check('Notebook real UI autosave',{id:docId,title:saved.title,lyrics:saved.lyrics});
 await click('#wrNotesMode');await until("!!document.querySelector('#wrNotesView strong')",'markdown notes');check('Notes markdown preview',await ev("document.getElementById('wrNotesView').textContent"));
 await click('#wrKeep');const label='Own snapshot '+scope;await modal(label);await until(`window.HeresyWriter.openDoc().versions.some(v=>v.label===${JSON.stringify(label)})`,'snapshot');
 await value('wrLyrics',lyrics+'\nA later own edit');await until(`window.HeresyWriter.openDoc().lyrics.includes('A later own edit')`,'later save');
 const vi=await ev(`window.HeresyWriter.openDoc().versions.findIndex(v=>v.label===${JSON.stringify(label)})`);await click(`#wrVersions [data-ver="${vi}"]`);
 await until("document.getElementById('wrLyrics').readOnly",'read-only version');await click('#wrVersionRestore');await until(`!document.getElementById('wrLyrics').readOnly&&document.getElementById('wrLyrics').value===${JSON.stringify(lyrics)}`,'version restored');check('Snapshot view and restore',{label,index:vi});
 await click('#wrExport');await until("!document.getElementById('wrTitle').disabled",'export');
 let files=[];for(let i=0;i<80;i++){files=(await readdir(join(output,'downloads'))).filter(n=>n.endsWith('.json'));if(files.length)break;await pause(100);}if(!files.length)throw Error('Browser backup file missing');
 const backupPath=join(output,'downloads',files[0]),backup=JSON.parse(await readFile(backupPath,'utf8'));if(!backup.docs.some(d=>d.id===docId&&d.lyrics===lyrics))throw Error('Backup missing own doc');
 const oldCount=await ev("document.querySelectorAll('#wrList [data-doc]').length");const dom=await send('DOM.getDocument');const fileNode=await send('DOM.querySelector',{nodeId:dom.root.nodeId,selector:'#wrImportFile'});await send('DOM.setFileInputFiles',{nodeId:fileNode.nodeId,files:[backupPath]});
 await until("document.body.textContent.includes('already here')",'idempotent backup import');const newCount=await ev("document.querySelectorAll('#wrList [data-doc]').length");if(newCount!==oldCount)throw Error('Identical import duplicated documents');check('Browser backup download and upload',{file:files[0],documents:backup.docs.length,versions:backup.docs.find(d=>d.id===docId).versions.length,idempotent:true});
 await click('#wrHandBtn');await pause(300);if(await ev("!!document.querySelector('.hd-back:not(.is-leaving)')"))await modal();
 await until(`document.getElementById('title').value===${JSON.stringify(title)}&&document.getElementById('lyrics').value===${JSON.stringify(lyrics)}`,'Creator handoff');check('Notebook into Creator',{title,lyrics});
 await click('.topbar [data-tab="write"]');await value('assistBrief','Write a calm synthetic verse for an isolated mock QA.');await click('#assistBtn');
 await until("document.getElementById('draftTitle').value==='QA Mock Draft'",'mock draft');if(await ev("document.getElementById('draftLyrics').value.split('\\n').length")<5)throw Error('Draft incomplete');
 await click('#applyDraft');await until("document.getElementById('title').value==='QA Mock Draft'",'draft apply');const applied=await ev("({title:document.getElementById('title').value,style:document.getElementById('style').value,lyrics:document.getElementById('lyrics').value})");
 await click('#undoApply');await until(`document.getElementById('title').value===${JSON.stringify(title)}&&document.getElementById('lyrics').value===${JSON.stringify(lyrics)}`,'draft undo');check('Mock draft parse/apply/undo',{applied,restored:true});await shot('writer');
 }
 await click('.topbar [data-tab="collection"]');await until(`!!document.querySelector('#collGrid [data-name="${take}"]')`,'own catalog take');
 collectionBefore=await ev("fetch('/lab/catalog').then(r=>r.json())");if(collectionBefore.trash_days!==0)throw Error('Trash retention must already be disabled');
 if(pinOnly){
  await click('#collSide [data-place=""]');
  if(!await ev(`window.HeresyCollection.pinned(${JSON.stringify(take)})`)){
  await click(`#collGrid [data-name="${take}"] [data-cmenu]`);
  await until("!!document.querySelector('.hm-menu')",'pin menu');
  const clicked=await ev("(()=>{const text=window.RuachI18n?window.RuachI18n.t('Pin here'):'Pin here';const b=[...document.querySelectorAll('.hm-menu .hm-item')].find(b=>b.querySelector('.hm-label')?.textContent===text);if(!b)return false;b.click();return true;})()");if(!clicked)throw Error('Native Pin here menu missing');
  }
  await until(`window.HeresyCollection.pinned(${JSON.stringify(take)})&&!!document.querySelector('#collPins [data-name="${take}"]')`,'pinned strip');
  const oldNavigation=navigationCount;await send('Page.reload');for(let i=0;i<100&&navigationCount===oldNavigation;i++)await pause(100);if(navigationCount===oldNavigation)throw Error('Reload navigation event missing');await until(`document.readyState!=='loading'&&!!document.querySelector('.topbar [data-tab="collection"]')&&!!window.HeresyCollection?.loaded()&&window.HeresyCollection.pinned(${JSON.stringify(take)})`,'pin survives page reload');await click('.topbar [data-tab="collection"]');await until(`!!document.querySelector('#collPins [data-unpin="${take}"]')`,'unpin button');
  await click(`#collPins [data-unpin="${take}"]`);await until(`!window.HeresyCollection.pinned(${JSON.stringify(take)})`,'unpin');check('Own fixture pin reload and unpin',{take,persisted:true,finalPinned:false});await shot('pin');
 }else{
 await value('collSearch',scope);await click('#collSide [data-ws-new]');const workspace=scope+' workspace';await modal(workspace);await until(`!!document.querySelector('#collSide [data-place="${workspace}"]')`,'workspace creation');
 await click('#collSide [data-place=""]');await until(`!!document.querySelector('#collGrid [data-sel="${take}"]')`,'all fixture');await click(`#collGrid [data-sel="${take}"]`);await value('collWsPick',workspace,'change');
 await until(`document.querySelector('#collGrid [data-name="${take}"]').textContent.includes(${JSON.stringify(workspace)})`,'take assigned');
 if(!await ev(`document.querySelector('#collGrid [data-name="${take}"] [data-cfav]').getAttribute('aria-pressed')==='true'`))await click(`#collGrid [data-name="${take}"] [data-cfav]`);await until(`document.querySelector('#collGrid [data-name="${take}"] [data-cfav]').getAttribute('aria-pressed')==='true'`,'favorite');
 if(!await ev(`document.querySelector('#collGrid [data-name="${take}"] [data-crate="1"]').getAttribute('aria-pressed')==='true'`))await click(`#collGrid [data-name="${take}"] [data-crate="1"]`);await until(`document.querySelector('#collGrid [data-name="${take}"] [data-crate="1"]').getAttribute('aria-pressed')==='true'`,'rating');
 await click('#collSelNone');
 await click(`#collGrid [data-name="${take}"] [data-open]`);await until("!document.getElementById('collSheet').hidden",'take sheet');await value('sheetNote','Own QA note '+scope);await until(`window.HeresyCollection.note(${JSON.stringify(take)})===${JSON.stringify('Own QA note '+scope)}`,'note saved');await click('#collSheet [data-sheet-close]');
 check('Workspace favorite rating and note',{workspace,take,note:'Own QA note '+scope});
 // Only our explicit checkbox is selected; never select all or permanently empty trash.
 await ev(`document.querySelectorAll('#collGrid [data-sel]').forEach(e=>{if(e.checked)e.click()});document.querySelector('#collGrid [data-sel="${take}"]').click()`);
 await click('#collTrash');await modal();await until(`!document.querySelector('#collGrid [data-name="${take}"]')`,'own trash move');
 await click('#collSide [data-place="__trash"]');await until(`!!document.querySelector('#collGrid [data-tsel$="/${take}"]')`,'own trash entry');await click(`#collGrid [data-tsel$="/${take}"]`);await click('#collRestore');await until(`!document.querySelector('#collGrid [data-tsel$="/${take}"]')`,'own restored');
 await click('#collSide [data-place=""]');await until(`!!document.querySelector('#collGrid [data-name="${take}"]')`,'restored catalog');
 collectionAfter=await ev("fetch('/lab/catalog').then(r=>r.json())");const row=collectionAfter.takes.find(t=>t.name===take);if(!row?.favorite||row.rating!==1||row.note!=='Own QA note '+scope||!row.workspaces.includes(workspace))throw Error('Restored metadata mismatch');check('Own fixture trash and restore',{row,trashDays:collectionAfter.trash_days});await shot('collection');
 }
 if(blocked.length)throw Error('Unexpected blocked heavy/destructive operation');if(exceptions.length)throw Error('Browser exception');
}catch(e){failure=e.stack;try{await shot('failure');await writeFile(join(output,'failure-dom.txt'),await ev('document.body.innerText'));}catch{}}
finally{
 const applicationExternal=requests.filter(r=>/^https?:/.test(r.url)&&!['127.0.0.1','localhost','[::1]'].includes(new URL(r.url).hostname)&&new URL(r.url).hostname!=='gc.kis.v2.scr.kaspersky-labs.com');
 if(applicationExternal.length&&!failure)failure='Unexpected application external network';
 const result={passed:!failure,mockAI:true,modelInference:false,scope,take,docId,checks,exceptions,blocked,applicationExternal,requests,downloads,collectionBefore,collectionAfter,failure,checkedAt:new Date().toISOString()};await writeFile(join(output,'report.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify({passed:result.passed,checks:checks.map(c=>c.name),failure,output}));try{await send('Browser.close');}catch{}ws.close();
}
if(failure)process.exitCode=1;
