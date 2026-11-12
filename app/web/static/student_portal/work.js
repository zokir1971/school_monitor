(() => {
  'use strict';
  const form=document.querySelector('#work');if(!form)return;
  const ru=form.dataset.language==='ru',say=(r,k)=>ru?r:k;
  const state=document.querySelector('#save-state'),error=document.querySelector('#error');
  const cards=Array.from(form.querySelectorAll('.question[data-index]'));
  const numbers=Array.from(form.querySelectorAll('[data-go]'));
  const previous=document.querySelector('#previous'),next=document.querySelector('#next'),flag=document.querySelector('#flag');
  const deadline=performance.now()+Number(form.dataset.seconds)*1000;
  let version=Number(form.dataset.version),dirty=false,serial=0,finishing=false,stopped=false;
  let inFlight=null,scheduled=null;
  let current=Math.max(0,Math.min(cards.length-1,Number(form.dataset.current)||0));
  let flagged=new Set(JSON.parse(form.dataset.flagged||'[]'));
  const controls=root=>Array.from(root.querySelectorAll('input[name],select[name],textarea[name]'));
  function status(kind,text){state.dataset.state=kind;state.textContent=text;}
  function values(){
    const data={};
    for(const el of controls(form)){
      if(el.closest('[data-order]'))continue;
      if(el.type==='checkbox'){data[el.name]??=[];if(el.checked)data[el.name].push(el.value);}
      else if(el.type==='radio'){data[el.name]??='';if(el.checked)data[el.name]=el.value;}
      else data[el.name]=el.value;
    }
    for(const group of form.querySelectorAll('[data-order]'))data[group.dataset.order]=Array.from(group.querySelectorAll('select'),e=>e.value);
    return data;
  }
  function hasAnswer(card){
    return controls(card).some(el=>(el.type==='radio'||el.type==='checkbox')?el.checked:String(el.value).trim()!=='');
  }
  function navigation(){return {current,flagged:Array.from(flagged).sort((a,b)=>a-b)};}
  function draw(focus=false){
    let answered=0;
    cards.forEach((card,index)=>{
      const yes=hasAnswer(card);if(yes)answered++;
      card.hidden=index!==current;
      const button=numbers[index];button.classList.toggle('answered',yes);button.classList.toggle('flagged',flagged.has(index));
      if(index===current)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');
      const label=say('Задание ','Тапсырма ')+(index+1)+', '+(yes?say('есть ответ','жауап бар'):say('не отвечено','жауап берілмеді'))+(flagged.has(index)?say(', отмечено для возврата',', қайта оралу үшін белгіленді'):'');
      button.setAttribute('aria-label',label);button.title=label;
      button.querySelector('.nav-marker').textContent=(yes?'✓':'○')+(flagged.has(index)?' ⚑':'');
    });
    previous.disabled=current===0;next.disabled=current===cards.length-1;
    flag.setAttribute('aria-pressed',String(flagged.has(current)));
    flag.textContent=flagged.has(current)?say('Снять отметку','Белгіні алып тастау'):say('Отметить для возврата','Қайта оралу үшін белгілеу');
    document.querySelector('#progress').textContent=say('Есть ответы: ','Жауаптар бар: ')+answered+' / '+cards.length+' · '+say('Для возврата: ','Қайта оралу үшін: ')+flagged.size;
    if(focus){cards[current].focus({preventScroll:true});cards[current].scrollIntoView({block:'start',behavior:'auto'});}
  }
  function schedule(){clearTimeout(scheduled);scheduled=setTimeout(()=>{if(!finishing)save(false);},300);}
  function changed(){
    if(stopped||finishing)return;dirty=true;serial++;draw();
    status('pending',say('Сохранение…','Сақталуда…'));schedule();
  }
  function go(index){if(stopped||finishing||index===current)return;current=index;changed();draw(true);}
  numbers.forEach((button,index)=>button.addEventListener('click',()=>go(index)));
  previous.addEventListener('click',()=>go(Math.max(0,current-1)));
  next.addEventListener('click',()=>go(Math.min(cards.length-1,current+1)));
  flag.addEventListener('click',()=>{if(stopped||finishing)return;if(flagged.has(current))flagged.delete(current);else flagged.add(current);changed();});
  form.addEventListener('input',event=>{
    const math=event.target.closest('math-field[data-input]');
    if(math)form.querySelector(`input[name="${math.dataset.input}"]`).value=math.value;
    if(math||event.target.matches('input[name],select[name],textarea[name]'))changed();
  });
  function orderOptions(group){
    const selects=Array.from(group.querySelectorAll('select'));
    for(const select of selects)for(const option of select.options)option.disabled=!!option.value&&selects.some(other=>other!==select&&other.value===option.value);
  }
  form.addEventListener('change',event=>{
    if(!event.target.matches('input[name],select[name],textarea[name]'))return;
    changed();const group=event.target.closest('[data-order]');if(group)orderOptions(group);
  });
  form.querySelectorAll('[data-order]').forEach(orderOptions);
  for(const button of form.querySelectorAll('[data-clear]'))button.addEventListener('click',()=>{
    if(stopped||finishing)return;
    for(const el of form.querySelectorAll(`input[name="${button.dataset.clear}"]`))el.checked=false;
    changed();
  });
  function disableInputs(){for(const el of form.querySelectorAll('input,select,textarea,math-field')){el.disabled=true;if(el.tagName==='MATH-FIELD')el.readOnly=true;}}
  function freeze(){stopped=true;disableInputs();for(const el of form.querySelectorAll('button'))el.disabled=true;}
  async function transmit(submit){
    const mark=serial;
    status('pending',say('Сохранение…','Сақталуда…'));error.textContent='';
    try{
      const response=await fetch(`/attempt/${form.dataset.attempt}/save`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':form.dataset.csrf},body:JSON.stringify({version,responses:values(),navigation:navigation(),submit}),signal:AbortSignal.timeout(20000)});
      const result=await response.json();
      if(!response.ok){
        if(response.status===409||response.status===401||response.status===403){freeze();status('error',say('Не сохранено','Сақталмады'));error.textContent=result.message+say(' Обновите страницу для продолжения.',' Жалғастыру үшін бетті жаңартыңыз.');}
        else {status('error',say('Не сохранено','Сақталмады'));error.textContent=result.message||say('Проверьте ответы и повторите сохранение.','Жауаптарды тексеріп, қайта сақтаңыз.');}
        return false;
      }
      version=result.version;
      if(result.status!=='active'){freeze();location.replace('/session');return true;}
      if(mark===serial)dirty=false;
      status(dirty?'pending':'saved',dirty?say('Сохранение…','Сақталуда…'):say('Сохранено','Сақталды'));
      return true;
    }catch(e){
      status('offline',say('Нет связи, ответ ещё не сохранён','Байланыс жоқ, жауап әлі сақталмады'));
      error.textContent=say('Не закрывайте страницу. Повторим сохранение после восстановления связи.','Бетті жаппаңыз. Байланыс қалпына келгенде қайта сақтаймыз.');return false;
    }
  }
  async function save(submit=false){
    if(stopped)return false;
    if(inFlight)return false;
    let ok=false;
    inFlight=transmit(submit);
    try{ok=await inFlight;return ok;}
    finally{inFlight=null;if(ok&&dirty&&!finishing&&!stopped)schedule();}
  }
  setInterval(()=>{if(!finishing&&(dirty||performance.now()>=deadline))save(false);},5000);
  window.addEventListener('online',()=>{if(dirty&&!stopped)save(false);});
  setInterval(()=>{
    const seconds=Math.max(0,Math.ceil((deadline-performance.now())/1000));
    document.querySelector('#timer').textContent=say('Осталось: ','Қалған уақыт: ')+Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');
    if(seconds===0&&!stopped){disableInputs();if(!inFlight)save(false);}
  },500);
  document.querySelector('#save').addEventListener('click',()=>save(false));
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(stopped||finishing)return;
    const unanswered=cards.filter(card=>!hasAnswer(card)).length;
    const summary=say('Без ответа: ','Жауапсыз: ')+unanswered+'; '+say('для возврата: ','қайта оралу үшін: ')+flagged.size+'.\n';
    if(!confirm(summary+say('Завершить предмет? Изменить ответы после отправки будет нельзя.','Пәнді аяқтау керек пе? Жібергеннен кейін жауаптарды өзгерту мүмкін емес.')))return;
    finishing=true;disableInputs();for(const button of form.querySelectorAll('button'))button.disabled=true;clearTimeout(scheduled);
    if(inFlight)await inFlight;
    if(!stopped)await save(true);
    finishing=false;
    if(!stopped){
      for(const button of form.querySelectorAll('button'))button.disabled=false;
      if(performance.now()<deadline)for(const el of form.querySelectorAll('input,select,textarea,math-field')){el.disabled=false;if(el.tagName==='MATH-FIELD')el.readOnly=el.hasAttribute('read-only');}
      form.querySelectorAll('[data-order]').forEach(orderOptions);draw();
    }
  });
  window.addEventListener('beforeunload',e=>{if(dirty&&!stopped){e.preventDefault();e.returnValue='';}});
  draw();status('saved',say('Сохранено','Сақталды'));
})();
