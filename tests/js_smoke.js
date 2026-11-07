const js = require('fs').readFileSync(process.argv[2], 'utf8');
const blocks = [...js.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(x => x[1]);
const code = blocks[blocks.length - 1];
if (!code) { console.log("NO SCRIPT FOUND"); process.exit(1); }
function makeEl(id){ return {id, innerHTML:'', textContent:'', value:'', setAttribute(){}, addEventListener(){}, style:{}, classList:{toggle(){}}, dataset:{}, appendChild(){}, getBoundingClientRect(){return {width:800,height:600}}}; }
const byId = {};
byId['osia-data'] = makeEl('osia-data');
byId['osia-data'].textContent = blocks[0];
global.document = {
  getElementById(id){ if(!byId[id]) byId[id]=makeEl(id); return byId[id]; },
  querySelector(s){ return global.document.getElementById(s.replace('#','')); },
  querySelectorAll(){ return []; },
  createElementNS(){ return makeEl('svgel'); },
  addEventListener(){},
};
global.window = { addEventListener(){} };
try {
  eval(code);
} catch (e) {
  console.log("SCRIPT CRASHED: " + e.message);
  process.exit(1);
}
const rendered = Object.keys(byId).map(k => byId[k].innerHTML).join('\n---\n');
console.log("SCRIPT OK");
console.log(rendered);
