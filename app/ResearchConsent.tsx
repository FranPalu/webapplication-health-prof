'use client';

import {useState} from 'react';
import {api} from '../lib/api/client';
import type {components} from '../lib/api/schema';

type Consent = components['schemas']['ResearchConsentOutput'];

export function ResearchConsent({patient, english}: {patient: string; english: boolean}) {
  const [consent, setConsent] = useState<Consent | null>(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const path = 'patients/' + patient + '/research-consent/';
  const t = (it: string, en: string) => english ? en : it;
  async function update(granted?: boolean) {
    setBusy(true);
    setError(false);
    try {
      setConsent(await api<Consent>(path, granted == null ? undefined : {granted, version: consent?.version}));
    } catch {setError(true);}
    finally {setBusy(false);}
  }
  return <details onToggle={event => {if (event.currentTarget.open && !busy) void update();}}>
    <summary>{t('Consenso alla ricerca', 'Research consent')}</summary>
    {error && <p role="alert">{t('Operazione non riuscita.', 'Action failed.')}</p>}
    {consent && <>
      <p>{consent.text}</p>
      <p role="status">{consent.granted ? t('Consenso attivo', 'Consent active') : t('Consenso assente', 'No consent')}</p>
      <button type="button" disabled={busy} onClick={() => void update(!consent.granted)}>
        {consent.granted ? t('Revoca consenso ricerca', 'Withdraw research consent') : t('Acconsento alla ricerca', 'Grant research consent')}
      </button>
    </>}
  </details>;
}
