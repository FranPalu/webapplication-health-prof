'use client';

import {useState, type FormEvent} from 'react';
import {api} from '../lib/api/client';
import type {components} from '../lib/api/schema';

type Job = components['schemas']['JobOutput'];
type Evidence = {
  id: string; page: number; line: number; source: string; flag: string;
  analyte?: string; value?: string; operator?: string; unit?: string; low?: string; high?: string;
};
type JobDetail = Job & {
  draft?: {rows: Evidence[]};
  suggestion?: string;
  disclaimer?: string;
  decision?: string;
  opinion?: {id: string; published: boolean};
};
type Page<T> = {results: T[]; next: string | null};

function useAction(english: boolean) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError('');
    try { await action(); }
    catch { setError(english ? 'Action unavailable or access changed.' : 'Operazione non disponibile o accesso modificato.'); }
    finally { setBusy(false); }
  }
  return {busy, error, run};
}

export function ClinicalAnalysis({version, english}: {version: string; english: boolean}) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [decision, setDecision] = useState('modify');
  const [text, setText] = useState('');
  const [loaded, setLoaded] = useState(false);
  const {busy, error, run} = useAction(english);
  const t = (it: string, en: string) => english ? en : it;
  const versionPath = 'clinical/versions/' + version + '/analysis/';
  const jobPath = (id: string) => 'clinical/analysis/' + id + '/';
  const states: Record<string, string> = {
    queued: t('In coda', 'Queued'), running: t('In elaborazione', 'Running'),
    ready: t('Pronta per la revisione', 'Ready for review'),
    failed: t('Elaborazione non riuscita', 'Analysis failed'),
    cancelled: t('Annullata', 'Cancelled'),
  };
  const flags: Record<string, string> = {
    below: t('Sotto intervallo', 'Below range'), above: t('Sopra intervallo', 'Above range'),
    within: t('Nell’intervallo', 'Within range'), ambiguous: t('Da verificare', 'Check required'),
    missing_range: t('Intervallo assente', 'Range missing'),
    unit_mismatch: t('Unità da verificare', 'Check unit'),
    unrecognized: t('Riga non riconosciuta', 'Unrecognized row'),
  };
  async function read(id: string) {
    setJob(await api<JobDetail>(jobPath(id)));
    setLoaded(true);
  }
  async function refresh() {
    const page = await api<Page<Job>>(versionPath);
    if (page.results[0]) await read(page.results[0].id);
    else setLoaded(true);
  }
  function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!job) return;
    const fields = new FormData(event.currentTarget);
    void run(async () => {
      await api(jobPath(job.id) + 'review/', {
        decision, text: decision === 'accept' ? job.suggestion : text,
        confirmed: fields.has('confirmed'),
      });
      setText('');
      await read(job.id);
    });
  }
  return <details onToggle={event => {
    if (event.currentTarget.open && !loaded && !busy) void run(refresh);
  }}>
    <summary>{t('Analisi preliminare', 'Preliminary analysis')}</summary>
    {error && <p role="alert">{error}</p>}
    <button type="button" disabled={busy} onClick={() => void run(refresh)}>{t('Aggiorna analisi', 'Refresh analysis')}</button>
    {loaded && !job && <button type="button" disabled={busy} onClick={() => void run(async () => {
      const created = await api<Job>(versionPath, {});
      await read(created.id);
    })}>{t('Avvia analisi del referto', 'Analyze report')}</button>}
    {job && <p role="status">{states[job.state ?? ''] ?? job.state}</p>}
    {job?.draft && <>
      <p><strong>{job.disclaimer}</strong></p>
      {job.draft.rows.length === 0 && <p>{t('Nessuna riga riconosciuta. Verifica il documento originale.', 'No rows recognized. Check the original document.')}</p>}
      <ul>{job.draft.rows.map(row => <li key={row.id}>
        {t('Pagina', 'Page')} {row.page}, {t('riga', 'line')} {row.line} · {row.source === 'ocr' ? 'OCR' : t('Testo PDF', 'PDF text')} · {row.analyte}
        {' '}{row.operator}{row.value} {row.unit}
        {row.low != null && (' · ' + row.low + '–' + row.high)}
        {' · '}{flags[row.flag] ?? row.flag}
      </li>)}</ul>
      {job.suggestion ? <p style={{whiteSpace:'pre-line'}}>{job.suggestion}</p>
        : <p>{t('Riepilogo non disponibile.', 'Summary unavailable.')}</p>}
      {!job.decision && <form onSubmit={review}>
        <label>{t('Decisione', 'Decision')}<select value={decision} onChange={event => setDecision(event.target.value)}>
          {job.suggestion && <option value="accept">{t('Accetta', 'Accept')}</option>}
          <option value="modify">{t('Modifica', 'Modify')}</option>
          <option value="reject">{t('Rifiuta', 'Reject')}</option>
        </select></label>
        {decision !== 'accept' && <label>{decision === 'reject' ? t('Motivazione', 'Reason') : t('Parere finale', 'Final opinion')}
          <textarea required maxLength={8000} value={text} onChange={event => setText(event.target.value)}/></label>}
        {decision !== 'reject' && <label><input type="checkbox" name="confirmed" required/>
          {t('Ho verificato il referto e attesto il testo finale', 'I verified the report and attest the final text')}
        </label>}
        <button disabled={busy}>{t('Registra revisione', 'Save review')}</button>
      </form>}
    </>}
    {job?.decision && <p>{t('Revisione registrata', 'Review saved')}</p>}
    {job?.opinion?.published && <p>{t('Parere pubblicato', 'Opinion published')}</p>}
    {job?.opinion && !job.opinion.published && <button disabled={busy} onClick={() => {
      if (!window.confirm(t('Pubblicare il parere attestato al paziente?', 'Publish the attested opinion to the patient?'))) return;
      void run(async () => {await api('clinical/opinions/' + job.opinion!.id + '/publish/', {}); await read(job.id);});
    }}>{t('Pubblica il parere al paziente', 'Publish opinion to patient')}</button>}
  </details>;
}

