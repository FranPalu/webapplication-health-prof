'use client';

import Link from 'next/link';
import { useState } from 'react';
import { ThemePicker } from '../PortalTheme';

const profiles = {
  patient: {
    label: 'Paziente',
    title: 'Il mio percorso di cura',
    intro: 'Un posto per ritrovare chi ti segue e gestire i tuoi consensi.',
    cards: [
      ['Équipe di cura', 'Centro Salute Aurora', 'Struttura dimostrativa collegata al tuo profilo.'],
      ['Condivisioni', '1 richiesta in attesa', 'Una richiesta può essere autorizzata o revocata dal paziente.'],
      ['Storico accessi', 'Ultimo accesso ieri', 'Consulta gli accessi registrati alla tua anagrafica.'],
    ],
  },
  professional: {
    label: 'Professionista',
    title: 'La mia attività clinica',
    intro: 'Anagrafiche autorizzate, richieste di condivisione e comunicazioni.',
    cards: [
      ['Anagrafiche', '3 pazienti sintetici', 'L’accesso dipende dal rapporto di cura e dai permessi.'],
      ['Condivisioni', '2 attive', 'Le richieste nuove restano in attesa del consenso.'],
      ['Identità professionale', 'Verifica completata', 'Il profilo ha completato la verifica e usa il TOTP.'],
    ],
  },
  organization: {
    label: 'Amministrazione struttura',
    title: 'La mia organizzazione',
    intro: 'Gestisci i ruoli e le appartenenze della struttura.',
    cards: [
      ['Organizzazione', 'Centro Salute Aurora', 'Esempio di organizzazione sanitaria.'],
      ['Team', '8 membri', 'Amministratori e professionisti con ruoli distinti.'],
      ['Accesso di emergenza', 'Disattivato', 'La struttura parte con il break-glass disabilitato.'],
    ],
  },
  platform: {
    label: 'Amministrazione piattaforma',
    title: 'Verifiche della piattaforma',
    intro: 'Esamina le richieste dei professionisti.',
    cards: [
      ['Coda di verifica', '2 richieste in esame', 'Controllo manuale delle dichiarazioni professionali.'],
      ['Esiti', '3 approvazioni di esempio', 'Gli esiti sono registrati nella cronologia di audit.'],
    ],
  },
  research: {
    label: 'Ricercatore',
    title: 'Spazio ricerca',
    intro: 'Anteprima del profilo di ricerca.',
    cards: [
      ['Profilo', 'Ricercatore dimostrativo', 'Esempio di account con ruolo ricerca.'],
      ['Dataset', 'Archivio previsto in M7', 'I dataset e le esportazioni saranno disponibili nella fase ricerca.'],
    ],
  },
} as const;

type Profile = keyof typeof profiles;

export default function DemoProfiles() {
  const [role, setRole] = useState<Profile>('patient');
  const profile = profiles[role];

  return (
    <main className="identity">
      <header className="identity-hero">
        <div>
          <p className="identity-brand"><span aria-hidden="true">✚</span> Health Collaboration</p>
          <h1>Esplora il portale</h1>
          <p>Scegli una prospettiva e scopri come cambia lo spazio di lavoro.</p>
        </div>
        <div className="identity-controls"><ThemePicker /></div>
      </header>
      <p className="identity-notice">Anteprima illustrativa con dati fittizi. Per provare le operazioni usa il portale con un account di test.</p>
      <label className="demo-picker">
        Profilo dimostrativo
        <select value={role} onChange={event => setRole(event.target.value as Profile)}>
          {Object.entries(profiles).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}
        </select>
      </label>
      <section aria-live="polite" className="demo-profile">
        <h2>{profile.title}</h2>
        <p>{profile.intro}</p>
        <div className="identity-body">
          {profile.cards.map(([label, value, detail]) => (
            <article key={label} className="identity-card demo-stat">
              <h3>{label}</h3>
              <strong>{value}</strong>
              <p>{detail}</p>
            </article>
          ))}
        </div>
      </section>
      <footer className="demo-links">
        <Link href="/">Vai al portale</Link>
        <Link href="/demo/agenda">Apri la demo di agenda e gestionale</Link>
      </footer>
    </main>
  );
}
