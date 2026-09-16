import React, {useState, useEffect} from 'react';

export async function api(path, body) {
  const response = await fetch('/api'+path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Please check your input and try again.');
  return result;
}
const fieldNames = {credit_score:'Credit score',dti_percent:'Debt-to-income ratio',income_verified:'Income verified',employment_months:'Employment tenure',amount:'Loan amount',term_months:'Loan term'};
const comparison = {lt:'below',gt:'above',eq:'equal to'};
function value(field, v) { if(typeof v === 'boolean') return v?'Yes':'No'; if(field==='amount') return '$'+Number(v).toLocaleString(); if(field==='dti_percent') return v+'%'; if(field.endsWith('_months')) return v+' months'; return String(v); }
const labels = {get_loan_application:'Application retrieved',plan_policy_search:'Policy search planned',search_bank_policies:'Policy sources retrieved',evaluate_application:'Assessment prepared',human_approval:'Human decision recorded',create_review_case:'Review case created'};

export default function App() {
  const [message,setMessage] = useState('Review application L002 against our lending policies. Identify risks and recommend the next action.');
  const [runId,setRunId] = useState(()=>localStorage.getItem('demobank-run') || '');
  const [run,setRun] = useState(null);
  const [health,setHealth] = useState(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [reviewer,setReviewer] = useState('Demo Reviewer');
  useEffect(()=>{api('/health').then(setHealth).catch(e=>setError(e.message));},[]);
  useEffect(()=>{
    if (!runId) return;
    let stopped=false, timer;
    async function poll(){
      try {
        const next=await api('/reviews/'+runId);
        if(stopped)return;
        setRun(next);
        if(next.status==='RUNNING') timer=setTimeout(poll,750);
      } catch(e) { if(!stopped) setError(e.message); }
    }
    poll();
    return ()=>{stopped=true;clearTimeout(timer);};
  },[runId,busy]);
  async function start(event){
    event.preventDefault();setBusy(true);setError('');
    try{const result=await api('/reviews',{message});setRun(null);setRunId(result.run_id);localStorage.setItem('demobank-run',result.run_id);}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function decide(approved){
    setBusy(true);setError('');
    try{await api('/reviews/'+runId+'/decision',{approved,reviewer});}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function retry(){
    setBusy(true);setError('');
    try{await api('/reviews/'+runId+'/retry',{});}catch(e){setError(e.message);}finally{setBusy(false);}
  }
  const events=run?.events || [];
  const applicant=events.find(e=>e.step==='get_loan_application')?.detail;
  const assessment=[...events].reverse().find(e=>e.step==='evaluate_application')?.detail;
  return <div className="shell">
    <header><a className="brand" href="/">D<span>DemoBank</span></a><span className="tag">RESEARCH LAB / SYNTHETIC DATA</span><span className="mode">{health ? (health.mode==='bedrock'?'AWS Bedrock / Claude':'Deterministic demo mode'):'Connecting...'}</span></header>
    <main><section className="intro"><div className="eyebrow">LENDING OPERATIONS</div><h1>A clearer path to review.</h1><p>Bring application data and lending policy together, with evidence at every step and a human in control.</p></section>
    <div className="workspace"><aside><div className="panel"><div className="eyebrow">01 / REQUEST</div><h2>Review an application</h2><form onSubmit={start}><label htmlFor="request">What would you like to review?</label><textarea id="request" value={message} onChange={e=>setMessage(e.target.value)} maxLength={1000}/><div className="examples">{['L001','L002','L003'].map(id=><button type="button" key={id} onClick={()=>setMessage(`Review application ${id} against our lending policies. Identify risks and recommend the next action.`)}>{id}</button>)}</div><button className="primary" disabled={busy || run?.status==='RUNNING'}>Start review <span>→</span></button></form><p className="muted">All applicants and policies are fictional. Reviewing an application does not approve or decline a loan.</p></div>
    {applicant && <div className="panel applicant"><div className="eyebrow">APPLICATION / {applicant.application_id}</div><h2>{applicant.name}</h2><div className="amount">${applicant.amount.toLocaleString()} <small>/ {applicant.term_months} months</small></div><dl>{[['Credit score',applicant.credit_score],['Annual income','$'+applicant.annual_income.toLocaleString()],['Debt-to-income',applicant.dti_percent+'%'],['Employment',applicant.employment_months+' months'],['Income verified',applicant.income_verified?'Yes':'No']].map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl></div>}</aside>
    <section className="results" aria-live="polite">{error && <div role="alert" className="error">{error}</div>}
    {!run && <div className="panel empty"><div className="empty-icon">↗</div><h2>From application to evidence</h2><p>Start a review to see the agent retrieve data, search policies, and prepare a cited assessment.</p><div className="steps">Application → Policy → Assessment → Your approval</div></div>}
    {run && <><div className="panel"><div className="section-head"><div><div className="eyebrow">02 / EXECUTION</div><h2>Follow the review</h2></div><span className={'status '+run.status.toLowerCase()}>{run.status.replaceAll('_',' ')}</span></div><ol className="timeline">{events.map((e,i)=><li key={e.event_id}><span className="dot">{i+1}</span><details><summary>{labels[e.step] || e.step}</summary><pre>{JSON.stringify(e.detail,null,2)}</pre></details></li>)}</ol>{run.status==='RUNNING' && <p className="working">Processing the next step…</p>}{run.status==='FAILED' && <div className="error">{run.error}<button onClick={retry} disabled={busy}>Retry review</button></div>}</div>
    {assessment && <div className="panel"><div className="eyebrow">03 / ASSESSMENT</div><h2 className="recommendation">{assessment.recommendation}</h2><p>{assessment.summary}</p><div className="checks">{assessment.checks.map(c=><details className="check" key={c.citation_id}><summary><span className={c.requires_review?'risk':'pass'}>{c.requires_review?'REVIEW':'PASS'}</span><span>{fieldNames[c.field]}<small>Observed: {value(c.field,c.actual)} · Review when {comparison[c.operator]} {value(c.field,c.threshold)}</small></span><span className="citation">[{c.citation_id}]</span></summary><blockquote>{c.excerpt}</blockquote><p className="muted">{c.source} · page {c.page}</p></details>)}</div><h3>Recommended next action</h3><p>{assessment.next_action}</p><p className="muted">{assessment.notice}</p></div>}
    {run.status==='AWAITING_APPROVAL' && <div className="panel approval"><div className="eyebrow">04 / YOUR DECISION</div><h2>Create a review case?</h2><p>Approval saves this assessment as a review case for a human credit reviewer. It does not change the loan’s status.</p><label htmlFor="reviewer">Reviewer name (demo audit label)</label><input id="reviewer" value={reviewer} maxLength={80} onChange={e=>setReviewer(e.target.value)}/><div className="actions"><button className="primary" onClick={()=>decide(true)} disabled={busy || !reviewer.trim()}>Approve & create case</button><button onClick={()=>decide(false)} disabled={busy || !reviewer.trim()}>Decline case creation</button></div></div>}
    {run.case && <div className="panel success"><h2>Review case created</h2><p>Saved in PostgreSQL with your approval and the cited assessment.</p><code>{run.case.case_id}</code><p className="muted">Reviewer: {run.case.reviewer}</p></div>}
    {run.status==='DECLINED' && <div className="panel"><h2>Case creation declined</h2><p>Your decision was recorded. No review case was created.</p></div>}</>}
    </section></div></main><footer>DemoBank Research · Loan Review Agent · Demo use only</footer>
  </div>;
}
