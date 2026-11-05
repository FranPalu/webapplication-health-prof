'use client';

import Link from 'next/link';
import {useState} from 'react';
import {ThemePicker} from '../PortalTheme';
import {ImagingDemo} from './ImagingDemo';
import {profiles, type Profile} from './profiles';

type Entry = {title: string; status: 'Da seguire' | 'Completato'; detail: string};
const worklists: Record<Exclude<Profile, 'research'>, {title: string; entries: Entry[]}> = {
  patient: {title:'I miei appuntamenti e referti', entries:[
    {title:'Controllo con medicina interna', status:'Da seguire', detail:'12 novembre, ore 09:30 · Centro Clarìa, ambulatorio 2.'},
    {title:'Sintesi TC torace ed ecocardiogramma', status:'Completato', detail:'Il team ha pubblicato le sintesi riviste. La nota eco riporta una vista parziale e nessuna misura pubblicata.'},
  ]},
  physician: {title:'Fascicolo clinico DEMO-042', entries:[
    {title:'Rivalutazione ambulatoriale', status:'Da seguire', detail:'La visita del 12 novembre riunisce il colloquio e il confronto con i referti rivisti.'},
    {title:'Revisione radiologica e cardiologica', status:'Completato', detail:'Il radiologo ha verificato la segnalazione TC. La cardiologa ha registrato un limite di qualità dell’eco. I dettagli sono nel visore.'},
  ]},
  nurse: {title:'Piano del turno e consegne', entries:[
    {title:'12:00 · Consegna al turno del pomeriggio', status:'Da seguire', detail:'Verificare il contatto in agenda e riportare al medico la disponibilità della paziente.'},
    {title:'08:40 · Accoglienza DEMO-042', status:'Completato', detail:'Identità verificata e lista dei farmaci consegnata al team.'},
    {title:'10:15 · Aggiornamento al medico', status:'Completato', detail:'Segnalata la disponibilità dei due esami nel fascicolo.'},
  ]},
  professional: {title:'Documenti e condivisioni di équipe', entries:[
    {title:'Invito alla condivisione', status:'Da seguire', detail:'La richiesta alla seconda struttura attende il consenso della paziente.'},
    {title:'Documento aggiunto al fascicolo', status:'Completato', detail:'La sintesi verificata è stata aggiunta al percorso clinico.'},
  ]},
  organization: {title:'Accettazione e capacità', entries:[
    {title:'Due appuntamenti da confermare', status:'Da seguire', detail:'Contattare gli utenti delle fasce delle 14:00 e delle 15:30. La coda mostra solo informazioni organizzative.'},
    {title:'Copertura del turno del mattino', status:'Completato', detail:'Medicina interna, diagnostica e ambulatorio infermieristico hanno confermato le presenze.'},
  ]},
  platform: {title:'Coda verifiche e audit', entries:[
    {title:'Pratica professionale DEMO-V17', status:'Da seguire', detail:'Verifica manuale dell’iscrizione professionale in attesa.'},
    {title:'Richiesta ricerca DEMO-R08', status:'Da seguire', detail:'Valutare la finalità dichiarata e l’accesso ai soli aggregati.'},
    {title:'Controllo del registro', status:'Completato', detail:'Controllo dimostrativo delle decisioni registrate alle 11:20.'},
  ]},
  pharmacy: {title:'Richieste e ritiri', entries:[
    {title:'Richiesta DEMO-F12', status:'Da seguire', detail:'Verificare la presenza del riferimento di prescrizione prima della conferma.'},
    {title:'Ritiro DEMO-F09', status:'Completato', detail:'Disponibilità confermata. Ritiro al banco con riferimento di prenotazione.'},
  ]},
};

function Worklist({list}: {list: {title: string; entries: Entry[]}}) {
  const [openOnly, setOpenOnly] = useState(false);
  const entries = openOnly ? list.entries.filter(entry => entry.status === 'Da seguire') : list.entries;
  return <section className="identity-card demo-operations" aria-labelledby="demo-worklist-title">
    <h2 id="demo-worklist-title">{list.title}</h2>
    <label className="demo-marker">
      <input type="checkbox" checked={openOnly} onChange={event => setOpenOnly(event.target.checked)}/>
      Solo da seguire
    </label>
    <ul className="demo-worklist">
      {entries.map(entry => <li key={entry.title}>
        <details>
          <summary>{entry.title} <span className="demo-work-status">{entry.status}</span></summary>
          <p>{entry.detail}</p>
        </details>
      </li>)}
    </ul>
  </section>;
}

function ResearchCatalog() {
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
  </section>;
}

export function DemoWorkspace({role}: {role: Profile}) {
  const profile = profiles[role];
  return <main className="identity demo-workspace">
    <a className="workspace-skip" href="#demo-workspace-content">Vai al contenuto</a>
    <header className="demo-workspace-bar">
      <Link href="/demo" className="identity-brand">Clarìa</Link>
      <p>Portale dimostrativo · Dati fittizi</p>
      <ThemePicker/>
    </header>
    <div className="demo-workspace-layout">
      <nav className="demo-workspace-nav" aria-label="Spazi per ruolo">
        {Object.entries(profiles).map(([key, item]) =>
          <Link key={key} href={`/demo/portale/${key}`} aria-current={key === role ? 'page' : undefined}>
            {item.label}
          </Link>)}
      </nav>
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
        {role === 'research' ? <ResearchCatalog/> : <Worklist list={worklists[role]}/>}
        {role === 'physician' && <ImagingDemo/>}
        <footer className="demo-links">
          <Link href="/demo">Torna ai profili demo</Link>
          <Link href="/">Accedi con un account</Link>
        </footer>
      </div>
    </div>
  </main>;
}
