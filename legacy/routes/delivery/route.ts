import {z} from 'zod';
import {owner,record,readRecords,runtimeEnv,reply,failure,database,save} from '../../../lib/server';
import {invoicePdf} from '../../../lib/document-templates';
import {defaultSettings} from '../../../lib/core';
import {emailHtml} from '../../../lib/providers';
export async function POST(req:Request){try{
 const o=await owner(req),input=z.object({kind:z.enum(['invoice','document']),id:z.string().min(1).max(100)}).parse(await req.json()),r=await record(o,input.id,input.kind==='invoice'?'invoices':'documents');
 if(!r)throw new Error('Documento non trovato.');const item=JSON.parse(r.payload),pr=await record(o,item.patientId,'patients');if(!pr)throw new Error('Paziente non trovato.');
 const p=JSON.parse(pr.payload),env=runtimeEnv();if(!p.email||!p.emailConsent)throw new Error('Registra indirizzo email e preferenza di comunicazione del paziente.');if(p.email.endsWith('.example'))throw new Error('Contatto dimostrativo: invio disattivato.');if(!env.RESEND_API_KEY||!env.MAIL_FROM)throw new Error('Configura il servizio email e il mittente verificato.');
 let bytes:Uint8Array,filename:string;
 if(input.kind==='document'){const file=await env.BUCKET?.get(item.key);if(!file)throw new Error('Il file non è disponibile.');if(file.size>5000000)throw new Error('Per l’invio email il limite è 5 MB.');bytes=new Uint8Array(await file.arrayBuffer());filename=item.name;}
 else{const sr=(await readRecords(o,'settings'))[0],s={...defaultSettings,...JSON.parse(sr?.payload||'{}')};filename='fattura-'+item.number.replace(/[^\w-]/g,'-')+'.pdf';bytes=invoicePdf(item,p,s);}
 const id=`delivery:${o}:${input.kind}:${input.id}`,m={id,patientId:p.id,channel:'Email',body:'Invio documento',status:'In elaborazione',date:new Date().toISOString()};
 const inserted=await database().prepare('INSERT INTO studio_records(id,owner,kind,payload,created_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO NOTHING RETURNING id').bind(id,o,'messages',JSON.stringify(m),m.date).first();if(!inserted)throw new Error('Invio già registrato. Verifica il registro prima di riprovare.');
 try{let binary='';for(let n=0;n<bytes.length;n+=4096)binary+=String.fromCharCode(...bytes.slice(n,n+4096));const body='Lo studio di Clarissa Bandini ti invia il documento concordato. Per qualsiasi necessità contatta lo studio.';
 const response=await fetch('https://api.resend.com/emails',{method:'POST',signal:AbortSignal.timeout(20000),headers:{Authorization:'Bearer '+env.RESEND_API_KEY,'Content-Type':'application/json','Idempotency-Key':id},body:JSON.stringify({from:env.MAIL_FROM,to:[p.email],subject:'Un documento dal tuo studio',text:body,html:emailHtml(body,'Un documento per te'),attachments:[{filename,content:btoa(binary)}]})});
 if(!response.ok)throw new Error('Il servizio email non ha accettato il documento.');const result=await response.json() as {id?:string};if(!result.id)throw new Error('Risposta email senza identificativo.');await save(o,'messages',{...m,status:'Accettato dal provider',providerId:result.id});return reply({ok:true,status:'Accettato dal provider'});
 }catch(e){await save(o,'messages',{...m,status:'Errore · da verificare'});throw e;}
}catch(e){return failure(e)}}
