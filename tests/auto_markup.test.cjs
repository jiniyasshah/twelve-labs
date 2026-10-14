const assert=require('node:assert/strict');
const {suggest}=require('../static/auto_markup.js');
function check(description,test){test();console.log('PASS:',description);}
check('emotion & events are recognized from obvious cues',()=>{
  const r=suggest('No way! Haha, that was hilarious. I am heartbroken.');
  assert.match(r.text,/\[surprised\]/);assert.match(r.text,/<laugh>/);assert.match(r.text,/\[sad\]/);
  assert.ok(r.stats.emotions>=2&&r.stats.events>=1);
});
check('emphasis wraps meaningful word but not whole sentence',()=>{
  const r=suggest('This is absolutely incredible.');assert.match(r.text,/\(\(\(absolutely\)\)\)/);
});
check('neutral text is unchanged byte-for-byte including whitespace',()=>{
  const s='Hello there.   Welcome to the studio.\n    Another line.';
  const r=suggest(s);assert.equal(r.text,s);assert.equal(r.changed,false);
});
check('manually inserted emotion is retained at start',()=>{
  const r=suggest('[sad] Haha, this is a funny joke.');
  assert.match(r.text,/^\[sad\]/);assert.match(r.text,/<laugh>/);
  assert.doesNotMatch(r.text,/\[joyful\]|\[surprised\]/);
});
check('never wraps existing emphasis and rerunning stays stable',()=>{
  const s='[excited] That was (((absolutely))) incredible!';
  const r=suggest(s);const reread=suggest(r.text);
  assert.equal(reread.text,r.text);
  assert.equal((r.text.match(/\(\(\(/g)||[]).length,1);
});
check('disabling tag classes is honored',()=>{
  const r=suggest('No way! Haha, that was absolutely incredible!',{emotions:false,events:false,emphasis:true});
  assert.equal(r.stats.emotions,0);assert.equal(r.stats.events,0);assert.ok(r.stats.emphasis>0);
});
check('subtle has fewer changes than expressive',()=>{
  const s='No way! This is absolutely incredible! We won!';
  assert.ok(suggest(s,{intensity:'subtle'}).total<=suggest(s,{intensity:'expressive'}).total);
});
