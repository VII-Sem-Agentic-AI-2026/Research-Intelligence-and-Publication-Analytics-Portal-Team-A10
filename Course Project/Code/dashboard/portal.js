let state=null,view='overview',setup=false;
const $=s=>document.querySelector(s),labels={admin:'Administrator',dean:'Dean',hod:'Head of Department',research_office:'Research Office',faculty:'Faculty'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const can=p=>state?.permissions.includes(p);
async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();if(!r.ok){if(r.status===401&&state){state=null;$('#appScreen').hidden=true;$('#authScreen').hidden=false;document.dispatchEvent(new Event('portal:auth-changed'))}throw Error(j.error||'Request failed')}return j}
function notify(text){$('#notice').textContent=text}
$('#backToOverview').onclick=()=>goBackWorkspace();
async function refresh(){state=await api('/api/workspace');$('#authScreen').hidden=true;$('#appScreen').hidden=false;document.title=labels[state.user.role]+' · Research Portal';$('#identity').innerHTML=`<strong>${esc(state.user.name)}</strong><span class="badge">${esc(labels[state.user.role])}</span><p class="muted">${esc(state.user.username)}${state.user.department?' · '+esc(state.user.department):''}</p>`;$('#workspaceLabel').textContent=state.user.role==='faculty'?'PERSONAL RESEARCH WORKSPACE':'INSTITUTIONAL RESEARCH WORKSPACE';renderNav();await render();document.dispatchEvent(new Event('portal:refreshed'))}
function renderNav(){const links=[['overview','Overview'],['directory','Faculty directory'],['publications',state.user.role==='faculty'?'My publications':'Publications'],['reports',can('review')?'Review & approval':'Reports']];if(can('self_profile')||can('profile'))links.push(['profiles',state.user.role==='faculty'?'My profile & consent':'Faculty & consent']);if(can('self_upload')||can('import'))links.push(['uploads','Upload data']);if(can('run'))links.push(['analysis','Create report']);if(['faculty','research_office','admin'].includes(state.user.role))links.push(['consents','Consent requests']);if(['dean','research_office','admin'].includes(state.user.role))links.push(['review_requests','Dean review requests']);if(can('accounts'))links.push(['accounts','Account management']);$('#navigation').innerHTML=links.map(([id,title])=>`<button data-view="${id}" aria-current="${view===id?'page':'false'}" class="${view===id?'active':''}">${title}</button>`).join('');$('#navigation').querySelectorAll('button').forEach(b=>b.onclick=()=>{navigateWorkspace(b.dataset.view)})}
function table(headers,rows){return rows.length?`<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<p class="empty">No records available in this workspace.</p>'}
async function render(){const box=$('#content');rememberPreviousScreen();$('#backToOverview').hidden=screenTrail.length===0;$('#pageTitle').textContent=({overview:'Overview',publications:'Publications',reports:can('review')?'Review & approval':'Reports',profiles:'Faculty profiles',uploads:'Upload data',analysis:'Create a research report',accounts:'Account management',password:'Change password',consents:'Consent requests',review_requests:'Dean review requests'})[view];
 if(state.user.role==='faculty'&&!state.user.department_confirmed&&view!=='password'){
  $('#pageTitle').textContent='Welcome · Select your department';
  box.innerHTML=`<section class="card"><h2>Complete your first login</h2><p>Your publication exports do not include a department. Select yours to link your existing publications and future uploads to the correct department.</p><p>Your login was created by the administrator. You can change your initial password using Change password.</p><form id="departmentForm"><label>Department<select id="firstDepartment" required><option value="">Choose your department</option>${state.departments.map(d=>`<option value="${esc(d)}">${esc(d)}</option>`).join('')}</select></label><p class="muted">If your department is missing, ask the administrator to add its faculty profile before continuing.</p><button>Save department and continue</button></form></section>`;
  $('#departmentForm').onsubmit=e=>{e.preventDefault();action(async()=>{await api('/api/onboarding',{department:$('#firstDepartment').value});view='overview';await refresh();notify('Department saved. Your publications are linked through your faculty profile.')})};return;
 }
 if(view==='overview'){renderDiscoveryOverview(box);return}
 if(view==='directory'){$('#pageTitle').textContent='Faculty directory';renderFacultyDirectory(box);return}
 if(view==='publications'){await renderPublicationPage(box);return}
 if(view==='consents'){renderConsentInbox(box);return}
 if(view==='review_requests'){renderReviewInbox(box);return}
 if(view==='reports'){await renderReportPage(box);return}
 if(view==='profiles'){renderProfiles(box);return}
 if(view==='uploads'){renderUploads(box);return}
 if(view==='analysis'){box.innerHTML=`<section class="card"><h2>Report scope</h2><form id="analysisForm"><label>Request<input id="request" required placeholder="Create the 2026 CSE bibliometric report"></label><label>Publication window<select id="scope"><option value="cumulative_through_year">Through reporting year</option><option value="publication_year">Reporting year only</option></select></label><p class="muted">Citation counts use imported snapshots. The complete analysis runs through all 14 labs and pauses for human review.</p><button>Generate draft</button></form></section>`;$('#analysisForm').onsubmit=async e=>{e.preventDefault();await action(async()=>{notify('Generating report…');const r=await api('/api/chat',{message:$('#request').value,scope:$('#scope').value,selected_labs:[14]});if(!r.run_id)throw Error(r.messages.at(-1).text);view='reports';await refresh();notify('Draft generated. Review is required before publication.')})};return}
 if(view==='accounts'){await renderAccounts(box);return}
 if(view==='password'){box.innerHTML='<section class="card"><form id="passwordForm"><label>Current password<input id="oldPassword" type="password" autocomplete="current-password" required></label><label>New password<input id="newPassword" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label><button>Change password and sign out</button></form></section>';$('#passwordForm').onsubmit=async e=>{e.preventDefault();await action(async()=>{await api('/api/password',{current_password:$('#oldPassword').value,new_password:$('#newPassword').value});location.reload()})}}
}
async function action(fn){try{await fn()}catch(e){notify(e.message)}}
async function navigateWorkspace(next){view=next;notify('');renderNav();await action(render);window.scrollTo(0,0)}
let screenTrail=[],renderedView='overview',screenOwner=null;
function rememberPreviousScreen(force=false){
 if(screenOwner!==state.user.id){screenTrail=[];renderedView=view;screenOwner=state.user.id}
 if(renderedView===view&&!force)return;
 const content=$('#content');
 content.querySelectorAll('input[type="password"]').forEach(input=>input.value='');
 screenTrail.push({view:renderedView,nodes:[...content.childNodes],title:$('#pageTitle').textContent,scroll:window.scrollY,assistantOpen:!$('#assistantPanel').hidden,publicationPage,publicationQuery,publicationYear,reportPage,reportTotal,selectedReportId,runs:state.runs});
 if(screenTrail.length>15)screenTrail.shift();renderedView=view;
}
function goBackWorkspace(){
 const previous=screenTrail.pop();if(!previous)return;
 view=renderedView=previous.view;publicationPage=previous.publicationPage;publicationQuery=previous.publicationQuery;publicationYear=previous.publicationYear;reportPage=previous.reportPage;reportTotal=previous.reportTotal;selectedReportId=previous.selectedReportId;state.runs=previous.runs;
 $('#content').replaceChildren(...previous.nodes);$('#pageTitle').textContent=previous.title;$('#backToOverview').hidden=screenTrail.length===0;$('#assistantPanel').hidden=!previous.assistantOpen;$('#assistantLauncher').setAttribute('aria-expanded',String(previous.assistantOpen));notify('');renderNav();window.scrollTo(0,previous.scroll);
}
function attributionChecklist(run,result){
 const row=document.createElement('div');row.className='review-row';
 const checks=[['identity_checked','I checked the faculty profile or author ID; the name and affiliation match.'],['publications_matched','I matched the listed publications to this faculty member.'],['conflicts_resolved','I checked for namesakes and found no unresolved ownership conflicts.']];
 const links=Object.entries(result.faculty.profiles||{}).filter(([,url])=>/^https?:\/\//i.test(String(url))).map(([source,url])=>'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">Open '+esc(source)+' profile ↗</a>').join(' · ');
 row.innerHTML='<h3>Confirm faculty attribution</h3><p>Review '+esc(result.faculty.name)+'’s publication ownership, then tick the checks you completed.</p>'+(links?'<p>'+links+'</p>':'')+'<fieldset class="attribution-checklist"><legend class="sr-only">Publication ownership checks</legend>'+checks.map(([id,label])=>'<label><input type="checkbox" name="'+id+'"> <span>'+esc(label)+'</span></label>').join('')+'</fieldset><button type="button" disabled>Confirm attribution</button><p class="muted">All three checks are required. Your selections, identity and review time are recorded automatically.</p>';
 const button=row.querySelector('button');
 row.querySelectorAll('input').forEach(input=>input.onchange=()=>{button.disabled=![...row.querySelectorAll('input')].every(c=>c.checked)});
 button.onclick=()=>action(async()=>{
  button.disabled=true;
  try{await api('/api/review-attribution',{run_id:run.run_id,faculty_id:result.faculty.faculty_id,checks:Object.fromEntries([...row.querySelectorAll('input')].map(c=>[c.name,c.checked]))});await refresh();notify('Faculty attribution confirmed. Your checklist is saved.')}finally{button.disabled=![...row.querySelectorAll('input')].every(c=>c.checked)}
 });
 return row;
}
function reportEvidenceLinks(evidence){
 return (evidence||[]).map(e=>{
  const url=String(e.url||'');const label=esc(e.source||'Source');
  return (/^https?:\/\//i.test(url)?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+label+' ↗</a>':label)+'<small class="evidence-date">'+esc(e.retrieved||'Date unavailable')+'</small>';
 }).join('<br>')||'No source evidence';
}
function reportPublicationTable(publications){
 return '<div class="table-wrap"><table><thead><tr><th>Publication / DOI</th><th>Year</th><th>Venue</th><th>Imported citations</th><th>Source evidence</th></tr></thead><tbody>'+publications.map(p=>'<tr><td><strong>'+esc(p.title)+'</strong><small class="evidence-date">'+esc(p.doi||'DOI unavailable')+'</small></td><td>'+esc(p.year||'Unknown')+'</td><td>'+esc(p.venue||p.journal||p.source_metadata?.journal_or_conference||'Not supplied')+'</td><td>'+esc(p.citations??'Not supplied')+'</td><td>'+reportEvidenceLinks(p.evidence)+'</td></tr>').join('')+'</tbody></table></div>';
}
function reportBarChart(title,rows,{horizontal=false,note='',unit='publications'}={}){
 const clean=rows.map(([label,value])=>[String(label),Math.max(0,Number(value)||0)]);
 const max=Math.max(1,...clean.map(r=>r[1]));
 const content=clean.length?clean.map(([label,value])=>{
  const description=label+': '+value.toLocaleString('en-IN')+' '+unit;
  const bar='<span class="chart-fill" style="--bar-size:'+(value/max*100).toFixed(3)+'%"></span>';
  return '<div class="chart-item" tabindex="0" role="img" aria-label="'+esc(description)+'" title="'+esc(description)+'"><span class="chart-label">'+esc(label)+'</span><span class="chart-track">'+bar+'</span><strong class="chart-number">'+value.toLocaleString('en-IN')+'</strong></div>';
 }).join(''):'<p class="empty">No data available for this chart.</p>';
 return '<figure class="report-chart '+(horizontal?'horizontal':'vertical')+'"><figcaption>'+esc(title)+'</figcaption><div class="chart-scroll"><div class="chart-plot">'+content+'</div></div><p class="muted">'+esc(note||('Counts start at zero. Hover or focus a bar for its full label and value.'))+'</p></figure>';
}
function reportCharts(i){
 const years=i.publication_years||[],q=i.quality||{};
 const total=Math.max(0,Number(i.publications)||0),corroborated=Math.min(total,Math.max(0,Number(i.corroborated_publications)||0)),other=total-corroborated;
 const coverage='<figure class="report-chart"><figcaption>Publication source corroboration</figcaption><div class="corroboration-bar" role="img" aria-label="'+esc(corroborated+' cross-source corroborated publications; '+other+' publications without cross-source corroboration')+'">'+(total?'<span class="corroborated" style="width:'+(corroborated/total*100)+'%" title="'+corroborated+' cross-source corroborated"></span><span class="uncorroborated" style="width:'+(other/total*100)+'%" title="'+other+' without cross-source corroboration"></span>':'<span>No publications</span>')+'</div><div class="chart-legend"><span><i class="corroborated"></i>'+corroborated+' cross-source corroborated</span><span><i class="uncorroborated"></i>'+other+' without cross-source corroboration</span></div><p class="muted">These are publication counts, not citation counts. Imported citations remain included for single-source records.</p></figure>';
 return '<div class="report-chart-grid">'+reportBarChart('Publications by year',years.map(y=>[y.year,y.publications]))+reportBarChart('Current citations grouped by publication year',years.map(y=>[y.year,y.imported_citations]),{unit:'imported citations',note:'Current imported snapshots grouped by publication year — not citations received in those years.'})+'</div>'+reportBarChart('Top 10 most-cited publications',(i.top_publications||[]).map(p=>[p.title,p.citations]),{horizontal:true,unit:'imported citations'})+'<div class="report-chart-grid">'+coverage+reportBarChart('Publications with missing metadata',[
 ['DOI',q.missing_doi],['Venue',q.missing_venue],['Publication year',q.missing_year],['Citation count',q.missing_citation_count],['Source URL / date',q.missing_provenance]],{horizontal:true,note:'A publication may appear in more than one category.'})+'</div>';
}
function reportAnalysisPanel(report){
 const i=report.insights;if(!i?.quality)return '';
 const num=n=>Number(n||0).toLocaleString('en-IN');
 const quality=i.quality||{};
 const profiles=(i.faculty||[]).map(f=>[f.name||f.faculty_id,f.department||'Not supplied',f.faculty_id]);
 return '<section class="report-analysis"><p class="report-scope">'+(i.scope==='publication_year'?'Publications in ':'Publications through ')+esc(i.reporting_year||'the reporting year')+' · Sources: '+esc((i.sources||[]).join(', ')||'None')+'</p>'+table(['Faculty','Department','Faculty ID'],profiles)+
 reportCharts(i)+'<p class="muted">Pending review: '+num(quality.pending_duplicate_groups)+' duplicate/match proposals · '+num(quality.attribution_awaiting_review)+' faculty attribution checks.</p>'+
 '<p class="muted">'+(report.approved_by?'Approved by '+esc(report.approved_by)+(report.approved_at?' · '+esc(report.approved_at):''):'No approval is recorded on this report. See the status above for its current workflow state.')+'</p></section>';
}
function reportMetricPanel(report){
 const i=report.insights;
 if(!i)return '<p>'+esc(report.summary?.publications??0)+' publications · '+esc(report.summary?.citations??0)+' cross-source corroborated citations</p>';
 const num=n=>Number(n||0).toLocaleString('en-IN');
 return '<div class="report-metrics"><div><strong>'+num(i.publications)+'</strong><span>Publications</span></div><div><strong>'+num(i.imported_citations)+'</strong><span>Imported citations</span></div><div><strong>'+num(i.imported_h_index)+'</strong><span>Imported-record h-index</span></div><div><strong>'+num(i.average_citations)+'</strong><span>Imported citations per publication</span></div></div><p class="muted">'+esc(i.citation_basis)+'</p>'+reportAnalysisPanel(report);
}
async function openWorkspaceReport(runId){
 if(view==='reports')rememberPreviousScreen(true);
 await navigateWorkspace('reports');
 selectedReportId=runId;
 const detail=await api('/api/report?run_id='+encodeURIComponent(runId));
 if(view!=='reports')return;
 const existing=state.runs.some(r=>r.run_id===runId);state.runs=existing?state.runs.map(r=>r.run_id===runId?detail:r):[detail,...state.runs];renderReports($('#content'));appendReportPager($('#content'));
 const card=[...$('#content').querySelectorAll('[data-run-id]')].find(c=>c.dataset.runId===runId);if(card){card.scrollIntoView({block:'start'})}
}
function overviewMetricCards(){
 const number=v=>Number(v||0).toLocaleString('en-IN');
 const role=state.user.role,personal=role==='faculty',departmentScoped=personal||role==='hod';
 const own=state.faculty.find(f=>f.faculty_id===state.user.faculty_id);
 const department=(personal?own?.department:state.user.department)||state.user.department||'Not assigned';
 const departments=new Set(state.faculty.map(f=>f.department).filter(Boolean));
 const cards=[];
 if(!personal)cards.push({value:number(state.faculty.length),label:'Faculty profiles',note:role==='hod'?'In your department':'In your workspace'});
 cards.push({value:number(state.counts.distinct_publications),label:'Distinct publications',note:'Across imported sources'});
 cards.push(departmentScoped?{value:department,label:'Your department',note:'',department:true}:{value:number(departments.size),label:'Departments',note:'Represented in the roster'});
 cards.push({value:number(state.counts.reports),label:'Research reports',note:'Available to your account'});
 return '<div class="insight-metrics">'+cards.map((card,index)=>'<section class="card stat-card"><span class="stat-symbol">'+String(index+1).padStart(2,'0')+'</span><div class="metric '+(card.department?'department-name':'')+'">'+esc(card.value)+'</div><h3>'+esc(card.label)+'</h3>'+(card.note?'<p>'+esc(card.note)+'</p>':'')+'</section>').join('')+'</div>';
}
function renderDiscoveryOverview(box){
 const number=v=>Number(v||0).toLocaleString('en-IN');
 const departments=[...new Set(state.faculty.map(f=>f.department).filter(Boolean))].sort();
 const eligible=state.counts.report_eligible??state.counts.publications??0;
 const review=state.counts.needs_review??0;
 box.innerHTML=`<section class="discovery-hero"><span class="eyebrow">RESEARCH DISCOVERY & INSIGHTS</span><h2>Your institution’s research,<br>connected.</h2><p>Explore scholarly output, discover faculty and turn publication evidence into decisions.</p><form id="discoverySearch" class="discovery-search"><label class="sr-only" for="discoveryQuery">Search publication titles</label><input id="discoveryQuery" type="search" maxlength="250" placeholder="Search publication titles…"><button>Search publications <span aria-hidden="true">↗</span></button></form><div class="hero-links"><button class="hero-link" data-go="directory">Browse faculty directory →</button>${can('run')?'<button class="hero-link" data-go="analysis">Create a research report →</button>':''}</div><div class="hero-orbit" aria-hidden="true"><i></i><i></i><i></i><span>RI</span></div></section>
 ${overviewMetricCards()}
 <div class="overview-columns"><section class="card"><div class="section-heading"><div><span class="eyebrow">EXPLORE YOUR COMMUNITY</span><h2>Research by department</h2></div><button class="text-button" data-go="directory">View directory →</button></div><div class="department-grid">${departments.length?departments.map(d=>{const count=state.faculty.filter(f=>f.department===d).length;return `<button class="department-tile" data-department="${esc(d)}"><span class="department-monogram">${esc(d.slice(0,2))}</span><span><strong>${esc(d)}</strong><small>${number(count)} faculty ${count===1?'profile':'profiles'}</small></span><span aria-hidden="true">↗</span></button>`}).join(''):'<p class="empty">Departments appear when faculty profiles are available.</p>'}</div></section><section class="card readiness-card"><span class="eyebrow">DATA READINESS</span><h2>From records to insight</h2><div class="readiness-line"><span class="status-dot ready"></span><span>Available for analysis</span><strong>${number(eligible)}</strong></div><div class="readiness-line"><span class="status-dot pending"></span><span>Needs record review</span><strong>${number(review)}</strong></div><p class="muted">Source record counts. Citation metrics use imported snapshots.</p><button class="secondary" data-go="publications">Inspect publication records →</button><div class="ai-status"><span class="status-dot ${state.groq_configured?'ready':'pending'}"></span><strong>${state.groq_configured?'Gemini is connected':'AI setup pending'}</strong><p>${state.groq_configured?'Ready to assist with report generation.':'Profiles, uploads and report review are available. An administrator can configure Gemini in the assistant.'}</p></div></section></div>
 <section class="card workspace-welcome"><div><span class="eyebrow">YOUR WORKSPACE</span><h2>Welcome, ${esc(state.user.name)}</h2><p>${state.user.role==='faculty'?'Keep your research profile current, manage source consent and upload your latest publication exports.':can('review')?'Review publication evidence and attribution, then approve reports with a clear decision trail.':'Manage faculty profiles, publication imports and account assignments across your institution.'}</p></div><button class="secondary" data-go="reports">${can('review')?'Open review queue':'Browse reports'} →</button></section>`;
 box.querySelector('#discoverySearch').onsubmit=e=>{e.preventDefault();publicationQuery=$('#discoveryQuery').value.trim();publicationYear='';publicationPage=1;navigateWorkspace('publications')};
 box.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>navigateWorkspace(b.dataset.go));
 box.querySelectorAll('[data-department]').forEach(b=>b.onclick=()=>{directoryDepartment=b.dataset.department;navigateWorkspace('directory')});
}
let directoryQuery='',directoryDepartment='';
function renderFacultyDirectory(box){
 const departments=[...new Set(state.faculty.map(f=>f.department).filter(Boolean))].sort();
 box.innerHTML=`<section class="directory-heading"><span class="eyebrow">YOUR RESEARCH COMMUNITY</span><h2>Faculty directory</h2><p>Find researchers by name, faculty ID or department within your account’s scope.</p></section><div class="directory-layout"><section class="card directory-filters"><h3>Refine your search</h3><label for="directoryQuery">Name or faculty ID</label><input id="directoryQuery" type="search" placeholder="Find a researcher…" value="${esc(directoryQuery)}"><label for="directoryDepartment">Department</label><select id="directoryDepartment"><option value="">All departments</option>${departments.map(d=>`<option ${directoryDepartment===d?'selected':''} value="${esc(d)}">${esc(d)}</option>`).join('')}</select><button id="clearDirectory" class="secondary">Clear filters</button><p class="muted">Only profiles available to your account are shown.</p></section><section><p id="directoryCount" class="muted" role="status"></p><div id="directoryResults" class="faculty-grid"></div></section></div>`;
 const update=()=>{
  directoryQuery=$('#directoryQuery').value;directoryDepartment=$('#directoryDepartment').value;
  const q=directoryQuery.trim().toLowerCase();
  const matches=state.faculty.filter(f=>(!directoryDepartment||f.department===directoryDepartment)&&(!q||[f.name,f.faculty_id,f.department].some(v=>String(v||'').toLowerCase().includes(q))));
  $('#directoryCount').textContent=`${matches.length.toLocaleString('en-IN')} ${matches.length===1?'researcher':'researchers'} found`;
  $('#directoryResults').innerHTML=matches.length?matches.map(f=>`<article class="card faculty-card"><div class="faculty-avatar" aria-hidden="true">${esc(String(f.name||'?').replace(/^Dr\.?\s+/i,'').split(/\s+/).slice(0,2).map(v=>v[0]).join('').toUpperCase())}</div><span class="badge">${esc(f.department||'Department not assigned')}</span><h3>${esc(f.name)}</h3><p class="muted">Faculty ID · ${esc(f.faculty_id)}</p><div class="faculty-sources">${['scholar','scopus','wos'].map(s=>`<span class="source-chip ${f.consent?.[s]?'enabled':''}">${s==='scholar'?'Scholar':s==='scopus'?'Scopus':'WoS'} ${f.consent?.[s]?'✓':'—'}</span>`).join('')}</div><p class="muted">Source access consent</p>${can('profile')||can('self_profile')?`<button class="text-button" data-profile="${esc(f.faculty_id)}">View profile & consent →</button>`:''}</article>`).join(''):'<section class="card empty">No faculty match these filters. Try another name or department.</section>';
  $('#directoryResults').querySelectorAll('[data-profile]').forEach(b=>b.onclick=async()=>{await navigateWorkspace('profiles');const select=$('#profileSelect');if(select){select.value=b.dataset.profile;select.onchange()}});
 };
 $('#directoryQuery').oninput=update;$('#directoryDepartment').onchange=update;$('#clearDirectory').onclick=()=>{$('#directoryQuery').value='';$('#directoryDepartment').value='';update()};update();
}
function renderProfiles(box){box.innerHTML=`<section class="card"><h2>${state.user.role==='faculty'?'Your profile':'Faculty profiles'}</h2><label>Select faculty<select id="profileSelect">${state.faculty.map(f=>`<option value="${esc(f.faculty_id)}">${esc(f.name)} · ${esc(f.faculty_id)}</option>`).join('')}</select></label><p>Faculty approve new consent in their own account. Research Office can send requests from Consent requests.</p><form id="profileForm"><div id="profileFields"></div><button>Save source consent</button></form></section>`;const fill=()=>{const f=state.faculty.find(f=>f.faculty_id===$('#profileSelect').value);if(!f){$('#profileFields').textContent='Import a faculty roster first.';return}$('#profileFields').innerHTML=`<p>${esc(f.name)} · ${esc(f.department)}</p>${f.import_consent?`<p>Consent confirmed for imported data: ${esc(f.import_consent.sources.join(', '))}. Source switches below control connector access; missing author profile links still need to be supplied.</p>`:''}`+['scholar','scopus','wos'].map(s=>`<label class="inline-label"><input type="checkbox" id="consent-${s}" ${f.consent?.[s]?'checked':''} ${state.user.role!=='faculty'&&!f.consent?.[s]?'disabled':''}>${s.toUpperCase()} consent</label><label>Profile URL<input id="url-${s}" type="url" ${state.user.role!=='faculty'&&f.consent?.[s]?'readonly':''} value="${esc(f.profiles?.[s]||'')}"></label>`).join('')};$('#profileSelect').onchange=fill;fill();$('#profileForm').onsubmit=async e=>{e.preventDefault();await action(async()=>{const f=state.faculty.find(f=>f.faculty_id===$('#profileSelect').value);if(!f)return;const profile={...f,consent:{},profiles:{}};for(const s of ['scholar','scopus','wos']){profile.consent[s]=$('#consent-'+s).checked;profile.profiles[s]=$('#url-'+s).value}await api('/api/faculty',{profile});await refresh();notify('Source consent saved.')})}}
function renderUploads(box){box.innerHTML=`<div class="grid two"><section class="card"><h2>Publication export</h2><form id="uploadForm"><label>Faculty<select id="uploadFaculty">${state.faculty.map(f=>`<option value="${esc(f.faculty_id)}">${esc(f.name)}</option>`).join('')}</select></label><label>Source<select id="uploadSource"><option value="scholar">Google Scholar</option><option value="scopus">Scopus</option><option value="wos">Web of Science</option></select></label><label>Export file<input id="publicationFile" type="file" accept=".csv,.tsv,.xlsx,.json,.bib,.bibtex,.ris" required></label><button>Upload publications</button></form></section>${can('import')?'<section class="card"><h2>Faculty roster</h2><p>Include Faculty ID, Full Name and Department columns.</p><form id="rosterForm"><input id="rosterFile" type="file" accept=".csv,.tsv,.xlsx,.json" required><button>Import roster</button></form></section>':''}</div>`;$('#uploadForm').onsubmit=async e=>{e.preventDefault();await upload($('#publicationFile').files[0],{kind:'publication',faculty_id:$('#uploadFaculty').value,source:$('#uploadSource').value})};if($('#rosterForm'))$('#rosterForm').onsubmit=async e=>{e.preventDefault();await upload($('#rosterFile').files[0],{kind:'roster'})}}
async function upload(file,fields){await action(async()=>{if(file.size>10*1024*1024)throw Error('Maximum file size is 10 MB');const encoded=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(file)});const r=await api('/api/upload',{...fields,filename:file.name,content_base64:encoded});await refresh();notify(`${r.records} records imported.`)})}
const accountDesignations=['Prof. & Head','Professor','Associate Professor','Assistant Professor'];
let accountAccessFilters={department:'',designation:'',query:'',page:1},accountFilterOwner=null;
function accountDepartment(user){return (user.role==='faculty'?state.faculty.find(f=>f.faculty_id===user.faculty_id)?.department:'')||user.department||''}
function accountDesignation(user){return user.designation||(user.role==='hod'?'Prof. & Head':'')}
function filterAccounts(users){
 const f=accountAccessFilters,q=f.query.trim().toLowerCase();
 return users.filter(u=>(!f.department||(accountDepartment(u)||'__unset')===f.department)&&(!f.designation||(accountDesignation(u)||'__unset')===f.designation)&&(!q||[u.name,u.username,u.faculty_id].some(v=>String(v||'').toLowerCase().includes(q))));
}
async function renderAccounts(box){
 const users=await api('/api/users');
 if(accountFilterOwner!==state.user.id){accountAccessFilters={department:'',designation:'',query:'',page:1};accountFilterOwner=state.user.id}
 box.innerHTML=`<div class="grid two"><section class="card"><h2>Create account</h2><form id="accountForm"><label>Full name<input name="name" required></label><label>Login ID<input name="username" autocomplete="off" minlength="3" required></label><label>Initial password<input name="password" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label><label>Role<select name="role">${Object.entries(labels).map(([r,l])=>`<option value="${r}" ${r==='faculty'?'selected':''}>${l}</option>`).join('')}</select></label><label>Designation<select name="designation"><option value="">Not set</option>${accountDesignations.map(d=>`<option value="${esc(d)}">${esc(d)}</option>`).join('')}</select></label><label>Faculty assignment (faculty accounts)<select name="faculty_id"><option value="">Select a profile</option>${state.faculty.map(f=>`<option value="${esc(f.faculty_id)}">${esc(f.name)} · ${esc(f.faculty_id)}</option>`).join('')}</select></label><label>Department (required for HoD)<input name="department" placeholder="CSE"></label><div class="form-actions"><button>Create account</button><button type="button" id="cancelAccount" class="secondary">Cancel</button></div></form></section><section class="card"><h2>Account access</h2><p class="muted">Faculty see their own data. HoDs review their assigned department. Deans and Research Office review institutional reports. Administrators manage accounts.</p><div class="account-filters"><label>Department<select id="accountDepartment"></select></label><label>Designation<select id="accountDesignation"><option value="">All designations</option>${accountDesignations.map(d=>`<option value="${esc(d)}">${esc(d)}</option>`).join('')}<option value="__unset">Not set</option></select></label><label class="account-search">Find account<input id="accountSearch" type="search" placeholder="Name, login ID or faculty ID"></label></div><button id="clearAccountFilters" type="button" class="text-button">Clear filters</button><p id="accountCount" class="muted" role="status"></p><div id="usersList"></div><div id="accountPager" class="toolbar"></div></section></div>`;
 $('#cancelAccount').onclick=()=>navigateWorkspace('overview');
 const departments=[...new Set(users.map(accountDepartment).filter(Boolean))].sort();
 $('#accountDepartment').innerHTML='<option value="">All departments</option>'+departments.map(d=>'<option value="'+esc(d)+'">'+esc(d)+'</option>').join('')+'<option value="__unset">Institution-wide / not assigned</option>';
 $('#accountDepartment').value=accountAccessFilters.department;$('#accountDesignation').value=accountAccessFilters.designation;$('#accountSearch').value=accountAccessFilters.query;
 const update=()=>{accountAccessFilters={department:$('#accountDepartment').value,designation:$('#accountDesignation').value,query:$('#accountSearch').value,page:1};renderAccountAccess(users)};
 $('#accountDepartment').onchange=update;$('#accountDesignation').onchange=update;$('#accountSearch').oninput=update;
 $('#clearAccountFilters').onclick=()=>{$('#accountDepartment').value='';$('#accountDesignation').value='';$('#accountSearch').value='';update()};
 renderAccountAccess(users);
 $('#accountForm').onsubmit=async e=>{e.preventDefault();await action(async()=>{await api('/api/users',Object.fromEntries(new FormData(e.target)));await render();notify('Account created. Share credentials privately; the user can change their password after signing in.')})}
}
function renderAccountAccess(users){
 const matches=filterAccounts(users),size=20;
 accountAccessFilters.page=Math.min(Math.max(1,accountAccessFilters.page),Math.max(1,Math.ceil(matches.length/size)));
 const page=accountAccessFilters.page,visible=matches.slice((page-1)*size,page*size);
 $('#accountCount').textContent=matches.length+' of '+users.length+' accounts match';
 $('#usersList').innerHTML=visible.length?visible.map(u=>'<div class="review-row"><strong>'+esc(u.name)+'</strong> · '+esc(u.username)+'<p>'+esc(labels[u.role])+' · '+esc(accountDepartment(u)||'Institution-wide / not assigned')+' · '+esc(accountDesignation(u)||'Designation not set')+' · '+(u.active?'Active':'Disabled')+'</p><div class="designation-editor"><label>Designation<select data-designation="'+u.id+'"><option value="">Not set</option>'+accountDesignations.map(d=>'<option value="'+esc(d)+'" '+(d===accountDesignation(u)?'selected':'')+'>'+esc(d)+'</option>').join('')+'</select></label><button type="button" class="secondary" data-save-designation="'+u.id+'">Save designation</button></div>'+(u.active&&u.id!==state.user.id?'<button class="danger" data-disable="'+u.id+'">Disable account</button>':!u.active?'<button class="danger" data-delete-account="'+u.id+'">Delete account permanently</button>':'')+'</div>').join(''):'<p class="empty">No accounts match these filters.</p>';
 $('#usersList').querySelectorAll('[data-save-designation]').forEach(b=>b.onclick=()=>action(async()=>{
  const id=Number(b.dataset.saveDesignation),designation=$('#usersList').querySelector('[data-designation="'+id+'"]').value;
  await api('/api/users/designation',{user_id:id,designation});users.find(u=>u.id===id).designation=designation;renderAccountAccess(users);notify('Designation saved. Account permissions are unchanged.');
 }));
 $('#usersList').querySelectorAll('[data-disable]').forEach(b=>b.onclick=()=>action(async()=>{await api('/api/users/disable',{user_id:Number(b.dataset.disable)});await render();notify('Account disabled and sessions revoked.')}));
 $('#usersList').querySelectorAll('[data-delete-account]').forEach(b=>b.onclick=()=>action(async()=>{if(!confirm('Permanently delete this disabled account and its private chat history? Faculty records, publications and audit history will remain.'))return;await api('/api/users/delete',{user_id:Number(b.dataset.deleteAccount),confirm:true});await render();notify('Disabled account deleted. Faculty records and audit history retained.')}));
 const pager=$('#accountPager');pager.replaceChildren();
 if(matches.length>size){const text=document.createElement('span');text.className='muted';text.textContent='Page '+page+' of '+Math.ceil(matches.length/size);pager.append(text);for(const [label,next,disabled] of [['Previous',page-1,page===1],['Next',page+1,page*size>=matches.length]]){const b=document.createElement('button');b.type='button';b.className='secondary';b.textContent=label;b.disabled=disabled;b.onclick=()=>{accountAccessFilters.page=next;renderAccountAccess(users)};pager.append(b)}}
}
function renderReports(box){box.innerHTML=state.runs.length?'<section class="card report-picker"><label for="reportPicker">Choose a report</label><select id="reportPicker">'+state.runs.map(r=>'<option value="'+esc(r.run_id)+'" '+(r.run_id===selectedReportId?'selected':'')+'>'+esc((r.report?.title||r.run_id)+' · '+r.status.replaceAll('_',' ')+' · '+r.run_id.slice(-6))+'</option>').join('')+'</select></section>':'<section class="card empty">No reports available yet.</section>';if(state.runs.length){const picker=box.querySelector('#reportPicker');selectedReportId=picker.value;picker.onchange=()=>action(async()=>{const next=picker.value;picker.value=selectedReportId;rememberPreviousScreen(true);selectedReportId=next;await loadSelectedReport();renderReports(box);appendReportPager(box)})}for(const run of state.runs.filter(r=>r.run_id===selectedReportId)){const card=document.createElement('section');card.className='card';card.dataset.runId=run.run_id;const report=run.report||{};card.innerHTML=`<h2>${esc(report.title||run.run_id)}</h2><span class="badge">${esc(run.status)}</span>${reportMetricPanel(report)}`;for(const result of report.faculty_results||[]){const detail=document.createElement('details');detail.innerHTML=`<summary>${esc(result.faculty.name)} · ${result.publications?.length||0} publications</summary>`+reportPublicationTable(result.publications||[]);card.append(detail);if(can('review')&&mayReviewRun(run)&&run.status==='AWAITING_APPROVAL'){if(result.attribution_status!=='reviewer_confirmed'){card.append(attributionChecklist(run,result))}for(const proposal of result.duplicate_proposals||[]){const row=document.createElement('div');row.className='review-row';row.innerHTML=`<strong>${esc(proposal.title)}</strong><p>${esc(proposal.match_rule||proposal.reason)} · ${esc(proposal.decision)}</p>`;if(proposal.decision==='pending')for(const decision of ['confirmed','rejected']){const button=document.createElement('button');button.textContent=decision==='confirmed'?'Accept match':'Reject match';button.onclick=()=>action(async()=>{await api('/api/review-duplicate',{run_id:run.run_id,faculty_id:result.faculty.faculty_id,group:proposal.group,decision});await refresh()});row.append(button)}card.append(row)}}}if(can('publish')&&mayReviewRun(run)&&run.status==='AWAITING_APPROVAL'){const approve=document.createElement('button');approve.textContent='Approve and publish';approve.onclick=()=>action(async()=>{await api('/api/approve',{run_id:run.run_id});await refresh();notify('Published with your reviewer identity. You are recorded in the audit trail.')});card.append(approve)}if(can('run')&&['RUNNING','FAILED'].includes(run.status)){const b=document.createElement('button');b.textContent='Resume report';b.onclick=()=>action(async()=>{await api('/api/resume',{run_id:run.run_id});await refresh()});card.append(b)}if(report.version&&can('read')){const links=document.createElement('p');links.innerHTML='<a href="/api/export/nirf.csv">Research CSV (current published version)</a>';card.append(links);if(can('rollback')){const b=document.createElement('button');b.className='secondary';b.textContent='Restore version '+report.version;b.onclick=()=>action(async()=>{await api('/api/rollback',{version:report.version});notify('Published version restored.')});card.append(b)}}if(run.detail_loaded===false){const more=document.createElement('button');more.textContent='Open report details';more.onclick=()=>action(async()=>{rememberPreviousScreen(true);$('#backToOverview').hidden=false;const detail=await api('/api/report?run_id='+encodeURIComponent(run.run_id));state.runs=state.runs.map(r=>r.run_id===run.run_id?detail:r);renderReports(box);appendReportPager(box)});card.append(more)}appendDeanRequest(card,run);appendReportDeletion(card,run);box.append(card)}}
$('#loginForm').onsubmit=async e=>{e.preventDefault();$('#loginSubmit').disabled=true;$('#authError').textContent='';try{await api(setup?'/api/setup':'/api/login',{username:$('#loginId').value,password:$('#loginPassword').value,name:$('#setupName').value});$('#loginPassword').value='';view='overview';await refresh()}catch(error){$('#authError').textContent=error.message}finally{$('#loginSubmit').disabled=false}};
$('#logout').onclick=()=>action(async()=>{await api('/api/logout',{});location.reload()});$('#refresh').onclick=()=>action(refresh);$('#passwordNav').onclick=()=>{view='password';renderNav();render()};
(async()=>{try{setup=(await api('/api/setup-status')).needs_setup;if(setup){$('#authEyebrow').textContent='FIRST-TIME SETUP';$('#authTitle').textContent='Create your administrator account';$('#authDescription').textContent='This one-time setup establishes the administrator. You can then create faculty and reviewer accounts.';$('#setupNameLabel').hidden=false;$('#setupName').required=true;$('#loginPassword').minLength=12;$('#loginPassword').autocomplete='new-password';$('#loginSubmit').textContent='Create administrator';$('#loginHint').textContent='Use a unique password of at least 12 characters. No default accounts are provided.'}else{try{await refresh()}catch{}}}catch(e){$('#authError').textContent=e.message}})();
function mayReviewRun(run){if(run.detail_loaded===false)return false;const a=run.review_assignment;return !a||!a.request_id||(state.user.role==='dean'&&a.dean_id===state.user.id&&a.status==='accepted')}
function bulkConsentForm(){
 const form=document.createElement('form');form.className='card';
 const departments=[...new Set(state.faculty.map(f=>f.department).filter(Boolean))].sort();
 form.innerHTML='<h3>Request consent from a group</h3><p>Send individual requests to faculty in one department or across the institution.</p><div class="grid two"><label>Request scope<select name="scope"><option value="department">Department-wide</option><option value="institution">Institution-wide</option></select></label><label id="bulkConsentDepartment">Department<select name="department">'+departments.map(d=>'<option value="'+esc(d)+'">'+esc(d)+'</option>').join('')+'</select></label></div><fieldset class="attribution-checklist"><legend>Sources to request</legend>'+['scholar','scopus','wos'].map(s=>'<label><input type="checkbox" name="source" value="'+s+'"> '+(s==='scholar'?'Google Scholar':s==='scopus'?'Scopus':'Web of Science')+'</label>').join('')+'</fieldset><label>Purpose<textarea name="message" required maxlength="2000" placeholder="Explain why consent is requested"></textarea></label><p class="muted">Uses each faculty member’s saved source profiles. Faculty without valid links or active accounts are listed as skipped. Existing consent and pending requests are not duplicated.</p><button type="submit">Preview recipients</button><div class="bulk-consent-preview" aria-live="polite"></div>';
 const preview=form.querySelector('.bulk-consent-preview');
 form.oninput=()=>{preview.replaceChildren();form.querySelector('#bulkConsentDepartment').hidden=form.elements.scope.value==='institution'};
 form.onsubmit=e=>{e.preventDefault();action(async()=>{
  const f=new FormData(form),body={scope:f.get('scope'),department:f.get('department'),sources:f.getAll('source'),message:f.get('message')};
  const result=await api('/api/consent/batch',body);
  preview.innerHTML='<h3>'+result.recipient_count+' faculty will receive a request</h3><p>'+result.skipped_count+' skipped. Consent is granted only after each faculty member approves.</p><details><summary>Recipients</summary>'+table(['Faculty','Department','Sources'],result.recipients.map(r=>[r.name,r.department,r.sources.join(', ')]))+'</details><details><summary>Skipped faculty & reasons</summary>'+table(['Faculty','Reason'],result.skipped.map(r=>[r.name,r.reason]))+'</details>';
  const send=document.createElement('button');send.type='button';send.textContent='Send '+result.recipient_count+' consent requests';send.disabled=result.recipient_count===0;
  send.onclick=()=>action(async()=>{send.disabled=true;try{const sent=await api('/api/consent/batch',{...body,confirm:true,preview_token:result.preview_token});await refresh();notify('Sent '+sent.sent+' individual consent requests. '+sent.skipped+' faculty skipped.')}catch(error){preview.replaceChildren();throw error}});
  preview.append(send);
 })};return form;
}
function renderConsentInbox(box){
 box.innerHTML='<section class="card"><h2>Faculty consent requests</h2><p>Requests do not grant access. Only the faculty member can approve or decline their request. Requests expire after seven days.</p></section>';
 if(can('request_consent')){
 box.append(bulkConsentForm());
 const form=document.createElement('form');form.className='card';
 form.innerHTML='<h3>Request source consent</h3><label>Faculty<select name="faculty_id">'+state.faculty.map(f=>'<option value="'+esc(f.faculty_id)+'">'+esc(f.name)+'</option>').join('')+'</select></label>'+['scholar','scopus','wos'].map(s=>'<label><input type="checkbox" name="source" value="'+s+'"> '+s.toUpperCase()+'</label><label>Profile URL<input type="url" name="'+s+'"></label>').join('')+'<label>Purpose<textarea name="message" required maxlength="2000"></textarea></label><button>Send to faculty</button>';
 form.onsubmit=e=>{e.preventDefault();action(async()=>{const f=new FormData(form);const sources=f.getAll('source');const profiles={};for(const s of sources)if(f.get(s))profiles[s]=f.get(s);await api('/api/consent/request',{faculty_id:f.get('faculty_id'),sources,profiles,message:f.get('message')});await refresh();notify('Consent request sent to the faculty inbox.')})};box.append(form)}
 const requests=state.consent_requests||[];
 if(state.user.role!=='faculty'){
  const batches=new Map();for(const request of requests)if(request.batch_id){if(!batches.has(request.batch_id))batches.set(request.batch_id,[]);batches.get(request.batch_id).push(request)}
  for(const [id,rows] of batches){const card=document.createElement('section');card.className='card';const counts={};rows.forEach(r=>counts[r.status]=(counts[r.status]||0)+1);card.innerHTML='<h3>Group consent request · '+rows.length+' faculty</h3><p>'+esc(rows[0].message)+'</p><p>'+esc(Object.entries(counts).map(([status,count])=>count+' '+status).join(' · '))+'</p><p class="muted">Requested by '+esc(rows[0].requester_name)+' · '+esc(rows[0].created_at)+'</p><details><summary>Individual responses</summary>'+table(['Faculty','Status','Sources'],rows.map(r=>[state.faculty.find(f=>f.faculty_id===r.faculty_id)?.name||r.faculty_id,r.status,r.sources.join(', ')]))+'</details>';box.append(card)}
 }
 for(const r of requests.filter(r=>state.user.role==='faculty'||!r.batch_id)){const card=document.createElement('section');card.className='card';card.innerHTML='<h3>'+esc(r.faculty_id)+' · '+esc(r.status)+'</h3><p>Requested by '+esc(r.requester_name)+'</p><p>'+esc(r.message)+'</p>'+table(['Source','Profile URL'],r.sources.map(s=>[s,r.links[s]]))+'<p>Expires: '+esc(r.expires_at)+'</p><p>'+esc(r.response_note||'')+'</p>';
 if(can('respond_consent')&&r.status==='pending'){const note=document.createElement('textarea');note.placeholder='Optional response note';note.maxLength=2000;card.append(note);for(const decision of ['approved','declined']){const b=document.createElement('button');b.textContent=decision==='approved'?'Approve consent':'Decline';b.onclick=()=>action(async()=>{await api('/api/consent/respond',{request_id:r.id,decision,note:note.value});await refresh();notify('Consent request '+decision+'.')});card.append(b)}}box.append(card)}
}
function appendDeanRequest(card,run){
 const a=run.review_assignment;
 if(a?.request_id){const p=document.createElement('p');p.textContent='Assigned Dean: '+a.dean_name+' · '+a.status+((can('request_dean_review')&&!(state.reviewers||[]).some(d=>d.id===a.dean_id))?' (account disabled; select a replacement below)':'');card.append(p)}
 if(!can('request_dean_review')||run.status!=='AWAITING_APPROVAL'||(a?.request_id&&(a.status==='completed'||(['pending','accepted'].includes(a.status)&&(state.reviewers||[]).some(d=>d.id===a.dean_id)))))return;
 const form=document.createElement('form');form.innerHTML='<h3>Request Dean review</h3><label>Dean<select name="dean_id" required>'+ (state.reviewers||[]).map(d=>'<option value="'+d.id+'">'+esc(d.name)+'</option>').join('')+'</select></label><label>Review request<textarea name="message" required maxlength="2000"></textarea></label><button>Send review request</button>';
 form.onsubmit=e=>{e.preventDefault();action(async()=>{const f=new FormData(form);await api('/api/review/request',{run_id:run.run_id,dean_id:Number(f.get('dean_id')),message:f.get('message')});await refresh();notify('Review request sent to the Dean inbox.')})};card.append(form)
}
function renderReviewInbox(box){
 box.innerHTML='<section class="card"><h2>Dean review requests</h2><p>The selected Dean accepts the assignment, reviews attribution and duplicate decisions, then approves publication. Research Office can send requests from Reports.</p></section>';
 for(const r of state.review_requests||[]){const card=document.createElement('section');card.className='card';card.innerHTML='<h3>'+esc(r.run_id)+' · '+esc(r.status)+'</h3><p>'+esc(r.message)+'</p><p>'+esc(r.response_note||'')+'</p>';
 if(can('respond_review_request')&&r.status==='pending'){const note=document.createElement('textarea');note.placeholder='Optional response note';note.maxLength=2000;card.append(note);for(const decision of ['accepted','declined']){const b=document.createElement('button');b.textContent=decision==='accepted'?'Accept review':'Decline';b.onclick=()=>action(async()=>{await api('/api/review/respond',{request_id:r.id,decision,note:note.value});await refresh();notify('Review request '+decision+'.')});card.append(b)}}const open=document.createElement('button');open.textContent='Open reports';open.onclick=()=>{view='reports';renderNav();render()};card.append(open);box.append(card)}
}
let publicationPage=1,publicationQuery='',publicationYear='',reportPage=1,reportTotal=0,selectedReportId=null;
async function renderPublicationPage(box){
 const page=await api('/api/publications?page='+publicationPage+'&query='+encodeURIComponent(publicationQuery)+'&year='+encodeURIComponent(publicationYear));
 box.innerHTML='<section class="card"><h2>Imported publications</h2><p>Records with missing metadata or indirect source verification remain visible as Needs review and are excluded from report calculations.</p><form id="publicationFilters"><label>Search title<input name="query" value="'+esc(publicationQuery)+'"></label><label>Year<input name="year" type="number" min="1900" max="2100" value="'+esc(publicationYear)+'"></label><button>Search</button></form>'+table(['Faculty ID','Title','Year','Source','Citations','Status','Review notes','Citation origin'],page.records.map(p=>[p.faculty_id,p.title,p.year??'Unknown',p.source,p.citations??'Unknown',p.record_status==='pending_review'?'Needs review':'Available for analysis',(p.review_reasons||[]).join('; '),p.citation_count_origin||'Imported source']))+'</section>';
 $('#publicationFilters').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target);publicationQuery=f.get('query');publicationYear=f.get('year');publicationPage=1;action(()=>renderPublicationPage(box))};
 appendPager(box,page.page,page.page_size,page.total,p=>{publicationPage=p;return renderPublicationPage(box)})
}
function appendPager(box,page,size,total,onPage){
 const controls=document.createElement('p');controls.textContent='Page '+page+' of '+Math.max(1,Math.ceil(total/size))+' · '+total+' records ';
 for(const [label,next,disabled] of [['Previous',page-1,page<=1],['Next',page+1,page*size>=total]]){const b=document.createElement('button');b.textContent=label;b.disabled=disabled;b.onclick=()=>action(()=>onPage(next));controls.append(b)}box.append(controls)
}
async function renderReportPage(box){
 const page=await api('/api/reports?page='+reportPage);
 if(view!=='reports')return;
 state.runs=page.records;reportTotal=page.total;
 if(!state.runs.some(r=>r.run_id===selectedReportId))selectedReportId=state.runs[0]?.run_id||null;
 await loadSelectedReport();if(view!=='reports')return;renderReports(box);appendReportPager(box)
}
async function loadSelectedReport(){
 const id=selectedReportId,run=state.runs.find(r=>r.run_id===id);
 if(!run||run.detail_loaded!==false)return;
 const detail=await api('/api/report?run_id='+encodeURIComponent(id));
 state.runs=state.runs.map(r=>r.run_id===id?detail:r);
}
function appendReportPager(box){appendPager(box,reportPage,10,reportTotal,p=>{reportPage=p;return renderReportPage(box)})}
function appendReportDeletion(card,run){
 if(!can('delete_reports')||run.status==='RUNNING')return;
 const button=document.createElement('button');button.className='danger';button.textContent='Delete report permanently';
 button.onclick=()=>action(async()=>{if(!confirm('Permanently delete this report and all its published versions? If it is the current published report, exports will stop until another report is published or restored. Source publications and audit history will remain.'))return;await api('/api/reports/delete',{run_id:run.run_id,confirm:true});reportPage=1;await refresh();notify('Report and its saved versions deleted. Source data and audit history retained.')});
 card.append(button)
}



