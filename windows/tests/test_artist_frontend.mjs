import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const elements = new Map(), storage = new Map(), requests = [];
function element(id) {
  if (!elements.has(id)) {
    const el = { id, value: '', checked: false, disabled: false, hidden: false, dataset: {}, options: [], textContent: '', attributes: {}, style: {},
      classList: { toggle() {}, add() {}, remove() {} }, setAttribute(k,v) { this.attributes[k]=v; },
      querySelector() { return null; }, closest() { return element(id+'Label'); }, addEventListener() {} };
    // Native select.value becomes empty when the requested option is absent.
    Object.defineProperty(el, 'value', {get() {return this.selectedValue || '';},set(v) {
      this.selectedValue = id==='arPainter' && !this.options.some(o=>o.value===String(v)) ? '' : String(v);
    }});
    Object.defineProperty(el, 'innerHTML', {get() {return this.html || '';},set(v) {
      this.html = v; this.options = [...String(v).matchAll(/<option value="([^"]*)"/g)].map(m=>({value:m[1]}));
      if (this.options.length) this.value=this.options[0].value;
    }});
    elements.set(id, el);
  }
  return elements.get(id);
}
const shapeInputs = ['1:1','16:9','9:16'].map(value=>({value,checked:value==='1:1'}));
const labels = shapeInputs.map((input,i)=>({...element('shape'+i),querySelector:()=>input}));
const document = {documentElement:{lang:"en"},addEventListener() {},getElementById:element, querySelectorAll:sel=>sel==='#arShapes input'?shapeInputs:sel==='#arShapes label'?labels:[],querySelector:sel=>sel==="#view-artist .artist-head .col-note-two"?element("artistHeaderNote"):null,body:{dataset:{tab:'artist'}}};
let painters = [
 {key:'krea2-q4',label:'Krea Q4',need_mb:12500,ready:true,viable:true,family:'krea2'},
 {key:'krea2-q8',label:'Krea Q8',need_mb:18500,ready:true,viable:true,family:'krea2'},
 {key:'qwen2512-fp8',label:'Qwen local fp8',need_mb:22500,ready:true,viable:true,family:'qwen-image-2512',models:['own.safetensors'],lightning:false},
 {key:'qwen21',label:'Qwen research',need_mb:21000,ready:true,viable:true,family:'qwen-image-2.1',differential_mask:false}
];
let failMetadata=false;
const context = {window:{addEventListener() {}},document,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
 fetch:async url=>{requests.push(url);if(failMetadata)throw Error('synthetic offline failure');return {ok:true,status:200,json:async()=>({painters})};},console,setTimeout,clearTimeout};
