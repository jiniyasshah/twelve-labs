/* Kitten Studio v2.5: deterministic, local narration direction suggestions.
   Zero network, no generative model, no external dependency; always preview before apply.
   All tags are from KittenTTS 2's documented expression vocabulary. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.KittenAutoMarkup = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const EMOTIONS = [
    ['tender', /\b(i love you|you are safe|you're safe|here for you|take care|hold you close)\b/i],
    ['angry', /\b(how dare|furious|unacceptable|outrageous|infuriating|never again|betrayed|i hate)\b/i],
    ['sad', /\b(heartbroken|passed away|miss you|i miss|grief|goodbye forever|so sorry|lonely|devastated|lost someone)\b/i],
    ['nervous', /\b(terrified|scared|i'm afraid|i am afraid|worried|what if|so nervous|anxious|uneasy)\b/i],
    ['excited', /\b(can't wait|cannot wait|let's go|big news|this is it|so excited|what a moment|we did it)\b/i],
    ['joyful', /\b(we won|we made it|congratulations|wonderful|so happy|delighted|grateful|thank you so much|best day|fantastic)\b/i],
    ['surprised', /\b(no way|wait,? what|oh my|wow|unbelievable|i can't believe|i cannot believe|what a surprise)\b/i],
    ['stern', /\b(listen carefully|do not ignore|never do that|this is a warning|this is important|you must understand|under no circumstances)\b/i],
    ['contemplative', /\b(i wonder|what if we|perhaps|imagine if|think about it|i've been thinking|what does it mean)\b/i]
  ];
  const EVENTS = [
    ['laugh', /\b(haha(?:ha)*|hehe(?:he)*|that's hilarious|so funny|i'm laughing)\b/i],
    ['gasp', /\b(oh my god|i can't believe my eyes|that's impossible|no way!)\b/i],
    ['sigh', /\b(ugh|what a long day|i'm exhausted|so disappointed)\b/i],
    ['sob', /\b(i can't stop crying|tears won't stop|i'm sobbing)\b/i],
    ['giggle', /\b(giggle|hee hee|how adorable)\b/i]
  ];
  const EMPHASIS = [
    ['absolutely',9],['never',9],['always',7],['only',7],['impossible',9],['critical',9],
    ['danger',8],['everything',8],['nothing',7],['finally',7],['secret',7],
    ['important',8],['incredible',8],['unbelievable',8],['amazing',7],['wonderful',6],
    ['must',7],['really',5],['truly',6],['completely',6],['perfect',5],
    ['love',5],['hate',6],['stop',7],['now',5],['won',7],['remember',6],['wait',6],
    ['exactly',6],['different',4],['first',4],['last',4],['today',3]
  ];
  const SAFE_EXISTING = /\[[a-z]+\]|<[a-z]+>|\(\(\([\s\S]*?\)\)\)/gi;
  const emotionAlready = /^\s*\[(angry|contemplative|excited|joyful|mundane|nervous|sad|stern|surprised|tender)\]/i;
  const eventAlready = /<(gasp|giggle|growl|gulp|laugh|pause|scoff|sigh|sob|um)>/i;
  const emphasisAlready = /\(\(\([\s\S]*?\)\)\)/;
  function maskSpans(text) {
    return text.replace(SAFE_EXISTING, m => ' '.repeat(m.length));
  }
  function eligibleEmotion(sentence, intensity) {
    const plain = maskSpans(sentence);
    for (const [name, matcher] of EMOTIONS) if (matcher.test(plain)) return name;
    if (intensity === 'expressive' && /^\s*(?:why|how|what)[^.!?]*\?\s*$/.test(plain.toLowerCase())) return 'surprised';
    if (intensity === 'expressive' && /!\s*$/.test(plain) && /\b(yes|great|success|awesome|amazing)\b/i.test(plain)) return 'excited';
    return null;
  }
  function eligibleEvent(sentence, intensity) {
    if (intensity === 'subtle') return null;
    const plain = maskSpans(sentence);
    for (const [tag, matcher] of EVENTS) if (matcher.test(plain)) return tag;
    if (intensity === 'expressive' && /\.\.\./.test(plain) && !/[!?]/.test(plain)) return 'pause';
    return null;
  }
  function emphasisPositions(sentence, intensity) {
    const masked=maskSpans(sentence);
    const candidates=[];
    for(const [word,score] of EMPHASIS) {
      const re=new RegExp('\\b'+word+'\\b','gi');let match;
      while((match=re.exec(masked))!==null){
        if(intensity==='subtle' && score<8)continue;
        if(intensity==='balanced' && score<6)continue;
        candidates.push({start:match.index,end:match.index+match[0].length,score});
      }
    }
    candidates.sort((a,b)=>b.score-a.score || a.start-b.start);
    const selected=[];
    const max=intensity==='expressive'?2:1;
    for(const c of candidates){
      if(selected.length>=max)break;
      if(selected.some(p=>c.start<p.end+5 && p.start<c.end+5))continue;
      selected.push(c);
    }
    return selected.sort((a,b)=>b.start-a.start);
  }
  function splitSentences(line, intensity){
    if(intensity==='subtle') return [line];
    // Do not split markup already added by users. Natural sentences are separated
    // only at strong punctuation followed by uppercase/new quoted speech.
    return line.split(/(?<=[!?])\s+(?=[A-Z"“])|(?<=\.)\s+(?=[A-Z"“])/g).filter(Boolean);
  }
  function processSentence(sentence, options, stats){
    if(!sentence.trim())return sentence;
    let out=sentence;
    if(options.emphasis && !emphasisAlready.test(out)) {
      const points=emphasisPositions(out, options.intensity);
      for(const p of points){out=out.slice(0,p.start)+'((('+out.slice(p.start,p.end)+')))' +out.slice(p.end);stats.emphasis++;}
    }
    if(options.events && !eventAlready.test(out)) {
      const event=eligibleEvent(out,options.intensity);
      if(event){
        // Keep a manually selected emotion at position zero: events are inline.
        const existingEmotion=out.match(/^(\s*\[(?:angry|contemplative|excited|joyful|mundane|nervous|sad|stern|surprised|tender)\]\s*)/i);
        if(existingEmotion)out=existingEmotion[0]+`<${event}> `+out.slice(existingEmotion[0].length);
        else out=`<${event}> `+out;
        stats.events++;
      }
    }
    if(options.emotions && !emotionAlready.test(out)){
      const emotion=eligibleEmotion(out,options.intensity);
      if(emotion){out=`[${emotion}] `+out;stats.emotions++;}
    }
    return out;
  }
  function suggest(text, options={}){
    const opts={intensity:'balanced',emotions:true,events:true,emphasis:true,...options};
    if(!['subtle','balanced','expressive'].includes(opts.intensity))opts.intensity='balanced';
    const stats={emotions:0,events:0,emphasis:0};
    // Preserve existing blank lines and leading indentation; do not rewrite their text.
    const result=String(text??'').split('\n').map(line=>{
      if(!line.trim())return line;
      const lead=line.match(/^\s*/)[0];
      const body=line.slice(lead.length);
      // Existing manual emotion tags apply to the entire line; leave that line
      // unsplit so an auto-generated emotion cannot silently replace the intent.
      const parts=emotionAlready.test(body)?[body]:splitSentences(body,opts.intensity);
      const output=parts.map(part=>processSentence(part,opts,stats));
      return lead+output.join(output.length>1 && opts.emotions?'\n':' ');
    }).join('\n');
    // If no cue was suggested, avoid incidental changes to sentence spacing.
    const total=stats.emotions+stats.events+stats.emphasis;
    const output=total?result:String(text??'');
    return {text:output,stats,total,changed:output!==text};
  }
  return {suggest};
});
