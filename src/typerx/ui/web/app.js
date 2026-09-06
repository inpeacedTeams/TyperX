'use strict';
const $ = id => document.getElementById(id);
let bridge = null, serial = 0, config = null, chats = [], target = null, editing = null;
const pending = new Map();
const labels = {idle:'Не запущен',ready:'Готов к F8',incoming:'Новое сообщение',thinking:'Думает',typing:'Печатает',listening:'Слушает',error:'Остановлен с ошибкой'};
function notice(text, error=false){$('notice').textContent=text;$('notice').hidden=!text;$('notice').classList.toggle('error',error);}
function view(name){document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!=='view-'+name);document.querySelectorAll('.nav').forEach(el=>el.classList.toggle('active',el.dataset.view===name));}
function request(operation,data={}){
  if(!bridge)return Promise.reject(new Error('Открой TyperX на Windows: в браузерном предпросмотре подключения недоступны.'));
  const id=String(++serial);
  return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error('Операция выполняется дольше минуты. Проверь состояние перед повтором.'));},65000);pending.set(id,{resolve,reject,timer});bridge.request(JSON.stringify({id,operation,data}));});
}
function activity(stage,detail){
  $('stage').textContent=labels[stage]||stage;$('detail').textContent=detail;
  $('stage').classList.toggle('running',['listening','thinking','typing','incoming'].includes(stage));
  const li=document.createElement('li'), dot=document.createElement('span'), box=document.createElement('div'), title=document.createElement('strong'), desc=document.createElement('p');
  dot.className='event-dot';title.textContent=(labels[stage]||stage)+' · '+new Date().toLocaleTimeString('ru',{hour:'2-digit',minute:'2-digit'});desc.textContent=detail;box.append(title,desc);li.append(dot,box);$('events').prepend(li);while($('events').children.length>30)$('events').lastChild.remove();
  if(stage==='error')notice(detail,true);
}
function receive(raw){
  const value=JSON.parse(raw);
  if(value.event==='state'){activity(value.stage,value.detail);return;}
  const item=pending.get(value.id);
  if(item){clearTimeout(item.timer);pending.delete(value.id);value.ok?item.resolve(value.data):item.reject(new Error(value.error));}
  else if(!value.ok)notice(value.error,true);
}
function button(id,fn){$(id).addEventListener('click',async()=>{const el=$(id);el.disabled=true;try{await fn();}catch(e){notice(e.message,true);}finally{el.disabled=false;}});}
function presetOptions(){
  for(const id of ['live-preset','preset-select']){
    $(id).replaceChildren();for(const p of config.presets){const option=document.createElement('option');option.value=p.id;option.textContent=p.name;$(id).append(option);}
  }
  $('live-preset').value=config.active_preset;
  if(!config.presets.some(p=>p.id===editing))editing=config.active_preset;
  $('preset-select').value=editing;
}
function fill(){
  for(const key of ['api_id','phone','base_url','model','wpm','words'])$(key).value=config[key];
  $('api_hash').value='';$('api_key').value='';$('clear-key').checked=false;
  $('api_hash').placeholder=config.has_api_hash?'Сохранён · оставь пустым, чтобы не менять':'Введи API hash';
  $('api_key').placeholder=config.has_api_key?'Сохранён · оставь пустым, чтобы не менять':'Не указан';
  presetOptions();editPreset();
}
function values(){
  if(!config)throw new Error('Подожди загрузки приложения');
  const raw=structuredClone(config);for(const key of ['api_id','phone','base_url','model'])raw[key]=$(key).value;
  raw.wpm=Number($('wpm').value);raw.words=Number($('words').value);raw.active_preset=$('live-preset').value;
  raw.api_hash=$('api_hash').value;raw.api_key=$('api_key').value;raw.clear_api_key=$('clear-key').checked;
  return raw;
}
async function save(){config=await request('save',values());fill();}
function promptRow(value){
  const row=document.createElement('div');row.className='prompt-row';const label=document.createElement('label');label.textContent='Системный промпт';const area=document.createElement('textarea');area.rows=5;area.maxLength=6000;area.value=value;label.append(area);const remove=document.createElement('button');remove.textContent='Убрать личность';remove.onclick=()=>{if($('prompts').children.length>1)row.remove();else notice('В наборе нужна хотя бы одна личность',true);};row.append(label,remove);$('prompts').append(row);
}
function editPreset(){
  if(!config)return;editing=$('preset-select').value;const p=config.presets.find(item=>item.id===editing);if(!p)return;
  $('preset-name').value=p.name;$('prompts').replaceChildren();p.prompts.forEach(promptRow);
}
function renderChats(){
  const query=$('search').value.toLocaleLowerCase();$('chats').replaceChildren();
  for(const c of chats.filter(item=>item.name.toLocaleLowerCase().includes(query))){const el=document.createElement('button');el.textContent=c.name;el.classList.toggle('selected',target?.id===c.id);const small=document.createElement('small');small.textContent=c.can_reply?'Личный чат':'Только просмотр истории';el.append(small);el.onclick=async()=>{el.disabled=true;try{const history=await request('select',{id:c.id});target=c;$('target-link').textContent=c.name+' ↗';$('history-title').textContent=c.name+' · последние 50';$('history').replaceChildren();for(const m of history){const bubble=document.createElement('div');bubble.className='bubble'+(m.role==='assistant'?' own':'');bubble.textContent=m.content;$('history').append(bubble);}if(!history.length)$('history').textContent='Текстовых сообщений нет';renderChats();notice(c.can_reply?'Собеседник выбран. Настрой модель и вернись к живому циклу.':'История загружена. Автоответ в этом чате недоступен.');}catch(e){notice(e.message,true);}finally{el.disabled=false;}};$('chats').append(el);}
  if(!$('chats').children.length)$('chats').textContent='Чаты не найдены';
}
document.querySelectorAll('.nav').forEach(el=>el.onclick=()=>view(el.dataset.view));
document.querySelector('.brand').onclick=e=>{e.preventDefault();view('live');};
$('target-link').onclick=()=>view('telegram');$('preset-select').onchange=editPreset;$('search').oninput=renderChats;
$('stop').onclick=()=>{if(bridge){bridge.stop();notice('Запрошена остановка. Проверь черновик в Telegram.');}else notice('Предпросмотр: активного цикла нет');};
$('live-preset').onchange=async()=>{try{await save();notice('Активный пресет сохранён');}catch(e){$('live-preset').value=config.active_preset;notice(e.message,true);}};
button('save-llm',async()=>{await save();notice('Настройки сохранены локально');});
button('test',async()=>{await save();$('test-result').textContent='Проверяем подключение…';try{const r=await request('test');$('test-result').textContent=r.message;}catch(e){$('test-result').textContent=e.message;throw e;}});
button('code',async()=>{await save();const r=await request('code');$('auth-status').textContent=r.authorized?'Аккаунт уже подключён. Загрузи чаты.':'Код отправлен. Проверь Telegram / SMS.';});
button('login',async()=>{try{const r=await request('login',{code:$('login-code').value,password:$('password').value});$('auth-status').textContent=r.password_needed?'Нужен пароль 2FA. Введи его и подтверди вход ещё раз.':'Вход выполнен. Можно загружать чаты.';}finally{$('login-code').value='';$('password').value='';}});
button('logout',async()=>{await request('logout');chats=[];target=null;renderChats();$('history').replaceChildren();$('target-link').textContent='Выбрать чат ↗';$('auth-status').textContent='Выход выполнен, локальная сессия удалена';});
button('load-chats',async()=>{chats=await request('chats');renderChats();notice('Чаты загружены');});
button('prepare',async()=>{await save();await request('prepare',{mode:'ai',consent:$('consent').checked});notice('Открой пустое поле выбранного чата в Telegram и нажми F8. F9 — остановка.');});
button('prepare-manual',async()=>{await save();await request('prepare',{mode:'manual',text:$('manual-text').value});notice('Открой пустое поле в другом приложении и нажми F8');});
button('new-preset',async()=>{if(!config)return;if(config.presets.length>=30)throw new Error('Максимум 30 пресетов');const id='preset-'+Date.now();config.presets.push({id,name:'Новый пресет',prompts:['Отвечай кратко и дружелюбно.']});editing=id;presetOptions();editPreset();notice('Отредактируй новый набор и нажми «Сохранить набор»');});
button('add-prompt',async()=>{if($('prompts').children.length>=8)throw new Error('Максимум 8 личностей в одном наборе');promptRow('');});
button('save-preset',async()=>{const raw=values();const p=raw.presets.find(item=>item.id===editing);p.name=$('preset-name').value;p.prompts=[...$('prompts').querySelectorAll('textarea')].map(el=>el.value);config=await request('save',raw);fill();notice('Набор сохранён');});
button('delete-preset',async()=>{if(config.presets.length===1)throw new Error('Нельзя удалить последний пресет');const raw=values();raw.presets=raw.presets.filter(p=>p.id!==editing);if(raw.active_preset===editing)raw.active_preset=raw.presets[0].id;config=await request('save',raw);editing=config.active_preset;fill();notice('Пресет удалён');});
if(window.qt&&window.QWebChannel){new QWebChannel(qt.webChannelTransport,async channel=>{bridge=channel.objects.studio;bridge.response.connect(receive);try{const state=await request('state');config=state.config;chats=state.chats;target=state.target;fill();if(config.warning)notice(config.warning,true);}catch(e){notice(e.message,true);}});}
else{notice('Предпросмотр интерфейса · подключения доступны в настольном TyperX');}