vm.createContext(context);
const source=fs.readFileSync(path.join(root,'build/tools/console/heresy-artist.js'),'utf8');
// Test-only access to the actual private Draw guard; all API calls remain recorded.
vm.runInContext(source.replace('window.HeresyArtist = {','window.HeresyArtist = { __draw: draw, __runHtml: function(runs) { state.runs=runs; paintRunsList(); return $("arRuns").innerHTML; },'),context);
const app=context.window.HeresyArtist;
element('arPrompt').value='synthetic only';element('arCount').value='1';element('arMkSoft').checked=true;
let checks=0;
function check(fn){fn();checks++;}
async function select(key){storage.set('yue2.arPainter',key);await app.painters();}
const allPainters=painters;
painters=allPainters.map(p=>({...p,ready:p.key==='qwen21',viable:p.key==='qwen21'}));
storage.delete('yue2.arPainter');
element('arPainter').innerHTML='<option value="krea2-q4">Krea default before metadata</option>';
await app.painters();
check(()=>assert.equal(element('arPainter').value,'qwen21'));
check(()=>assert.deepEqual(element('arPainter').options.map(o=>o.value),['qwen21']));
check(()=>assert.equal(element('arDraw').disabled,false));
await select('krea2-q4');
check(()=>assert.equal(element('arPainter').value,'qwen21'));
await select('sdxl');
check(()=>assert.equal(element('arPainter').value,'qwen21'));
painters=allPainters;
await select('krea2-q8');
check(()=>assert.equal(element('arPainter').value,'krea2-q8'));
check(()=>assert.equal(element('arPainter').disabled,false));
check(()=>assert.equal(app.sampling.now().steps,8));
check(()=>assert.equal(app.sampling.now().sampler,'euler'));
check(()=>assert.ok(element('arSampler').options.some(o=>o.value==='res_2s')));
check(()=>assert.equal(element('arSampler').options.some(o=>o.value==='dpmpp'),false));
check(()=>assert.equal(element('arCfgBox').hidden,true));
check(()=>assert.equal(element('arMkSoft').disabled,false));
check(()=>assert.match(element('artistHeaderNote').textContent,/Local pictures/));
document.documentElement.lang='ru';
await select('krea2-q4');
check(()=>assert.match(element('artistHeaderNote').textContent,/Локальные изображения/));
check(()=>assert.equal(/Krea|Qwen|SDXL/.test(element('artistHeaderNote').textContent),false));
check(()=>assert.equal(app.resolution,undefined));
check(()=>assert.equal(elements.has('arResolutionBox'),false));
storage.set('yue2.arSampling',JSON.stringify({'krea2-q4':{steps:500,sampler:'dpmpp',schedule:'unknown'}}));
check(()=>assert.deepEqual(JSON.parse(JSON.stringify(app.sampling.now())),{steps:16,sampler:'euler',schedule:'simple'}));
check(()=>assert.deepEqual(JSON.parse(JSON.stringify(app.sampling.body())),{steps:16}));
await select('qwen21');
check(()=>assert.equal(element('arMkSoft').disabled,true));
check(()=>assert.equal(element('arMkSoft').checked,false));
check(()=>assert.match(element('arMkSoft').title,/Differential diffusion/));
check(()=>assert.equal(app.sampling.now().steps,30));
await select('krea2-q4');
check(()=>assert.equal(element('arMkSoft').disabled,false));
check(()=>assert.equal(element('arMkSoft').checked,true));
await select('qwen2512-fp8');
check(()=>assert.equal(element('arModelBox').hidden,false));
check(()=>assert.equal(element('arModelBox').style.display,''));
check(()=>assert.equal(element('arModel').value,'own.safetensors'));
check(()=>assert.equal(element('arCfgBox').hidden,false));
check(()=>assert.equal(element('arLightBox').hidden,true));
check(()=>assert.equal(app.sampling.now().steps,30));
check(()=>assert.equal(app.sampling.now().cfg,4));
// Stale ready SDXL metadata cannot resurrect a removed option or sampling family.
painters=[{key:'sdxl',label:'stale SDXL',ready:true,viable:true,need_mb:8000,family:'sdxl'},...allPainters];
await select('sdxl');
check(()=>assert.equal(element('arPainter').value,'krea2-q4'));
check(()=>assert.equal(element('arPainter').options.some(o=>o.value==='sdxl'),false));
// Installed weights with an explicit hardware refusal remain unavailable.
painters=allPainters.map(p=>({...p,ready:true,viable:false,unavailable_reason:'GPU budget does not fit'}));
await app.painters();
check(()=>assert.equal(element('arPainter').value,'__unavailable__'));
check(()=>assert.deepEqual(element('arPainter').options.map(o=>o.value),['__unavailable__']));
check(()=>assert.equal(element('arPainter').disabled,true));
check(()=>assert.equal(element('arDraw').disabled,true));
check(()=>assert.match(element('arPainter').innerHTML,/Local Artist painter unavailable/));
check(()=>assert.match(element('arDraw').dataset.tip,/GPU budget does not fit/));
check(()=>assert.equal(element('arPainterNote').hidden,false));
check(()=>assert.match(element('arPainterNote').textContent,/GPU budget does not fit/));
check(()=>assert.equal(element('arModelBox').hidden,true));
check(()=>assert.equal(element('arModelBox').style.display,'none'));
check(()=>assert.match(element('arCost').textContent,/Drawing unavailable: .*GPU budget does not fit/));
check(()=>assert.match(element('arLoraSay').textContent,/choose an available painter/));
const ownHistory={id:'own-history',painter:'sdxl',prompt:'retained synthetic history',created:1,status:'failed',error:'original recorded failure',seed:1,count:1,pictures:[]};
let historyHtml=app.__runHtml([ownHistory]);
check(()=>assert.match(historyHtml,/sdxl \(retained history\)/));
check(()=>assert.match(historyHtml,/data-act="again"[^>]* disabled/));
check(()=>assert.match(historyHtml,/original recorded failure/));
check(()=>assert.equal(/data-act="form"[^>]* disabled/.test(historyHtml),false));
check(()=>assert.equal(/data-act="trash"[^>]* disabled/.test(historyHtml),false));
const upscaleHistory={...ownHistory,kind:'upscale',painter:'upscale',factor:4};
historyHtml=app.__runHtml([upscaleHistory]);
check(()=>assert.equal(/data-act="again"[^>]* disabled/.test(historyHtml),false));

const beforeBlocked=requests.length;
app.__draw();
app.__draw({painter:'sdxl',prompt:'retired image',shapes:['1:1'],count:1});
check(()=>assert.equal(requests.length,beforeBlocked));
painters=allPainters.map(p=>({...p,ready:false,viable:false}));
await app.painters();
check(()=>assert.equal(element('arPainter').value,'__unavailable__'));
check(()=>assert.notEqual(element('arPainter').value,''));
check(()=>assert.match(element('arDraw').dataset.tip,/No installed Krea or Qwen painter/));
check(()=>assert.match(element('arCost').textContent,/Drawing unavailable: No installed Krea or Qwen painter/));
check(()=>assert.equal(element('arDraw').disabled,true));
// Availability read errors fail closed rather than retaining a fake-ready default.
painters=allPainters;
await select('krea2-q4');
failMetadata=true;
await app.painters();
check(()=>assert.equal(element('arPainter').value,'__unavailable__'));
check(()=>assert.equal(element('arDraw').disabled,true));
check(()=>assert.match(element('arPainterNote').textContent,/could not be checked/));
failMetadata=false;
await select('qwen21');
check(()=>assert.equal(element('arPainter').value,'qwen21'));
check(()=>assert.equal(element('arPainter').disabled,false));
check(()=>assert.equal(element('arDraw').disabled,false));
check(()=>assert.equal(/Drawing unavailable/.test(element('arCost').textContent),false));
historyHtml=app.__runHtml([{...ownHistory,painter:'qwen21'}]);
check(()=>assert.equal(/data-act="again"[^>]* disabled/.test(historyHtml),false));
historyHtml=app.__runHtml([ownHistory]);
check(()=>assert.match(historyHtml,/data-act="again"[^>]* disabled/));
check(()=>assert.ok(requests.every(u=>u==='/lab/artist/painters')));
check(()=>assert.equal(/SDXL|sdxl/.test(source),false));
console.log(JSON.stringify({checks,passed:true,syntheticMetadataOnly:true,synthRequests:0}));
