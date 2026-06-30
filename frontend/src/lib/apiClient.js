import { CLIENT_ID, getToken } from '../auth/authService';

export async function authFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  headers['X-Climeto-Client'] = CLIENT_ID;

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401 && !getToken() && typeof window !== 'undefined') {
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
  }

  return response;
}
