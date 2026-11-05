'use client';

import Link from 'next/link';
import {useState, useSyncExternalStore} from 'react';
import {ThemePicker} from '../PortalTheme';
import {ImagingDemo} from './ImagingDemo';
import {profiles, type Profile} from './profiles';

const actions = {
  appointment: ['Conferma appuntamento', 'Appuntamento confermato'],
  review: ['Registra revisione dimostrativa', 'Revisione registrata'],
  handoff: ['Registra consegna', 'Consegna registrata'],
  share: ['Invia richiesta di condivisione', 'Richiesta inviata'],
  reception: ['Segna contatti effettuati', 'Contatti registrati'],
  verification: ['Concludi verifica dimostrativa', 'Verifica conclusa'],
  researchRequest: ['Richiedi accesso dimostrativo', 'Richiesta di accesso inviata'],
  researchDecision: ['Approva accesso dimostrativo', 'Accesso approvato'],
  pickup: ['Conferma disponibilità per il ritiro', 'Ritiro confermato'],
} as const;

type Action = keyof typeof actions;
type Entry = {
  title: string;
  status: 'Da seguire' | 'Completato';
  detail: string;
  action?: Action;
};

const storageKey = 'claria-demo-workspace-actions-v1';
let memorySnapshot = '';

function subscribe(listener: () => void) {
  window.addEventListener('storage', listener);
  window.addEventListener(storageKey, listener);
  return () => {
    window.removeEventListener('storage', listener);
    window.removeEventListener(storageKey, listener);
  };
}

function getSnapshot() {
  try {
    return window.localStorage.getItem(storageKey) ?? '';
  } catch {
    return memorySnapshot;
  }
}

function saveSnapshot(snapshot: string) {
  memorySnapshot = snapshot;
  try {
    window.localStorage.setItem(storageKey, snapshot);
  } catch {
    // Keep the demo usable when browser storage is unavailable.
  }
  window.dispatchEvent(new Event(storageKey));
}

const worklists: Record<Exclude<Profile, 'research'>, {title: string; entries: Entry[]}> = {
  patient: {title:'I miei appuntamenti e referti', entries:[
    {title:'Controllo con medicina interna', action:'appointment', status:'Da seguire', detail:'12 novembre, ore 09:30 · Centro Clarìa, ambulatorio 2.'},
    {title:'Sintesi TC torace ed ecocardiogramma', status:'Completato', detail:'Il team ha pubblicato le sintesi riviste. La nota eco riporta una vista parziale e nessuna misura pubblicata.'},
  ]},
  physician: {title:'Fascicolo clinico DEMO-042', entries:[
    {title:'Rivalutazione ambulatoriale', action:'review', status:'Da seguire', detail:'La visita del 12 novembre riunisce il colloquio e il confronto con i referti rivisti.'},
    {title:'Revisione radiologica e cardiologica', status:'Completato', detail:'Il radiologo ha verificato la segnalazione TC. La cardiologa ha registrato un limite di qualità dell’eco. I dettagli sono nel visore.'},
  ]},
  nurse: {title:'Piano del turno e consegne', entries:[
    {title:'12:00 · Consegna al turno del pomeriggio', action:'handoff', status:'Da seguire', detail:'Verificare il contatto in agenda e riportare al medico la disponibilità della paziente.'},
    {title:'08:40 · Accoglienza DEMO-042', status:'Completato', detail:'Identità verificata e lista dei farmaci consegnata al team.'},
    {title:'10:15 · Aggiornamento al medico', status:'Completato', detail:'Segnalata la disponibilità dei due esami nel fascicolo.'},
  ]},
  professional: {title:'Documenti e condivisioni di équipe', entries:[
    {title:'Invito alla condivisione', action:'share', status:'Da seguire', detail:'Prepara l’invio alla seconda struttura. Dopo l’invio, la richiesta attende il consenso della paziente.'},
    {title:'Documento aggiunto al fascicolo', status:'Completato', detail:'La sintesi verificata è stata aggiunta al percorso clinico.'},
  ]},
  organization: {title:'Accettazione e capacità', entries:[
    {title:'Due appuntamenti da confermare', action:'reception', status:'Da seguire', detail:'Contattare gli utenti delle fasce delle 14:00 e delle 15:30. La coda mostra solo informazioni organizzative.'},
    {title:'Copertura del turno del mattino', status:'Completato', detail:'Medicina interna, diagnostica e ambulatorio infermieristico hanno confermato le presenze.'},
  ]},
  platform: {title:'Coda verifiche e audit', entries:[
    {title:'Pratica professionale DEMO-V17', action:'verification', status:'Da seguire', detail:'Verifica manuale dell’iscrizione professionale in attesa.'},
    {title:'Richiesta ricerca DEMO-R08', action:'researchDecision', status:'Da seguire', detail:'Valutare la finalità dichiarata e l’accesso ai soli aggregati.'},
    {title:'Controllo del registro', status:'Completato', detail:'Controllo dimostrativo delle decisioni registrate alle 11:20.'},
  ]},
  pharmacy: {title:'Richieste e ritiri', entries:[
    {title:'Richiesta DEMO-F12', action:'pickup', status:'Da seguire', detail:'Il riferimento di prescrizione fittizio è già verificato nello scenario. Puoi confermare la disponibilità al banco.'},
    {title:'Ritiro DEMO-F09', status:'Completato', detail:'Disponibilità confermata. Ritiro al banco con riferimento di prenotazione.'},
  ]},
};

