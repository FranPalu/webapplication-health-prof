import {useState} from 'react';

const exams = {
  tc: {
    name: 'TC torace',
    frames: ['Apice', 'Livello medio', 'Basi'],
    marker: 'Regione polmonare periferica',
    draft: 'La bozza evidenzia una piccola area periferica nel fotogramma centrale e la invia al radiologo per verifica.',
    review: 'Il radiologo ha rimosso la segnalazione dalla sintesi. Nel caso simulato, il reperto non è confermato confrontando le sezioni adiacenti.',
  },
  eco: {
    name: 'Ecocardiogramma',
    frames: ['Fotogramma 1', 'Fotogramma 2', 'Fotogramma 3'],
    marker: 'Bordo della cavità ventricolare',
    draft: 'La bozza segnala un bordo visibile solo in parte e lascia la misura in sospeso.',
    review: 'La cardiologa ha mantenuto la nota sulla qualità della vista. Nel caso simulato, la misura non viene pubblicata.',
  },
} as const;

function Illustration({exam, frame, marker}: {exam: keyof typeof exams; frame: number; marker: boolean}) {
  const tc = exam === 'tc';
  const offset = [0, 8, 3][frame];
  return (
    <svg className="demo-scan" viewBox="0 0 400 300" role="img"
      aria-label={tc ? 'Schema di una sezione assiale del torace' : 'Schema di un fotogramma ecocardiografico'}>
      <rect width="400" height="300" fill="#10151d"/>
      {tc ? <>
        <ellipse cx="200" cy="150" rx={152 - offset} ry={112 - offset} fill="#7e8790" stroke="#c0c7cb" strokeWidth="5"/>
        <ellipse cx="200" cy="150" rx={131 - offset} ry="92" fill="#a2a8ad"/>
        <path d="M180 91 C132 55 82 92 85 157 C91 204 138 229 174 194 C190 172 175 147 180 91Z" fill="#202731" transform={`translate(${offset} 0)`}/>
        <path d="M219 91 C270 56 320 93 315 158 C311 207 263 230 228 194 C210 167 225 145 219 91Z" fill="#202731" transform={`translate(${-offset} 0)`}/>
        <path d="M192 122 C211 107 232 123 243 151 C254 181 217 203 192 184 C178 166 176 142 192 122Z" fill="#c2c7cc"/>
        <ellipse cx="200" cy="222" rx="23" ry="18" fill="#e4e7eb" stroke="#66717a" strokeWidth="5"/>
        <path d="M185 142 L148 122 L116 127 M153 125 L138 167 M224 143 L265 122 L289 141 M263 125 L272 164" stroke="#68717a" strokeWidth="4" fill="none"/>
        {frame === 1 && <circle cx="284" cy="174" r="5" fill="#a9adb5"/>}
      </> : <>
        <path d="M200 24 L54 243 Q200 315 346 243 Z" fill="#42474f" stroke="#9098a1"/>
        <path d="M114 170 Q183 111 214 88 Q265 128 289 178 M84 215 Q151 187 178 197 M233 198 Q281 181 320 220" fill="none" stroke="#8f969d" strokeWidth="5"/>
        <path d={`M195 102 C135 123 121 185 153 228 C185 263 225 244 234 ${207 + offset} C243 170 230 117 195 102Z`} fill="#a8aeb4"/>
        <path d={`M193 125 C154 147 149 185 173 218 C196 239 222 204 218 ${184 + offset} C215 155 204 134 193 125Z`} fill="#22282f"/>
        <path d="M237 125 Q299 157 275 215 Q252 244 234 221 M166 173 Q190 159 211 175" fill="none" stroke="#ced1d4" strokeWidth="4"/>
        <path d="M75 231 Q199 284 324 229 M104 197 Q199 251 297 197" stroke="#747b84" strokeDasharray="2 5" fill="none"/>
      </>}
      {marker && (tc ? frame === 1 : true) && <circle cx={tc ? 284 : 216} cy={tc ? 174 : 184 + offset}
        r="18" fill="none" stroke="#f7ce74" strokeWidth="3" strokeDasharray="4 4"/>}
    </svg>
  );
}

export function ImagingDemo() {
  const [exam, setExam] = useState<keyof typeof exams>('tc');
  const [frame, setFrame] = useState(1);
  const [marker, setMarker] = useState(true);
  const detail = exams[exam];

  return <section className="identity-card demo-imaging" aria-labelledby="demo-imaging-title">
    <h3 id="demo-imaging-title">Imaging · confronto tra bozza e revisione</h3>
    <p>Immagini schematiche sintetiche e risultati simulati per il caso DEMO-042.</p>
    <div className="demo-imaging-grid">
      <figure>
        <Illustration exam={exam} frame={frame} marker={marker}/>
        <figcaption>{detail.name} · {detail.frames[frame]}{marker && (exam === 'eco' || frame === 1) ? ' · ' + detail.marker : ''}</figcaption>
      </figure>
      <div className="demo-imaging-controls">
        <label>Esame illustrativo<select value={exam} onChange={event => {
          setExam(event.target.value as keyof typeof exams);
          setFrame(1);
        }}>
          {Object.entries(exams).map(([id, item]) => <option key={id} value={id}>{item.name}</option>)}
        </select></label>
        <label>Sezione o fotogramma<select value={frame} onChange={event => setFrame(Number(event.target.value))}>
          {detail.frames.map((item, index) => <option key={item} value={index}>{item}</option>)}
        </select></label>
        <label className="demo-marker"><input type="checkbox" checked={marker} onChange={event => setMarker(event.target.checked)}/> Mostra il marcatore illustrativo</label>
        <div className="demo-review" aria-live="polite">
          <h4>Analisi automatica preliminare – non è una diagnosi</h4>
          <p>{detail.draft}</p>
          <h4>Revisione clinica simulata</h4>
          <p>{detail.review}</p>
        </div>
      </div>
    </div>
  </section>;
}
