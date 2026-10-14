'use strict';
/* Small, dependency-free helpers shared by the sentence-editor UI and tests.
 * KittenTTS2 recognizes one leading emotion, inline events, and (((emphasis))).
 * All helpers return fresh strings rather than mutating source text. */
(function(root, factory) {
  const helpers = factory();
  if (typeof module === 'object' && module.exports) module.exports = helpers;
  if (root) root.KittenDirection = helpers;
})(typeof globalThis !== 'undefined' ? globalThis : undefined, function() {
  const EMOTIONS = ['angry','contemplative','excited','joyful','mundane','nervous','sad','stern','surprised','tender'];
  const EVENTS = ['gasp','giggle','growl','gulp','laugh','pause','scoff','sigh','sob','um'];
  const emotionNames = EMOTIONS.join('|');
  const eventNames = EVENTS.join('|');
  const leading = new RegExp('^([ \\t]*)(?:\\[(?:'+emotionNames+')\\][ \\t]*)*', 'i');
  const firstEmotion = new RegExp('^[ \\t]*\\[('+emotionNames+')\\]', 'i');
  const emotionPattern = new RegExp('\\[(?:'+emotionNames+')\\]', 'gi');
  const eventPattern = new RegExp('<(?:'+eventNames+')>', 'gi');
  function detectEmotion(text) {return firstEmotion.exec(text)?.[1]?.toLowerCase() || '';}
  function hasDirection(text) {return (text.match(emotionPattern)||[]).length > 0 || (text.match(eventPattern)||[]).length > 0 || /\(\(\([\s\S]+?\)\)\)/.test(text);}
  // Reusable RegExp /g objects reset lastIndex on each .test() call if needed.
  function countCues(text) {
    return {emotions:(text.match(emotionPattern)||[]).length,
            events:(text.match(eventPattern)||[]).length,
            emphasis:(text.match(/\(\(\([\s\S]*?\)\)\)/g)||[]).length};
  }
  function setEmotion(text, value, start=0, end=start) {
    if (value && !EMOTIONS.includes(value)) throw Error('Unsupported KittenTTS emotion');
    const m=leading.exec(text), replaced=m?.[0]?.length||0, indent=m?.[1]||'';
    const prefix=indent+(value?'['+value+'] ':'');
    const updated=prefix+text.slice(replaced);
    const mapped=p=> p<=replaced ? prefix.length : Math.max(prefix.length,p+prefix.length-replaced);
    return {text:updated,start:mapped(start),end:mapped(end)};
  }
  function insertEvent(text, value, start=0, end=start) {
    if (!EVENTS.includes(value)) throw Error('Unsupported KittenTTS event');
    const pos=Math.min(text.length,Math.max(0,start));
    const before=text.slice(0,pos), after=text.slice(pos);
    const leftSpace=before.length && !/\s$/.test(before) ? ' ' : '';
    const rightSpace=after.length && !/^\s/.test(after) ? ' ' : '';
    const inserted=leftSpace+'<'+value+'>'+rightSpace;
    return {text:before+inserted+after, start:pos+inserted.length,
            end:pos+inserted.length+Math.max(0,end-start)};
  }
  function toggleEmphasis(text, start, end) {
    const a=Math.max(0,Math.min(text.length,start)),b=Math.max(a,Math.min(text.length,end));
    if(a===b)throw Error('Highlight the word or phrase to emphasize first.');
    const target=text.slice(a,b);
    // Existing emphasis: allow selecting the wrapped text or only its contents.
    if (text.slice(a-3,a)==='(((' && text.slice(b,b+3)=== ')))') {
      return {text:text.slice(0,a-3)+target+text.slice(b+3),start:a-3,end:b-3};
    }
    if(target.startsWith('(((') && target.endsWith(')))')) {
      const word=target.slice(3,-3);
      return {text:text.slice(0,a)+word+text.slice(b),start:a,end:a+word.length};
    }
    if (/\(\(\(|\)\)\)|\[[^\]]*\]|<[^>]*>/.test(target))
      throw Error('Select only spoken words, not existing direction tags.');
    if(!target.trim())throw Error('Select a spoken word or phrase first.');
    const prefix='(((',suffix=')))';
    return {text:text.slice(0,a)+prefix+target+suffix+text.slice(b),start:a+3,end:b+3};
  }
  function clearDirection(text) {
    // Keep the actual spoken words and spacing. Only recognize official tags.
    return text.replace(emotionPattern,'').replace(eventPattern,'')
      .replace(/\(\(\(([\s\S]*?)\)\)\)/g,'$1')
      .replace(/[ \t]{2,}/g,' ').trim();
  }
  return {EMOTIONS,EVENTS,detectEmotion,countCues,hasDirection,setEmotion,insertEvent,toggleEmphasis,clearDirection};
});