function Worklist({list, completed, complete}: {
  list: {title: string; entries: Entry[]};
  completed: string[];
  complete: (action: Action) => void;
}) {
  const [openOnly, setOpenOnly] = useState(false);
  const entries = list.entries.filter(entry => {
    if (entry.action === 'researchDecision' && !completed.includes('researchRequest')) return false;
    return !openOnly || (entry.status === 'Da seguire' && !completed.includes(entry.action ?? ''));
  });
  return <section className="identity-card demo-operations" aria-labelledby="demo-worklist-title">
    <h2 id="demo-worklist-title">{list.title}</h2>
    <label className="demo-marker">
      <input type="checkbox" checked={openOnly} onChange={event => setOpenOnly(event.target.checked)}/>
      Solo da seguire
    </label>
    <ul className="demo-worklist">
      {entries.map(({title, detail, status, action}) => {
        const done = action && completed.includes(action);
        return <li key={title}>
          <details>
            <summary>{title} <span className="demo-work-status">{done ? actions[action][1] : status}</span></summary>
            <p>{detail}</p>
          </details>
          {action && !done && <button type="button" onClick={() => complete(action)}>{actions[action][0]}</button>}
        </li>;
      })}
    </ul>
    {entries.length === 0 && <p>Nessuna attività da seguire.</p>}
  </section>;
}

function ResearchCatalog({completed, complete}: {completed: string[]; complete: (action: Action) => void}) {
  const requested = completed.includes('researchRequest');
  const approved = requested && completed.includes('researchDecision');
  return <section className="identity-card demo-operations" aria-labelledby="demo-research-title">
    <h2 id="demo-research-title">Catalogo di ricerca aggregato</h2>
    <p>Le celle sotto la soglia di 10 account sono soppresse.</p>
    <table className="demo-catalog">
      <caption>Osservazioni sintetiche per anno e codice</caption>
      <thead><tr><th scope="col">Anno</th><th scope="col">LOINC</th><th scope="col">Account distinti</th></tr></thead>
      <tbody>
        <tr><td>2025</td><td>718-7</td><td>28</td></tr>
        <tr><td>2024</td><td>718-7</td><td>Soppressa</td></tr>
      </tbody>
    </table>
    <div className="demo-research-action">
      {requested
        ? <p>{approved ? 'Accesso approvato dall’amministrazione di piattaforma.' : 'Richiesta in attesa di approvazione dall’amministrazione di piattaforma.'}</p>
        : <button type="button" onClick={() => complete('researchRequest')}>{actions.researchRequest[0]}</button>}
    </div>
  </section>;
}

export function DemoWorkspace({role}: {role: Profile}) {
  const profile = profiles[role];
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, () => '');
  const completed = snapshot.split(',');
  const [message, setMessage] = useState('');

  function complete(action: Action) {
    const current = getSnapshot().split(',').filter(Boolean);
    if (current.includes(action)) return;
    if (action === 'researchDecision' && !current.includes('researchRequest')) return;
    saveSnapshot([...current, action].join(','));
    setMessage(actions[action][1]);
  }
  return <main className="identity demo-workspace">
    <a className="workspace-skip" href="#demo-workspace-content">Vai al contenuto</a>
    <header className="demo-workspace-bar">
      <Link href="/demo" className="identity-brand">Clarìa</Link>
      <p>Portale dimostrativo · Operazioni salvate in questo browser</p>
      <ThemePicker/>
    </header>
    <div id="demo-workspace-content" tabIndex={-1} className="demo-workspace-content">
      <header className="identity-hero">
        <div>
          <p className="workspace-kicker">{profile.label}</p>
          <h1>{profile.title}</h1>
          <p>{profile.intro}</p>
        </div>
      </header>
      <div className="demo-workspace-summary" aria-label="Riepilogo">
        {profile.cards.map(([label, value]) => <div key={label}><p>{label}</p><strong>{value}</strong></div>)}
      </div>
      <p role="status">{message}</p>
      {role === 'research'
        ? <ResearchCatalog completed={completed} complete={complete}/>
        : <Worklist list={worklists[role]} completed={completed} complete={complete}/>}
      {role === 'physician' && <ImagingDemo/>}
      <footer className="demo-links">
        <Link href="/demo">Torna ai profili demo</Link>
        <Link href="/">Accedi con un account</Link>
        {snapshot && <button type="button" onClick={() => {
          saveSnapshot('');
          setMessage('Operazioni della demo azzerate.');
        }}>Azzera la demo</button>}
      </footer>
    </div>
  </main>;
}
