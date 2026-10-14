'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const d=require('../static/edit_direction.js');
test('Leading emotions replace rather than stack and preserve spoken words',()=>{
  const initial='[sad] Hello there.';
  const replaced=d.setEmotion(initial,'joyful',initial.length,initial.length);
  assert.equal(replaced.text,'[joyful] Hello there.');
  assert.equal(d.detectEmotion(replaced.text),'joyful');
  assert.equal(d.setEmotion(replaced.text,'').text,'Hello there.');
});
test('Emotion insertion respects existing whitespace and caret',()=>{
  const r=d.setEmotion('  Hello, world.', 'tender',8,8);
  assert.equal(r.text,'  [tender] Hello, world.');
  assert.equal(r.start,17);assert.equal(r.end,17);
});
test('Event insertion never deletes selected narration',()=>{
  const t='She finally opened the door.';
  const start=t.indexOf('opened');
  const r=d.insertEvent(t,'gasp',start,start+6);
  assert.equal(r.text,'She finally <gasp> opened the door.');
  assert.equal(r.text.slice(r.start,r.end),'opened');
  assert.equal(d.countCues(r.text).events,1);
});
test('Event insertion in middle works without moving to first position',()=>{
  const t='Wait for me.';const r=d.insertEvent(t,'sigh',5,5);
  assert.equal(r.text,'Wait <sigh> for me.');
  assert.equal(r.start,r.end);
  assert.ok(r.start>5);
});
test('Emphasis toggles selected text and avoids nested cues',()=>{
  const t='The answer is absolutely yes.';
  const a=t.indexOf('absolutely'), b=a+'absolutely'.length;
  const r=d.toggleEmphasis(t,a,b);
  assert.equal(r.text,'The answer is (((absolutely))) yes.');
  assert.equal(r.text.slice(r.start,r.end),'absolutely');
  assert.equal(d.toggleEmphasis(r.text,r.start,r.end).text,t);
  assert.throws(()=>d.toggleEmphasis('Hello',0,0),/Highlight/);
  assert.throws(()=>d.toggleEmphasis('Hi <laugh>!',3,10),/only spoken words/);
});
test('Clearing cues leaves words and punctuation intact',()=>{
  assert.equal(d.clearDirection('[stern] I am (((very))) serious. <sigh> '),'I am very serious.');
  assert.equal(d.countCues('Hello!').events,0);
  assert.equal(d.hasDirection('<laugh>'),true);
  assert.equal(d.hasDirection('Hello world.'),false);
  assert.equal(d.hasDirection('Hello world.'),false);
});
test('Only supported cue names can be generated',()=>{
  assert.throws(()=>d.insertEvent('Hello','rm -rf /',0,0),/Unsupported/);
  assert.throws(()=>d.setEmotion('Hello','unknown'),/Unsupported/);
});
