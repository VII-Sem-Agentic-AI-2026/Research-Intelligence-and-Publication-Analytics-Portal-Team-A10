/* Small text-only Markdown renderer: never inserts model output as HTML. */
(function(root){
function inlineTokens(value){
 const text=String(value).replace(/\\([*`_])/g,'$1'),tokens=[];
 const pattern=/(\*\*([^*]+)\*\*|`([^`]+)`|\*([^*]+)\*)/g;let pos=0,match;
 while((match=pattern.exec(text))){if(match.index>pos)tokens.push({type:'text',text:text.slice(pos,match.index)});tokens.push({type:match[2]?'strong':match[3]?'code':'em',text:match[2]||match[3]||match[4]});pos=pattern.lastIndex}
 if(pos<text.length)tokens.push({type:'text',text:text.slice(pos)});return tokens;
}
function parseChatBlocks(value){
 const lines=String(value??'').replace(/\r\n?/g,'\n').split('\n'),blocks=[];let i=0;
 const bullet=line=>/^\s*(?:[-*•]|\d+[.)])\s+/.test(line);
 const cells=line=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(c=>c.trim());
 while(i<lines.length){
  const line=lines[i].trim();if(!line){i++;continue}
  if(line.startsWith('```')){const content=[];i++;while(i<lines.length&&!lines[i].trim().startsWith('```'))content.push(lines[i++]);if(i<lines.length)i++;blocks.push({type:'code',text:content.join('\n')});continue}
  if(line.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])&&/^[\s|:\-]+$/.test(lines[i+1])){const headers=cells(line),rows=[];i+=2;while(i<lines.length&&lines[i].trim().includes('|'))rows.push(cells(lines[i++]));blocks.push({type:'table',headers,rows});continue}
  if(/^#{1,6}\s+/.test(line)){blocks.push({type:'heading',text:line.replace(/^#{1,6}\s+/,'')});i++;continue}
  if(bullet(lines[i])){const ordered=/^\s*\d+[.)]/.test(lines[i]),items=[];while(i<lines.length&&bullet(lines[i])&&/^\s*\d+[.)]/.test(lines[i])===ordered){let item=lines[i++].replace(/^\s*(?:[-*•]|\d+[.)])\s+/,'');while(i<lines.length&&/^\s{2,}\S/.test(lines[i])&&!bullet(lines[i]))item+=' '+lines[i++].trim();items.push(item)}blocks.push({type:ordered?'ordered':'list',items});continue}
  const paragraph=[line];i++;while(i<lines.length&&lines[i].trim()&&!bullet(lines[i])&&!/^\s*(?:#{1,6}\s|```)/.test(lines[i])&&!(lines[i].includes('|')&&i+1<lines.length&&/^[\s|:\-]+$/.test(lines[i+1])))paragraph.push(lines[i++].trim());blocks.push({type:'paragraph',text:paragraph.join(' ')});
 }return blocks;
}
function appendInline(node,text,doc){for(const token of inlineTokens(text)){if(token.type==='text')node.append(doc.createTextNode(token.text));else{const el=doc.createElement(token.type);el.textContent=token.text;node.append(el)}}}
function renderChatContent(target,text){
 const doc=target.ownerDocument||document;target.replaceChildren();
 for(const block of parseChatBlocks(text)){
  if(block.type==='list'||block.type==='ordered'){const list=doc.createElement(block.type==='list'?'ul':'ol');for(const item of block.items){const li=doc.createElement('li');appendInline(li,item,doc);list.append(li)}target.append(list)}
  else if(block.type==='table'){const wrap=doc.createElement('div');wrap.className='chat-table-wrap';const table=doc.createElement('table'),head=doc.createElement('thead'),hr=doc.createElement('tr'),body=doc.createElement('tbody');for(const title of block.headers){const cell=doc.createElement('th');appendInline(cell,title,doc);hr.append(cell)}head.append(hr);for(const row of block.rows){const tr=doc.createElement('tr');for(let n=0;n<block.headers.length;n++){const td=doc.createElement('td');appendInline(td,row[n]||'',doc);tr.append(td)}body.append(tr)}table.append(head,body);wrap.append(table);target.append(wrap)}
  else if(block.type==='code'){const pre=doc.createElement('pre'),code=doc.createElement('code');code.textContent=block.text;pre.append(code);target.append(pre)}
  else{const el=doc.createElement(block.type==='heading'?'h4':'p');appendInline(el,block.text,doc);target.append(el)}
 }
}
root.renderChatContent=renderChatContent;
if(typeof module!=='undefined'&&module.exports)module.exports={parseChatBlocks,inlineTokens,renderChatContent};
})(typeof globalThis!=='undefined'?globalThis:this);
