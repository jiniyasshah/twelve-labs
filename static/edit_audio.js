'use strict';
// Sentence editor. Native Canvas waveform; no remote dependencies or paid APIs.
(() => {
  const $e = s => document.querySelector(s);
  const editor = {rid:null, item:null, sentences:[], selected:-1, peaks:[], aligned:false,
                  previewJob:null, listening:false, busy:false, caret:{start:0,end:0},
                  drafts:{}, directionUndo:null};
  const direction=window.KittenDirection;
  const clamp = (n,lo,hi) => Math.min(hi,Math.max(lo,n));
  const format = n => Number(n||0).toFixed(2)+'s';
  function setStatus(message, error=false) {
    const el=$e('#edit-job-status');el.textContent=message||'';el.classList.toggle('bad',error);
  }
  function selected() {return editor.sentences[editor.selected]||null;}
  function supportsDirection(){return editor.item?.model==='KittenML/kitten-tts-2';}
  function captureCaret(){
    const t=$e('#edit-replacement');
    editor.caret={start:t.selectionStart,end:t.selectionEnd};
  }
  function saveDraft(){
    if(editor.selected<0)return;
    editor.drafts[editor.selected]={text:$e('#edit-replacement').value,
      delivery:$e('#edit-delivery').value,start:$e('#edit-start').value,end:$e('#edit-end').value};
  }
  function changeSentence(index){
    if(index===editor.selected)return;
    saveDraft();editor.selected=index;editor.directionUndo=null;
    clearPreview();renderSentences();renderSelection();drawWaveform();
  }
  function directionSummary(message){
    const c=direction.countCues($e('#edit-replacement').value);
    $e('#edit-direction-hint').textContent=message ||
      `${c.emotions} emotion · ${c.events} event${c.events===1?'':'s'} · ${c.emphasis} emphasized phrase${c.emphasis===1?'':'s'}. `+
      'Select words to emphasize, or place the cursor to insert an event.';
    $e('#edit-emotion').value=direction.detectEmotion($e('#edit-replacement').value);
    $e('#edit-clear-cues').disabled=!(c.emotions||c.events||c.emphasis);
    $e('#edit-undo-direction').disabled=!editor.directionUndo;
  }
  function modifyDirection(change){
    if(editor.busy||!supportsDirection())return;
    const t=$e('#edit-replacement'), prior=t.value;
    try{
      const result=change(prior,editor.caret.start,editor.caret.end);
      if(result.text===prior)return;
      editor.directionUndo={text:prior,caret:{...editor.caret}};
      t.value=result.text;t.focus();
      t.setSelectionRange(result.start,result.end);
      captureCaret();clearPreview();saveDraft();directionSummary();
    }catch(e){directionSummary(e.message);}
  }

  function clearPreview() {
    editor.previewJob=null;
    $e('#edit-preview-wrap').hidden=true;
    $e('#edit-preview-audio').pause();$e('#edit-preview-audio').removeAttribute('src');
  }
  async function fetchInfo() {
    if(!editor.rid)return;
    const [info,wave] = await Promise.all([api('/api/edit/'+encodeURIComponent(editor.rid)),api('/api/edit/'+encodeURIComponent(editor.rid)+'/waveform')]);
    editor.item=info.recording;editor.sentences=info.sentences;
    editor.aligned=info.aligned;editor.peaks=wave.peaks;
    $e('#edit-record-name').textContent=info.recording.title;
    $e('#edit-duration').textContent=format(info.recording.duration);
    $e('#edit-wave-end').textContent=formatTime(info.recording.duration);
    $e('#edit-original-audio').src='/api/audio/'+encodeURIComponent(editor.rid);
    $e('#edit-align-method').textContent=info.aligned
      ? (info.method==='whisper-word-timestamps'?'Whisper word timestamps · review before editing':'Estimated boundaries · optional alignment engine unavailable')
      : 'No timestamps yet. Run Detect sentences.';
    $e('#edit-editor-warning').textContent=info.aligned && info.method==='whisper-word-timestamps'
      ? 'Detection is approximate, especially around pauses, event tags and repeated words. Review start/end before applying.'
      : 'Times are estimates, not verified speech boundaries. Install the free alignment engine with INSTALL_ALIGNMENT_WINDOWS.bat, re-detect and review.';
    $e('#edit-preview').disabled=!info.aligned || !info.can_replace;
    if(!info.can_replace)setStatus('Combined multi-voice scripts: edit an individual segment from History, then rebuild the script.');
    if(!info.has_saved_settings && info.can_replace)setStatus('Older recording: original generation settings were not saved. Default settings will be used for regeneration.');
    editor.selected=clamp(editor.selected,0,Math.max(0,editor.sentences.length-1));
    renderSentences();renderSelection();drawWaveform();
  }
  function renderSentences(){
    $e('#edit-sentence-count').textContent=editor.sentences.length+' sentence'+(editor.sentences.length===1?'':'s');
    const root=$e('#edit-sentence-list');root.replaceChildren();
    editor.sentences.forEach((s,i)=>{
      const btn=document.createElement('button');btn.type='button';btn.className='edit-sentence'+(i===editor.selected?' active':'');
      const meta=document.createElement('span');meta.className='edit-sentence-meta';
      meta.textContent=`${String(i+1).padStart(2,'0')}  ·  ${s.start===undefined?'not aligned':format(s.start)+' – '+format(s.end)}`;
      const body=document.createElement('span');body.className='edit-sentence-text';body.textContent=s.text;
      btn.append(meta,body);
      btn.addEventListener('click',()=>changeSentence(i));
      root.appendChild(btn);
    });
  }
  function renderSelection(){
    const s=selected();
    const draft=editor.drafts[editor.selected];
    $e('#edit-replacement').value=draft?.text??s?.text??'';
    $e('#edit-delivery').value=draft?.delivery||'original';
    $e('#edit-start').value=draft?.start??Number(s?.start??0).toFixed(2);
    $e('#edit-end').value=draft?.end??Number(s?.end??0).toFixed(2);
    editor.caret={start:0,end:0};
    $e('#edit-direction-panel').hidden=!supportsDirection();
    $e('#edit-onnx-direction-note').hidden=supportsDirection();
    editor.directionUndo=null;directionSummary();
    const score=Math.round(Number(s?.confidence||0)*100);
    $e('#edit-confidence').textContent=s?.start===undefined?'Run detection':score>=75?`Matched ${score}%`:`Low confidence · ${score}%`;
    $e('#edit-preview').disabled=!editor.aligned||!editor.item?.kind||editor.item.kind==='script'||!s;
    $e('#edit-listen').disabled=!editor.aligned||!s;
  }
  function drawWaveform(){
    const canvas=$e('#edit-waveform');if(!canvas)return;
    const rect=canvas.getBoundingClientRect();
    const pixelRatio=window.devicePixelRatio||1;
    const w=Math.max(100,Math.round(rect.width*pixelRatio)),h=Math.round(130*pixelRatio);
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
    const ctx=canvas.getContext('2d');if(!ctx)return;
    const dark=document.documentElement.dataset.theme==='dark';
    ctx.clearRect(0,0,w,h);ctx.fillStyle=dark?'#161820':'#f5f7fa';ctx.fillRect(0,0,w,h);
    const duration=editor.item?.duration||0;
    if(!duration)return;
    const s=selected();if(s&&s.start!==undefined){
      ctx.fillStyle=dark?'#263e70':'#dfeaff';
      const x1=s.start/duration*w,x2=s.end/duration*w;ctx.fillRect(x1,0,x2-x1,h);
    }
    ctx.lineWidth=Math.max(1,pixelRatio);ctx.strokeStyle=dark?'#7488b6':'#607fab';
    ctx.beginPath();
    const wave=editor.peaks||[];
    for(let i=0;i<w;i++){
      const amp=Math.min(1,Number(wave[Math.floor(i/w*wave.length)]||0)*1.4);
      const height=amp*h*.43;
      ctx.moveTo(i,h/2-height);ctx.lineTo(i,h/2+height);
    }
    ctx.stroke();
    ctx.strokeStyle=dark?'#566173':'#a9bdd4';
    editor.sentences.slice(1).forEach(part=>{
      if(part.start===undefined)return;
      const x=part.start/duration*w;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
    });
    if(s?.start!==undefined){
      ctx.strokeStyle=dark?'#69a0ff':'#2462d6';ctx.lineWidth=2*pixelRatio;
      for(const v of [s.start,s.end]){const x=v/duration*w;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}
    }
  }
  async function poll(jobId){
    for(let i=0;i<2400;i++){
      await new Promise(r=>setTimeout(r,850));
      const job=await api('/api/jobs/'+encodeURIComponent(jobId));
      setStatus([job.message,job.warning].filter(Boolean).join(' · '));
      if(job.status==='error')throw new Error(job.error||'Job failed');
      if(job.status==='done')return job;
      if(job.status==='cancelled')throw new Error('Job cancelled');
    }
    throw new Error('Job is still running. Try again after it finishes.');
  }
  async function run(action){
    if(editor.busy||!editor.rid)return;
    editor.busy=true;
    for(const id of ['edit-align','edit-preview','edit-apply'])$e('#'+id).disabled=true;
    try{
      const rid=encodeURIComponent(editor.rid);
      if(action==='align'){
        clearPreview();setStatus('Detecting speech and matching words to your transcript…');
        const r=await api('/api/edit/'+rid+'/align',{method:'POST',body:'{}'});
        const job=await poll(r.job_id);editor.drafts={};editor.directionUndo=null;await fetchInfo();
        setStatus(job.warning||'Sentence boundaries ready. Listen to the boundaries before editing.');
      }else if(action==='preview'){
        const s=selected();if(!s)throw new Error('Select a sentence.');
        const text=$e('#edit-replacement').value.trim();if(!text)throw new Error('Enter replacement speech.');
        clearPreview();setStatus('Generating only this sentence…');
        const delivery=$e('#edit-delivery').value;
        const r=await api('/api/edit/'+rid+'/preview',{method:'POST',body:JSON.stringify({
          sentence_index:editor.selected,text,device:$e('#device-select').value,
          ...(delivery!=='original'?{preset:delivery}:{})
        })});
        const job=await poll(r.job_id);editor.previewJob=job.id;
        $e('#edit-preview-audio').src=job.preview_url;
        $e('#edit-preview-wrap').hidden=false;
        setStatus('Listen to the preview. Adjust start/end and apply only when satisfied.');
      }else if(action==='apply'){
        if(!editor.previewJob)throw new Error('Generate a preview first.');
        const s=selected();if(!s)throw new Error('Select a sentence.');
        const start=Number($e('#edit-start').value),end=Number($e('#edit-end').value);
        if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>editor.item.duration||end-start<.04)throw new Error('Check the replacement start and end times.');
        setStatus('Splicing audio, preserving the other sentences…');
        const r=await api('/api/edit/'+rid+'/apply',{method:'POST',body:JSON.stringify({sentence_index:editor.selected,start,end,preview_job_id:editor.previewJob})});
        const job=await poll(r.job_id);
        clearPreview();await loadLibrary();
        editor.selected=0;await open(job.result_id);
        setStatus('New version saved. Original remains in History. Re-align to make another edit.');
        toast('Replacement saved as a new recording.');
      }
    }catch(e){setStatus(e.message,true);toast(e.message,true);}
    finally{
      editor.busy=false;$e('#edit-align').disabled=false;$e('#edit-apply').disabled=false;
      $e('#edit-preview').disabled=!editor.aligned||editor.item?.kind==='script';
    }
  }
  async function open(rid){
    editor.rid=rid;editor.item=null;editor.sentences=[];editor.selected=0;editor.aligned=false;
    editor.drafts={};editor.directionUndo=null;
    clearPreview();
    $e('#edit-empty').hidden=true;$e('#edit-workspace').hidden=false;
    selectView('edit');setStatus('Loading audio and transcript…');
    try{await fetchInfo();if(!editor.aligned)setStatus('Click Detect sentences to locate each phrase in the audio.');else setStatus('Select a sentence, listen to its region, and generate a replacement preview.');}
    catch(e){setStatus(e.message,true);toast(e.message,true);}
  }
  function onView(){
    if(!editor.rid)return;
    requestAnimationFrame(drawWaveform);
  }
  function init(){
    $e('#edit-open-history').addEventListener('click',()=>selectView('library'));
    $e('#edit-align').addEventListener('click',()=>run('align'));
    $e('#edit-preview').addEventListener('click',()=>run('preview'));
    $e('#edit-apply').addEventListener('click',()=>run('apply'));
    const narration=$e('#edit-replacement');
    narration.addEventListener('input',()=>{captureCaret();editor.directionUndo=null;
      clearPreview();saveDraft();directionSummary();});
    for(const ev of ['select','click','keyup']) narration.addEventListener(ev,captureCaret);
    // Remember the selection before the toolbar steals focus.
    for(const id of ['edit-add-event','edit-emphasis','edit-clear-cues','edit-undo-direction','edit-emotion','edit-event'])
      $e('#'+id).addEventListener('pointerdown',captureCaret);
    $e('#edit-emotion').addEventListener('change',e=>{
      modifyDirection((t,a,b)=>direction.setEmotion(t,e.target.value,a,b));
    });
    $e('#edit-add-event').addEventListener('click',()=>{
      const event=$e('#edit-event').value;
      if(!event){directionSummary('Choose a vocal event first.');return;}
      modifyDirection((t,a,b)=>direction.insertEvent(t,event,a,b));
      $e('#edit-event').value='';
    });
    $e('#edit-emphasis').addEventListener('click',()=>{
      modifyDirection((t,a,b)=>direction.toggleEmphasis(t,a,b));
    });
    $e('#edit-clear-cues').addEventListener('click',()=>{
      modifyDirection((t)=>({text:direction.clearDirection(t),start:0,end:0}));
    });
    $e('#edit-undo-direction').addEventListener('click',()=>{
      const old=editor.directionUndo;if(!old)return;
      narration.value=old.text;narration.focus();
      narration.setSelectionRange(old.caret.start,old.caret.end);
      captureCaret();editor.directionUndo=null;
      clearPreview();saveDraft();directionSummary('Last direction change undone.');
    });
    $e('#edit-delivery').addEventListener('change',()=>{clearPreview();saveDraft();});
    for(const id of ['edit-start','edit-end'])$e('#'+id).addEventListener('input',()=>{drawWaveform();saveDraft();});
    $e('#edit-listen').addEventListener('click',()=>{
      const s=selected();if(!s||!editor.aligned)return;
      const audio=$e('#edit-original-audio');audio.currentTime=Number($e('#edit-start').value)||s.start;
      editor.listening=true;audio.play().catch(()=>{});
    });
    $e('#edit-original-audio').addEventListener('timeupdate',()=>{
      const audio=$e('#edit-original-audio');
      if(editor.listening && audio.currentTime>=(Number($e('#edit-end').value)||selected()?.end||0)){
        audio.pause();editor.listening=false;
      }
    });
    $e('#edit-waveform').addEventListener('click',e=>{
      if(!editor.aligned||!editor.item)return;
      const rect=e.currentTarget.getBoundingClientRect();
      const when=clamp((e.clientX-rect.left)/rect.width,0,1)*editor.item.duration;
      const idx=editor.sentences.findIndex(s=>s.start<=when&&s.end>=when);
      if(idx>=0){changeSentence(idx);}
      $e('#edit-original-audio').currentTime=when;
    });
    window.addEventListener('resize',drawWaveform);
    new MutationObserver(()=>drawWaveform()).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
  }
  window.KittenEditor={init,open,onView};
  init();
})();
