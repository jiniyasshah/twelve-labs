'use strict';
// Kitten Studio: framework-free, private local UI.
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const EXTRA_VOICES = {
  'hexgrad/Kokoro-82M':['af_heart','af_bella','af_nicole','am_adam','am_michael','bf_emma','bm_george','hf_alpha','hf_beta','hm_omega','hm_psi'],
  'ai4bharat/indic-parler-tts':['Hindi · Rohit','Hindi · Divya','Hindi · Aman','Hindi · Rani','Nepali · Amrita','English · Mary','English · Thoma']
};
const ONNX_VOICES = ['Bella','Jasper','Luna','Bruno','Rosie','Hugo','Kiki','Leo'];
const KEY = 'kitten-studio-v2-draft';
const ADVANCED = {
  seed:'seed', 'repetition-penalty':'repetition_penalty', 'repetition-window':'repetition_window',
  'token-run-penalty':'token_run_penalty', 'token-run-grace':'token_run_grace',
  'chunk-chars':'chunk_chars', 'chunk-min-chars':'chunk_min_chars', 'chunk-gap':'chunk_gap_s'
};
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatTime = (n) => { const secs = Math.max(0,Math.round(Number(n)||0));return `${String(Math.floor(secs/60)).padStart(2,'0')}:${String(secs%60).padStart(2,'0')}`; };
const newId = () => (globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`);
const state = {
  info:null, view:'speech', voice:'Bruno', source:'builtin', preset:'stable',
  segments:[{id:newId(),voice:'Bruno',text:'Hello. Welcome to the first scene.'}],
  library:[], activeJob:null, referenceId:null, referenceName:null, voiceFilter:'all', deleteId:null,
  busy:false, references:[], insertionTarget:null, autoTarget:null, autoUndo:null,
  lastTiming:null, lastTimedResultId:null
};
let toastTimer;

async function api(url, options={}) {
  const response = await fetch(url, {
    ...options,
    headers: options.body instanceof FormData ? (options.headers||{}) : {'Content-Type':'application/json',...(options.headers||{})}
  });
  let data;
  try { data = await response.json(); } catch { data = null; }
  if (!response.ok) {
    const detail = data?.detail ?? data?.error ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data;
}
function toast(message, error=false) {
  const el=$('#toast');el.textContent=message;el.classList.toggle('error',error);el.hidden=false;
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>el.hidden=true,5200);
}
function saveDraft() {
  const values={};
  const ids=['speech-text','model-select','device-select','weights-select','decoder-select','normalize','streaming',
    'speed','max-tokens','reference-prompt','temperature','top-k','top-p','min-p','emotion-mode','reference-text',
    'scene-gap','loop-protection','indic-description', ...Object.keys(ADVANCED)];
  for(const id of ids){const el=$('#'+id);if(el)values[id]=el.type==='checkbox'?el.checked:el.value;}
  try { localStorage.setItem(KEY,JSON.stringify({values,voice:state.voice,preset:state.preset,source:state.source,segments:state.segments,referenceId:state.referenceId,referenceName:state.referenceName})); } catch{}
}
function restoreDraft() {
  try {
    const saved=JSON.parse(localStorage.getItem(KEY)||'{}');
    for(const [id,value] of Object.entries(saved.values||{})){
      const el=$('#'+id);if(el){if(el.type==='checkbox')el.checked=!!value;else el.value=value;}
    }
    if(typeof saved.values?.['model-select']==='string')state.savedModel=saved.values['model-select'];
    if(typeof saved.voice==='string')state.voice=saved.voice;
    if(['stable','expressive'].includes(saved.preset))state.preset=saved.preset;
    if(['builtin','clone'].includes(saved.source))state.source=saved.source;
    if(Array.isArray(saved.segments)&&saved.segments.length&&saved.segments.length<=30)
      state.segments=saved.segments.filter(s=>typeof s.text==='string'&&typeof s.voice==='string').map(s=>({...s,id:s.id||newId()}));
    state.referenceId=saved.referenceId||null;state.referenceName=saved.referenceName||null;
  }catch{}
}
function isV2(){return ($('#model-select').value || 'KittenML/kitten-tts-2')==='KittenML/kitten-tts-2';}
function modelConfig(){return {model:$('#model-select').value,device:$('#device-select').value,weights:$('#weights-select').value,decoder:$('#decoder-select').value};}
function voices(){
  const model=$('#model-select').value, key=state.info?.engine?.key;
  if(state.info?.engine?.ready&&key?.[0]===model&&state.info.engine.voices?.length)return state.info.engine.voices;
  return EXTRA_VOICES[model] || (isV2()?Object.keys(state.info?.profiles||{Bruno:[],Luna:[],Bella:[]}).filter(v=>!Object.values(EXTRA_VOICES).some(group=>group.includes(v))):ONNX_VOICES);
}
function voiceInfo(voice){return state.info?.profiles?.[voice]||['Natural voice','English'];}
function selectedVoice(){return state.source==='clone'?'__clone__':state.voice;}
function chooseVoice(voice){state.voice=voice;state.source='builtin';if(voiceInfo(voice)[1]!=='English'&&$('#normalize').checked){$('#normalize').checked=false;toast('English normalization disabled for this language.');}renderSource();renderVoices();selectView('speech');saveDraft();}
function refreshVoiceOptions(){
  const options=voices();if(!options.includes(state.voice))state.voice=options.includes('Bruno')?'Bruno':options[0];
  $('#voice-select').innerHTML=options.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
  $('#voice-select').value=state.voice;
  $('#selected-avatar').textContent=state.voice[0]||'?';
  $('#voice-description').textContent=voiceInfo(state.voice)[0];
}
function renderSource(){
  if(!isV2())state.source='builtin';
  $$('#source-tabs button').forEach(b=>{b.classList.toggle('active',b.dataset.source===state.source);b.disabled=b.dataset.source==='clone'&&!isV2();});
  $('#source-builtin').hidden=state.source!=='builtin';$('#source-clone').hidden=state.source!=='clone';
  $('#upload-title').textContent=state.referenceName||'Select a reference recording';
  const available=state.references.filter(r=>r.available);
  $('#reference-select').innerHTML='<option value="">Select a saved reference…</option>'+available.map(r=>`<option value="${esc(r.id)}">${esc(r.filename)}</option>`).join('');
  const selected=available.find(r=>r.id===state.referenceId);
  $('#reference-select').value=selected?.id||'';
  $('#reference-status').textContent=selected ? 'Reference ready · Stored locally' : 'No valid reference selected. Upload or choose a saved recording.';
  $('#reference-status').classList.toggle('reference-warning',!selected);
  if(selected){$('#reference-audio').src='/api/reference/'+encodeURIComponent(selected.id);$('#reference-audio').hidden=false;}
  else {$('#reference-audio').hidden=true;$('#reference-audio').removeAttribute('src');}
  refreshVoiceOptions();
}
function renderModel(){
  const v2=isV2(); $('#v2-model-options').hidden=!v2;$('#v2-generation-options').hidden=!v2;
  const family=state.info?.models?.[$('#model-select').value]?.family;
  $('#onnx-options').hidden=family!=='onnx';$('#indic-options').hidden=family!=='indic';$('#advanced-panel').hidden=!v2;
  const model=$('#model-select').value;$('#model-description').textContent=state.info?.models?.[model]?.size||'';
  const voiceModel=$('#voice-model-select');if(voiceModel){voiceModel.innerHTML=$('#model-select').innerHTML;voiceModel.value=model;}
  const onnxCuda=$('#device-select option[value="cuda"]');onnxCuda.textContent=family==='onnx'?'CUDA (requires ONNX GPU runtime)':'NVIDIA CUDA';
  $('#add-emotion').disabled=!v2;$('#add-event').disabled=!v2;$('#add-emphasis').disabled=!v2;$('#auto-direct').disabled=!v2;$('#auto-direct-script').disabled=!v2;
  renderSource();renderSegments();updateReady();saveDraft();
}
function updateReady(){
  const selected=[modelConfig().model,modelConfig().device,...(isV2()?[modelConfig().weights,modelConfig().decoder]:[null,null])];
  const ready=state.info?.engine?.ready&&JSON.stringify(selected)===JSON.stringify(state.info?.engine?.key);
  $('#system-status').classList.toggle('ready',!!ready);
  $('#system-status').innerHTML=`<span class="status-led"></span> ${ready?'Model ready':'Engine idle'}`;
  $('#top-load').textContent=ready?'Reload model':'Load model';
}
function renderPresets(){ $$('#preset-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.preset===state.preset)); }
function updateCount(){const count=$('#speech-text').value.length;$('#text-count').textContent=`${count.toLocaleString()} characters`;$('#estimate').textContent=count?`${count.toLocaleString()} characters · ${Math.max(1,Math.ceil(count/950))} estimated chunks`:'Add some text to begin';}
function selectView(view){
  state.view=view;
  $$('.view').forEach(v=>{const active=v.id==='view-'+view;v.hidden=!active;v.classList.toggle('active',active);});
  $$('#navigation button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  $('#section-name').textContent={speech:'Speech',script:'Script builder',voices:'Voices',library:'History',edit:'Edit audio'}[view];
  $('.sidebar').classList.remove('open');window.scrollTo({top:0,behavior:'instant'});
  if(view==='library')loadLibrary();if(view==='edit')window.KittenEditor?.onView();if(view==='voices')renderVoices();if(view==='script')renderSegments();
}
function configPayload(){
  const payload={...modelConfig(),preset:state.preset,normalize:$('#normalize').checked,streaming:$('#streaming').checked,speed:Number($('#speed').value),loop_protection:$('#loop-protection').value};
  if(state.info?.models?.[payload.model]?.family==='indic')payload.description=$('#indic-description').value.trim();
  if(!isV2())return payload;
  payload.max_new_tokens=Number($('#max-tokens').value)||1000;
  payload.use_reference_prompt=$('#reference-prompt').value;
  for(const [id,name] of [['temperature','temperature'],['top-k','top_k'],['top-p','top_p'],['min-p','min_p']]){
    if($('#'+id).value.trim()!=='')payload[name]=Number($('#'+id).value);
  }
  payload.advanced={};
  for(const [id,name] of Object.entries(ADVANCED))if($('#'+id).value.trim()!=='')payload.advanced[name]=Number($('#'+id).value);
  if($('#emotion-mode').value!=='auto')payload.advanced.use_emotion=$('#emotion-mode').value==='on';
  return payload;
}
function withClone(payload,voice){
  if(voice!=='__clone__')return;
  if(!isV2())throw new Error('Voice cloning is only available for KittenTTS 2.');
  if(!state.referenceId || !state.references.some(r=>r.id===state.referenceId && r.available))
    throw new Error('Your saved voice reference is unavailable. Select another recording or upload one.');
  payload.reference_id=state.referenceId;
  payload.reference_text=$('#reference-text').value.trim();
}
function formatBenchmark(t){
  const speed=t.rtf>0?(1/t.rtf).toFixed(2)+'× real time':'n/a';
  return `Model setup ${Number(t.model_setup_s).toFixed(1)}s · Synthesis ${Number(t.synthesis_s).toFixed(1)}s · Audio ${Number(t.audio_s).toFixed(1)}s · ${speed} · ${String(t.device).toUpperCase()}${t.reused_model?' · Reused model':' · Loaded model'}`;
}
function renderJob(job){
  const tray=$('#job-tray');tray.hidden=false;
  const done=['done','error','cancelled'].includes(job.status);
  $('#job-spinner').className='spinner'+(job.status==='error'?' error':done?' done':'');
  const title=job.status==='error'?'Could not complete request':job.status==='done'?'Finished successfully':job.status==='queued'?'Waiting in queue':job.kind==='load'?'Loading model':'Generating audio';
  $('#job-title').textContent=title;
  $('#job-message').textContent=[job.error||job.message||'',job.warning].filter(Boolean).join('  •  ');
  const benchmark=$('#job-benchmark');benchmark.hidden=!job.timings;
  if(job.timings)benchmark.textContent=formatBenchmark(job.timings);
  const pct=job.status==='done'?100:job.total?Math.round(job.completed/job.total*100):job.status==='running'?12:0;
  $('#job-progress').style.width=pct+'%';
  $('#cancel-job').hidden=job.status!=='queued';
  $('#chunk-links').innerHTML=(job.chunks||[]).map(c=>`<a href="${esc(c.url)}" target="_blank" rel="noopener" title="Play generated audio chunk">Chunk ${c.index+1} ↗</a>`).join('');
}
async function startJob(path,payload){
  saveDraft();
  const result=await api(path,{method:'POST',body:JSON.stringify(payload)});
  const id=result.job_id;state.activeJob=id;
  renderJob({status:'queued',kind:path.endsWith('load')?'load':'generate',message:'Waiting for engine…',total:0,chunks:[]});
  while(state.activeJob===id){
    await new Promise(r=>setTimeout(r,950));
    let job;
    try{job=await api('/api/jobs/'+id);}catch(e){toast(e.message,true);break;}
    renderJob(job);
    if(['done','error','cancelled'].includes(job.status)){
      state.activeJob=null; if(job.status==='done'){
        await loadInfo();
        if(job.result_id){state.lastTiming=job.timings||null;state.lastTimedResultId=job.result_id;await loadLibrary();if(payload.segments)selectView('speech');showResult(job.result_id);toast('Your audio is ready.');}
        else toast(job.warning||'Model is ready.',!!job.warning);
      }else if(job.status==='error'){toast(job.error||'Model generation failed',true);}
      break;
    }
  }
}
async function loadModel(){
  try { await startJob('/api/load',modelConfig()); } catch(e){toast(e.message,true);}
}
async function generateSpeech(){
  try{
    const text=$('#speech-text').value.trim();if(!text)throw new Error('Enter some text first.');
    const payload={...configPayload(),text,voice:selectedVoice()};withClone(payload,payload.voice);
    await startJob('/api/generate',payload);
  }catch(e){toast(e.message,true);}
}
function showResult(id){
  const r=state.library.find(x=>x.id===id);
  $('#output-panel').hidden=false;
  $('#output-title').textContent=r?.title||'Generated audio';
  $('#output-meta').textContent=`${r?.voice||'Speech'} · ${formatTime(r?.duration)} · WAV`;
  const bm=$('#output-benchmark');bm.hidden=!(state.lastTiming && state.lastTimedResultId===id);
  if(!bm.hidden)bm.textContent=formatBenchmark(state.lastTiming);
  $('#output-audio').src='/api/audio/'+encodeURIComponent(id);
  $('#output-download').href='/api/download/'+encodeURIComponent(id);
}
async function loadInfo(){
  const result=await api('/api/info');state.info=result;
  if(!$('#model-select').options.length){$('#model-select').innerHTML=Object.entries(result.models).map(([id,v])=>`<option value="${esc(id)}">${esc(v.label)}</option>`).join('');$('#model-select').value='KittenML/kitten-tts-2';}
  if(state.savedModel&&result.models[state.savedModel])$('#model-select').value=state.savedModel;
  state.savedModel=null;
  if(!result.models[$('#model-select').value])$('#model-select').value='KittenML/kitten-tts-2';
  renderModel();renderPresets();updateComputeNote();
  $('#connection-label').textContent=result.engine.offline?'Offline mode · cached assets only':result.engine.authenticated?'HF token detected':'Hugging Face · public downloads';
  $('#connection-note').textContent=result.engine.offline?'Missing files cannot download. Relaunch with python studio.py.':result.engine.authenticated?'Credentials found locally (not yet network verified). Downloads use the HF cache.':'Set HF_TOKEN in Windows or a local .env file for authenticated downloads.';
}
function updateComputeNote(){
  const el=$('#compute-note');if(!el)return;
  const info=state.info?.engine?.compute;
  if(!info){el.textContent='CPU works without NVIDIA GPU support.';return;}
  const family=state.info?.models?.[$('#model-select').value]?.family||'v2';
  const available=family!=='onnx'?info.torch_cuda:info.onnx_cuda;
  const selection=$('#device-select').value;
  if(available){el.textContent=family==='v2'?'CUDA acceleration is available in PyTorch.':'ONNX CUDA provider is available.';return;}
  if(selection==='cuda'){
    el.textContent=family==='v2'?'CUDA is not available in this PyTorch installation. Studio will use CPU. To enable NVIDIA GPU, run python studio.py --setup --gpu.':'ONNX CUDA provider is unavailable. Studio will use CPU.';
  }else if(family==='v2'&&!info.torch_cuda_build){
    el.textContent='This installation uses CPU-only PyTorch. Auto selects CPU; run python studio.py --setup --gpu to enable CUDA.';
  }else{
    el.textContent='Auto selects CPU on this machine. No CUDA backend detected.';
  }
}
function renderVoices(){
  const all=voices(),term=$('#voice-search').value.trim().toLowerCase();
  const filtered=all.filter(v=>{const [character,language]=voiceInfo(v);const matches=!term||`${v} ${character} ${language}`.toLowerCase().includes(term);return matches&&(state.voiceFilter==='all'||(state.voiceFilter==='English'?language==='English':language!=='English'));});
  $('#voice-cards').innerHTML=filtered.length?filtered.map(v=>{
    const [character,language]=voiceInfo(v);
    return `<button type="button" class="voice-card ${state.voice===v?'selected':''}" data-voice="${esc(v)}"><div class="voice-avatar">${esc(v[0])}</div><span class="voice-card-text"><strong>${esc(v)}</strong><small>${esc(character)} · ${esc(language)}</small></span><span class="selected-mark">${state.voice===v?'✓':'↗'}</span></button>`;
  }).join(''):'<div class="empty">No matching voices.</div>';
  $$('.voice-card').forEach(b=>b.addEventListener('click',()=>chooseVoice(b.dataset.voice)));
}
function renderSegments(){
  const voiceNames=voices();
  const choices=voiceNames.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('')+(isV2()?'<option value="__clone__">Cloned reference voice</option>':'');
  $('#scene-list').innerHTML=state.segments.map((s,i)=>`<div class="scene-card" data-index="${i}"><div class="scene-head"><strong>Scene ${String(i+1).padStart(2,'0')}</strong><div class="scene-actions"><button data-action="up" title="Move up" ${i===0?'disabled':''}>↑</button><button data-action="down" title="Move down" ${i===state.segments.length-1?'disabled':''}>↓</button><button data-action="copy" title="Duplicate scene">⧉</button><button data-action="remove" title="Remove scene">×</button></div></div><textarea class="scene-body" placeholder="What should the speaker say?">${esc(s.text)}</textarea><div class="scene-tag-tools"><button type="button" data-tag-type="emotion">＋ Emotion</button><button type="button" data-tag-type="event">＋ Event</button><button type="button" data-tag-type="emphasis">Emphasis</button><button type="button" class="scene-auto" data-tag-type="auto" ${isV2()?'':'disabled title="Requires KittenTTS 2"'}>✦ Auto-direct</button></div><div class="scene-foot"><select class="field-select scene-voice" aria-label="Scene ${i+1} voice">${choices}</select><span class="helper scene-count">${s.text.length} characters</span></div></div>`).join('');
  $$('.scene-card').forEach((element,i)=>{
    const item=state.segments[i],select=$('.scene-voice',element);
    select.value=voiceNames.includes(item.voice)||item.voice==='__clone__'&&isV2()?item.voice:(voiceNames.includes('Bruno')?'Bruno':voiceNames[0]);item.voice=select.value;
    select.addEventListener('change',()=>{item.voice=select.value;saveDraft();});
    const textarea=$('.scene-body',element);
    textarea.addEventListener('input',e=>{item.text=e.target.value;$('.scene-count',element).textContent=item.text.length+' characters';updateSceneSummary();saveDraft();});
    for(const btn of $$('.scene-tag-tools button',element)){
      btn.addEventListener('mousedown',()=>captureInsertion(textarea));
      btn.addEventListener('click',()=>{
        captureInsertion(textarea); // textarea selection is retained even after focus loss
        if(btn.dataset.tagType==='auto')openAutoDialog('scene', item.id);
        else if(btn.dataset.tagType==='emphasis')insertAtCursor('(((', ')))');
        else showTagDialog(btn.dataset.tagType,textarea);
      });
    }
    $$('.scene-actions button',element).forEach(b=>b.addEventListener('click',()=>{
      if(b.dataset.action==='remove'){if(state.segments.length===1)return toast('A script needs at least one scene.',true);state.segments.splice(i,1);}
      if(b.dataset.action==='copy'){if(state.segments.length>=30)return toast('Maximum 30 scenes.',true);state.segments.splice(i+1,0,{...item,id:newId()});}
      if(b.dataset.action==='up'&&i>0)[state.segments[i-1],state.segments[i]]=[state.segments[i],state.segments[i-1]];
      if(b.dataset.action==='down'&&i<state.segments.length-1)[state.segments[i+1],state.segments[i]]=[state.segments[i],state.segments[i+1]];
      renderSegments();saveDraft();
    }));
  });updateSceneSummary();
}
function updateSceneSummary(){$('#scene-count').textContent=String(state.segments.length);$('#scene-chars').textContent=state.segments.reduce((n,s)=>n+s.text.length,0).toLocaleString();}
function addScene(){if(state.segments.length>=30)return toast('Maximum 30 scenes.',true);state.segments.push({id:newId(),voice:state.voice,text:''});renderSegments();saveDraft();$$('.scene-body').at(-1)?.focus();}
async function generateScript(){
  try{
    if(!state.segments.length||state.segments.some(s=>!s.text.trim()))throw new Error('Fill in all script scenes first.');
    const payload={...configPayload(),segments:state.segments.map(s=>({text:s.text.trim(),voice:s.voice})),segment_gap:Number($('#scene-gap').value)};
    if(payload.segments.some(s=>s.voice==='__clone__'))withClone(payload,'__clone__');
    payload.streaming=false;
    await startJob('/api/generate',payload);
  }catch(e){toast(e.message,true);}
}
async function loadReferences(){
  try {
    state.references=await api('/api/references');
    const chosen=state.references.find(r=>r.id===state.referenceId && r.available);
    if(!chosen){state.referenceId=null;state.referenceName=null;saveDraft();}
    else state.referenceName=chosen.filename;
    renderSource();
  } catch(e) {toast('Could not load saved voice references: '+e.message,true);}
}
async function loadLibrary(){
  try{state.library=await api('/api/history');renderLibrary();}catch(e){toast(e.message,true);}
}
function renderLibrary(){
  const term=$('#library-search').value.toLowerCase().trim(), kind=$('#history-kind').value;
  const found=state.library.filter(r=>(kind==='all'||kind===r.kind) && `${r.title} ${r.voice} ${r.text} ${r.kind} ${r.model}`.toLowerCase().includes(term));
  $('#history-count').textContent=`${found.length} of ${state.library.length} saved generations · Newest first`;
  $('#library-items').innerHTML=found.length?found.map(r=>`<div class="library-row" data-id="${esc(r.id)}"><div class="library-name"><strong>${esc(r.title)}</strong><small>${esc(r.voice)} · ${esc(r.kind)} · ${new Date(r.created).toLocaleString()}</small></div><span class="library-duration">${formatTime(r.duration)}</span><div class="library-actions"><button type="button" data-action="play">Play</button><button type="button" data-action="reuse">Reuse</button><button type="button" data-action="edit">Edit speech</button><a href="/api/download/${encodeURIComponent(r.id)}" download>WAV ↓</a><button class="delete" type="button" data-action="delete">Delete</button></div></div>`).join(''):'<div class="empty"><strong>No generations found.</strong>Your saved WAV files will appear here, including recordings from earlier versions.</div>';
  $$('.library-row').forEach(el=>el.addEventListener('click',ev=>{
    const action=ev.target.closest('[data-action]')?.dataset.action;if(!action)return;
    const r=state.library.find(s=>s.id===el.dataset.id);if(!r)return;
    if(action==='play'){showResult(r.id);selectView('speech');$('#output-audio').play().catch(()=>{});}
    if(action==='edit'){window.KittenEditor?.open(r.id);}
    if(action==='reuse'){$('#speech-text').value=r.text;updateCount();selectView('speech');saveDraft();toast('Text added to your editor.');}
    if(action==='delete'){state.deleteId=r.id;$('#confirm-dialog').showModal();}
  }));
}
// Capture the exact textarea and caret BEFORE clicking a toolbar button or opening a dialog.
// Clicking a dialog moves focus, so activeElement/selectionStart at insertion time is unreliable.
function captureInsertion(input){
  if(!input)return;
  state.insertionTarget={input,start:input.selectionStart,end:input.selectionEnd};
}
function currentInsertion(){
  const saved=state.insertionTarget;
  if(saved?.input?.isConnected)return saved;
  const input=$('#speech-text');return {input,start:input.selectionStart,end:input.selectionEnd};
}
function insertAtCursor(before,after='',lineStart=false){
  const {input,start:initial,end:initialEnd}=currentInsertion();
  const old=input.value;
  // Emotions belong to the current line, NOT the beginning of the entire script.
  const start=lineStart ? old.lastIndexOf('\n',Math.max(0,initial-1))+1 : initial;
  const end=lineStart ? start : initialEnd;
  const selected=lineStart?'':old.slice(start,end);
  const addition=before+selected+after;
  input.value=old.slice(0,start)+addition+old.slice(end);
  input.focus();
  const caret=lineStart?initial+before.length:start+before.length;
  input.setSelectionRange(caret,lineStart?caret:caret+selected.length);
  state.insertionTarget={input,start:input.selectionStart,end:input.selectionEnd};
  input.dispatchEvent(new Event('input',{bubbles:true}));
}
function showTagDialog(kind,source){
  if(source)captureInsertion(source);
  const choices=kind==='emotion'?state.info?.emotions:state.info?.events;
  $('#tag-title').textContent=kind==='emotion'?'Choose emotion':'Choose vocal event';
  $('#tag-helper').textContent=kind==='emotion'?'Applies to the line where the caret is located, not the beginning of the document.':'Insert a vocal direction at your saved cursor position.';
  $('#tag-items').innerHTML=(choices||[]).map(t=>`<button type="button" data-tag="${esc(t)}">${esc(kind==='emotion'?`[${t}]`:`<${t}>`)}</button>`).join('');
  $$('#tag-items button').forEach(b=>b.addEventListener('click',()=>{
    if(kind==='emotion')insertAtCursor('['+b.dataset.tag+'] ', '',true);
    else insertAtCursor('<'+b.dataset.tag+'> ');
    $('#tag-dialog').close();
  }));
  $('#tag-dialog').showModal();
}
// Never change the narration automatically. Suggestions are reviewed in a modal.
// Every application retains a reversible snapshot as long as the user has not edited it again.
function autoOptions(){
  return {intensity:$('#auto-strength').value,emotions:$('#auto-emotions').checked,
    events:$('#auto-events').checked,emphasis:$('#auto-emphasis').checked};
}
function snapshotForAuto(){
  const target=state.autoTarget;
  if(!target)return null;
  if(target.kind==='speech')return [{id:'speech',text:$('#speech-text').value}];
  if(target.kind==='scene'){
    const item=state.segments.find(s=>s.id===target.id);
    return item?[{id:item.id,text:item.text}]:null;
  }
  if(target.kind==='script')return state.segments.map(s=>({id:s.id,text:s.text}));
  return null;
}
function recomputeAuto(){
  const entries=snapshotForAuto();
  const original=$('#auto-original'),proposed=$('#auto-proposal');
  if(!entries){original.value='';proposed.value='';$('#auto-apply').disabled=true;return;}
  const options=autoOptions();
  const proposals=entries.map(e=>({...e,result:window.KittenAutoMarkup.suggest(e.text,options)}));
  state.autoProposals=proposals;
  const counts={emotions:0,events:0,emphasis:0};
  for(const p of proposals)for(const key of Object.keys(counts))counts[key]+=p.result.stats[key];
  original.value=entries.map(e=>e.text).join('\n\n─── Scene ───\n\n');
  proposed.value=proposals.map(p=>p.result.text).join('\n\n─── Scene ───\n\n');
  const count=counts.emotions+counts.events+counts.emphasis;
  $('#auto-stats').textContent=count?`${counts.emotions} emotions · ${counts.events} events · ${counts.emphasis} emphasis`:'No suitable cues found';
  $('#auto-apply').disabled=count===0;
}
function openAutoDialog(kind,id=null){
  if(!isV2()){toast('Automatic direction requires KittenTTS 2.',true);return;}
  state.autoTarget={kind,id};
  recomputeAuto();
  $('#auto-dialog').showModal();
}
function updateAutoUndo(){
  const undo=state.autoUndo;
  $('#undo-auto').hidden=!(undo?.kind==='speech');
  $('#undo-auto-script').hidden=!(undo?.kind==='script'||undo?.kind==='scene');
}
function applyAutoSuggestions(){
  const proposals=state.autoProposals;
  if(!proposals?.length||!proposals.some(p=>p.result.changed))return;
  const current=snapshotForAuto();
  if(!current||current.length!==proposals.length||current.some((e,i)=>e.id!==proposals[i].id||e.text!==proposals[i].text)){
    toast('Text changed while preview was open. Review the updated suggestions.',true);
    recomputeAuto();return;
  }
  const kind=state.autoTarget.kind;
  state.autoUndo={kind,previous:current.map(e=>({...e})),applied:proposals.map(p=>({id:p.id,text:p.result.text}))};
  if(kind==='speech'){
    $('#speech-text').value=proposals[0].result.text;
    $('#speech-text').dispatchEvent(new Event('input',{bubbles:true}));
  }else{
    for(const p of proposals){const scene=state.segments.find(s=>s.id===p.id);if(scene)scene.text=p.result.text;}
    renderSegments();saveDraft();
  }
  updateAutoUndo();
  $('#auto-dialog').close();
  toast('Directions added. Review the narration before generating.');
}
function undoAuto(){
  const undo=state.autoUndo;if(!undo)return;
  if(undo.kind==='speech'){
    if($('#speech-text').value!==undo.applied[0].text){toast('The narration has changed; undo would overwrite your edits.',true);return;}
    $('#speech-text').value=undo.previous[0].text;
    $('#speech-text').dispatchEvent(new Event('input',{bubbles:true}));
  }else{
    if(undo.applied.some(e=>state.segments.find(s=>s.id===e.id)?.text!==e.text)){
      toast('Some scenes were edited since applying. Undo would overwrite your work.',true);return;
    }
    for(const entry of undo.previous){const s=state.segments.find(x=>x.id===entry.id);if(s)s.text=entry.text;}
    renderSegments();saveDraft();
  }
  state.autoUndo=null;updateAutoUndo();toast('Automatic directions undone.');
}
function bindTheme(){
  const apply=()=>{
    const dark=document.documentElement.dataset.theme==='dark';
    $('#theme-toggle').textContent=dark?'☀':'☾';
    $('#theme-toggle').title=dark?'Switch to light mode':'Switch to dark mode';
    $('#theme-toggle').setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');
    document.querySelector('meta[name="theme-color"]').content=dark?'#101013':'#f7f7f5';
  };
  $('#theme-toggle').addEventListener('click',()=>{
    const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';
    document.documentElement.dataset.theme=theme;
    try{localStorage.setItem('kitten-studio-theme',theme);}catch{}
    apply();
  });
  apply();
}
function bindEvents(){
  bindTheme();
  $('#speech-text').addEventListener('select',()=>captureInsertion($('#speech-text')));
  $('#speech-text').addEventListener('keyup',()=>captureInsertion($('#speech-text')));
  $('#speech-text').addEventListener('click',()=>captureInsertion($('#speech-text')));
  $$('#navigation button').forEach(b=>b.addEventListener('click',()=>selectView(b.dataset.view)));
  $('#mobile-menu').addEventListener('click',()=>$('.sidebar').classList.toggle('open'));
  $('#speech-text').addEventListener('input',()=>{updateCount();saveDraft();});
  $('#clear-text').addEventListener('click',()=>{$('#speech-text').value='';updateCount();saveDraft();});
  $('#text-file').addEventListener('change',async e=>{const file=e.target.files?.[0];if(!file)return;if(file.size>1024*1024)return toast('Text files must be smaller than 1 MB.',true);$('#speech-text').value=await file.text();updateCount();saveDraft();e.target.value='';});
  for(const id of ['add-emotion','add-event','add-emphasis'])$('#'+id).addEventListener('mousedown',()=>captureInsertion($('#speech-text')));
  $('#add-emotion').addEventListener('click',()=>showTagDialog('emotion'));
  $('#add-event').addEventListener('click',()=>showTagDialog('event'));
  $('#add-emphasis').addEventListener('click',()=>insertAtCursor('(((', ')))'));
  $('#auto-direct').addEventListener('click',()=>openAutoDialog('speech'));
  $('#auto-direct-script').addEventListener('click',()=>openAutoDialog('script'));
  $('#undo-auto').addEventListener('click',undoAuto);
  $('#undo-auto-script').addEventListener('click',undoAuto);
  for(const id of ['auto-strength','auto-emotions','auto-events','auto-emphasis'])$('#'+id).addEventListener('change',recomputeAuto);
  $('#auto-apply').addEventListener('click',applyAutoSuggestions);
  $('#voice-select').addEventListener('change',e=>{state.voice=e.target.value;refreshVoiceOptions();saveDraft();});
  $('#browse-voices').addEventListener('click',()=>selectView('voices'));
  $$('#source-tabs button').forEach(b=>b.addEventListener('click',()=>{state.source=b.dataset.source;renderSource();saveDraft();}));
  $$('#preset-tabs button').forEach(b=>b.addEventListener('click',()=>{state.preset=b.dataset.preset;renderPresets();saveDraft();}));
  $('#model-select').addEventListener('change',()=>{renderModel();updateComputeNote();});
  $('#voice-model-select').addEventListener('change',e=>{$('#model-select').value=e.target.value;renderModel();renderVoices();updateComputeNote();});
  for(const id of ['weights-select','decoder-select','device-select'])$('#'+id).addEventListener('change',()=>{updateReady();updateComputeNote();saveDraft();});
  for(const id of ['normalize','streaming','reference-prompt','max-tokens','temperature','top-k','top-p','min-p','seed','repetition-penalty','repetition-window','token-run-penalty','token-run-grace','chunk-chars','chunk-min-chars','chunk-gap','emotion-mode','reference-text','scene-gap','loop-protection'])$('#'+id).addEventListener('change',saveDraft);
  $('#speed').addEventListener('input',()=>{$('#speed-display').textContent=Number($('#speed').value).toFixed(2)+'×';saveDraft();});
  $('#generate-speech').addEventListener('click',generateSpeech);
  $('#generate-script').addEventListener('click',generateScript);
  $('#top-load').addEventListener('click',loadModel);
  $('#add-scene').addEventListener('click',addScene);
  $('#reset-advanced').addEventListener('click',()=>{for(const id of [...Object.keys(ADVANCED),'temperature','top-k','top-p','min-p'])$('#'+id).value='';$('#max-tokens').value=1000;$('#reference-prompt').value='auto';$('#emotion-mode').value='auto';$('#loop-protection').value='off';saveDraft();toast('Advanced settings reset.');});
  $('#voice-upload').addEventListener('change',async e=>{
    const file=e.target.files?.[0];if(!file)return;if(file.size>32*1024*1024)return toast('Audio reference must be below 32 MB.',true);
    const body=new FormData();body.append('file',file);$('#upload-title').textContent='Uploading reference…';
    try{const data=await api('/api/reference',{method:'POST',body});state.referenceId=data.reference_id;state.referenceName=data.filename;await loadReferences();renderSource();saveDraft();toast('Reference saved on this computer.');}
    catch(error){$('#upload-title').textContent=state.referenceName||'Select a reference recording';toast(error.message,true);}
    e.target.value='';
  });
  $('#reference-select').addEventListener('change',e=>{
    const found=state.references.find(r=>r.id===e.target.value && r.available);
    state.referenceId=found?.id||null;state.referenceName=found?.filename||null;
    renderSource();saveDraft();
  });
  $('#voice-search').addEventListener('input',renderVoices);
  $$('#voice-filter button').forEach(b=>b.addEventListener('click',()=>{state.voiceFilter=b.dataset.lang;$$('#voice-filter button').forEach(el=>el.classList.toggle('active',el===b));renderVoices();}));
  $('#library-search').addEventListener('input',renderLibrary);$('#history-kind').addEventListener('change',renderLibrary);$('#refresh-library').addEventListener('click',loadLibrary);
  $('#confirm-delete').addEventListener('click',async()=>{try{await api('/api/history/'+encodeURIComponent(state.deleteId),{method:'DELETE'});$('#confirm-dialog').close();state.deleteId=null;await loadLibrary();toast('Recording deleted.');}catch(e){toast(e.message,true);}});
  $$('.dialog-close').forEach(btn=>btn.addEventListener('click',()=>btn.closest('dialog').close()));
  $('#help-button').addEventListener('click',()=>$('#help-dialog').showModal());
  $('#cancel-job').addEventListener('click',async()=>{if(!state.activeJob)return;try{await api('/api/jobs/'+state.activeJob+'/cancel',{method:'POST'});toast('Queued job cancelled.');}catch(e){toast(e.message,true);}});
  $('#close-job').addEventListener('click',()=>$('#job-tray').hidden=true);
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();state.view==='script'?generateScript():generateSpeech();}});
}
async function boot(){
  bindEvents();restoreDraft();
  $('#speed-display').textContent=Number($('#speed').value).toFixed(2)+'×';
  updateCount();renderPresets();
  try{await loadInfo();}catch(e){toast('Failed to initialize the studio: '+e.message,true);}
  renderVoices();renderSegments();renderSource();await loadReferences();loadLibrary();
}
boot();
