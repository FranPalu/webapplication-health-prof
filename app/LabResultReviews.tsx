'use client';

import {useState} from 'react';
import {api, ApiError} from '../lib/api/client';
import type {components} from '../lib/api/schema';

type Review = components['schemas']['LabReviewOutput'];
type Page = {results: Review[]; next: string | null};

export function LabResultReviews({patient, patientLabel, english}: {
  patient: string; patientLabel: string; english: boolean;
}) {
  const [page, setPage] = useState<Page | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const path = 'clinical/patients/' + patient + '/result-reviews/';
  const text = (it: string, en: string) => english ? en : it;

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage('');
    try {
      await action();
    } catch (error) {
      setPage(null);
      setMessage(error instanceof ApiError && error.status === 404
        ? text('Coda non disponibile.', 'Review queue unavailable.')
        : text('Operazione non riuscita.', 'The request failed.'));
    } finally {
      setBusy(false);
    }
  }

  async function load() {
    setPage(await api<Page>(path));
  }

  function acknowledge(review: Review) {
    if (!window.confirm(text('Confermi la presa visione per ', 'Acknowledge this result for ') + patientLabel + '?')) return;
    void run(async () => {
      await api('clinical/result-reviews/' + review.id + '/acknowledge/', {patient});
      await load();
    });
  }

  return <details>
    <summary>{text('Referti da prendere in visione', 'Results awaiting acknowledgment')}</summary>
    <p><strong>{patientLabel}</strong></p>
    <p>{text('Solo collaudo sintetico. La presa visione non firma il referto.', 'Synthetic testing only. Acknowledgment does not sign the report.')}</p>
    <button disabled={busy} onClick={() => void run(load)}>{text('Aggiorna coda', 'Refresh queue')}</button>
    {message && <p role="status">{message}</p>}
    {page && !page.results.length && <p>{text('Nessun referto in coda.', 'No results in the queue.')}</p>}
    <ul>{page?.results.map(review => <li key={review.id}>
      <strong>{review.outcome === 'critical' ? text('Limite critico configurato raggiunto', 'Configured critical limit reached')
        : review.outcome === 'within_limits' ? text('Entro i limiti configurati', 'Within configured limits')
        : text('Dato insufficiente', 'Insufficient data')}</strong>
      {review.due_at && <p>{text('Scadenza di presa visione', 'Acknowledgment deadline')} {new Date(review.due_at).toLocaleString(english ? 'en' : 'it')}</p>}
      {review.escalation_assigned === false && <p>{text('Escalation senza destinatario. Verifica manuale richiesta.', 'Escalation has no recipient. Manual follow-up required.')}</p>}
      <a href={'/api/v1/fhir/DiagnosticReport/' + review.report + '/_history/' + review.version}>
        {text('Apri versione del referto', 'Open report version')} {review.version}
      </a>{' '}
      <button disabled={busy} onClick={() => acknowledge(review)}>{text('Registra presa visione', 'Record acknowledgment')}</button>
    </li>)}</ul>
    {page?.next && <button disabled={busy} onClick={() => void run(async () => {
      const next = await api<Page>(path + new URL(page.next!, window.location.origin).search);
      setPage({results: [...page.results, ...next.results], next: next.next});
    })}>{text('Carica altri', 'Load more')}</button>}
  </details>;
}