export function PublishedOpinions({patient, english}: {patient: string; english: boolean}) {
  type Opinion = {id: string; text: string; created_at: string};
  const [page, setPage] = useState<Page<Opinion> | null>(null);
  const {busy, error, run} = useAction(english);
  const path = 'clinical/patients/' + patient + '/opinions/';
  return <details onToggle={event => {
    if (event.currentTarget.open) void run(async () => setPage(await api<Page<Opinion>>(path)));
  }}>
    <summary>{english ? 'Published professional opinions' : 'Pareri professionali pubblicati'}</summary>
    {error && <p role="alert">{error}</p>}
    {page?.results.length === 0 && <p>{english ? 'No published opinions.' : 'Nessun parere pubblicato.'}</p>}
    {page?.results.map(opinion => <article key={opinion.id}>
      <time dateTime={opinion.created_at}>{new Date(opinion.created_at).toLocaleString(english ? 'en' : 'it')}</time>
      <p style={{whiteSpace:'pre-line'}}>{opinion.text}</p>
    </article>)}
    {page?.next && <button disabled={busy} onClick={() => void run(async () => {
      const next = await api<Page<Opinion>>(path + new URL(page.next!, window.location.origin).search);
      setPage({results: [...page.results, ...next.results], next: next.next});
    })}>{english ? 'Load more' : 'Carica altri'}</button>}
  </details>;
}

type Metric = {
  job__pipeline: string; job__draft__model__name: string | null;
  job__draft__model__revision: string | null; job__draft__model__checksum: string | null;
  total: number; modify_rate: number; reject_rate: number;
};

export function AnalysisMetrics({organization, english}: {organization: string; english: boolean}) {
  const [metrics, setMetrics] = useState<Metric[] | null>(null);
  const {error, run} = useAction(english);
  return <details onToggle={event => {
    if (event.currentTarget.open) void run(async () => setMetrics(
      await api<Metric[]>('organizations/' + organization + '/analysis/metrics/'),
    ));
  }}>
    <summary>{english ? 'Analysis review metrics' : 'Metriche di revisione delle analisi'}</summary>
    {error && <p role="alert">{error}</p>}
    {metrics?.map(row => <p key={[row.job__pipeline, row.job__draft__model__checksum].join(':')}>
      {row.job__draft__model__name ?? row.job__pipeline} {row.job__draft__model__revision}
      {' · '}{row.total} {english ? 'reviews' : 'revisioni'}
      {' · '}{english ? 'Modified' : 'Modificate'} {(row.modify_rate * 100).toFixed(1)}%
      {' · '}{english ? 'Rejected' : 'Rifiutate'} {(row.reject_rate * 100).toFixed(1)}%
    </p>)}
  </details>;
}
