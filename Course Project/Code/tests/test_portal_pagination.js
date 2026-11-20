const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function setup(){
 class Element{constructor(){this.children=[];this.innerHTML='';this.textContent=''}append(...items){this.children.push(...items)}}
 const elements=new Map(),calls=[];
 const document={querySelector(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id)},createElement(){return new Element()}};
 let source=fs.readFileSync(path.join(__dirname,'../dashboard/portal.js'),'utf8').split('\n').filter(line=>!line.startsWith("$('#loginForm')")&&!line.startsWith("$('#logout')")&&!line.startsWith('(async()=>')).join('\n');
 const ctx=vm.createContext({document,console,URL,FormData:class{},Event:class{}});
 vm.runInContext(source,ctx);
 vm.runInContext("state={user:{id:1,role:'faculty'},permissions:[],faculty:[],runs:[],counts:{distinct_publications:125,reports:23}}",ctx);
 ctx.responses={};ctx.calls=calls;
 vm.runInContext("api=async function(url){calls.push(url);return responses[url]||{records:[],total:0,page:1,page_size:50}}",ctx);
 return {ctx,elements,Element}
}
test('publication page uses server pagination and filters',async()=>{
 const {ctx,Element}=setup();ctx.box=new Element();
 ctx.responses['/api/publications?page=2&query=Agents&year=2025']={records:[{faculty_id:'F001',title:'<script>unsafe</script>',year:2025,source:'scopus',citations:1}],total:125,page:2,page_size:50};
 await vm.runInContext("publicationPage=2;publicationQuery='Agents';publicationYear='2025';renderPublicationPage(box)",ctx);
 assert.equal(ctx.calls[0],'/api/publications?page=2&query=Agents&year=2025');
 assert.ok(ctx.box.innerHTML.includes('&lt;script&gt;'));
 assert.equal(ctx.box.children[0].children.length,2);
 assert.equal(ctx.box.children[0].children[1].disabled,false);
});
test('pager disables unavailable pages',()=>{
 const {ctx,Element}=setup();ctx.box=new Element();
 vm.runInContext('appendPager(box,1,50,2,()=>{})',ctx);
 assert.equal(ctx.box.children[0].children[0].disabled,true);assert.equal(ctx.box.children[0].children[1].disabled,true)
});
test('pending rows show unknown values and review status',async()=>{
 const {ctx,Element}=setup();ctx.box=new Element();
 ctx.responses['/api/publications?page=1&query=&year=']={records:[{faculty_id:'F001',title:'Pending record',year:null,source:'vidwan',citations:null,record_status:'pending_review',review_reasons:['Citation count unknown']}],total:1,page:1,page_size:50};
 await vm.runInContext('renderPublicationPage(box)',ctx);
 assert.ok(ctx.box.innerHTML.includes('Unknown'));
 assert.ok(ctx.box.innerHTML.includes('Needs review'));
 assert.ok(ctx.box.innerHTML.includes('Citation count unknown'))
});
test('reports list uses summaries and offers on-demand details',async()=>{
 const {ctx,Element}=setup();ctx.box=new Element();
 ctx.responses['/api/reports?page=1']={records:[{run_id:'run-a',status:'AWAITING_APPROVAL',detail_loaded:false,report:{title:'Draft',summary:{publications:1,citations:2}}}],total:1};
 await vm.runInContext('renderReportPage(box)',ctx);
 assert.equal(ctx.calls[0],'/api/reports?page=1');
 assert.ok(ctx.box.children[0].children.some(e=>e.textContent==='Open report details'));
});
test('review controls wait for report detail and assigned Dean acceptance',()=>{
 const {ctx}=setup();
 assert.equal(vm.runInContext("mayReviewRun({detail_loaded:false})",ctx),false);
 assert.equal(vm.runInContext("state.user={id:2,role:'dean'};mayReviewRun({detail_loaded:true,review_assignment:{request_id:'r',dean_id:2,status:'pending'}})",ctx),false);
 assert.equal(vm.runInContext("mayReviewRun({detail_loaded:true,review_assignment:{request_id:'r',dean_id:2,status:'accepted'}})",ctx),true)
});
test('only administrator report permission exposes delete and cancel sends no request',async()=>{
 const {ctx,Element}=setup();ctx.card=new Element();ctx.confirm=()=>false;
 vm.runInContext("appendReportDeletion(card,{run_id:'run-a',status:'AWAITING_APPROVAL'})",ctx);
 assert.equal(ctx.card.children.length,0);
 vm.runInContext("state.permissions=['delete_reports'];appendReportDeletion(card,{run_id:'run-a',status:'AWAITING_APPROVAL'})",ctx);
 assert.equal(ctx.card.children.length,1);
 await ctx.card.children[0].onclick();
 assert.equal(ctx.calls.length,0);
 ctx.runningCard=new Element();
 vm.runInContext("appendReportDeletion(runningCard,{run_id:'run-a',status:'RUNNING'})",ctx);
 assert.equal(ctx.runningCard.children.length,0)
});
