'use client';

import {useState, type FormEvent} from 'react';
import {api} from '../lib/api/client';
import type {components} from '../lib/api/schema';

type Screening = components['schemas']['MedicationSafetyOutput'];
type Medication = {id: number; code: string; route: string; unit: string; daily_dose: string};
const emptyRow = (id: number): Medication => ({id, code:'', route:'', unit:'', daily_dose:''});
const codes = (value: FormDataEntryValue | null) => String(value ?? '').split(/\s+/).filter(Boolean);

export function MedicationSafetyPanel({patient, patientLabel, english}: {
  patient: string; patientLabel: string; english: boolean;
}) {
  const [medications, setMedications] = useState([emptyRow(0)]);
  const [nextId, setNextId] = useState(1);
  const [result, setResult] = useState<Screening | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [overridden, setOverridden] = useState(false);
  const text = (it: string, en: string) => english ? en : it;

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage('');
    try { await action(); }
    catch { setMessage(text('Screening non disponibile o dati non validi.', 'Screening unavailable or invalid data.')); }
    finally { setBusy(false); }
  }

  function screen(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setResult(null);
    setOverridden(false);
    void run(async () => {
      const response = await api<Screening>('clinical/patients/' + patient + '/medication-checks/', {
        identifier_kind: data.get('identifier_kind'), identifier_value: data.get('identifier_value'),
        source_birth_date: data.get('source_birth_date'), context_confirmed: data.has('context'),
        medications: medications.map(({code, route, unit, daily_dose}) => ({code, route, unit, daily_dose})),
        allergies: codes(data.get('allergies')), conditions: codes(data.get('conditions')),
      });
      setResult(response);
    });
  }

  function override(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!result || !window.confirm(text('Confermi la registrazione per ', 'Confirm recording for ') + patientLabel + '?')) return;
    const reason = new FormData(event.currentTarget).get('reason');
    void run(async () => {
      await api('clinical/medication-checks/' + result.id + '/override/', {patient, reason});
      setOverridden(true);
    });
  }

  return <details>
    <summary>{text('Screening farmacologico sintetico', 'Synthetic medication screening')}</summary>
    <p className="clinical-patient-context"><strong>{patientLabel}</strong></p>
    <p>{text('Solo collaudo. Inserire esclusivamente codici sintetici.', 'Testing only. Enter synthetic codes only.')}</p>
    <form onSubmit={screen} onChange={() => {setResult(null); setOverridden(false);}}>
      <fieldset disabled={busy}>
        <label>{text('Tipo identificativo per screening', 'Screening identifier type')}<select name="identifier_kind">
          <option value="facility">{text('Identificativo di struttura', 'Facility identifier')}</option>
          <option value="tax_code">{text('Codice fiscale', 'Italian tax code')}</option>
          <option value="health_card">{text('Numero tessera sanitaria', 'Health card number')}</option>
        </select></label>
        <label>{text('Identificativo per screening', 'Screening identifier')}<input name="identifier_value" maxLength={64} autoComplete="off" required/></label>
        <label>{text('Data di nascita per screening', 'Screening date of birth')}<input name="source_birth_date" type="date" required/></label>
        {medications.map((item, index) => <fieldset key={item.id}>
          <legend>{text('Medicinale', 'Medication')} {index + 1}</legend>
          {([
            ['code', text('Codice', 'Code'), 64],
            ['route', text('Via', 'Route'), 32],
            ['unit', text('Unità', 'Unit'), 32],
            ['daily_dose', text('Dose giornaliera', 'Daily dose'), 20],
          ] as const).map(([field, label, length]) =>
            <label key={field}>{label}<input maxLength={length} value={item[field]} required
              onChange={event => setMedications(medications.map(row => row.id === item.id ? {...row, [field]:event.target.value} : row))}/></label>
          )}
          {medications.length > 1 && <button type="button" disabled={busy}
            onClick={() => setMedications(medications.filter(row => row.id !== item.id))}>{text('Rimuovi medicinale', 'Remove medication')}</button>}
        </fieldset>)}
        <button type="button" disabled={busy || medications.length >= 20} onClick={() => {
          setMedications([...medications, emptyRow(nextId)]);
          setNextId(nextId + 1);
        }}>{text('Aggiungi medicinale', 'Add medication')}</button>
        <label>{text('Codici allergeni separati da spazi', 'Space-separated allergen codes')}<input name="allergies" maxLength={3250}/></label>
        <label>{text('Codici condizioni separati da spazi', 'Space-separated condition codes')}<input name="conditions" maxLength={3250}/></label>
        <label><input type="checkbox" name="context"/>{text('Confermo la completezza del contesto', 'I confirm the context is complete')}</label>
        <button disabled={busy}>{text('Esegui screening', 'Run screening')}</button>
      </fieldset>
    </form>
    {message && <p role="status">{message}</p>}
    {result && <section aria-label={text('Esito screening', 'Screening result')}>
      <p role="status">{result.result.status === 'no_findings' ? text('Nessuna segnalazione nella fonte consultata', 'No findings in the source consulted')
        : result.result.status === 'findings' ? text('Segnalazioni da valutare', 'Findings require review')
        : text('Dato insufficiente', 'Insufficient data')}</p>
      {result.result.source && <p>{result.result.source.name} · {result.result.source.version} · {result.result.source.license}
        {' · '}{result.result.source.reference} · {result.result.source.evidence_level}</p>}
      <ul>{result.result.findings.map((finding, index) => <li key={index}>
        {finding.kind} · {finding.medications.join(', ')} · {finding.reference} · {finding.evidence_level}
      </li>)}</ul>
      {result.result.status === 'findings' && (overridden ? <p role="status">{text('Motivazione registrata.', 'Reason recorded.')}</p>
        : <form onSubmit={override}>
          <label>{text('Motivazione override', 'Override reason')}<input name="reason" maxLength={500} required/></label>
          <button disabled={busy}>{text('Registra override', 'Record override')}</button>
        </form>)}
    </section>}
  </details>;
}
