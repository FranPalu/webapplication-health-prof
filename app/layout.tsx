import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={title:'Clarissa Bandini · Studio',description:'Nutrizione, ascolto e cura. Lo spazio digitale dello studio di Clarissa Bandini.',icons:{icon:'/favicon.svg'}};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="it"><body>{children}</body></html>}
