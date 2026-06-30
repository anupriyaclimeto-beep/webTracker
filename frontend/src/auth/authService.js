const TOKEN_KEY = 'webtracker_auth_token';
const USER_KEY = 'webtracker_current_user';
export const CLIENT_ID = 'web-tracker';
const REQUIRED_USER_TYPE_NORM = 'webtracker';

export function normalizeUserType(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[\s_-]+/g, '')
    .trim();
}

export function isWebTrackerUser(user) {
  return normalizeUserType(user?.user_type) === REQUIRED_USER_TYPE_NORM;
}

function authApiRoot() {
  if (import.meta.env.DEV) {
    const override = import.meta.env.VITE_AUTH_API_BASE_URL;
    if (override) return String(override).replace(/\/$/, '');
    return '/climeto-api';
  }
  const base =
    import.meta.env.VITE_AUTH_API_BASE_URL ||
    import.meta.env.VITE_CLIMETO_API_BASE_URL ||
    'https://api.climeto.in/api';
  return String(base).replace(/\/$/, '');
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(
    USER_KEY,
    JSON.stringify({
      id: user.id,
      email: user.email,
      user_type: user.user_type,
      company_name: user.company_name,
    }),
  );
  localStorage.setItem('isAuthenticated', 'true');
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem('isAuthenticated');
}

export function userFromStorage() {
  const stored = getStoredUser();
  if (stored && isWebTrackerUser(stored)) return stored;
  return null;
}

function decodeJwtPayload(token) {
  try {
    const part = String(token).split('.')[1];
    if (!part) return null;
    return JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    return null;
  }
}

export function userFromToken(token) {
  const payload = decodeJwtPayload(token);
  if (!payload?.email || !payload?.user_type) return null;
  const user = {
    id: payload.id,
    email: payload.email,
    user_type: payload.user_type,
    company_name: payload.company_name,
  };
  return isWebTrackerUser(user) ? user : null;
}

export function hydrateAuthFromStorage() {
  const token = getToken();
  let user = userFromStorage();

  if (token && !user) {
    const fromToken = userFromToken(token);
    if (fromToken) {
      setSession(token, fromToken);
      user = fromToken;
    }
  }

  return {
    token,
    user,
    isAuthenticated: Boolean(token && user),
    bootstrapped: Boolean(token && user),
  };
}

async function parseResponse(res) {
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { msg: text };
  }
  if (!res.ok) {
    const err = new Error(data?.msg || data?.message || res.statusText || 'Request failed');
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Request timed out')), ms);
    promise
      .then((value) => {
        clearTimeout(timer);
        resolve(value);
      })
      .catch((err) => {
        clearTimeout(timer);
        reject(err);
      });
  });
}

export async function login({ email, password, force = false }) {
  const res = await fetch(`${authApiRoot()}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Climeto-Client': CLIENT_ID,
    },
    body: JSON.stringify({
      email: String(email || '').trim(),
      password,
      force: Boolean(force),
      client: CLIENT_ID,
    }),
  });

  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { msg: text };
  }

  if (res.status === 409 && data?.requiresConfirmation) {
    const err = new Error(data.msg || 'Session conflict');
    err.status = 409;
    err.data = data;
    throw err;
  }

  if (!res.ok) {
    const err = new Error(data?.msg || data?.message || res.statusText || 'Login failed');
    err.status = res.status;
    err.data = data;
    throw err;
  }

  const token = data?.token;
  const user = data?.user;

  if (!token || !user) {
    throw new Error('Login succeeded but token or user was missing.');
  }

  if (!isWebTrackerUser(user)) {
    clearSession();
    const err = new Error('Unauthorized: WEB_TRACKER access required.');
    err.status = 403;
    throw err;
  }

  setSession(token, user);
  return { success: true, token, user };
}

export async function getMe({ clearOnFailure = true } = {}) {
  const token = getToken();
  if (!token) return { success: false, error: 'Not logged in.' };

  try {
    const res = await withTimeout(
      fetch(`${authApiRoot()}/auth/me`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${token}`,
          'X-Climeto-Client': CLIENT_ID,
        },
      }),
      8000,
    );
    const data = await parseResponse(res);
    const user = data?.user || data;

    if (!isWebTrackerUser(user)) {
      if (clearOnFailure) clearSession();
      return { success: false, error: 'Unauthorized: WEB_TRACKER access required.', status: 403 };
    }

    setSession(token, user);
    return { success: true, user };
  } catch (err) {
    if (clearOnFailure && (err.status === 401 || err.status === 403)) {
      clearSession();
    }
    return { success: false, error: err.message || 'Session expired.', status: err.status };
  }
}

export function refreshSessionInBackground(onUser) {
  void getMe({ clearOnFailure: false }).then((res) => {
    if (res?.success && res.user) onUser(res.user);
  });
}

export async function logout() {
  const token = getToken();
  if (token) {
    try {
      await fetch(`${authApiRoot()}/auth/logout`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'X-Climeto-Client': CLIENT_ID,
        },
      });
    } catch {
      /* still clear local session */
    }
  }
  clearSession();
  return { success: true };
}

export function displayName(user) {
  if (!user) return 'User';
  return String(user.company_name || user.email || 'User').split('@')[0];
}
