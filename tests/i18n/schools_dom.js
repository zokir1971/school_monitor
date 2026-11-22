const vm=require('vm'),fs=require('fs'),args=JSON.parse(fs.readFileSync(0,'utf8'));const check=(v,m)=>{if(!v)throw Error(m)};
function el(value=''){return {value,children:[],events:{},files:[],addEventListener(e,f){this.events[e]=f},appendChild(o){this.children.push(o);if(o.selected)this.value=String(o.value)},set innerHTML(s){this.html=s;this.children=[];this.value=''},get innerHTML(){return this.html||''}}}
const ids={region_id:el('2'),district_id:el('3'),settlement:el(args.settlement),'check-all':el(),'schools-file':el(),'file-name':el()};let changes=[],confirms=[],confirmResult=false,requests=[],mode='good',ready;
const rows=[{checked:false},{checked:false}],buttons=[el()];
const sandbox={document:{getElementById(id){return ids[id]||null},querySelectorAll(q){return q==='.row-check'?rows:q==='.single-delete-btn'?buttons:[]},createElement(){return el()}},window:{addEventListener(e,f){ready=f}},console:{error(){}},confirm(s){confirms.push(s);return confirmResult},async fetch(url){requests.push(url);if(mode==='throw')throw Error('offline');return {ok:mode!=='bad',async json(){return {items:url.includes('districts')?[{id:3,name:'DATA <DISTRICT>'}]:[{name:args.settlement}]}}}}};
vm.createContext(sandbox);vm.runInContext(args.script,sandbox);
(async()=>{await ready();check(ids.district_id.value==='3','restore district');check(ids.district_id.children[0].textContent==='DATA <DISTRICT>','district data');
if(args.page==='schools'){
 check(ids.settlement.value===args.settlement,'restore settlement with quotes');ids['check-all'].checked=true;ids['check-all'].events.change();check(rows.every(r=>r.checked),'select all');
 ids['schools-file'].files=[{name:'DATA <FILE>.xlsx'}];ids['schools-file'].events.change.call(ids['schools-file']);check(ids['file-name'].textContent==='DATA <FILE>.xlsx'&&ids['file-name'].title==='DATA <FILE>.xlsx','file');ids['schools-file'].files=[];ids['schools-file'].events.change.call(ids['schools-file']);changes.push(ids['file-name'].textContent);
 let blocked=false;buttons[0].events.click({preventDefault(){blocked=true}});check(blocked,'delete cancel');confirmResult=true;blocked=false;buttons[0].events.click({preventDefault(){blocked=true}});check(!blocked,'delete confirm');
 await sandbox.loadSettlements('');changes.push(ids.settlement.innerHTML);mode='bad';await sandbox.loadSettlements('3');changes.push(ids.settlement.innerHTML);mode='good';await sandbox.loadSettlements('3',args.settlement);check(ids.settlement.value===args.settlement,'settlement exact');
}
await sandbox.loadDistricts('');changes.push(ids.district_id.innerHTML);mode='bad';await sandbox.loadDistricts('2');changes.push(ids.district_id.innerHTML);mode='throw';await sandbox.loadDistricts('2');changes.push(ids.district_id.innerHTML);mode='good';await sandbox.loadDistricts('2','3');check(ids.district_id.value==='3','district reload');
process.stdout.write(JSON.stringify({requests,changes,confirms}));})().catch(e=>{process.stderr.write(String(e));process.exitCode=1});
