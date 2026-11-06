'use client';

import {useState, type FormEvent} from 'react';
import {api, ApiError} from '../lib/api/client';
import type {components} from '../lib/api/schema';

type Review = components['schemas']['LabReviewOutput'];
type Order = components['schemas']['LabOrderOutput'];
type Page<T = Review> = {results: T[]; next: string | null};

export function LabResultReviews({patient, patientLabel, english}: {
  patient: string; patientLabel: string; english: boolean;
}) {
  const [page, setPage] = useState<Page | null>(null);
  const [orders, setOrders] = useState<Page<Order> | null>(null);
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
      setOrders(null);
      setMessage(error instanceof ApiError && error.status === 404
        ? text('Coda non disponibile.', 'Review queue unavailable.')
        : text('Operazione non riuscita.', 'The request failed.'));
    } finally {
      setBusy(false);
    }
  }

  async function load() {
    const [reviews, pending] = await Promise.all([
      api<Page>(path), api<Page<Order>>('clinical/patients/' + patient + '/lab-orders/'),
    ]);
    setPage(reviews);
    setOrders(pending);
  }

  function acknowledge(review: Review) {
    if (!window.confirm(text('Confermi la presa visione per ', 'Acknowledge this result for ') + patientLabel + '?')) return;
    void run(async () => {
      await api('clinical/result-reviews/' + review.id + '/acknowledge/', {patient});
      await load();
    });
  }

  function complete(event: FormEvent<HTMLFormElement>, review: Review) {
    event.preventDefault();
    const note = new FormData(event.currentTarget).get('note');
    if (!window.confirm(text('Confermi la revisione per ', 'Complete the review for ') + patientLabel + '?')) return;
    void run(async () => {
      await api('clinical/result-reviews/' + review.id + '/complete/', {patient, note});
      await load();
    });
  }

  return <details>
    <summary>{text('Esami e referti in sospeso', 'Pending orders and results')}</summary>
    <p className="clinical-patient-context"><strong>{patientLabel}</strong></p>
    <p>{text('Solo collaudo sintetico. La presa visione non firma il referto.', 'Synthetic testing only. Acknowledgment does not sign the report.')}</p>
    <button disabled={busy} onClick={() => void run(load)}>{text('Aggiorna coda', 'Refresh queue')}</button>
    {message && <p role="status">{message}</p>}
    {orders && <section>
      <h4>{text('Richieste di esame in sospeso', 'Pending laboratory orders')}</h4>
      {!orders.results.length && <p>{text('Nessuna richiesta in sospeso.', 'No pending orders.')}</p>}
      <ul>{orders.results.map(order => <li key={order.id}>
        {order.code} · {order.status === 'awaiting_result'
          ? text('Risultato atteso', 'Awaiting result')
          : text('Revisione attesa', 'Awaiting review')}
        {order.overdue && <strong> · {text('Scaduta', 'Overdue')}</strong>}
        {' · '}{new Date(order.due_at).toLocaleString(english ? 'en' : 'it')}
      </li>)}</ul>
      {orders.next && <button disabled={busy} onClick={() => void run(async () => {
        const next = await api<Page<Order>>('clinical/patients/' + patient + '/lab-orders/' + new URL(orders.next!, window.location.origin).search);
        setOrders({results: [...orders.results, ...next.results], next: next.next});
      })}>{text('Altre richieste', 'More orders')}</button>}
    </section>}
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
      {review.acknowledged_at ? <form onSubmit={event => complete(event, review)}>
        <label>{text('Nota di revisione', 'Review note')}<input name="note" maxLength={500} required/></label>
        <button disabled={busy}>{text('Completa revisione', 'Complete review')}</button>
      </form> : <button disabled={busy} onClick={() => acknowledge(review)}>{text('Registra presa visione', 'Record acknowledgment')}</button>}
    </li>)}</ul>
    {page?.next && <button disabled={busy} onClick={() => void run(async () => {
      const next = await api<Page>(path + new URL(page.next!, window.location.origin).search);
      setPage({results: [...page.results, ...next.results], next: next.next});
    })}>{text('Carica altri', 'Load more')}</button>}
  </details>;
}
