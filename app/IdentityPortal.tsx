'use client';
import {useEffect, useState, type FormEvent, type ReactNode} from 'react';
import Link from 'next/link';
import {api, ApiError} from '../lib/api/client';
import type {components} from '../lib/api/schema';
import {AnalysisMetrics, PublishedOpinions} from './ClinicalAnalysis';
import {ResearchWorkspace} from './ResearchWorkspace';
import {ResearchConsent} from './ResearchConsent';
import {BookingAdministration, BookingPortal} from './BookingPortal';
import {WorkspaceOverview} from './WorkspaceOverview';
import {ClinicalDocuments} from './ClinicalDocuments';
import {LabResultReviews} from './LabResultReviews';
import {MedicationSafetyPanel} from './MedicationSafetyPanel';
import {ThemePicker} from './PortalTheme';
type User = components['schemas']['UserOutput'];
type Org = components['schemas']['Organization'];
type Patient = components['schemas']['Patient'];
type Review = components['schemas']['VerificationOutput'];
type Share = components['schemas']['ShareOutput'];
type ConsentText = components['schemas']['ConsentTextOutput'];
type ConsentEvent = components['schemas']['ConsentEventOutput'];
type AccessEvent = components['schemas']['AccessHistoryOutput'];
type Notification = components['schemas']['NotificationOutput'];
type SecureMessage = components['schemas']['SecureMessageOutput'];
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
    empty:'Nessun elemento accessibile.',notice:'M2 · Identità, organizzazioni, consensi e condivisioni controllate.',
    resetMfa:'Reimposta MFA (richiede password e sessione MFA verificata)',demo:'Apri demo con dati fittizi',
    organization:'Organizzazione', refresh:'Aggiorna', membershipRole:'Ruolo organizzativo',
    adminRole:'Amministratore', accept:'Accetta collegamento', selected:'Seleziona organizzazione',more:'Carica altri',
    shares:'Condivisioni e consensi',pendingConsent:'Richiede il tuo consenso',activeShare:'Condivisione attiva',
    revokedShare:'Revocata',grant:'Concedi accesso',revoke:'Revoca accesso',purpose:'Finalità',
    recipient:'Destinatario (ID professionista o organizzazione)',recipientKind:'Tipo destinatario',
    individual:'Professionista',facility:'Organizzazione',share:'Richiedi condivisione',
    consentCopy:'Condividi l’anagrafica con il destinatario e per la finalità indicata. Puoi revocare in ogni momento.',
    accessHistory:'Storico degli accessi',noAccess:'Nessun accesso registrato.',notifications:'Notifiche',
    consentGranted:'Consenso registrato.',consentRevoked:'Consenso revocato.',shareScope:'Ambito',
    consentState:'Stato del consenso',expiredShare:'Scaduta',
    messages:'Messaggi sicuri',messageText:'Scrivi un messaggio',sendMessage:'Invia messaggio',
  },
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
    empty:'No accessible items.',notice:'M2 · Identity, organizations, consent and controlled sharing.',
    resetMfa:'Reset MFA (requires password and verified MFA session)',demo:'Open synthetic demo',
    organization:'Organization', refresh:'Refresh', membershipRole:'Organization role',
    adminRole:'Administrator', accept:'Accept link', selected:'Select organization',more:'Load more',
    shares:'Shares and consent',pendingConsent:'Your consent is required',activeShare:'Active share',
    revokedShare:'Revoked',grant:'Grant access',revoke:'Revoke access',purpose:'Purpose',
    recipient:'Recipient (professional or organization ID)',recipientKind:'Recipient type',
    individual:'Professional',facility:'Organization',share:'Request sharing',
    consentCopy:'Share this patient record with the named recipient for the stated purpose. You can withdraw at any time.',
    accessHistory:'Access history',noAccess:'No access recorded.',notifications:'Notifications',
    consentGranted:'Consent recorded.',consentRevoked:'Consent withdrawn.',shareScope:'Scope',
    consentState:'Consent state',expiredShare:'Expired',
    messages:'Secure messages',messageText:'Write a message',sendMessage:'Send message',
  },
};
function Field({label,name,type='text',required=true,value,onChange}:{label:string;name:string;type?:string;required?:boolean;value?:string;onChange?:(value:string)=>void}) {
  return <label>{label}<input name={name} type={type} required={required} {...(value === undefined ? {} : {value,onChange:e=>onChange?.(e.target.value)})} autoComplete={type==='password'?'current-password':undefined}/></label>;
}
export default function IdentityPortal() {
  const [locale,setLocale]=useState<'it'|'en'>('it'); const t=words[locale];
  const [user,setUser]=useState<User|null>(null), [loading,setLoading]=useState(true), [busy,setBusy]=useState(false);
  const [localMail,setLocalMail]=useState(false);
  const [mode,setMode]=useState('login'), [message,setMessage]=useState(''), [error,setError]=useState('');
  const [token,setToken]=useState(''), [action,setAction]=useState(''), [uri,setUri]=useState(''), [codes,setCodes]=useState<string[]>([]);
  const [orgNext,setOrgNext]=useState<string|null>(null), [patientNext,setPatientNext]=useState<string|null>(null), [reviewNext,setReviewNext]=useState<string|null>(null);
  const [organizations,setOrganizations]=useState<Org[]>([]), [org,setOrg]=useState(''), [patients,setPatients]=useState<Patient[]>([]), [reviews,setReviews]=useState<Review[]>([]);
  const [shares,setShares]=useState<Share[]>([]), [consentTexts,setConsentTexts]=useState<ConsentText[]>([]),
    [consentEvents,setConsentEvents]=useState<ConsentEvent[]>([]), [accessHistory,setAccessHistory]=useState<AccessEvent[]>([]),
    [notifications,setNotifications]=useState<Notification[]>([]), [openThread,setOpenThread]=useState(''),
    [messageThreads,setMessageThreads]=useState<Record<string,SecureMessage[]>>({});
  const checkEmail = localMail
    ? (locale === 'it' ? 'Controlla Mailpit per continuare.' : 'Check Mailpit to continue.')
    : t.check;
  const organizationKinds: Record<string, string> = locale === 'it'
    ? {hospital:'Ospedale', clinic:'Clinica', practice:'Studio', pharmacy:'Farmacia', research:'Ricerca'}
    : {hospital:'Hospital', clinic:'Clinic', practice:'Practice', pharmacy:'Pharmacy', research:'Research'};
  const ready=!!user?.email_verified && (!user.requires_mfa || user.mfa_verified);
  async function session() {
    const result=await api<User|{status:string}>('auth/session/');
    const current='id' in result?result:null; setUser(current); return current;
  }
  useEffect(() => {
    document.documentElement.lang = locale;
    return () => { document.documentElement.lang = 'it'; };
  }, [locale]);
  useEffect(()=>{async function init(){setLocalMail(['localhost','127.0.0.1','[::1]'].includes(window.location.hostname)&&window.location.port==='8080');try{const current=await api<User|{status:string}>('auth/session/');setUser('id' in current?current:null);
    if('id' in current && (!current.requires_mfa||current.mfa_verified)){
      const [o,p,s,n]=await Promise.all([api<Page<Org>>('organizations/'),api<Page<Patient>>('patients/'),api<Page<Share>>('shares/'),api<Notification[]>('notifications/')]);setOrganizations(o.results);setOrgNext(o.next);setOrg(selected=>selected||(!o.next&&o.results.length===1?o.results[0].id:''));setPatients(p.results);setPatientNext(p.next);setShares(s.results);setNotifications(n);
      if(current.role==='patient'){
        const [texts,events,access]=await Promise.all([api<ConsentText[]>('consents/texts/'),api<ConsentEvent[]>('consents/'),api<AccessEvent[]>('patients/access-history/')]);
        setConsentTexts(texts);setConsentEvents(events);setAccessHistory(access);
      }
      if(current.is_platform_admin){const r=await api<Page<Review>>('admin/verifications/');setReviews(r.results);setReviewNext(r.next);}
    }
    const url=new URL(window.location.href);setAction(url.searchParams.get('action')||'');setToken(new URLSearchParams(url.hash.slice(1)).get('token')||'');

    }catch{setError('Impossibile caricare il portale. Ricarica la pagina e riprova.');}finally{setLoading(false);}}void init();},[]);
  useEffect(()=>{
    const updateToken=()=>setToken(new URLSearchParams(window.location.hash.slice(1)).get('token')||'');
    window.addEventListener('hashchange',updateToken);
    return ()=>window.removeEventListener('hashchange',updateToken);
  },[]);
  async function refresh() {
    const current=await session();
    if(!current || (current.requires_mfa&&!current.mfa_verified))return;
    const [o,p,s,n]=await Promise.all([api<Page<Org>>('organizations/'),api<Page<Patient>>('patients/'),api<Page<Share>>('shares/'),api<Notification[]>('notifications/')]);
    setOrganizations(o.results);setOrgNext(o.next);setOrg(selected=>selected||(!o.next&&o.results.length===1?o.results[0].id:''));setPatients(p.results);setPatientNext(p.next);setShares(s.results);setNotifications(n);
    if(current.role==='patient'){
      const [texts,events,access]=await Promise.all([api<ConsentText[]>('consents/texts/'),api<ConsentEvent[]>('consents/'),api<AccessEvent[]>('patients/access-history/')]);
      setConsentTexts(texts);setConsentEvents(events);setAccessHistory(access);
    }
    if(current.is_platform_admin){const r=await api<Page<Review>>('admin/verifications/');setReviews(r.results);setReviewNext(r.next);}
  }
  function errorMessage(error: unknown) {
    const english = locale === 'en';
    if (error instanceof ApiError) {
      if (error.status === 429) return english ? 'Too many requests. Wait and try again.' : 'Troppe richieste. Attendi e riprova.';
      if (error.status === 401 || error.status === 403) return english ? 'Access denied. Check your credentials or permissions.' : 'Accesso negato. Controlla credenziali o permessi.';
      if (error.status === 400) return english ? 'Check the fields you entered and try again.' : 'Controlla i dati inseriti e riprova.';
      if (error.status === 404 || error.status === 409) return english ? 'This action is no longer available. Refresh and try again.' : 'Operazione non più disponibile. Aggiorna e riprova.';
    }
    return english ? 'The service could not complete your request. Try again.' : 'Il servizio non ha completato la richiesta. Riprova.';
  }
  async function run(job:()=>Promise<void>){
    setBusy(true);setError('');setMessage('');
    try{await job();}catch(error){setError(errorMessage(error));}finally{setBusy(false);}
  }
  function form(handler:(data:Record<string,string>)=>Promise<void>){return(e:FormEvent<HTMLFormElement>)=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.currentTarget).entries()) as Record<string,string>;void run(()=>handler(data));};}
  function card(title:string, children:ReactNode, id?:string){return <section className="identity-card" id={id} tabIndex={id ? -1 : undefined}><h2>{title}</h2>{children}</section>;}
  async function send(path:string,data:unknown){await api(path,data);setMessage(t.done);}
  if(loading)return <main className="identity"><p role="status">{t.loading}</p></main>;
  return <main className="identity" lang={locale}><a className="workspace-skip" href="#portal-content" onClick={event=>{
      const content=document.getElementById('portal-content');
      if(content){event.preventDefault();content.focus();content.scrollIntoView({block:'start'});}
    }}>{locale==='it'?'Vai al contenuto':'Skip to content'}</a><header className="identity-hero"><div><p className="identity-brand"><span aria-hidden="true">✚</span> Clarìa</p><h1>{t.title}</h1><p>{t.intro}</p></div><div className="identity-controls"><ThemePicker english={locale==='en'}/><label>Lingua / Language<select value={locale} onChange={e=>setLocale(e.target.value as 'it'|'en')}><option value="it">Italiano</option><option value="en">English</option></select></label></div></header>
    {localMail&&!user&&<aside className="identity-notice">
      <strong>{locale==='it'?'Email di prova':'Development email'}</strong>
      <p>{locale==='it'?'In locale, verifica e recupero password arrivano in Mailpit. Se hai già creato l’account, usa «Reinvia verifica».':'Local verification and password reset messages go to Mailpit. If you already registered, use “Resend verification”.'}</p>
      <a href="http://localhost:8025" target="_blank" rel="noreferrer">{locale==='it'?'Apri Mailpit':'Open Mailpit'} ↗</a>
    </aside>}{error&&<p role="alert" className="identity-error">{error}</p>}{(message||busy)&&<p role="status">{message||t.loading}</p>}
    <fieldset id="portal-content" tabIndex={-1} disabled={busy} aria-busy={busy} className="identity-body">
    {(['verify','reset','link'].includes(action))&&card(
      action==='verify'?(locale==='it'?'Verifica il tuo indirizzo email':'Verify your email address'):t.confirm,
      <form onSubmit={form(async d=>{
        const path=action==='verify'?'auth/verify/':action==='reset'?'auth/reset/':'patients/link/accept/';
        try {
          await send(path,{...d,token:token.trim()});
        } catch(error) {
          if(action==='verify'&&error instanceof Error&&error.message.includes('Invalid or expired token')){
            setError(locale==='it'
              ? 'Questo link è scaduto o è già stato usato. Se non riesci ad accedere, usa «Reinvia verifica» e apri il messaggio più recente.'
              : 'This link has expired or was already used. If you cannot sign in, request another verification email and open the newest message.');
            return;
          }
          throw error;
        }
        const url=new URL(window.location.href);
        url.searchParams.delete('action');
        url.hash='';
        window.history.replaceState(null,'',url.pathname+url.search);
        setAction('');setToken('');await refresh();
      })}>
        {action==='verify'&&<p>{locale==='it'?'Conferma per attivare il tuo account.':'Confirm to activate your account.'}</p>}
        <Field label={t.token} name="token" type="password" value={token} onChange={setToken}/>
        {action==='reset'&&<Field label={t.newPassword} name="password" type="password"/>}
        <button>{action==='link'?t.accept:t.confirm}</button>
      </form>)}
    {!user&&card(mode==='register'?t.register:mode==='login'?t.login:t.forgot,<><form onSubmit={form(async d=>{
      if(mode==='register'){await api('auth/register/',{...d,locale});setMessage(checkEmail);setMode('login');}
      else if(mode==='login'){await api('auth/login/',d);await refresh();}
      else {await api('auth/reset/request/',d);setMessage(checkEmail);}
    })}><Field label={t.email} name="email" type="email"/>{mode!=='reset'&&<Field label={mode==='register'?t.newPassword:t.password} name="password" type="password"/>}
    {mode==='register'&&<label>{t.role}<select name="role">{(['patient','professional','researcher','organization_admin'] as const).map(r=><option key={r} value={r}>{t[r]}</option>)}</select></label>}
    <button>{mode==='register'?t.register:mode==='login'?t.login:t.forgot}</button></form><nav>{['login','register','reset'].filter(x=>x!==mode).map(x=><button type="button" key={x} onClick={()=>setMode(x)}>{x==='login'?t.login:x==='register'?t.register:t.forgot}</button>)}</nav>
    <details><summary>{t.resend}</summary><form onSubmit={form(async d=>{await api('auth/resend/',d);setMessage(checkEmail);})}><Field label={t.email} name="email" type="email"/><button>{t.resend}</button></form></details></>)}
    {user&&<>{ready&&<WorkspaceOverview role={user.role} platform={user.is_platform_admin} selectedKind={organizations.find(item=>item.id===org)?.kind}
        english={locale==='en'} patients={patients.length} organizations={organizations.length}
        notifications={notifications.filter(item=>!item.read).length}/>}
    <section className="identity-account"><p>{user.email} · {t[user.role]}<br/><small>ID: {user.id}</small></p><button onClick={()=>void run(async()=>{await api('auth/logout/',{});setUser(null);setPatients([]);setOrganizations([]);setReviews([]);setShares([]);setConsentEvents([]);setAccessHistory([]);setNotifications([]);setOpenThread('');setMessageThreads({});setOrg('');setOrgNext(null);setPatientNext(null);setReviewNext(null);setCodes([]);setUri('');})}>{t.logout}</button><button onClick={()=>void run(refresh)}>{t.refresh}</button></section>
    {!user.mfa_enabled&&card(t.mfa,<><form onSubmit={form(async d=>{const result=await api<{uri:string}>('auth/mfa/setup/',d);setUri(result.uri);})}><Field label={t.password} name="password" type="password"/><button>{t.setup}</button></form>{uri&&<><p>{t.secret}</p><code className="identity-secret">{new URL(uri).searchParams.get('secret')}</code><form onSubmit={form(async d=>{const result=await api<{recovery_codes:string[]}>('auth/mfa/confirm/',d);setCodes(result.recovery_codes);setUri('');await refresh();})}><Field label={t.code} name="code"/><button>{t.confirm}</button></form></>}</>)}
    {user.mfa_enabled&&!user.mfa_verified&&card(t.mfa,<form onSubmit={form(async d=>{await api('auth/mfa/verify/',d);await refresh();})}><Field label={t.code} name="code"/><button>{t.verify}</button></form>)}
    {!!codes.length&&card(t.recovery,<ul>{codes.map(code=><li key={code}><code>{code}</code></li>)}</ul>)}
    {ready&&<>
      {user.role==='professional'&&card(t.pending,<><p>{user.verification_status}</p><form onSubmit={form(async d=>{await send('professional/verification/',d);await refresh();})}><Field label={t.registry} name="register"/><Field label={t.license} name="license_number"/><button>{t.submit}</button></form></>)}
      {card(t.organizations,<><ul>{organizations.map(o=><li key={o.id}>{o.name} · {organizationKinds[o.kind] ?? o.kind}<br/><small>{o.id}</small></li>)}</ul>{!organizations.length&&<p>{t.empty}</p>}{orgNext&&<button onClick={()=>void run(async()=>{const p=await api<Page<Org>>(nextPath(orgNext));setOrganizations([...organizations,...p.results]);setOrgNext(p.next);})}>{t.more}</button>}
      {['professional','organization_admin'].includes(user.role)&&<form onSubmit={form(async d=>{await send('organizations/',d);await refresh();})}><Field label={t.name} name="name"/><label>{t.kind}<select name="kind">{Object.entries(organizationKinds).map(([kind,label])=><option key={kind} value={kind}>{label}</option>)}</select></label><button>{t.create}</button></form>}
      <label>{t.selected}<select value={org} onChange={e=>setOrg(e.target.value)}><option value="">—</option>{organizations.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}</select></label></>, 'workspace-organizations')}
      {user.is_platform_admin&&<div id="workspace-review-research" tabIndex={-1} className="workspace-section"><ResearchWorkspace review english={locale==='en'}/></div>}
      {org&&organizations.find(item=>item.id===org)?.kind==='research'&&<div id="workspace-research" tabIndex={-1} className="workspace-section"><ResearchWorkspace key={org} organization={org} english={locale==='en'}/></div>}
      {org&&user.role==='organization_admin'&&<div id="workspace-management" tabIndex={-1} className="workspace-section"><BookingAdministration key={org} organization={org} pharmacy={organizations.find(item=>item.id===org)?.kind==='pharmacy'} english={locale==='en'}/></div>}
      {org&&user.role==='organization_admin'&&<AnalysisMetrics key={org} organization={org} english={locale==='en'}/>}
      {org&&user.role!=='patient'&&card(t.members,<form onSubmit={form(async d=>{await send(`organizations/${org}/memberships/`,{...d,active:d.active==='on'});})}><Field label={t.email} name="email" type="email"/><label>{t.membershipRole}<select name="role"><option value="professional">{t.professional}</option><option value="researcher">{t.researcher}</option><option value="admin">{t.adminRole}</option></select></label><label><input type="checkbox" name="active" defaultChecked/>{t.active}</label><button>{t.save}</button></form>)}
      {org&&user.role==='professional'&&card(t.newPatient,<form onSubmit={form(async d=>{await send(`organizations/${org}/patients/`,d);await refresh();})}><Field label={t.first} name="first_name"/><Field label={t.last} name="last_name"/><Field label={t.birth} name="birth_date" type="date"/><Field label={t.email} name="email" type="email" required={false}/><button>{t.create}</button></form>)}
      {user.role==='patient'&&<div id="workspace-bookings" tabIndex={-1} className="workspace-section"><BookingPortal organizations={[...new Set(patients.map(p=>p.organization))]} english={locale==='en'}/></div>}
      {card(t.patients,<>{!patients.length&&<p>{t.empty}</p>}{patientNext&&<button onClick={()=>void run(async()=>{const p=await api<Page<Patient>>(nextPath(patientNext));setPatients([...patients,...p.results]);setPatientNext(p.next);})}>{t.more}</button>}{patients.map(p=><article key={p.id}><h3>{p.first_name} {p.last_name}</h3><p>{p.birth_date}</p><small>{p.id}</small><ClinicalDocuments patient={p.id} write={user.role==='professional'} english={locale==='en'} shareChanged={refresh}/>{user.role==='professional'&&<><LabResultReviews patient={p.id} patientLabel={p.first_name+' '+p.last_name+' · '+p.birth_date} english={locale==='en'}/><MedicationSafetyPanel patient={p.id} patientLabel={p.first_name+' '+p.last_name+' · '+p.birth_date} english={locale==='en'}/></>}{user.role==='patient'&&<><PublishedOpinions patient={p.id} english={locale==='en'}/><ResearchConsent patient={p.id} english={locale==='en'}/></>}
        {user.role==='professional'&&<details><summary>{t.link}</summary><form onSubmit={form(async d=>send(`organizations/${p.organization}/patients/${p.id}/link/`,d))}><Field label={t.email} name="email" type="email"/><button>{t.link}</button></form></details>}
        {user.role==='professional'&&<details><summary>{t.share}</summary><form onSubmit={form(async d=>{const target=d.recipientKind==='organization'?{recipient_organization:d.recipient}:{recipient_user:d.recipient};await api('shares/',{patient:p.id,...target,scope:'item',permissions:['view','download','comment'],purpose:d.purpose});await refresh();setMessage(t.done);})}><label>{t.recipientKind}<select name="recipientKind"><option value="user">{t.individual}</option><option value="organization">{t.facility}</option></select></label><Field label={t.recipient} name="recipient"/><Field label={t.purpose} name="purpose"/><button>{t.share}</button></form></details>}</article>)}</>, 'workspace-patients')}
      {card(t.shares,<>{shares.map(s=><article key={s.id}><h3>{s.revoked_at||s.consent_decision==='revoked'?t.revokedShare:s.consent_decision==='granted'?(s.active?t.activeShare:t.expiredShare):t.pendingConsent}</h3><p>{t.recipient}: {s.recipient_user||s.recipient_organization}</p><p>{t.purpose}: {s.purpose}</p>{s.resource_label&&<p>{s.resource_label}</p>}<p>{locale==='it'?'Permessi':'Permissions'}: {Array.isArray(s.permissions)?s.permissions.join(', '): '—'} · {locale==='it'?'Scadenza':'Expiration'}: {s.expires_at?new Date(s.expires_at).toLocaleString(locale):'—'}</p><small>{s.patient} · {t.shareScope}: {s.scope}{s.document && (locale==='it' ? ' · Documento ' : ' · Document ') + s.document}{s.folder && (locale==='it' ? ' · Cartella ' : ' · Folder ') + s.folder}</small>{s.clinical_active&&<ClinicalDocuments patient={s.patient} write={false} english={locale==='en'}/>}
        {user.role==='patient'&&(s.consent_decision!=='granted'||(!s.clinical_active&&(s.document||s.folder||s.scope==='chart')))&&!s.revoked_at&&<><p>{consentTexts.find(text=>text.purpose==='care_sharing'&&text.locale===locale)?.text||t.consentCopy}</p><button onClick={()=>void run(async()=>{const text=consentTexts.find(item=>item.purpose==='care_sharing'&&item.locale===locale);if(!text)throw new Error('Consent text is unavailable');await api('consents/',{share:s.id,text_version:text.version,locale,decision:'granted'});await refresh();setMessage(t.consentGranted);})}>{t.grant}</button></>}
        {user.role==='patient'&&s.consent_decision==='granted'&&!s.revoked_at&&<button onClick={()=>void run(async()=>{const text=consentTexts.find(item=>item.purpose==='care_sharing'&&item.locale===locale);if(!text)throw new Error('Consent text is unavailable');await api('consents/',{share:s.id,text_version:text.version,locale,decision:'revoked'});await refresh();setMessage(t.consentRevoked);})}>{t.revoke}</button>}
        {user.role==='professional'&&s.granted_by===user.id&&!s.revoked_at&&<button onClick={()=>void run(async()=>{await api(`shares/${s.id}/revoke/`,{});await refresh();})}>{t.revoke}</button>}
        {s.active&&Array.isArray(s.permissions)&&s.permissions.includes('comment')&&<><button type="button" onClick={()=>void run(async()=>{if(openThread===s.id){setOpenThread('');return;}const thread=await api<SecureMessage[]>(`shares/${s.id}/messages/`);setMessageThreads({...messageThreads,[s.id]:thread});setOpenThread(s.id);})}>{t.messages}</button>{openThread===s.id&&<><ul>{(messageThreads[s.id]||[]).map(m=><li key={m.id}><small>{m.sender} · {new Date(m.created_at).toLocaleString(locale)}</small><p>{m.body}</p></li>)}</ul><form onSubmit={form(async d=>{await api(`shares/${s.id}/messages/`,{body:d.body});const thread=await api<SecureMessage[]>(`shares/${s.id}/messages/`);setMessageThreads({...messageThreads,[s.id]:thread});setMessage('');})}><Field label={t.messageText} name="body"/><button>{t.sendMessage}</button></form></>}</>}
      </article>)}{!shares.length&&<p>{t.empty}</p>}</>, 'workspace-shares')}
      {!!notifications.length&&card(t.notifications,<ul>{notifications.slice(0,10).map(n=><li key={n.id}>{n.category} · {new Date(n.created_at).toLocaleString(locale)}</li>)}</ul>, 'workspace-notifications')}
      {user.role==='patient'&&card(t.accessHistory,<>{!accessHistory.length&&<p>{t.noAccess}</p>}<ul>{accessHistory.slice(0,50).map((event,index)=><li key={`${event.at}-${index}`}>{event.action} · {event.actor||'—'} · {new Date(event.at).toLocaleString(locale)}</li>)}</ul><details><summary>{t.consentState}</summary><ul>{consentEvents.map((event,index)=><li key={`${event.created_at}-${index}`}>{event.decision} · v{event.version} · {new Date(event.created_at).toLocaleString(locale)}</li>)}</ul></details></>)}
      {org&&user.role!=='patient'&&card(t.relationship,<form onSubmit={form(async d=>send(`organizations/${org}/patients/${d.patient}/relationships/`,{professional:d.professional,active:d.active==='on'}))}><Field label="Patient ID" name="patient"/><Field label={t.professionalId} name="professional"/><label><input type="checkbox" name="active" defaultChecked/>{t.active}</label><button>{t.save}</button></form>)}
      {user.is_platform_admin&&card(t.admin,<>{!reviews.length&&<p>{t.empty}</p>}{reviewNext&&<button onClick={()=>void run(async()=>{const p=await api<Page<Review>>(nextPath(reviewNext));setReviews([...reviews,...p.results]);setReviewNext(p.next);})}>{t.more}</button>}{reviews.map(r=><article key={r.user}><h3>{r.register} · {r.license_number}</h3><p>{r.user}</p><form onSubmit={form(async d=>{await send(`admin/verifications/${r.user}/`,d);await refresh();})}><Field label={t.reason} name="reason"/><select name="status" aria-label={t.admin}><option value="approved">{t.approve}</option><option value="rejected">{t.reject}</option></select><button>{t.save}</button></form></article>)}</>, 'workspace-reviews')}
      {user.mfa_enabled&&user.mfa_verified&&<details><summary>{t.resetMfa}</summary><form onSubmit={form(async d=>{await send('auth/mfa/reset/',d);await session();setCodes([]);})}><Field label={t.password} name="password" type="password"/><button>{t.confirm}</button></form></details>}
    </>}</>}
    </fieldset><footer><Link href="/demo">{t.demo}</Link></footer>
  </main>;
}
