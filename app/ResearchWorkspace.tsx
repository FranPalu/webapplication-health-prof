'use client';

import {useState, type FormEvent} from 'react';
import {api} from '../lib/api/client';
import type {components} from '../lib/api/schema';

type Access = components['schemas']['AccessOutput'];
type Cell = {year: number; code: string; accounts: number};
type Format = 'csv' | 'parquet' | 'fhir';

export function ResearchWorkspace({organization, review, english}: {
  organization?: string; review?: boolean; english: boolean;
}) {
  const [requests, setRequests] = useState<Access[]>([]);
  const [cells, setCells] = useState<Cell[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const t = (it: string, en: string) => english ? en : it;
  const statuses: Record<string, string> = {
    pending: t('In attesa', 'Pending'),
    approved: t('Approvata', 'Approved'),
    rejected: t('Rifiutata', 'Rejected'),
    revoked: t('Revocata', 'Revoked'),
  };
  const path = review ? 'research/admin/requests/' : 'organizations/' + organization + '/research/requests/';
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage('');
    try {await action();}
    catch {setMessage(t('Operazione non disponibile. Verifica permessi e validità dello snapshot.', 'Action unavailable. Check permissions and snapshot validity.'));}
    finally {setBusy(false);}
  }
  async function load() {
    setRequests((await api<{results: Access[]}>(path)).results);
  }
  function requestAccess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const purpose = new FormData(form).get('purpose');
    void run(async () => {await api(path, {purpose}); form.reset(); await load();});
  }
  async function download(id: string, format: Format) {
    const csrf = document.cookie.split('; ').find(cookie => cookie.startsWith('csrftoken='))?.slice(10) ?? '';
    const response = await fetch('/api/v1/research/requests/' + id + '/export/', {
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json', 'X-CSRFToken':decodeURIComponent(csrf)},
      body:JSON.stringify({format_name:format}),
    });
    if (!response.ok) throw new Error('Export unavailable');
    const href = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = href;
    link.download = 'claria-research.' + (format === 'fhir' ? 'json' : format);
    link.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  }
  return <details>
    <summary>{review ? t('Approvazioni ricerca', 'Research approvals') : t('Archivio di ricerca', 'Research archive')}</summary>
    <p>{t('Conteggi aggregati per anno e codice di laboratorio. Soglia minima di dieci account distinti.', 'Aggregate counts by year and laboratory code. Minimum of ten distinct accounts.')}</p>
    {message && <p role="alert">{message}</p>}
    <fieldset disabled={busy}>
      <button type="button" onClick={() => void run(load)}>{t('Aggiorna richieste', 'Refresh requests')}</button>
      {!review && <form onSubmit={requestAccess}>
        <label>{t('Finalità della ricerca', 'Research purpose')}<textarea name="purpose" required maxLength={500}/></label>
        <button>{t('Richiedi accesso', 'Request access')}</button>
      </form>}
      <ul>{requests.map(row => <li key={row.id}>
        <p>{row.purpose} · {statuses[row.status ?? ''] ?? row.status}</p>
        {review && <p>{row.organization}</p>}
        {review && (row.status === 'pending' || row.status === 'approved') &&
          (row.status === 'pending' ? (['approve', 'reject'] as const) : (['revoke'] as const)).map(decision =>
            <button key={decision} type="button" onClick={() => void run(async () => {
              await api(path + row.id + '/decision/', {decision});
              await load();
            })}>{({approve:t('Approva', 'Approve'), reject:t('Rifiuta', 'Reject'), revoke:t('Revoca', 'Revoke')})[decision]}</button>)}
        {!review && row.status === 'approved' && <>
          <button type="button" onClick={() => void run(async () => {
            setCells((await api<{cells: Cell[]}>('research/requests/' + row.id + '/export/', {format_name:'dashboard'})).cells);
          })}>{t('Mostra aggregati', 'Show aggregates')}</button>
          {(['csv', 'parquet', 'fhir'] as const).map(format => <button key={format} type="button"
            onClick={() => void run(() => download(row.id, format))}>{format.toUpperCase()}</button>)}
        </>}
      </li>)}</ul>
    </fieldset>
    {!!cells.length && <table>
      <caption>{t('Ultimo snapshot consultato', 'Last snapshot viewed')}</caption>
      <thead><tr><th>{t('Anno', 'Year')}</th><th>LOINC</th><th>{t('Account distinti', 'Distinct accounts')}</th></tr></thead>
      <tbody>{cells.map(row => <tr key={row.year + ':' + row.code}><td>{row.year}</td><td>{row.code}</td><td>{row.accounts}</td></tr>)}</tbody>
    </table>}
  </details>;
}
