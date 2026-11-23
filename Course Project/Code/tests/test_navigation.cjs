// Run with node tests/test_navigation.cjs. No server or browser credentials needed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) elements.set(selector, {
    hidden:true, textContent:'', innerHTML:'', childNodes:[],
    querySelectorAll:()=>[], setAttribute(){},
    replaceChildren(...nodes){this.childNodes=nodes;}
  });
  return elements.get(selector);
}
const context=vm.createContext({
  document:{querySelector:element, dispatchEvent(){}},
  window:{scrollY:0,scrollTo(x,y){this.scrollY=y;}},
  fetch:()=>new Promise(()=>{}), console, Event:class {},
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../dashboard/portal.js'),'utf8'),context);
vm.runInContext(`
state={user:{id:1,role:'faculty'},permissions:[],faculty:[],runs:[]};
rememberPreviousScreen();
view='publications';rememberPreviousScreen();
publicationQuery='neural';publicationYear='2025';publicationPage=3;
$('#pageTitle').textContent='Publications';
$('#content').childNodes=[{id:'filtered-results',expanded:true}];
window.scrollY=420;
view='reports';rememberPreviousScreen();
$('#content').childNodes=[{id:'reports'}];
$('#pageTitle').textContent='Reports';
goBackWorkspace();
`,context);
const restored=JSON.parse(vm.runInContext(`JSON.stringify({view,publicationQuery,publicationYear,publicationPage,title:$('#pageTitle').textContent,nodes:$('#content').childNodes,scroll:window.scrollY})`,context));
assert.deepEqual(restored,{view:'publications',publicationQuery:'neural',publicationYear:'2025',publicationPage:3,title:'Publications',nodes:[{id:'filtered-results',expanded:true}],scroll:420});
assert.match(vm.runInContext(`reportMetricPanel({insights:{publications:148,imported_citations:967,imported_h_index:15,corroborated_citations:0,corroborated_publications:0,sources:['scholar'],citation_basis:'Imported snapshots'}})`,context),/967/);
console.log('PASS: Back restores previous screen, filters, page, expanded content and scroll; imported citations are rendered.');
