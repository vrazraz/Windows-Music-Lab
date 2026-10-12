import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const elements = new Map(), storage = new Map(), requests = [];
function element(id) {
  if (!elements.has(id)) {
    const el = { id, value: '', checked: false, disabled: false, hidden: false, dataset: {}, options: [], textContent: '', attributes: {},
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
let painters = [{key:'sdxl',label:'SDXL local',need_mb:8000,ready:true,family:'sdxl',differential_mask:false,
  samplers:['euler','euler-sde','dpmpp','heun'],schedules:['simple','karras'],step_limits:[10,60],
  resolution_choices:[512,1024],resolutions_by_size:{"512":{"1:1":[512,512],"16:9":[672,384],"9:16":[384,672]}},defaults:{steps:28,cfg:5.5,sampler:'dpmpp',schedule:'simple'},resolutions:{'1:1':[1024,1024],'16:9':[1344,768],'9:16':[768,1344]}},
 {key:'krea2-q4',label:'Krea Q4',need_mb:12500,ready:true,family:'krea2'},
 {key:'qwen21',label:'Qwen research',need_mb:21000,ready:true,family:'qwen-image-2.1',differential_mask:false}];
const context = {window:{addEventListener() {}},document,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
 fetch:async url=>{requests.push(url);return {ok:true,status:200,json:async()=>({painters})};},console,setTimeout,clearTimeout};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'build/tools/console/heresy-artist.js'),'utf8'),context);
const app=context.window.HeresyArtist;
element('arPrompt').value='synthetic only';element('arCount').value='1';element('arMkSoft').checked=true;
let checks=0;
function check(fn){fn();checks++;}
async function select(key){storage.set('yue2.arPainter',key);await app.painters();}
const allPainters=painters;
painters=allPainters.map(p=>({...p,ready:p.key==='sdxl'}));
storage.delete('yue2.arPainter');
element('arPainter').innerHTML='<option value="krea2-q4">Krea default before metadata</option>';
await app.painters();
check(()=>assert.equal(element('arPainter').value,'sdxl'));
check(()=>assert.deepEqual(element('arPainter').options.map(o=>o.value),['sdxl']));
check(()=>assert.equal(element('arDraw').disabled,false));
await select('krea2-q4');
check(()=>assert.equal(element('arPainter').value,'sdxl'));
check(()=>assert.equal(app.sampling.now().sampler,'dpmpp'));
painters=allPainters;
await select('qwen21');
check(()=>assert.equal(element('arPainter').value,'qwen21'));
await select('sdxl');
check(()=>assert.match(element('artistHeaderNote').textContent,/Local pictures/));
document.documentElement.lang='ru';
await select('sdxl');
check(()=>assert.match(element('artistHeaderNote').textContent,/Локальные изображения/));
check(()=>assert.equal(/Krea|Qwen/.test(element('artistHeaderNote').textContent),false));
check(()=>assert.equal(app.sampling.now().steps,28));
check(()=>assert.equal(app.sampling.now().sampler,'dpmpp'));
check(()=>assert.equal(app.sampling.now().cfg,5.5));
check(()=>assert.deepEqual(element('arSampler').options.map(o=>o.value),['euler','euler-sde','dpmpp','heun']));
check(()=>assert.deepEqual(element('arSchedule').options.map(o=>o.value),['simple','karras']));
check(()=>assert.equal(element('arCfgBox').hidden,false));
check(()=>assert.equal(element('arMkSoft').disabled,true));
check(()=>assert.equal(element('arMkSoft').checked,false));
check(()=>assert.match(element('arMkSoft').title,/Differential diffusion/));
check(()=>assert.equal(labels[1].attributes['aria-label'],'16:9 · 1344×768'));
check(()=>assert.equal(element('arLoraAdd').disabled,false));
storage.set('yue2.arSampling',JSON.stringify({sdxl:{steps:500,sampler:'res_2s',schedule:'beta57',cfg:19}}));
check(()=>assert.deepEqual(JSON.parse(JSON.stringify(app.sampling.now())),{steps:60,cfg:10,sampler:'dpmpp',schedule:'simple'}));
check(()=>assert.equal(app.sampling.body().cfg,10));
storage.set('yue2.arSampling',JSON.stringify({sdxl:{sampler:'euler',schedule:'karras'}}));
app.sampling.paint();
check(()=>assert.equal(app.sampling.now().schedule,'simple'));
check(()=>assert.deepEqual(element('arSchedule').options.map(o=>o.value),['simple']));
storage.set('yue2.arResolution','512');
await select('sdxl');
check(()=>assert.equal(app.resolution.now(),512));
check(()=>assert.equal(element('arResolutionBox').hidden,false));
check(()=>assert.equal(labels[1].attributes['aria-label'],'16:9 · 672×384'));
await select('krea2-q4');
check(()=>assert.equal(element('arResolutionBox').hidden,true));
check(()=>assert.equal(app.sampling.now().steps,8));
check(()=>assert.equal(element('arMkSoft').disabled,false));
check(()=>assert.equal(element('arMkSoft').checked,true));
check(()=>assert.ok(element('arSampler').options.some(o=>o.value==='res_2s')));
check(()=>assert.equal(element('arSampler').options.some(o=>o.value==='dpmpp'),false));
await select('qwen21');
check(()=>assert.equal(element('arMkSoft').disabled,true));
painters=painters.map(p=>({...p,ready:false}));
await app.painters();
check(()=>assert.equal(element('arPainter').value,''));
check(()=>assert.deepEqual(element('arPainter').options.map(o=>o.value),['']));
check(()=>assert.equal(element('arDraw').disabled,true));
check(()=>assert.match(element('arDraw').dataset.tip,/Install approved local/));
check(()=>assert.ok(requests.every(u=>u==='/lab/artist/painters')));
console.log(JSON.stringify({checks,passed:true,syntheticMetadataOnly:true,synthRequests:0}));