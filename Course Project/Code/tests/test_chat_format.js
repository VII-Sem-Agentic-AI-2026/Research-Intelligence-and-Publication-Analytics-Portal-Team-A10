const test=require('node:test');
const assert=require('node:assert/strict');
const {parseChatBlocks,inlineTokens,renderChatContent}=require('../dashboard/chat-format.js');

test('paragraphs and lists form separate readable blocks',()=>{
 const blocks=parseChatBlocks('I can help with your research.\n\n- **Generate reports** for a year.\n- Upload publication exports.\n\nTry: create my report.');
 assert.deepEqual(blocks.map(b=>b.type),['paragraph','list','paragraph']);
 assert.equal(blocks[1].items.length,2);
 assert.deepEqual(inlineTokens(blocks[1].items[0])[0],{type:'strong',text:'Generate reports'});
});
test('old Markdown tables render as bounded tables instead of raw pipes',()=>{
 const blocks=parseChatBlocks('| Feature | Access |\n| --- | --- |\n| **Reports** | Own records |');
 assert.equal(blocks[0].type,'table');assert.deepEqual(blocks[0].headers,['Feature','Access']);
 assert.deepEqual(blocks[0].rows,[['**Reports**','Own records']]);
});
test('numbered steps and code remain distinct',()=>{
 assert.deepEqual(parseChatBlocks('1. Sign in\n2. Open Assistant\n\n```\nexample\n```').map(b=>b.type),['ordered','code']);
 assert.deepEqual(inlineTokens('\\*\\*Reports\\*\\*')[0],{type:'strong',text:'Reports'});
});
test('untrusted model output is always inserted as text, never HTML',()=>{
 class Element{constructor(tag){this.tag=tag;this.children=[];this.ownerDocument=doc}append(...nodes){this.children.push(...nodes)}replaceChildren(){this.children=[]}set innerHTML(v){throw Error('HTML insertion forbidden')}}
 const doc={createElement:tag=>new Element(tag),createTextNode:text=>({text})};
 const target=new Element('div');renderChatContent(target,'<img src=x onerror=alert(1)> **Safe text**');
 assert.equal(target.children[0].tag,'p');assert.equal(target.children[0].children[0].text,'<img src=x onerror=alert(1)> ');
 assert.equal(target.children[0].children[1].tag,'strong');
});
