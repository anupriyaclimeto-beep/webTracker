import React, { useEffect, useRef, useState } from 'react';

// Self-contained Climeto portal switcher. Only these 3 constants change per portal.
const TOKEN_KEY = 'webtracker_auth_token';
const CLIENT_ID = 'web-tracker';
const CURRENT_APP_ID = 'web_tracker';

function authApiRoot() {
  const env = import.meta.env || {};
  if (env.DEV) {
    const override = env.VITE_AUTH_API_BASE_URL;
    return override ? String(override).replace(/\/$/, '') : '/climeto-api';
  }
  const base =
    env.VITE_AUTH_API_BASE_URL || env.VITE_CLIMETO_API_BASE_URL || 'https://api.climeto.in/api';
  return String(base).replace(/\/$/, '');
}

function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

async function authedJson(path, options = {}) {
  const token = getToken();
  const res = await fetch(`${authApiRoot()}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Climeto-Client': CLIENT_ID,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { msg: text };
  }
  if (!res.ok) {
    const err = new Error(data?.msg || data?.code || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function buildSwitchUrl(app, token, user) {
  const base = String(app.frontendUrl).replace(/\/$/, '');
  if (app.appId === 'climeto_admin' || app.appId === 'climeto_desktop') {
    return `${base}/sso?token=${encodeURIComponent(token)}`;
  }
  const landing = app.appId === 'cpcb_scraper' ? '/sso' : '/';
  const params = new URLSearchParams({
    climeto_sso: '1',
    token,
    tokenKey: app.tokenStorageKey || 'token',
  });
  if (app.userStorageKey) params.set('userKey', app.userStorageKey);
  if (user) params.set('currentUser', JSON.stringify(user));
  return `${base}${landing}?${params.toString()}`;
}

const styles = {
  wrap: { position: 'relative', display: 'inline-block' },
  btn: {
    background: 'transparent',
    border: '1px solid #cbd5e1',
    color: '#334155',
    borderRadius: '6px',
    padding: '6px 12px',
    fontSize: '13px',
    cursor: 'pointer',
  },
  menu: {
    position: 'absolute',
    top: 'calc(100% + 6px)',
    right: 0,
    minWidth: '260px',
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: '10px',
    boxShadow: '0 10px 28px rgba(15,23,42,0.16)',
    padding: '6px',
    zIndex: 60,
  },
  note: { padding: '10px 12px', fontSize: '12px', color: '#64748b' },
  error: { padding: '10px 12px', fontSize: '12px', color: '#dc2626' },
  item: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    width: '100%',
    textAlign: 'left',
    background: 'transparent',
    border: 'none',
    borderRadius: '8px',
    padding: '9px 12px',
    cursor: 'pointer',
  },
  itemName: { fontSize: '13px', fontWeight: 600, color: '#0f172a' },
  itemSub: { fontSize: '11px', color: '#64748b' },
};

export default function PortalSwitcher() {
  const [open, setOpen] = useState(false);
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [switching, setSwitching] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  async function loadApps() {
    setLoading(true);
    setError('');
    try {
      const data = await authedJson('/auth/my-apps', { method: 'GET' });
      const list = (Array.isArray(data?.apps) ? data.apps : []).filter(
        (a) => a.appId !== CURRENT_APP_ID,
      );
      setApps(list);
      setLoaded(true);
    } catch (err) {
      setError(err.message || 'Could not load portals.');
    }
    setLoading(false);
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !loaded) loadApps();
  }

  async function handleSwitch(appId) {
    setSwitching(appId);
    setError('');
    try {
      const data = await authedJson('/auth/switch-app', {
        method: 'POST',
        body: JSON.stringify({ appId }),
      });
      const { token, user, app } = data || {};
      if (!token || !app?.frontendUrl) throw new Error('Switch failed.');
      window.location.href = buildSwitchUrl(app, token, user);
    } catch (err) {
      setError(err.message || 'Switch failed.');
      setSwitching(null);
    }
  }

  return (
    <div style={styles.wrap} ref={wrapRef}>
      <button type="button" style={styles.btn} onClick={toggle}>
        Switch portal ▾
      </button>
      {open && (
        <div style={styles.menu}>
          {loading && <div style={styles.note}>Loading…</div>}
          {error && <div style={styles.error}>{error}</div>}
          {!loading && !error && apps.length === 0 && (
            <div style={styles.note}>No other portals available.</div>
          )}
          {apps.map((app) => (
            <button
              key={app.appId}
              type="button"
              style={styles.item}
              disabled={Boolean(switching)}
              onClick={() => handleSwitch(app.appId)}
              onMouseEnter={(e) => (e.currentTarget.style.background = '#f1f5f9')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <span style={styles.itemName}>{app.name}</span>
              <span style={styles.itemSub}>
                {switching === app.appId ? 'Opening…' : app.description}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
