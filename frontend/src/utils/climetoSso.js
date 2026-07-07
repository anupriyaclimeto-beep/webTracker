import { setSession, userFromToken } from '../auth/authService';

function readSsoParam(params, key) {
  const raw = params.get(key);
  if (!raw) return null;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export function applyClimetoSsoFromUrl() {
  const hash = window.location.hash?.replace(/^#/, '').trim();
  const params =
    hash && (hash.includes('climeto_sso=1') || hash.includes('token='))
      ? new URLSearchParams(hash)
      : new URLSearchParams(window.location.search);
  if (params.get('climeto_sso') !== '1') return false;

  const token = readSsoParam(params, 'token');
  const tokenKey = params.get('tokenKey') || 'webtracker_auth_token';
  const userKey = params.get('userKey') || 'webtracker_current_user';
  const currentUser = readSsoParam(params, 'currentUser');

  if (token && currentUser) {
    try {
      const user = JSON.parse(currentUser);
      setSession(token, user);
    } catch {
      localStorage.setItem(tokenKey, token);
      localStorage.setItem(userKey, currentUser);
    }
  } else if (token) {
    const fromJwt = userFromToken(token);
    if (fromJwt) {
      setSession(token, fromJwt);
    } else {
      localStorage.setItem(tokenKey, token);
    }
  }

  ['climeto_sso', 'token', 'tokenKey', 'userKey', 'currentUser'].forEach((k) =>
    params.delete(k),
  );

  const nextPath = window.location.pathname === '/login' ? '/overview' : window.location.pathname;
  window.history.replaceState({}, '', nextPath);
  return Boolean(token);
}
