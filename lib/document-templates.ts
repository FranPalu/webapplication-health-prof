import {currency,displayDate,invoiceTotal,type Invoice,type Patient,type Settings} from './core';

// Shared by downloads, demo and email: no external fonts or remote clinical data.
type Block={text:string;style?:'title'|'section'|'muted'|'total'};
const ink='0.16 0.25 0.23',sage='0.28 0.43 0.36';
const encode=(s:string)=>Array.from(s).map(c=>{const special:Record<string,number>={'€':128,'’':146,'“':147,'”':148,'–':150,'—':151,'•':149};const n=special[c]??c.charCodeAt(0);return (n>255?63:n).toString(16).padStart(2,'0')}).join('');
function wrap(text:string,width=72){const result:string[]=[];for(const line of text.split('\n')){let row='';for(const token of line.split(/\s+/)){const chunks=token.match(new RegExp(`.{1,${width}}`,'g'))||[''];for(const word of chunks){if(row.length+word.length+1>width){result.push(row);row=word;}else row+=(row?' ':'')+word;}}result.push(row);}return result;}
function text(s:string,x:number,y:number,size=11,bold=false,color=ink){return `${color} rg BT /${bold?'F2':'F1'} ${size} Tf 1 0 0 1 ${x} ${y} Tm <${encode(s)}> Tj ET\n`;}
export function templatePdf(settings:Settings,label:string,blocks:Block[]){
 const pages:string[]=[];let stream='',y=0;
 const header=()=>{stream='0.96 0.97 0.94 rg 0 730 595 112 re f\n'+text('CB',42,784,26,true,sage)+text(settings.name,105,790,19,true)+text('NUTRIZIONE & ASCOLTO',105,770,9,false,sage)+text(label.toUpperCase(),42,747,9,true,sage);y=703;};
 const finish=()=>{pages.push(stream);};header();
 for(const b of blocks){const large=b.style==='title',section=b.style==='section',total=b.style==='total';const size=large?21:total?15:11,leading=large?29:total?24:17;
  const lines=wrap(b.text,large?39:total?54:72);if((section||total)&&y<116){finish();header();}
  if(section||large||total)y-=10;
  for(const line of lines){if(y<75){finish();header();}if(total)stream+=`0.91 0.95 0.91 rg 36 ${y-7} 523 28 re f\n`;stream+=text(line,44,y,size,large||section||total,b.style==='muted'?'0.40 0.46 0.43':ink);y-=leading;}
  y-=5;
 }
 finish();const objects:string[]=['<< /Type /Catalog /Pages 2 0 R >>',`<< /Type /Pages /Count ${pages.length} /Kids [${pages.map((_,i)=>`${3+i*2} 0 R`).join(' ')}] >>`];const font=3+pages.length*2;
 pages.forEach((page,i)=>{const content=page+'0.78 0.84 0.79 RG 44 53 m 551 53 l S\n'+text('Studio '+settings.name+' · Documento riservato',44,37,8)+text(`${i+1} / ${pages.length}`,515,37,8);objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 ${font} 0 R /F2 ${font+1} 0 R >> >> /Contents ${4+i*2} 0 R >>`,`<< /Length ${content.length} >>\nstream\n${content}endstream`);});
 objects.push('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>');let output='%PDF-1.4\n';const offsets:number[]=[];objects.forEach((o,i)=>{offsets.push(output.length);output+=`${i+1} 0 obj\n${o}\nendobj\n`;});const xref=output.length;output+=`xref\n0 ${objects.length+1}\n0000000000 65535 f \n${offsets.map(n=>String(n).padStart(10,'0')+' 00000 n \n').join('')}trailer\n<< /Size ${objects.length+1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;return new TextEncoder().encode(output);
}
export function invoicePdf(i:Invoice,patient:Patient,settings:Settings,demo=false){const s=i.issuer??settings,p=i.recipient??patient;return templatePdf(s,'Documento fiscale',[
 {text:demo?'ANTEPRIMA DIMOSTRATIVA · NON FISCALE':i.status==='Bozza'?'BOZZA · NON FISCALE':'FATTURA',style:'title'},
 {text:`${i.number} · ${displayDate(i.date)}`,style:'muted'},
 {text:s.qualification},{text:s.address||'Indirizzo studio da completare'},
 {text:`P. IVA ${s.vat||'da completare'}${s.taxCode?' · CF '+s.taxCode:''}`},
 {text:`Iscrizione Ordine dei Biologi: ${s.registerNumber||'da completare'}`},
 {text:[s.email,s.phone].filter(Boolean).join(' · '),style:'muted'},
 {text:'INTESTATARIO',style:'section'},{text:p.firstName+' '+p.lastName},{text:`${p.address} · ${p.zip} ${p.city}`},{text:'Codice fiscale: '+(p.cf||'da completare')},
 {text:'PRESTAZIONE PROFESSIONALE',style:'section'},{text:i.description},{text:'Compenso professionale: '+currency(i.amount)},
 {text:`Contributo integrativo ENPAB ${i.enpabRate??0}%: ${currency(i.enpabAmount??0)}`},{text:'Imposta di bollo: '+currency(i.stamp)},
 {text:'TOTALE DOCUMENTO    '+currency(invoiceTotal(i)),style:'total'},
 {text:`Pagamento: ${i.payment} · Stato: ${i.status}${i.paidDate?' · Incasso: '+displayDate(i.paidDate):''}`},
 ...(s.iban?[{text:'IBAN: '+s.iban}]:[]),
 {text:s.fiscalNote||'Dicitura fiscale da completare prima dell’emissione.',style:'muted'},
 ...(i.opposition?[{text:'Opposizione all’utilizzo dei dati per la dichiarazione precompilata registrata.',style:'muted' as const}]:[])
 ]);}
export const planTemplates={
 daily:{label:'Percorso quotidiano',text:'OBIETTIVI CONDIVISI\n\nCOLAZIONE\n\nSPUNTINO DEL MATTINO\n\nPRANZO\n\nMERENDA\n\nCENA\n\nALTERNATIVE E SOSTITUZIONI\n\nINDICAZIONI CONCORDATE\n\nPROSSIMO INCONTRO\n'},
 weekly:{label:'Settimana alimentare',text:'OBIETTIVI CONDIVISI\n\nLUNEDÌ\n\nMARTEDÌ\n\nMERCOLEDÌ\n\nGIOVEDÌ\n\nVENERDÌ\n\nSABATO\n\nDOMENICA\n\nALTERNATIVE E SOSTITUZIONI\n\nINDICAZIONI CONCORDATE\n'},
 flexible:{label:'Indicazioni personalizzate',text:'IL TUO PERCORSO\n\nOBIETTIVI CONDIVISI\n\nINDICAZIONI CONCORDATE\n\nNOTE E PROSSIMI PASSI\n'}
};
export function planPdf(p:Patient,s:Settings,body:string,date:string,title='Piano alimentare'){return templatePdf(s,'Nutrizione · percorso personale',[{text:title,style:'title'},{text:p.firstName+' '+p.lastName},{text:displayDate(date),style:'muted'},{text:'Un percorso costruito insieme, nel rispetto dei tuoi tempi.',style:'muted'},...body.split('\n').map(line=>({text:line,style:line.trim()&&line===line.toUpperCase()?'section' as const:undefined})),{text:[s.email,s.phone].filter(Boolean).join(' · '),style:'muted'}]);}
