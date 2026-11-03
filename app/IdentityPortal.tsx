'use client';
import {useEffect, useState, type FormEvent, type ReactNode} from 'react';
import Link from 'next/link';
import {api} from '../lib/api/client';
import type {components} from '../lib/api/schema';
import './identity.css';
type User = components['schemas']['UserOutput'];
type Org = components['schemas']['Organization'];
type Patient = components['schemas']['Patient'];
type Review = components['schemas']['VerificationOutput'];
type Page<T> = {results:T[];next:string|null};
function nextPath(url:string){const parsed=new URL(url,window.location.origin);return parsed.pathname.replace(/^\/api\/v1\//,'')+parsed.search;}
const words = {
  it: {title:'Il tuo spazio di cura', intro:'Accedi in modo sicuro e collabora con la tua organizzazione.',
    email:'Email',password:'Password',login:'Accedi',register:'Registrati',role:'Profilo',
    patient:'Paziente',professional:'Professionista',researcher:'Ricercatore',organization_admin:'Amministratore organizzazione',
    logout:'Esci',forgot:'Recupera password',resend:'Reinvia verifica',check:'Controlla la tua email per continuare.',
    loading:'Caricamento…',done:'Operazione completata.',mfa:'Verifica in due passaggi',
    setup:'Configura autenticatore',code:'Codice TOTP o di recupero',verify:'Verifica',confirm:'Conferma',
    recovery:'Conserva questi codici in un luogo sicuro. Sono mostrati una sola volta.',
    secret:'Inserisci questo segreto nella tua app autenticatore (account Health):',
    license:'Numero iscrizione / licenza',registry:'Albo / registro',submit:'Invia per verifica',
    pending:'Stato verifica professionale',organizations:'Le tue organizzazioni',name:'Nome',kind:'Tipo',create:'Crea',
    members:'Gestisci appartenenza',active:'Attiva',save:'Salva',patients:'Anagrafiche autorizzate',
    first:'Nome paziente',last:'Cognome',birth:'Data di nascita',newPatient:'Crea anagrafica',
    link:'Invita account paziente',relationship:'Relazione di cura',professionalId:'ID professionista',
    token:'Token ricevuto per email',newPassword:'Nuova password (almeno 12 caratteri)',
    admin:'Verifiche professionali',approve:'Approva',reject:'Rifiuta',reason:'Motivazione',
    empty:'Nessun elemento accessibile.',notice:'M1 · Identità e organizzazioni. Condivisione e funzioni cliniche saranno disponibili nelle milestone successive.',
    resetMfa:'Reimposta MFA (richiede password e sessione MFA verificata)',demo:'Apri demo con dati fittizi',
    back:'Torna all’accesso', organization:'Organizzazione', refresh:'Aggiorna', membershipRole:'Ruolo organizzativo',
    adminRole:'Amministratore', accept:'Accetta collegamento', selected:'Seleziona organizzazione',more:'Carica altri'},
  en: {title:'Your care workspace', intro:'Sign in securely and collaborate with your organization.',
    email:'Email',password:'Password',login:'Sign in',register:'Register',role:'Profile',
    patient:'Patient',professional:'Professional',researcher:'Researcher',organization_admin:'Organization administrator',
    logout:'Sign out',forgot:'Reset password',resend:'Resend verification',check:'Check your email to continue.',
    loading:'Loading…',done:'Operation completed.',mfa:'Two-step verification',
    setup:'Set up authenticator',code:'TOTP or recovery code',verify:'Verify',confirm:'Confirm',
    recovery:'Store these codes securely. They are displayed only once.',
    secret:'Enter this secret in your authenticator app (Health account):',
    license:'Registration / license number',registry:'Professional register',submit:'Submit for verification',
    pending:'Professional verification status',organizations:'Your organizations',name:'Name',kind:'Type',create:'Create',
    members:'Manage membership',active:'Active',save:'Save',patients:'Authorized patient records',
    first:'Patient first name',last:'Last name',birth:'Date of birth',newPatient:'Create patient record',
    link:'Invite patient account',relationship:'Care relationship',professionalId:'Professional ID',
    token:'Token received by email',newPassword:'New password (at least 12 characters)',
    admin:'Professional verifications',approve:'Approve',reject:'Reject',reason:'Reason',
    empty:'No accessible items.',notice:'M1 · Identity and organizations. Sharing and clinical features will follow in later milestones.',
    resetMfa:'Reset MFA (requires password and verified MFA session)',demo:'Open synthetic demo',
    back:'Back to sign in', organization:'Organization', refresh:'Refresh', membershipRole:'Organization role',
    adminRole:'Administrator', accept:'Accept link', selected:'Select organization',more:'Load more'},
};
function Field({label,name,type='text',required=true,value,onChange}:{label:string;name:string;type?:string;required?:boolean;value?:string;onChange?:(value:string)=>void}) {
  return <label>{label}<input name={name} type={type} required={required} {...(value === undefined ? {} : {value,onChange:e=>onChange?.(e.target.value)})} autoComplete={type==='password'?'current-password':undefined}/></label>;
}
export default function IdentityPortal() {
  const [locale,setLocale]=useState<'it'|'en'>('it'); const t=words[locale];
  const [user,setUser]=useState<User|null>(null), [loading,setLoading]=useState(true), [busy,setBusy]=useState(false);
  const [mode,setMode]=useState('login'), [message,setMessage]=useState(''), [error,setError]=useState('');
  const [token,setToken]=useState(''), [action,setAction]=useState(''), [uri,setUri]=useState(''), [codes,setCodes]=useState<string[]>([]);
  const [orgNext,setOrgNext]=useState<string|null>(null), [patientNext,setPatientNext]=useState<string|null>(null), [reviewNext,setReviewNext]=useState<string|null>(null);
  const [organizations,setOrganizations]=useState<Org[]>([]), [org,setOrg]=useState(''), [patients,setPatients]=useState<Patient[]>([]), [reviews,setReviews]=useState<Review[]>([]);
  const ready=!!user?.email_verified && (!user.requires_mfa || user.mfa_verified);
  async function session() {
    const result=await api<User|{status:string}>('auth/session/');
    const current='id' in result?result:null; setUser(current); return current;
  }
  useEffect(()=>{async function init(){try{const current=await api<User|{status:string}>('auth/session/');setUser('id' in current?current:null);
    if('id' in current && (!current.requires_mfa||current.mfa_verified)){
      const [o,p]=await Promise.all([api<Page<Org>>('organizations/'),api<Page<Patient>>('patients/')]);setOrganizations(o.results);setOrgNext(o.next);setPatients(p.results);setPatientNext(p.next);
      if(current.is_platform_admin){const r=await api<Page<Review>>('admin/verifications/');setReviews(r.results);setReviewNext(r.next);}
    }
    const url=new URL(window.location.href);setAction(url.searchParams.get('action')||'');setToken(new URLSearchParams(url.hash.slice(1)).get('token')||'');
    if(url.hash)window.history.replaceState({},'',url.pathname+url.search);
    }catch(e){setError(String(e));}finally{setLoading(false);}}void init();},[]);
  async function refresh() {
    const current=await session();
    if(!current || (current.requires_mfa&&!current.mfa_verified))return;
    const [o,p]=await Promise.all([api<Page<Org>>('organizations/'),api<Page<Patient>>('patients/')]);
    setOrganizations(o.results);setOrgNext(o.next);setPatients(p.results);setPatientNext(p.next);
    if(current.is_platform_admin){const r=await api<Page<Review>>('admin/verifications/');setReviews(r.results);setReviewNext(r.next);}
  }
  async function run(job:()=>Promise<void>){setBusy(true);setError('');setMessage('');try{await job();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  function form(handler:(data:Record<string,string>)=>Promise<void>){return(e:FormEvent<HTMLFormElement>)=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.currentTarget).entries()) as Record<string,string>;void run(()=>handler(data));};}
  function card(title:string, children:ReactNode){return <section className="identity-card"><h2>{title}</h2>{children}</section>;}
  async function send(path:string,data:unknown){await api(path,data);setMessage(t.done);}
  if(loading)return <main className="identity"><p role="status">{t.loading}</p></main>;
  return <main className="identity" lang={locale}><header><div><p className="identity-brand">HEALTH · COLLABORATION</p><h1>{t.title}</h1><p>{t.intro}</p></div><label>Lingua / Language<select value={locale} onChange={e=>setLocale(e.target.value as 'it'|'en')}><option value="it">Italiano</option><option value="en">English</option></select></label></header>
    <p className="identity-notice">{t.notice}</p>{error&&<p role="alert" className="identity-error">{error}</p>}{message&&<p role="status">{message}</p>}
    <fieldset disabled={busy} className="identity-body">
    {action&&card(t.confirm,<form onSubmit={form(async d=>{if(action==='verify')await send('auth/verify/',d);else if(action==='reset')await send('auth/reset/',d);else if(action==='link')await send('patients/link/accept/',d);setAction('');setToken('');await refresh();})}>
      <Field label={t.token} name="token" value={token} onChange={setToken}/>{action==='reset'&&<Field label={t.newPassword} name="password" type="password"/>}<button>{action==='link'?t.accept:t.confirm}</button></form>)}
    {!user&&card(mode==='register'?t.register:mode==='login'?t.login:t.forgot,<><form onSubmit={form(async d=>{
      if(mode==='register'){await api('auth/register/',{...d,locale});setMessage(t.check);setMode('login');}
      else if(mode==='login'){await api('auth/login/',d);await refresh();}
      else {await api('auth/reset/request/',d);setMessage(t.check);}
    })}><Field label={t.email} name="email" type="email"/>{mode!=='reset'&&<Field label={mode==='register'?t.newPassword:t.password} name="password" type="password"/>}
    {mode==='register'&&<label>{t.role}<select name="role">{(['patient','professional','researcher','organization_admin'] as const).map(r=><option key={r} value={r}>{t[r]}</option>)}</select></label>}
    <button>{mode==='register'?t.register:mode==='login'?t.login:t.forgot}</button></form><nav>{['login','register','reset'].filter(x=>x!==mode).map(x=><button type="button" key={x} onClick={()=>setMode(x)}>{x==='login'?t.login:x==='register'?t.register:t.forgot}</button>)}</nav>
    <details><summary>{t.resend}</summary><form onSubmit={form(async d=>{await api('auth/resend/',d);setMessage(t.check);})}><Field label={t.email} name="email" type="email"/><button>{t.resend}</button></form></details></>)}
    {user&&<><section className="identity-account"><p>{user.email} · {t[user.role]}<br/><small>ID: {user.id}</small></p><button onClick={()=>void run(async()=>{await api('auth/logout/',{});setUser(null);setPatients([]);setOrganizations([]);setReviews([]);setOrg('');setOrgNext(null);setPatientNext(null);setReviewNext(null);setCodes([]);setUri('');})}>{t.logout}</button><button onClick={()=>void run(refresh)}>{t.refresh}</button></section>
    {!user.mfa_enabled&&card(t.mfa,<><form onSubmit={form(async d=>{const result=await api<{uri:string}>('auth/mfa/setup/',d);setUri(result.uri);})}><Field label={t.password} name="password" type="password"/><button>{t.setup}</button></form>{uri&&<><p>{t.secret}</p><code className="identity-secret">{new URL(uri).searchParams.get('secret')}</code><form onSubmit={form(async d=>{const result=await api<{recovery_codes:string[]}>('auth/mfa/confirm/',d);setCodes(result.recovery_codes);setUri('');await refresh();})}><Field label={t.code} name="code"/><button>{t.confirm}</button></form></>}</>)}
    {user.mfa_enabled&&!user.mfa_verified&&card(t.mfa,<form onSubmit={form(async d=>{await api('auth/mfa/verify/',d);await refresh();})}><Field label={t.code} name="code"/><button>{t.verify}</button></form>)}
    {!!codes.length&&card(t.recovery,<ul>{codes.map(code=><li key={code}><code>{code}</code></li>)}</ul>)}
    {ready&&<>
      {card(t.role,<form onSubmit={form(async d=>{await api('auth/profiles/',d);await session();setCodes([]);setMessage(t.back);})}><select name="role" aria-label={t.role}>{(['patient','professional','researcher','organization_admin'] as const).map(r=><option key={r} value={r}>{t[r]}</option>)}</select><button>{t.save}</button></form>)}
      {user.role==='professional'&&card(t.pending,<><p>{user.verification_status}</p><form onSubmit={form(async d=>{await send('professional/verification/',d);await refresh();})}><Field label={t.registry} name="register"/><Field label={t.license} name="license_number"/><button>{t.submit}</button></form></>)}
      {card(t.organizations,<><ul>{organizations.map(o=><li key={o.id}>{o.name} · {o.kind}<br/><small>{o.id}</small></li>)}</ul>{!organizations.length&&<p>{t.empty}</p>}{orgNext&&<button onClick={()=>void run(async()=>{const p=await api<Page<Org>>(nextPath(orgNext));setOrganizations([...organizations,...p.results]);setOrgNext(p.next);})}>{t.more}</button>}
      {['professional','organization_admin'].includes(user.role)&&<form onSubmit={form(async d=>{await send('organizations/',d);await refresh();})}><Field label={t.name} name="name"/><label>{t.kind}<select name="kind">{['hospital','clinic','practice','pharmacy','research'].map(k=><option key={k}>{k}</option>)}</select></label><button>{t.create}</button></form>}
      <label>{t.selected}<select value={org} onChange={e=>setOrg(e.target.value)}><option value="">—</option>{organizations.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}</select></label></>)}
      {org&&card(t.members,<form onSubmit={form(async d=>{await send(`organizations/${org}/memberships/`,{...d,active:d.active==='on'});})}><Field label={t.email} name="email" type="email"/><label>{t.membershipRole}<select name="role"><option value="professional">{t.professional}</option><option value="researcher">{t.researcher}</option><option value="admin">{t.adminRole}</option></select></label><label><input type="checkbox" name="active" defaultChecked/>{t.active}</label><button>{t.save}</button></form>)}
      {org&&user.role==='professional'&&card(t.newPatient,<form onSubmit={form(async d=>{await send(`organizations/${org}/patients/`,d);await refresh();})}><Field label={t.first} name="first_name"/><Field label={t.last} name="last_name"/><Field label={t.birth} name="birth_date" type="date"/><Field label={t.email} name="email" type="email" required={false}/><button>{t.create}</button></form>)}
      {card(t.patients,<>{!patients.length&&<p>{t.empty}</p>}{patientNext&&<button onClick={()=>void run(async()=>{const p=await api<Page<Patient>>(nextPath(patientNext));setPatients([...patients,...p.results]);setPatientNext(p.next);})}>{t.more}</button>}{patients.map(p=><article key={p.id}><h3>{p.first_name} {p.last_name}</h3><p>{p.birth_date}</p><small>{p.id}</small>
        {user.role==='professional'&&<details><summary>{t.link}</summary><form onSubmit={form(async d=>send(`organizations/${p.organization}/patients/${p.id}/link/`,d))}><Field label={t.email} name="email" type="email"/><button>{t.link}</button></form></details>}</article>)}</>)}
      {org&&card(t.relationship,<form onSubmit={form(async d=>send(`organizations/${org}/patients/${d.patient}/relationships/`,{professional:d.professional,active:d.active==='on'}))}><Field label="Patient ID" name="patient"/><Field label={t.professionalId} name="professional"/><label><input type="checkbox" name="active" defaultChecked/>{t.active}</label><button>{t.save}</button></form>)}
      {user.is_platform_admin&&card(t.admin,<>{!reviews.length&&<p>{t.empty}</p>}{reviewNext&&<button onClick={()=>void run(async()=>{const p=await api<Page<Review>>(nextPath(reviewNext));setReviews([...reviews,...p.results]);setReviewNext(p.next);})}>{t.more}</button>}{reviews.map(r=><article key={r.user}><h3>{r.register} · {r.license_number}</h3><p>{r.user}</p><form onSubmit={form(async d=>{await send(`admin/verifications/${r.user}/`,d);await refresh();})}><Field label={t.reason} name="reason"/><select name="status" aria-label={t.admin}><option value="approved">{t.approve}</option><option value="rejected">{t.reject}</option></select><button>{t.save}</button></form></article>)}</>)}
      {user.mfa_enabled&&user.mfa_verified&&<details><summary>{t.resetMfa}</summary><form onSubmit={form(async d=>{await send('auth/mfa/reset/',d);await session();setCodes([]);})}><Field label={t.password} name="password" type="password"/><button>{t.confirm}</button></form></details>}
    </>}</>}
    </fieldset><footer><Link href="/demo">{t.demo}</Link></footer>
  </main>;
}
