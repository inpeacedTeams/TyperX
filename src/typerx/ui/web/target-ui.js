'use strict';
// Sender selection is resolved by Python from the displayed message ID, never a supplied name.
let activeChat = null, visibleHistory = [], selectingSender = false, targetOnly = false;
function targetSummary(){
  $('target-link').textContent=target?target.sender_name+' ↗':'Выбрать автора ↗';
  $('target-banner').hidden=!target;
  $('filter-target').disabled=!target;
  $('filter-target').setAttribute('aria-pressed',String(targetOnly));
  if(target){
    $('target-name').textContent=target.sender_name;
    $('target-chat').textContent='В чате «'+target.name+'» · ID '+target.sender_id;
    const count=visibleHistory.filter(m=>m.sender_id===target.sender_id&&m.can_target).length;
    $('target-count').textContent=count+' из '+visibleHistory.length+' сообщений в контексте';
  }
  $('context-scope').textContent=target?'Модель читает только сообщения '+target.sender_name+' в чате «'+target.name+'».':'Нажми на сообщение в истории: его автор станет таргетом.';
}
async function chooseChat(chat){
  if(selectingSender)return;
  selectingSender=true;
  try{
    const rows=await request('select',{id:chat.id});
    activeChat=chat;target=null;targetOnly=false;visibleHistory=rows;
    $('history-title').textContent=chat.name+' · последние 50';
    renderChats();renderHistory();targetSummary();
    notice(chat.can_reply?'Нажми на сообщение нужного человека, чтобы выбрать таргета.':'История доступна. Автоответ здесь не поддерживается.');
  }catch(e){notice(e.message,true);}finally{selectingSender=false;}
}
renderChats=function(){
  const query=$('search').value.toLocaleLowerCase();$('chats').replaceChildren();
  for(const chat of chats.filter(c=>c.name.toLocaleLowerCase().includes(query))){
    const item=document.createElement('button');item.className='chat-choice';item.classList.toggle('selected',activeChat?.id===chat.id);item.textContent=chat.name;
    const type=document.createElement('small');type.textContent=chat.can_reply?(chat.kind==='group'?'Группа · выбор участника':'Личный чат · выбор автора'):'Только история';item.append(type);item.onclick=()=>chooseChat(chat);$('chats').append(item);
  }
  if(!$('chats').children.length){const p=document.createElement('p');p.className='empty';p.textContent='Чаты не найдены';$('chats').append(p);}
};
function renderHistory(){
  $('history').removeAttribute('aria-busy');$('history').replaceChildren();
  const rows=targetOnly&&target?visibleHistory.filter(m=>m.sender_id===target.sender_id):visibleHistory;
  for(const message of rows){
    const selectable=Boolean(message.can_target&&activeChat?.can_reply);
    const selected=Boolean(target&&message.sender_id===target.sender_id&&message.can_target);
    const bubble=document.createElement(selectable?'button':'article');
    bubble.className='bubble message-card'+(message.role==='assistant'?' own':'')+(selected?' is-target':'');
    const meta=document.createElement('span');meta.className='message-meta';
    const avatar=document.createElement('span');avatar.className='avatar';avatar.textContent=message.sender_name.slice(0,1).toLocaleUpperCase();
    const name=document.createElement('strong');name.textContent=message.sender_name;
    const tag=document.createElement('span');tag.className='sender-tag';tag.textContent=selected?'◎ Таргет':selectable?'Выбрать →':'Только просмотр';
    meta.append(avatar,name,tag);
    const text=document.createElement('span');text.className='message-content';text.textContent=message.content;bubble.append(meta,text);
    if(selectable){
      bubble.setAttribute('aria-pressed',String(selected));
      bubble.setAttribute('aria-label','Выбрать автора '+message.sender_name+' как таргета. '+message.content.slice(0,100));
      bubble.onclick=async()=>{
        if(selectingSender)return;selectingSender=true;bubble.disabled=true;
        try{target=await request('select_sender',{message_id:message.id});targetSummary();renderHistory();notice('Таргет выбран: '+target.sender_name+'. Остальные сообщения не передаются модели.');}
        catch(e){notice(e.message,true);}finally{selectingSender=false;bubble.disabled=false;}
      };
    }
    $('history').append(bubble);
  }
  if(!rows.length){const empty=document.createElement('p');empty.className='empty';empty.textContent=activeChat?'Текстовых сообщений в этом окне истории нет':'Выбери чат, затем нажми на сообщение нужного автора';$('history').append(empty);}
}
button('clear-target',async()=>{await request('clear_target');target=null;targetOnly=false;targetSummary();renderHistory();});
$('filter-target').onclick=()=>{if(!target)return;targetOnly=!targetOnly;targetSummary();renderHistory();};
const baseRequest=request;
request=async function(operation,data={}){
  // Keep current context visible until a new selection has actually succeeded.
  const box=operation==='chats'?$('chats'):operation==='select'?$('history'):null;
  if(box)box.setAttribute('aria-busy','true');
  try{
    const result=await baseRequest(operation,data);
    if(operation==='state'){
      activeChat=result.selected_chat||null;visibleHistory=result.history||[];target=result.target||null;
      targetSummary();renderHistory();
    }
    if(operation==='logout'){activeChat=null;visibleHistory=[];target=null;targetOnly=false;targetSummary();renderHistory();}
    return result;
  }finally{if(box)box.removeAttribute('aria-busy');}
};
targetSummary();
