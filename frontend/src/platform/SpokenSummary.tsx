import type { Workspace } from '../types';
import { bilingual as t, useLanguage } from '../i18n';
export default function SpokenSummary({view, itemId, source}: {view: Workspace; itemId?:string; source?:(id:string)=>void}) {
 const lang=useLanguage();
 const rows=view.summary?.items.filter(r=>!itemId||r.work_item_id===itemId) || [];
 if(!rows.length)return null;
 return <section className="platform-panel" aria-label={t('अभी की जानकारी','Current update')}><h2>{t('अभी की जानकारी','Current update')}</h2>
  {rows.map((r,i)=><div key={i}><p><strong>{!itemId?r.work_item_id+' · ':''}</strong>{r.text[lang]}</p>{source && r.note_ids.length>0 && <details><summary>{t('विवरण','Details')}</summary>{r.note_ids.map(id=><button className="text-button" key={id} onClick={()=>source(id)}>{t('मूल रिपोर्ट देखें','View source report')}</button>)}</details>}</div>)}
 </section>;
}
