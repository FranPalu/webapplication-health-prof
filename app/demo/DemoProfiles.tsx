'use client';

import Link from 'next/link';
import { useState } from 'react';
import { ThemePicker } from '../PortalTheme';
import { ImagingDemo } from './ImagingDemo';

import { profiles, type Profile } from './profiles';

export default function DemoProfiles() {
  const [role, setRole] = useState<Profile>('patient');
  const profile = profiles[role];

  return (
    <main className="identity">
      <header className="identity-hero">
        <div>
          <p className="identity-brand"><span aria-hidden="true">✚</span> Clarìa</p>
          <h1>Esplora il portale</h1>
          <p>Segui il caso DEMO-042 attraverso i ruoli del centro e scopri come cambia lo spazio di lavoro.</p>
        </div>
        <div className="identity-controls"><ThemePicker /></div>
      </header>
      <p className="identity-notice">Persone, eventi ed esami sono fittizi. Scegli «Medico» per confrontare le bozze simulate di TC ed eco con la revisione clinica.</p>
      <label className="demo-picker">
        Profilo dimostrativo
        <select value={role} onChange={event => setRole(event.target.value as Profile)}>
          {Object.entries(profiles).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}
        </select>
      </label>
      <section className="demo-profile">
        <h2 aria-live="polite">{profile.title}</h2>
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
        {role === 'physician' && <ImagingDemo />}
      </section>
      <footer className="demo-links">
        <Link className="demo-open-workspace" href={`/demo/portale/${role}`}>Apri il portale · {profile.label}</Link>
        <Link href="/">Accedi con un account</Link>
        <Link href="/demo/agenda">Apri la demo di agenda e gestionale</Link>
      </footer>
    </main>
  );
}
