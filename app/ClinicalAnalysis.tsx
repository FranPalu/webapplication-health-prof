'use client';

import {useEffect, useState, type FormEvent} from 'react';
import {api} from '../lib/api/client';
import type {components} from '../lib/api/schema';

type Job = components['schemas']['JobOutput'];
type Evidence = {
  id: string; page: number; line: number; source: string; flag: string;
  source_text?: string; bbox?: number[] | null; coordinate_system?: string;
  confidence?: number | null; requires_confirmation?: boolean; loinc?: string | null; ucum?: string | null;
  analyte?: string; value?: string; operator?: string; unit?: string; low?: string; high?: string;
};
type JobDetail = Job & {
  draft?: {rows: Evidence[]; notices?: string[]};
  suggestion?: string;
  disclaimer?: string;
  decision?: string;
  opinion?: {id: string; published: boolean; signed: boolean; digest: string; signing_content: string};
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

export function ClinicalAnalysis({version, english, organization}: {version: string; english: boolean; organization?: string}) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [decision, setDecision] = useState('modify');
  const [text, setText] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [incidentSaved, setIncidentSaved] = useState(false);
  const [registry, setRegistry] = useState<{manifest_hash: string; enabled: boolean; manifest: unknown} | null>(null);
  const [source, setSource] = useState<{url: string; pdf: boolean} | null>(null);
  useEffect(() => () => {if (source) URL.revokeObjectURL(source.url);}, [source]);
  const {busy, error, run} = useAction(english);
  const t = (it: string, en: string) => english ? en : it;
  const versionPath = 'clinical/versions/' + version + '/analysis/';
  const jobPath = (id: string) => 'clinical/analysis/' + id + '/';
  const states: Record<string, string> = {
    queued: t('In coda', 'Queued'), running: t('In elaborazione', 'Running'),
    ready: t('Pronta per la revisione', 'Ready for review'),
    in_review: t('In revisione', 'In review'), accepted: t('Accettata', 'Accepted'),
    modified: t('Modificata', 'Modified'), rejected: t('Rifiutata', 'Rejected'),
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
    const detail = await api<JobDetail>(jobPath(id));
    if (detail.draft && detail.state === 'ready' && !detail.decision) {
      const started = await api<Job>(jobPath(id) + 'review-start/', {});
      setJob({...detail, ...started});
    } else setJob(detail);
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
        confirmed: fields.has('confirmed'), source_checked: fields.has('source_checked'),
        confirmed_rows: fields.getAll('confirmed_rows'),
      });
      setText('');
      await read(job.id);
    });
  }
  async function openSource() {
    const response = await fetch('/api/v1/clinical/versions/' + version + '/download/', {credentials:'same-origin'});
    if (!response.ok) throw new Error('Source unavailable');
    const bytes = await response.arrayBuffer();
    const prefix = new TextDecoder().decode(bytes.slice(0, 5));
    const pdf = prefix === '%PDF-';
    const type = pdf ? 'application/pdf' : new Uint8Array(bytes)[0] === 137 ? 'image/png' : 'image/jpeg';
    setSource({url:URL.createObjectURL(new Blob([bytes], {type})), pdf});
  }

  function sign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const file = fields.get('signature');
    if (!job?.opinion || !(file instanceof File)) return;
    const opinionId = job.opinion.id;
    void run(async () => {
      if (!file.size || file.size > 48000) throw new Error('Signature size');
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = '';
      for (const byte of bytes) binary += String.fromCharCode(byte);
      await api('clinical/opinions/' + opinionId + '/sign/', {artifact:btoa(binary), identifier_kind:fields.get('identifier_kind'),
        identifier_value:fields.get('identifier_value'), source_birth_date:fields.get('source_birth_date')});
      await read(job.id);
    });
  }

  return <details onToggle={event => {
    if (event.currentTarget.open && !loaded && !busy) void run(refresh);
  }}>
    <summary>{t('Analisi preliminare', 'Preliminary analysis')}</summary>
    {organization && <details>
      <summary>{t('Registro modelli e controllo di esecuzione', 'Model registry and execution control')}</summary>
      <button disabled={busy} onClick={() => void run(async () => {
        setRegistry(await api('organizations/' + organization + '/analysis/registry/'));
      })}>{t('Mostra schede e stato', 'Show model cards and status')}</button>
      {registry && <>
        <pre style={{whiteSpace:'pre-wrap', overflowWrap:'anywhere'}}>{JSON.stringify(registry.manifest, null, 2)}</pre>
        <p>{registry.enabled ? t('Esecuzione approvata', 'Execution approved') : t('Esecuzione sospesa', 'Execution suspended')}</p>
        <form onSubmit={event => {
          event.preventDefault();
          const reason = new FormData(event.currentTarget).get('reason');
          void run(async () => {
            await api('organizations/' + organization + '/analysis/registry/', {
              enabled:!registry.enabled, manifest_hash:registry.manifest_hash, reason,
            });
            setRegistry({...registry, enabled:!registry.enabled});
            setJob(null); setLoaded(false);
          });
        }}>
          <label>{t('Motivo della decisione sui modelli', 'Model decision reason')}<input name="reason" required maxLength={500}/></label>
          <button disabled={busy}>{registry.enabled ? t('Sospendi esecuzione', 'Suspend execution') : t('Approva per collaudo sintetico', 'Approve for synthetic testing')}</button>
        </form>
      </>}
    </details>}
    {error && <p role="alert">{error}</p>}
    <button type="button" disabled={busy} onClick={() => void run(refresh)}>{t('Aggiorna analisi', 'Refresh analysis')}</button>
    {loaded && !job && <button type="button" disabled={busy} onClick={() => void run(async () => {
      const created = await api<Job>(versionPath, {});
      await read(created.id);
    })}>{t('Avvia analisi del referto', 'Analyze report')}</button>}
    {job && <p role="status">{states[job.state ?? ''] ?? job.state}</p>}
    {incidentSaved && <p role="status">{t('Segnalazione AI registrata', 'AI issue recorded')}</p>}
    {job && <details><summary>{t('Segnala un problema dell’analisi', 'Report an analysis issue')}</summary>
      <form onSubmit={event => {
        event.preventDefault(); const form = event.currentTarget; const fields = new FormData(form);
        setIncidentSaved(false);
        void run(async () => {await api(jobPath(job.id) + 'incidents/', Object.fromEntries(fields)); form.reset(); setIncidentSaved(true);});
      }}>
        <label>{t('Tipo di problema AI', 'AI issue type')}<select name="category">
          <option value="incorrect_extraction">{t('Estrazione errata', 'Incorrect extraction')}</option>
          <option value="missed_finding">{t('Informazione omessa', 'Missed finding')}</option>
          <option value="unexpected_output">{t('Output inatteso', 'Unexpected output')}</option>
          <option value="privacy">Privacy</option><option value="other">{t('Altro', 'Other')}</option>
        </select></label>
        <label>{t('Descrizione del problema AI', 'AI issue description')}<textarea name="note" required maxLength={2000}/></label>
        <button disabled={busy}>{t('Registra segnalazione AI', 'Record AI issue')}</button>
      </form>
    </details>}
    {job?.draft && <>
      <p><strong>{job.disclaimer}</strong></p>
      {!!job.draft.notices?.length && <p role="alert">{t(
        'Estrazione incompleta: sono stati raggiunti i limiti di lettura. Verifica tutte le righe nel referto originale prima di attestare il parere.',
        'Incomplete extraction: reading limits were reached. Check all rows in the original report before attesting the opinion.',
      )}</p>}
      {job.draft.rows.length === 0 && <p>{t('Nessuna riga riconosciuta. Verifica il documento originale.', 'No rows recognized. Check the original document.')}</p>}
      <button disabled={busy} onClick={() => void run(openSource)}>{t('Apri referto originale', 'Open source report')}</button>
      {source && <section>
        <button onClick={() => setSource(null)}>{t('Chiudi originale', 'Close source')}</button>
        {source.pdf
          ? <iframe src={source.url} title={t('Referto originale', 'Source report')} style={{width:'100%',height:420}}/>
          // Source is an authenticated, local object URL; never send it to an image optimizer.
          // eslint-disable-next-line @next/next/no-img-element
          : <img src={source.url} alt={t('Immagine originale del referto', 'Source report image')} style={{maxWidth:'100%'}}/>}
      </section>}
      <ul>{job.draft.rows.map(row => <li key={row.id}>
        {t('Pagina', 'Page')} {row.page}, {t('riga', 'line')} {row.line} · {row.source === 'ocr' ? 'OCR' : t('Testo PDF', 'PDF text')} · {row.analyte}
        {' '}{row.operator}{row.value} {row.unit}
        {row.low != null && (' · ' + row.low + '–' + row.high)}
        {' · '}{flags[row.flag] ?? row.flag}
        <blockquote>{row.source_text}</blockquote>
        {row.bbox && <p>{t('Riquadro sorgente', 'Source box')} [{row.bbox.join(', ')}] · {row.coordinate_system}</p>}
        {row.confidence != null && <p>{t('Confidenza OCR', 'OCR confidence')} {row.confidence}/100</p>}
        {row.loinc && <p>LOINC {row.loinc} · UCUM {row.ucum}</p>}
      </li>)}</ul>
      {job.suggestion ? <p style={{whiteSpace:'pre-line'}}>{job.suggestion}</p>
        : <p>{t('Riepilogo non disponibile.', 'Summary unavailable.')}</p>}
      {!job.decision && <form key={job.id} onSubmit={review}>
        {decision !== 'reject' && job.draft.rows.filter(row => row.requires_confirmation !== false).map(row => <label key={row.id}>
          <input type="checkbox" name="confirmed_rows" value={row.id} required/>
          {t('Confermo dalla fonte la riga', 'I confirm the source for row')} {row.id}
        </label>)}
        {decision !== 'reject' && <label><input type="checkbox" name="source_checked" required/>
          {t('Ho confrontato ogni valore con il documento originale', 'I compared every value with the source document')}
        </label>}
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
    {job?.opinion && !job.opinion.signed && <form onSubmit={sign}>
      <p>{t('La pubblicazione richiede una firma verificata dal provider della struttura.', 'Publication requires a signature verified by the organization provider.')}</p>
      <code>{job.opinion.digest}</code>
      <button type="button" onClick={() => {
        const url = URL.createObjectURL(new Blob([job.opinion!.signing_content], {type:'application/json;charset=utf-8'}));
        const link = document.createElement('a'); link.href = url; link.download = 'reviewed-opinion.json'; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }}>{t('Scarica contenuto da firmare', 'Download content to sign')}</button>
      <fieldset><legend>{t('Conferma il paziente prima della firma', 'Confirm patient before signing')}</legend>
        <label>{t('Tipo identificativo per firma', 'Signing identifier type')}<select name="identifier_kind">
          <option value="facility">{t('Identificativo di struttura', 'Facility identifier')}</option>
          <option value="tax_code">{t('Codice fiscale', 'Italian tax code')}</option>
          <option value="health_card">{t('Tessera sanitaria', 'Health card')}</option>
        </select></label>
        <label>{t('Identificativo dalla fonte per firma', 'Source identifier for signing')}<input name="identifier_value" required maxLength={64} autoComplete="off"/></label>
        <label>{t('Data di nascita dalla fonte per firma', 'Source birth date for signing')}<input name="source_birth_date" type="date" required autoComplete="off"/></label>
      </fieldset>
      <label>{t('Artefatto firmato PAdES o CAdES', 'PAdES or CAdES signed artifact')}<input type="file" name="signature" required/></label>
      <button disabled={busy}>{t('Verifica firma', 'Verify signature')}</button>
    </form>}
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
  average_review_duration: number | null; average_extracted_rows: number | null; average_uncertain_rows: number | null;
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
    <p>{english ? 'These indicators do not measure clinical accuracy or validated drift.' : 'Questi indicatori non misurano accuratezza clinica o deriva validata.'}</p>
    {error && <p role="alert">{error}</p>}
    {metrics?.map(row => <p key={[row.job__pipeline, row.job__draft__model__checksum].join(':')}>
      {row.job__draft__model__name ?? row.job__pipeline} {row.job__draft__model__revision}
      {' · '}{row.total} {english ? 'reviews' : 'revisioni'}
      {' · '}{english ? 'Modified' : 'Modificate'} {(row.modify_rate * 100).toFixed(1)}%
      {' · '}{english ? 'Rejected' : 'Rifiutate'} {(row.reject_rate * 100).toFixed(1)}%
      {' · '}{english ? 'Mean review seconds' : 'Secondi medi di revisione'} {row.average_review_duration?.toFixed(1) ?? '—'}
      {' · '}{english ? 'Mean uncertain rows' : 'Righe incerte medie'} {row.average_uncertain_rows?.toFixed(1) ?? '—'}
    </p>)}
  </details>;
}
