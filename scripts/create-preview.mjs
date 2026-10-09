import {build} from 'esbuild';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
const target=process.argv[2];if(!target||!path.isAbsolute(target))throw new Error('Provide an absolute output HTML path');
const result=await build({stdin:{contents:"import React from 'react';import {createRoot} from 'react-dom/client';import Studio from './app/Studio';createRoot(document.getElementById('root')).render(<Studio/>);",resolveDir:process.cwd(),sourcefile:'preview.tsx',loader:'tsx'},bundle:true,write:false,format:'iife',platform:'browser',minify:true,define:{'process.env.NODE_ENV':'"production"'}});
const css=await readFile('app/globals.css','utf8');const js=result.outputFiles[0].text.replace(/<\/script/gi,'<\\/script');await mkdir(path.dirname(target),{recursive:true});await writeFile(target,`<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Clarissa Bandini · Studio · Anteprima</title><style>${css}</style></head><body><div id="root"></div><script>${js}</script></body></html>`);console.log('Self-contained preview created');
