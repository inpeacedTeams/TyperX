'use strict';
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
let motionEnabled=!reducedMotion.matches, stageTimer=null;
function updateMotion(){
  const on=motionEnabled&&!reducedMotion.matches;
  document.body.dataset.motion=on?'on':'off';
  $('motion-toggle').textContent=on?'◌ Анимации: вкл':'◌ Анимации: выкл';
  $('motion-toggle').setAttribute('aria-pressed',String(on));
  $('motion-toggle').title=reducedMotion.matches?'Уменьшение движения включено в системе':'Включить или выключить анимации';
}
$('motion-toggle').onclick=()=>{motionEnabled=!motionEnabled;updateMotion();};
reducedMotion.addEventListener('change',updateMotion);updateMotion();
function stageMotion(stage){
  document.body.dataset.stage=stage;
  const pipeline=document.querySelector('.pipeline');pipeline.dataset.stage=stage;
  const index={incoming:0,thinking:1,typing:2}[stage];
  pipeline.querySelectorAll(':scope > div').forEach((node,i)=>node.classList.toggle('is-current',i===index));
  if(stageTimer){clearInterval(stageTimer);stageTimer=null;}
  $('stage-clock').textContent='';
  if(stage==='thinking'||stage==='typing'){
    const started=performance.now();
    stageTimer=setInterval(()=>{
      if(!document.hidden)$('stage-clock').textContent=Math.floor((performance.now()-started)/1000)+' с';
    },1000);
  }
}
const baseActivity=activity;
activity=function(stage,detail){baseActivity(stage,detail);stageMotion(stage);};
const motionRequest=request;
request=async function(operation,data={}){
  const id={chats:'load-chats',code:'code',login:'login',test:'test',prepare:data.mode==='manual'?'prepare-manual':'prepare',save:'save-llm'}[operation];
  const buttonElement=id?$(id):null;
  if(buttonElement)buttonElement.setAttribute('aria-busy','true');
  try{return await motionRequest(operation,data);}
  finally{if(buttonElement)buttonElement.removeAttribute('aria-busy');}
};
stageMotion('idle');
