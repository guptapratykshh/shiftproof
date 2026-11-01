import { Select } from "../components/Select";
import {useEffect,useState} from 'react';
import {call} from './client';
import {bilingual as t} from '../i18n';
import type {Operations} from './OperationsSetup';
export default function AssistedPermissions({base,members,operations}:{base:string;members:{id:string;name:string}[];operations:Operations|null}){
 const [grants,setGrants]=useState<Record<string,string[]>>({}),[person,setPerson]=useState(''),[shifts,setShifts]=useState<string[]>([]),[error,setError]=useState(''),[notice,setNotice]=useState('');
 useEffect(()=>{call<{permissions:Record<string,string[]>}>(base+'/assisted-capture').then(r=>setGrants(r.permissions)).catch(e=>setError(e.message));},[base]);
 return <details className="platform-panel"><summary>{t('साझा फ़ोन पर रिकॉर्डिंग की मदद','Shared-phone recording assistance')}</summary><p>{t('केवल चुनी शिफ्ट में नियुक्त सहायक दूसरे नियुक्त कर्मचारी की बात रिकॉर्ड कर सकता है।','An assigned helper may record for another assigned worker only in the selected shifts.')}</p>
 {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 <label>{t('सहायक','Helper')}<Select value={person} onChange={e=>{setPerson(e.target.value);setShifts(grants[e.target.value]||[]);setNotice('');}}><option value="">{t('चुनें','Choose')}</option>{members.map(m=><option value={m.id} key={m.id}>{m.name} · {m.id.slice(-4)}</option>)}</Select></label>
 {operations?.shifts.filter(s=>operations.assignments?.some(a=>a.user_id===person&&a.shift_id===s.id)).map(s=><label className="checkbox-label" key={s.id}><input type="checkbox" checked={shifts.includes(s.id)} onChange={e=>setShifts(e.target.checked?[...shifts,s.id]:shifts.filter(id=>id!==s.id))}/>{s.name}</label>)}
 <button className="button-outline" disabled={!person} onClick={async()=>{setError('');try{await call(base+'/assisted-capture',{user_id:person,shift_ids:shifts},'PUT');setGrants({...grants,[person]:shifts});setNotice(t('अनुमति सहेजी गई','Permission saved'));}catch(e){setError((e as Error).message);}}}>{t('सहायक की अनुमति सहेजें','Save helper permission')}</button></details>;
}
