(() => {
  const root=document.querySelector('[data-work-selection-root]');if(!root)return;
  const key=`work-plan-selection:v86:${root.dataset.user}:${root.dataset.plan}`;
  const read=suffix=>{try{return JSON.parse(sessionStorage.getItem(key+suffix)||'{}');}catch{return {};}};
  const write=(suffix,value)=>{try{sessionStorage.setItem(key+suffix,JSON.stringify(value));}catch{}};
  let selected=read('');
  let applied='';try{applied=sessionStorage.getItem(key+':applied')||'';}catch{}
  if(root.dataset.clear&&root.dataset.clear!=='0'&&root.dataset.clear!==applied){
    selected={};try{sessionStorage.removeItem(key);sessionStorage.removeItem(key+':choices');sessionStorage.setItem(key+':applied',root.dataset.clear);}catch{}
    const url=new URL(location.href);url.searchParams.delete('builder_saved');history.replaceState(null,'',url);
  }
  if(/^[1-9][0-9]{0,9}$/.test(root.dataset.seed||'')&&Object.keys(selected).length<50){
    selected[root.dataset.seed]=true;write('',selected);
  }
  const form=document.querySelector('[data-selection-form]');
  const boxes=()=>[...document.querySelectorAll('[data-select-source]')];
  function draw(){
    boxes().forEach(box=>{box.checked=Boolean(selected[box.value]);});
    document.querySelectorAll('[data-selected-count]').forEach(el=>{el.textContent=String(Object.keys(selected).length);});
    const chips=document.querySelector('[data-selected-chips]');
    if(chips){chips.replaceChildren();Object.keys(selected).forEach(id=>{
      const button=document.createElement('button');button.type='button';button.className='work-plan-chip';button.textContent=`№${id} ×`;
      button.addEventListener('click',()=>{delete selected[id];write('',selected);draw();});chips.append(button);
    });}
  }
  boxes().forEach(box=>{box.removeAttribute('name');box.addEventListener('change',()=>{
    if(box.checked){if(Object.keys(selected).length>=50){box.checked=false;alert(root.dataset.limit);return;}selected[box.value]=true;}
    else delete selected[box.value];write('',selected);draw();
  });});
  document.querySelector('[data-clear-selection]')?.addEventListener('click',()=>{selected={};write('',selected);draw();});
  document.querySelector('[data-select-existing]')?.addEventListener('click',event=>{
    let ids=[];try{ids=JSON.parse(event.currentTarget.dataset.selectExisting);}catch{}
    ids.forEach(id=>{if(Object.keys(selected).length<50)selected[String(id)]=true;});write('',selected);draw();
    document.querySelector('#work-plan-bank')?.scrollIntoView({block:'start'});
  });
  document.querySelectorAll('[data-select-one]').forEach(button=>button.addEventListener('click',()=>{
    if(Object.keys(selected).length<50)selected[button.dataset.selectOne]=true;write('',selected);draw();
    document.querySelector('#work-plan-bank')?.scrollIntoView({block:'start'});
  }));
  const mode=form?.querySelector('[data-selection-mode]');
  if(mode){const saved=read(':mode:v101');if(saved==='variants'||saved==='separate')mode.value=saved;mode.addEventListener('change',()=>write(':mode:v101',mode.value));}
  form?.addEventListener('submit',event=>{
    const ids=Object.keys(selected);
    if(!ids.length){event.preventDefault();alert(root.dataset.empty);return;}
    form.querySelectorAll('[data-basket-input]').forEach(input=>input.remove());
    ids.forEach(id=>{const input=document.createElement('input');input.type='hidden';input.name='item_ids';input.value=id;input.dataset.basketInput='1';form.append(input);});
    write('',selected);
  });
  window.addEventListener('pageshow',()=>{selected=read('');draw();});draw();
})();
