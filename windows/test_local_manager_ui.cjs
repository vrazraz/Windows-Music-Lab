'use strict';
// Actual UI functions in Node VM with a deterministic DOM, events and fetch boundary.
// No packages, browser profiles, installed models or network calls are used.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');

class Element {
  constructor(id='') { this.id=id; this.hidden=false; this.disabled=false; this.textContent=''; this.className=''; this.value=''; this.dataset={}; this.events={}; this.controls=[]; this.classList={contains:()=>false}; }
  set innerHTML(value) {
    this.html=value;
    this.controls=[];
    for (const match of value.matchAll(/<(button|select)\b([^>]*)>/g)) {
      const element=new Element(); element.tag=match[1]; element.hidden=/\bhidden\b/.test(match[2]); element.disabled=/\bdisabled\b/.test(match[2]);
      for(const attr of match[2].matchAll(/([\w-]+)="([^"]*)"/g)) {
        if(attr[1].startsWith('data-')) element.dataset[attr[1].slice(5).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase())]=attr[2];
      }
      this.controls.push(element);
    }
  }
  get innerHTML() { return this.html||''; }
  addEventListener(type,listener) { (this.events[type] ||= []).push(listener); }
  closest(selector) { return selector.startsWith('button') ? this : null; }
  fire(type,target=this) { for(const listener of this.events[type]||[]) listener.call(this,{target}); }
}

function harness(filename, response, preferences={}) {
  const ids=['view-engine','modelsCard','wtParts','wtLine','wtFetch','wtProg','wtCheck','wtExtras','wtLog','wtRestart','updLine','updEvery','updMode','updRc','updWhy','updRun','updNotes','updCheck'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element(id)]));
  const requests=[], dialogs=[], toasts=[], opened=[], timers=new Map(), storage=new Map(); let sequence=0;
  if(Object.keys(preferences).length) storage.set('yue2.updates',JSON.stringify(preferences));
  const window={addEventListener(){},open:(...args)=>opened.push(args),HeresyDialog:{
    confirm:(...args)=>{dialogs.push(['confirm',...args]);return Promise.resolve(true);},
    choose:(...args)=>{dialogs.push(['choose',...args]);return Promise.resolve('never');},
    alert:(...args)=>{dialogs.push(['alert',...args]);return Promise.resolve();}
  }};
  const context=vm.createContext({window,document:{getElementById:id=>elements[id]||null},location:{search:'',reload(){}},
    localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},
    fetch:(url,options)=>{requests.push({url,method:options?.method||'GET',body:options?.body});return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(response(url,options))});},
    setTimeout:(callback,ms)=>{timers.set(++sequence,{callback,ms});return sequence;},clearTimeout:id=>timers.delete(id),
    setInterval:(callback,ms)=>{timers.set(++sequence,{callback,ms,interval:true});return sequence;},clearInterval:id=>timers.delete(id),
    console,Date,Promise});
  vm.runInContext(fs.readFileSync(path.join(root,'build/tools/console',filename),'utf8'),context,{filename});
  return {window,elements,requests,dialogs,toasts,opened,timers,storage,hooks:{toast:(...args)=>toasts.push(args)},
    async flush(){for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));}};
}

const localWeights={mode:'local',script:false,download_enabled:false,notice:'Local presence and size only; SHA256 was not validated.',now:100,
  last:{at:100,mode:'local-presence-and-size',counts:{here:1,missing:1,differs:1,unknown:0,failed:0},
    parts:[{part:'backbone',label:'Backbone',size:'4.3 GB',rows:[{state:'here',text:'model.gguf'},{state:'differs',text:'partial.gguf'},{state:'missing',text:'vae.gguf'}]}]},
  extras:[{name:'artwork',label:'Artwork',what:'Local models',variants:[{id:'q4',label:'Krea 2 Muse Q4',size:'26 GB',here:false}]}],
  job:{status:'running',kind:'fetch',started:100,which:{part:'backbone'},expect:4000,written:1000,lines:['fake legacy job']}};
const localUpdate={mode:'local',lookup_disabled:true,current:'2.0.0-rc5',newer:true,checked:0,can_run:false,running:false,
  latest:{version:'99.0.0',notes:'Cached release',url:'https://evil.invalid'},why:'Update manually from https://github.com/vrazraz/Windows-Music-Lab after reviewing your local branch.'};
let passed=0;
async function test(name,fn){await fn();passed++;console.log('PASS '+name);}

