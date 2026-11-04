import type { paths } from './schema';
export type ApiPath = keyof paths;
export async function api<T>(path: string, body?: unknown, method?: 'DELETE'): Promise<T> {
  const csrf = document.cookie.split('; ').find(x => x.startsWith('csrftoken='))?.split('=')[1] || '';
  const multipart = body instanceof FormData;
  const response = await fetch(`/api/v1/${path}`, {
    method: method ?? (body === undefined ? 'GET' : 'POST'), credentials: 'same-origin',
    headers: {...(multipart ? {} : {'Content-Type': 'application/json'}), 'X-CSRFToken': decodeURIComponent(csrf)},
    ...(body === undefined ? {} : {body: multipart ? body : JSON.stringify(body)}),
  });
  if (response.status === 204) return undefined as T;
  const value: unknown = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(value));
  return value as T;
}
