/* Safe read-only rendering of the canonical explanation_layout output. */
(() => {
  if (window.QBMathProse?.version === 144) return;
  const symbols = {"in": "∈", "notin": "∉", "ni": "∋", "cap": "∩", "cup": "∪", "subset": "⊂", "subseteq": "⊆", "subsetneq": "⊊", "supset": "⊃", "supseteq": "⊇", "emptyset": "∅", "varnothing": "∅", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠", "times": "×", "cdot": "·", "pm": "±", "mp": "∓", "infty": "∞", "to": "→", "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔", "Rightarrow": "⇒", "Leftrightarrow": "⇔", "forall": "∀", "exists": "∃", "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "theta": "θ", "lambda": "λ", "pi": "π", "sigma": "σ", "omega": "ω", "Delta": "Δ", "Sigma": "Σ", "Omega": "Ω"};
  function split(value) {
    const text=String(value), result=[]; let offset=0;
    const pattern=/\\\((.*?)\\\)|\\\[(.*?)\\\]/gs;
    for (const match of text.matchAll(pattern)) {
      if(match.index>offset) result.push({type:'text',text:text.slice(offset,match.index)});
      result.push({type:'latex',text:match[1] ?? match[2]}); offset=match.index+match[0].length;
    }
    if(offset<text.length) result.push({type:'text',text:text.slice(offset)});
    return result;
  }
  function convert(value) {
    return split(value).map(segment=>segment.type==='latex' ? '\\('+segment.text+'\\)' : segment.text.replace(/(?<!\\)\\([A-Za-z]+)/g,(whole,key)=>Object.prototype.hasOwnProperty.call(symbols,key) ? symbols[key] : whole)).join('');
  }
  function render(node) {
    if(node.dataset.explanationRendered==='144') return;
    const value=node.textContent; node.dataset.explanationRendered='144';
    const paragraphs=value.split(/\n\s*\n/).filter(text=>text.trim()).map(text=>{
      const paragraph=document.createElement('span'); paragraph.className='qb-explanation-step';
      paragraph.style.cssText='display:block;white-space:pre-wrap;padding:8px 12px;margin:10px 0;border-left:3px solid #d8e1ef;overflow-wrap:anywhere';
      for(const segment of split(text)) {
        if(segment.type==='latex') {
          const field=document.createElement('math-field');field.setAttribute('read-only','');field.setAttribute('tabindex','-1');field.setAttribute('math-virtual-keyboard-policy','manual');
          field.style.cssText='border:0;background:transparent;max-width:100%;overflow:auto;pointer-events:none;vertical-align:middle';field.textContent=segment.text;paragraph.appendChild(field);
        } else paragraph.appendChild(document.createTextNode(segment.text));
      }
      return paragraph;
    });
    node.replaceChildren(...paragraphs);
  }
  function scan(root) {
    if(root.matches?.('[data-readable-math-prose]'))render(root);
    root.querySelectorAll?.('[data-readable-math-prose]').forEach(render);
  }
  window.QBMathProse=Object.freeze({version:144,convert,split,scan});
  function init() {
    scan(document);
    new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{if(node.nodeType===1)scan(node);}))).observe(document.body,{childList:true,subtree:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
