import {runtimeEnv,reply,database} from '../../../../lib/server';
import {runDueReminders} from '../../../../lib/reminders';
export async function POST(req:Request){const env=runtimeEnv();if(!env.REMINDER_JOB_SECRET)return reply({error:'Servizio automatico non configurato.'},503);const token=req.headers.get('authorization');if(token!=='Bearer '+env.REMINDER_JOB_SECRET)return reply({error:'Non autorizzato.'},401);return reply(await runDueReminders(database(),env));}
