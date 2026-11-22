"""Offline association selection UI; no DB writes or HTTP submissions."""
import copy,json,re,subprocess,unittest
from html.parser import HTMLParser
from types import SimpleNamespace as NS
from test_ui_language import environment,request
from test_task_review_i18n import context as review_context,render as render_review
from app.core.i18n import translate
from app.core.method_associations_i18n import association_name,association_error,METHOD_ASSOCIATION_ERRORS
from app.modules.schools.method_assoc import METHOD_ASSOCIATION_OPTIONS
class Fields(HTMLParser):
 def __init__(self):super().__init__();self.fields=[]
 def handle_starttag(self,tag,attrs):
  if tag in ['form','input','button']:self.fields.append((tag,tuple((k,v) for k,v in attrs if k not in ['class','title','placeholder','aria-label','aria-pressed'])))
def context(lang,filled=True):return dict(request=request(lang),user={'role':'school_admin','full_name':'DATA USER'},options=[NS(code=o.code,name=o.name,selected=i%2==0) for i,o in enumerate(METHOD_ASSOCIATION_OPTIONS)] if filled else [],error=None,success=False)
def render(data):return environment().get_template('school_admin/method_associations.html').render(**data)
class MethodAssociationsI18nTests(unittest.TestCase):
 def test_codes_checked_values_and_names(self):
  for filled in [False,True]:
   parsers=[]
   for lang in ['ru','kk']:
    data=context(lang,filled);before=copy.deepcopy(data['options']);html=render(data);p=Fields();p.feed(html);parsers.append(p)
    self.assertIn(translate('Настройка методических объединений',lang),html);self.assertEqual(data['options'],before)
    if filled:
     for option in METHOD_ASSOCIATION_OPTIONS:self.assertIn('value="'+option.code+'"',html);self.assertIn(translate(option.name,lang),html)
    else:self.assertIn(translate('Методикалық бірлестіктер тізімі табылмады.',lang),html)
   self.assertEqual(parsers[0].fields,parsers[1].fields)
 def test_real_script_counter_selection_submit(self):
  for lang in ['ru','kk']:
   html=render(context(lang));script=next(s for s in re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S) if 'updateSelectionCounter' in s)
   js='''const vm=require('vm');const el=(x={})=>Object.assign({events:{},addEventListener(e,f){this.events[e]=f}},x);const boxes=[el({checked:true,value:'mathematics'}),el({checked:false,value:'primary_school'})];const form=el({querySelectorAll(){return boxes}}),ids={'method-associations-form':form,'select-all-button':el(),'clear-all-button':el(),'selection-counter':el(),'save-button':el()};
vm.runInNewContext(SCRIPT,{document:{addEventListener(e,f){f()},getElementById(id){return ids[id]}}});const states=[ids['selection-counter'].textContent];ids['select-all-button'].events.click();states.push(ids['selection-counter'].textContent);if(!boxes.every(b=>b.checked))throw Error('all');ids['clear-all-button'].events.click();states.push(ids['selection-counter'].textContent);if(boxes.some(b=>b.checked))throw Error('clear');boxes[1].checked=true;boxes[1].events.change();states.push(ids['selection-counter'].textContent);form.events.submit();if(!ids['save-button'].disabled)throw Error('submit');process.stdout.write(JSON.stringify({states,saving:ids['save-button'].textContent,selected:boxes.filter(b=>b.checked).map(b=>b.value)}));'''.replace('SCRIPT',json.dumps(script))
   r=subprocess.run(['node','-e',js],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr);data=json.loads(r.stdout)
   self.assertEqual(data['states'],[translate('Таңдалды: ',lang)+str(n) for n in [1,2,0,1]]);self.assertEqual(data['saving'],translate('Сақталуда...',lang));self.assertEqual(data['selected'],['primary_school'])
 def test_review_selector_consistency_custom_names_escaped(self):
  for lang in ['ru','kk']:
   data=review_context(lang,'method_assoc');data['method_associations']=[NS(id=5,name='Математика және информатика'),NS(id=8,name='DATA <CUSTOM>')];html=render_review(data)
   self.assertIn(translate('Математика және информатика',lang),html);self.assertIn('DATA &lt;CUSTOM&gt;',html);self.assertIn('value="5"',html);self.assertIn('value="8"',html)
   self.assertEqual(association_name('DATA <CUSTOM>',lang),'DATA <CUSTOM>')
 def test_errors_and_success(self):
  for lang in ['ru','kk']:
   for source in METHOD_ASSOCIATION_ERRORS:
    data=context(lang);data['error']=source;self.assertIn(translate(source,lang),render(data));self.assertEqual(association_error(source,lang),translate(source,lang))
   data=context(lang);data['success']=True;self.assertIn(translate('Методикалық бірлестіктер тізімі сәтті сақталды.',lang),render(data));self.assertNotIn('private',association_error('private <stack>',lang))
if __name__=='__main__':unittest.main()
