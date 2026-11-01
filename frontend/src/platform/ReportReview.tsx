import { Select } from "../components/Select";
import { useState } from 'react';
import { bilingual as t, tr, claimValue } from '../i18n';
import { Dialog } from '../components/OperationalUI';
import { API, call, type Organization } from './client';
import type { Note, Claim } from '../types';

type Row = { claim?: Claim; property: string; value: string; excerpt: string; choice: string; modality: string; condition: string; supersedes: string[] };
export default function ReportReview({note, claims, allClaims, org, base, version, close, done}: {
 note: Note; claims: Claim[]; allClaims: Claim[]; org: Organization; base: string; version: number; close:()=>void; done:()=>Promise<unknown>;
}) {
 const text=note.transcripts.at(-1)?.text || '';
 const existing=claims.filter(c=>!['rejected','superseded'].includes(c.status));
 const [rows,setRows]=useState<Row[]>(existing.length ? existing.map(c=>({claim:c,property:c.property,value:String(c.value),excerpt:c.excerpt,choice:'',modality:c.modality,condition:c.condition||'',supersedes:[]})) : Object.keys(org.profile.properties).map(property=>({property,value:'',excerpt:text.slice(0,2000),choice:'',modality:'actual',condition:'',supersedes:[]})));
 const [reviewVersion,setReviewVersion]=useState(version);
 const [reason,setReason]=useState(''); const [preset,setPreset]=useState(false);const [empty,setEmpty]=useState(false);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const [requestId,setRequestId]=useState(()=>crypto.randomUUID());
 const [reopened,setReopened]=useState(false);
 const closed=(note as any).review_outcome?.action==='no_operational_claims' && !note.claim_ids.length && note.status==='processed' && !reopened;
 const change=(i:number,changes:Partial<Row>)=>{setRows(old=>old.map((r,k)=>i===k?{...r,...changes}:r));setRequestId(crypto.randomUUID());};
 const protectedValue=(r:Row)=>['quality:cleared','documents:verified','fault:resolved','repair:verified'].includes(`${r.property}:${r.value}`);
 const labels:Record<string,string>={task:t('क्या काम बाकी है?','What task remains?'),packing:t('पैकिंग पूरी हुई?','Is packing complete?'),documents:t('भेजने के दस्तावेज़ जाँचे गए?','Were dispatch documents verified?'),quality:t('गुणवत्ता जाँच का नतीजा क्या है?','What was the quality result?'),dispatch:t('भेजने की तैयारी के बारे में क्या बताया?','What was reported about dispatch?'),quantity:t('कितनी संख्या बताई?','What quantity was reported?'),operating:t('मशीन चल रही है?','Is the machine running?'),fault:t('खराबी की स्थिति क्या है?','What is the fault status?'),repair:t('मरम्मत की स्थिति क्या है?','What is the repair status?')};
 async function save(noWork=false){
  setError('');setBusy(true);
  try{
   const why=reason.trim() || (preset ? 'Checked against the recording' : '');
   if(why.length<3)throw Error(t('जाँच का कारण चुनें या लिखें।','Choose or enter a review reason.'));
   if(noWork){
    if(!empty || reason.trim().length<3)throw Error(t('पुष्टि करें और कारण लिखें।','Confirm and enter a reason.'));
    await call(base+'/notes/'+note.id+'/review-transcript',{expected_version:reviewVersion,claims:[],reason,no_operational_update:true});
   }else{
    const decisions:any[]=[];
    for(const r of rows){
     if(!r.choice)continue;
     if(r.claim && r.choice==='cannot')continue;
     if(!r.claim && !r.value)continue;
     if(r.claim && r.choice==='correct')decisions.push({claim_id:r.claim.id,action:'confirm',reason:why,supersedes:r.supersedes});
     else {
      if(r.claim && r.choice==='corrected')decisions.push({claim_id:r.claim.id,action:'reject',reason:why});
      decisions.push({candidate:{property:r.property,value:r.property==='quantity'?Number(r.value):r.value,excerpt:r.excerpt,modality:r.modality,condition:r.condition||null},action:r.choice==='cannot'?'draft':'confirm',reason:why,supersedes:r.supersedes});
     }
    }
    if(!decisions.length)throw Error(t('कम से कम एक बात जाँचें। अभी पुष्टि नहीं कर सकते तो रिपोर्ट खुली छोड़ें।','Check at least one statement. If you cannot confirm anything, leave the report open.'));
    await call(base+'/notes/'+note.id+'/review',{expected_version:reviewVersion,request_id:requestId,decisions});
   }
   await done();close();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <Dialog title={t('रिपोर्ट सुनें और जाँचें','Listen and check report')} close={close}>
  <p><strong>{note.reported_by?.name || note.actor.name} · {note.batch_id}</strong></p>
  {note.assisted_by && <p>{t("रिकॉर्डिंग में मदद", "Recorded with assistance from")}: {note.assisted_by.name}</p>}
  {note.has_audio && <audio controls src={API+base+'/notes/'+note.id+'/audio'}/>}
  {note.clarification_context && <p>{t("इस सवाल का जवाब", "Answering this question")}: {note.clarification_context.text}</p>}
  <blockquote>{text || t('लिखे हुए शब्द अभी उपलब्ध नहीं हैं।','The transcript is not available yet.')}</blockquote>
  {error && <p className="platform-error" role="alert">{tr(error)}</p>}
  {closed ? <section><p>{t('यह रिपोर्ट पहले बिना काम का अपडेट माने बंद हुई थी। दोबारा खोलने से कोई काम मंज़ूर नहीं होता।','This report was closed without a work update. Reopening does not approve any work.')}</p>
   <label>{t('दोबारा खोलने का कारण','Reason for reopening')}<textarea value={reason} onChange={e=>setReason(e.target.value)}/></label>
   <button className="button-orange" disabled={busy||reason.trim().length<3} onClick={async()=>{setBusy(true);try{await call(base+'/notes/'+note.id+'/reopen',{expected_version:reviewVersion,reason});setReopened(true);await done();const fresh=await call<{version:number}>(base+"/workspace");setReviewVersion(fresh.version);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>{t('रिपोर्ट फिर जाँच के लिए खोलें','Reopen report for review')}</button>
  </section> : <>
   {!existing.length && <p>{t('नीचे केवल वही बातें चुनें जो रिकॉर्डिंग में कही गई हैं। जो नहीं कहा गया, खाली छोड़ें।','Choose only facts stated in the recording. Leave anything not mentioned blank.')}</p>}
   {rows.map((r,i)=><section className="review-statement" data-property={r.property} key={i}>
    <h3>{labels[r.property] || tr(r.property)}</h3>
    {r.claim && <p>{claimValue(r.claim)} · {r.claim.status==='confirmed'?t('पहले जाँची गई','Previously checked'):t('जाँच बाकी','Awaiting review')}</p>}
    {(!r.claim || r.choice==='corrected') && <label>{t('रिकॉर्डिंग में बताई स्थिति','Status stated in the recording')}
     {org.profile.properties[r.property].length ? <Select value={r.value} onChange={e=>change(i,{value:e.target.value})}><option value="">{t('चुनें','Choose')}</option>{org.profile.properties[r.property].map(v=><option key={v} value={v}>{tr(v)}</option>)}</Select> : <input type={r.property==='quantity'?'number':'text'} min={0} value={r.value} onChange={e=>change(i,{value:e.target.value})}/>}
    </label>}
    <label>{t('आपकी जाँच','Your check')}<Select value={r.choice} onChange={e=>change(i,{choice:e.target.value})}>
     <option value="">{t('अभी नहीं चुना','Not selected')}</option>
     <option value="correct" disabled={protectedValue(r)&&org.role!=='quality'}>{t('सही है','Correct')}</option>
     {r.claim && <option value="corrected">{t('सुधार चाहिए','Needs correction')}</option>}
     <option value="cannot">{t('अभी पुष्टि नहीं कर सकता','Cannot confirm')}</option>
    </Select></label>
    {protectedValue(r)&&org.role!=='quality' && <p>{t('इसकी मंज़ूरी अधिकृत जाँचकर्ता देंगे। आप इसे जाँच के लिए भेज सकते हैं।','An authorized reviewer must approve this. You can save it for their review.')}</p>}
    {r.choice && <details><summary>{t('कहे गए शब्द और शर्त','Spoken words and conditions')}</summary>
     <label>{t('रिकॉर्डिंग के ठीक वही शब्द','Exact words from the recording')}<textarea value={r.excerpt} onChange={e=>change(i,{excerpt:e.target.value})}/></label>
     <label>{t('यह काम कब पूरा होता है?','When is this work complete?')}<Select value={r.modality} onChange={e=>change(i,{modality:e.target.value})}><option value="actual">{t('अभी की स्थिति','Current status')}</option><option value="planned">{t('आगे करने का वादा','Planned for later')}</option><option value="conditional">{t('शर्त पूरी होने पर','Only if a condition is met')}</option></Select></label>
     {r.modality==='conditional'&&<input aria-label={t('शर्त','Condition')} value={r.condition} onChange={e=>change(i,{condition:e.target.value})}/>}
    </details>}
    {r.choice && allClaims.filter(c=>c.id!==r.claim?.id&&c.batch_id===note.batch_id&&c.property===r.property&&!['rejected','superseded'].includes(c.status)&&String(c.value)!==r.value).map(c=><label className="checkbox-label" key={c.id}><input type="checkbox" checked={r.supersedes.includes(c.id)} onChange={e=>change(i,{supersedes:e.target.checked?[...r.supersedes,c.id]:r.supersedes.filter(id=>id!==c.id)})}/>{t('इस पुरानी बात की जगह नई स्थिति मानें:','Replace this earlier report:')} {claimValue(c)} · {c.actor.name}</label>)}
   </section>)}
   <label className="checkbox-label"><input type="checkbox" checked={preset} onChange={e=>setPreset(e.target.checked)}/>{t('रिकॉर्डिंग सुनकर जाँच की','Checked against the recording')}</label>
   <label>{t('ज़रूरत हो तो कारण लिखें','Explain if needed')}<textarea value={reason} onChange={e=>{setReason(e.target.value);setRequestId(crypto.randomUUID());}}/></label>
   <p>{t('रोक हटाने या अलग रिपोर्ट बदलने के लिए साफ़ कारण लिखें।','Give a specific reason for clearing a hold or replacing a conflicting report.')}</p>
   <button className="button-orange" disabled={busy||!text} onClick={()=>void save()}>{t('जाँचे हुए अपडेट सहेजें','Save checked updates')}</button>
   {!note.claim_ids.length && ['failed','manual_review'].includes(note.status) && <details><summary>{t('रिकॉर्डिंग में काम का कोई अपडेट नहीं है','This recording contains no work update')}</summary><p>{t('यह काम पूरा होने की मंज़ूरी नहीं है। केवल असंबंधित रिकॉर्डिंग के लिए चुनें।','This does not approve completed work. Use it only for a recording unrelated to work.')}</p><label className="checkbox-label"><input type="checkbox" checked={empty} onChange={e=>setEmpty(e.target.checked)}/>{t('मैंने सुना है; इसमें काम की कोई बात नहीं है','I listened; this contains no work update')}</label><button className="button-outline" disabled={busy||!empty||reason.trim().length<3} onClick={()=>void save(true)}>{t('कारण के साथ बंद करें','Close with reason')}</button></details>}
  </>}
 </Dialog>;
}
