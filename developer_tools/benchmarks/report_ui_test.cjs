// Offline interaction check; no browser packages, network or external assets.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(process.argv[2],'utf8');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.listeners={};this.value='';this.style={setProperty(){}};this.classList={toggle(){}};this._text='';}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=[...nodes];this._text='';}
 scrollIntoView(){}
 setAttribute(key,value){this.attributes[key]=value;}
 addEventListener(type,handler){this.listeners[type]=handler;}
 get textContent(){return this._text+this.children.map(n=>n.textContent||'').join(' ');}
 set textContent(value){this._text=String(value);this.children=[];}
 get selectedOptions(){return [{textContent:this.value}];}
}
const nodes=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element('div')]));
for(const id of ['run','level','phase'])nodes.get(id).value='all';nodes.get('metric').value='execution_first_text';
const context=vm.createContext({Intl,Set,Map,document:{getElementById:id=>{assert(nodes.has(id),'unknown ID '+id);return nodes.get(id);},createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)}});
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
vm.runInContext(script,context,{timeout:10000});
const evaluate=code=>vm.runInContext(code,context,{timeout:10000});
assert.equal(evaluate('allSelectedTurns().length'),20);
assert.equal(nodes.get('cards').children.length,2);
assert.equal(nodes.get('rows').children.length,20);
assert.match(nodes.get('component-coverage').textContent,/20 tours observés · 20 fenêtres mesurables · 1 tours/);
assert.match(nodes.get('detail-title').textContent,/Swift/);
assert.equal(nodes.get('call-map').children.length,1);
assert.equal(nodes.get('service-map').children[0].tag,'svg');
assert.match(nodes.get('service-map').textContent,/Runtime.*LLM/);
assert.equal(evaluate(`observedCalls({rootId:'root',spans:[{id:'server',parent:'root',kind:2,service:'control-plane',peer:'unknown'},{id:'call',parent:'server',kind:3,service:'control-plane',peer:'fred-agents'},{id:'child',parent:'call',kind:2,service:'fred-agents',peer:'unknown'},{id:'internal',parent:'child',kind:1,service:'fred-agents',peer:'mcp'}]}).edges.length`),2);
assert.equal(evaluate(`observedCalls({rootId:'root',spans:[{parent:'root',kind:1,service:'fred-agents',peer:'mcp'}]}).edges.length`),0);
assert.match(nodes.get('call-map').textContent,/Client \(observation\).*LLM.*appel client vers llm/);
assert.match(nodes.get('detail-coverage').textContent,/LLM 1.?000 ms/);
assert(nodes.get('waterfall').children.length>1);
assert.match(nodes.get('waterfall').textContent,/v2.react.model.*statut non renseigné.*premier fragment LLM 0 ms/);
nodes.get('phase').value='following';nodes.get('phase').listeners.change();
assert.equal(evaluate('allSelectedTurns().length'),18);
assert.match(nodes.get('detail-warnings').textContent,/ne porte pas de corrélation/);
nodes.get('run').value='1';nodes.get('run').listeners.change();
assert.equal(evaluate('allSelectedTurns().length'),9);
assert.equal(nodes.get('cards').children.length,1);
assert.match(nodes.get('detail-title').textContent,/Weaver/);
assert.match(nodes.get('component-coverage').textContent,/0 tours avec des spans/);
nodes.get('detail-next').listeners.click();assert.match(nodes.get('detail-title').textContent,/tour 3/);
nodes.get('rows').children[4].children.at(-1).children[0].listeners.click();assert.match(nodes.get('detail-title').textContent,/tour 6/);
nodes.get('phase').value='first';nodes.get('phase').listeners.change();
assert.equal(evaluate('allSelectedTurns().length'),1);assert(nodes.get('detail-next').disabled);assert(nodes.get('detail-previous').disabled);
nodes.get('metric').value='auth_refresh';nodes.get('metric').listeners.change();
assert.match(nodes.get('cards').textContent,/Non mesuré/);
assert(!nodes.get('components').textContent.includes('NaN'));
assert.equal(evaluate('summary([1,2,100]).p95'),100);
// Component evidence includes failures; client latency keeps successful samples.
nodes.get('phase').value='all';nodes.get('run').value='all';nodes.get('metric').value='execution_first_text';
evaluate("runs[0].turns[0].outcome='error'; render()");
assert.equal(evaluate('samples(allSelectedTurns().map(({t})=>t)).length'),19);
assert.match(nodes.get('components').textContent,/LLM 1 \/ 10 1.?000 ms/);
// A trace with no usable client end is visible but not a duration sample.
evaluate('runs[0].turns[0].detail.duration=null; render()');
assert.match(nodes.get('component-coverage').textContent,/20 tours observés · 19 fenêtres mesurables · 1 tours avec des spans importés/);
assert.match(nodes.get('components').textContent,/LLM 0 \/ 9 Non mesuré/);
// Concurrency filtering and an empty selection do not preserve stale detail.
nodes.get('level').value='999';nodes.get('level').listeners.change();
assert.equal(evaluate('allSelectedTurns().length'),0);
assert.equal(nodes.get('detail-title').textContent,'Aucun tour sélectionné');
assert(nodes.get('detail-next').disabled);assert(nodes.get('detail-previous').disabled);
console.log('Offline report interactions passed');
