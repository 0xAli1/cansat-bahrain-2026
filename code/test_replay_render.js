// Minimal DOM stub to actually execute the replay logic for every sample.
const fs=require('fs');
const src=fs.readFileSync('flight_replay_script.js','utf8');
const ctxStub=new Proxy({},{get:()=>()=>{}, set:()=>true});
function el(){return {style:{},classList:{toggle(){},add(){},remove(){}},textContent:'',
  value:0,width:700,height:150,clientHeight:210,clientWidth:62,
  getContext:()=>ctxStub,addEventListener(){},onclick:null,oninput:null};}
const store={};
global.document={getElementById:id=>(store[id]=store[id]||el()),
  body:{}, querySelector:()=>null};
global.getComputedStyle=()=>({getPropertyValue:()=>''});
global.performance={now:()=>0};
let frames=0;
global.requestAnimationFrame=cb=>{frames++; if(frames<5000) cb(frames*16);};
eval(src);
// walk the whole flight through the scrubber handler
const scrub=store['scrub'];
let errors=0, seen=new Set();
for(let v=0; v<=1000; v+=5){
  try{ scrub.oninput({target:{value:v}}); seen.add(store['r_t'].textContent); }
  catch(e){ errors++; if(errors<3) console.log('ERR at',v,e.message); }
}
console.log('scrub sweep values rendered:', seen.size, 'errors:', errors);
console.log('final readouts -> t:',store['r_t'].textContent,
  'alt:',store['r_alt'].textContent,'descent:',store['r_des'].textContent,
  'temp:',store['r_temp'].textContent,'RH:',store['r_hum'].textContent,
  'phase:',store['r_phase'].textContent);
// exercise play loop
store['play'].onclick(); store['play'].onclick();
console.log('play frames requested:', frames);