(async()=>{
  await test('Local weights render inventory, enable Check and hide every fetch control',async()=>{
    const h=harness('heresy-weights.js',()=>localWeights);h.window.HeresyWeights.init(h.hooks);await h.window.HeresyWeights.load();
    assert.equal(h.elements.wtCheck.disabled,false);assert.equal(h.elements.wtFetch.hidden,true);assert.equal(h.elements.wtFetch.disabled,true);
    assert.equal(h.elements.wtParts.controls.length,0);assert.equal(h.elements.wtExtras.controls.length,0);
    assert.match(h.elements.wtLine.textContent,/SHA256 was not validated/);assert.match(h.elements.wtParts.innerHTML,/model\.gguf/);
    assert.doesNotMatch(h.elements.wtParts.innerHTML,/own copies kept|all expected sizes match/);
    assert.equal(h.window.HeresyWeights.state().running,false);assert.equal(h.elements.wtLog.hidden,true);assert.equal(h.elements.wtRestart.hidden,true);
    assert.equal(h.dialogs.length,0);assert.equal(h.timers.size,0);
  });
  await test('Local weights Check invokes actual local API and repeated hidden fetch events are blocked',async()=>{
    const h=harness('heresy-weights.js',()=>localWeights);h.window.HeresyWeights.init(h.hooks);await h.window.HeresyWeights.load();
    h.elements.modelsCard.fire('click',h.elements.wtCheck);await h.flush();
    assert.ok(h.requests.some(r=>r.url==='/lab/weights/check'&&r.method==='POST'));
    for(const button of [h.elements.wtFetch,Object.assign(new Element(),{dataset:{wtPart:'backbone'}}),Object.assign(new Element(),{dataset:{wtExtra:'artwork'}})]){
      button.disabled=false;h.elements.modelsCard.fire('click',button);
    }
    await h.flush();assert.equal(h.dialogs.length,0);assert.equal(h.requests.filter(r=>r.url.includes('/fetch')).length,0);
  });
  await test('Legacy weights retain explicit confirmed download behavior',async()=>{
    const data={...localWeights,mode:'legacy',script:true,download_enabled:true,job:null};
    const h=harness('heresy-weights.js',()=>data);h.window.HeresyWeights.init(h.hooks);await h.window.HeresyWeights.load();
    assert.equal(h.elements.wtFetch.hidden,false);assert.ok(h.elements.wtParts.controls.some(c=>c.dataset.wtPart==='backbone'));
    h.elements.modelsCard.fire('click',h.elements.wtFetch);await h.flush();
    assert.equal(h.dialogs.length,1);assert.equal(h.requests.filter(r=>r.url==='/lab/weights/fetch'&&r.method==='POST').length,1);
  });
  await test('Local updater paints manual fork status without claiming a release check',async()=>{
    const h=harness('heresy-updates.js',()=>localUpdate);h.window.HeresyUpdates.init(h.hooks);await h.window.HeresyUpdates.refresh();
    assert.match(h.elements.updLine.textContent,/release lookup is disabled/);assert.doesNotMatch(h.elements.updLine.textContent,/up to date|is out/i);
    assert.equal(h.elements.updEvery.disabled,true);assert.equal(h.elements.updEvery.value,'never');assert.equal(h.elements.updMode.disabled,true);assert.equal(h.elements.updRc.disabled,true);
    assert.equal(h.elements.updRun.hidden,true);assert.equal(h.elements.updRun.disabled,true);assert.match(h.elements.updWhy.textContent,/vrazraz\/Windows-Music-Lab/);
    await h.window.HeresyUpdates.check(true);
    assert.ok(h.toasts.length);assert.doesNotMatch(h.toasts.at(-1)[0],/up to date|is out/i);assert.match(h.toasts.at(-1)[0],/manually/);
    assert.ok(h.requests.every(r=>r.url==='/lab/update'&&r.method==='GET'));
  });
  await test('Local schedule, offer and gems execute no dialogs, downloads or preference changes',async()=>{
    const prefs={mode:'auto',every:'day',first:Date.now()-3*86400000,asked:false,seen:''};
    const h=harness('heresy-updates.js',()=>localUpdate,prefs);h.window.HeresyUpdates.init(h.hooks);const before=h.storage.get('yue2.updates');
    await h.window.HeresyUpdates.schedule();await h.window.HeresyUpdates.offer(localUpdate,true);await h.window.HeresyUpdates.gems(localUpdate);
    assert.equal(h.dialogs.length,0);assert.equal(h.opened.length,0);assert.equal(h.storage.get('yue2.updates'),before);
    assert.ok(h.requests.every(r=>r.url==='/lab/update'&&r.method==='GET'));
    assert.ok([...h.timers.values()].every(t=>!t.interval));
  });
  await test('Explicit local repository button opens own fork, never cached release URL',async()=>{
    const h=harness('heresy-updates.js',()=>localUpdate);h.window.HeresyUpdates.init(h.hooks);await h.window.HeresyUpdates.refresh();
    h.elements.updNotes.fire('click');assert.equal(h.opened.length,1);assert.equal(h.opened[0][0],'https://github.com/vrazraz/Windows-Music-Lab');assert.equal(h.dialogs.length,0);
  });
  await test('Manual check before initial mode discovery still avoids false Up to date toast',async()=>{
    const h=harness('heresy-updates.js',()=>localUpdate);h.window.HeresyUpdates.init(h.hooks);await h.window.HeresyUpdates.check(true);
    assert.match(h.toasts.at(-1)[0],/manually/);assert.doesNotMatch(h.toasts.at(-1)[0],/up to date/i);assert.equal(h.dialogs.length,0);
  });
  await test('Legacy schedule retains release check and release offer',async()=>{
    const update={current:'2.0.0',newer:true,checked:0,can_run:false,latest:{version:'2.1.0',notes:'Release',url:'https://github.com/vrazraz/Windows-Music-Lab/releases'},why:'manual'};
    const h=harness('heresy-updates.js',url=>url==='/lab/collection/diamonds'?{sets:[]}:update,{mode:'ask',every:'day',asked:true,seen:'2.0.0',first:Date.now()});
    h.window.HeresyUpdates.init(h.hooks);await h.window.HeresyUpdates.schedule();
    assert.ok(h.requests.some(r=>r.url==='/lab/update'&&r.method==='POST'));assert.ok(h.dialogs.some(d=>d[0]==='confirm'));
    assert.ok(h.opened.some(args=>args[0]===update.latest.url));
  });
  console.log('\n'+passed+' UI behavior checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
