import React, { useCallback, useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './components/Dashboard';
import Overview from './pages/Overview';
import Changes from './pages/Changes';
import Console from './pages/Console';
import {
  hydrateAuthFromStorage,
  logout as authLogout,
  refreshSessionInBackground,
  getToken,
  userFromStorage,
  userFromToken,
  getMe,
  setSession,
  displayName,
} from './auth/authService';
import { redirectToPortalSignedOut } from './utils/portalUrl';

function App() {
  const [bootstrapped, setBootstrapped] = useState(() => {
    const h = hydrateAuthFromStorage();
    return h.bootstrapped || !getToken();
  });
  const [user, setUser] = useState(() => hydrateAuthFromStorage().user || userFromStorage());

  const isAuthenticated = Boolean(user && getToken());

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setUser(null);
      setBootstrapped(true);
      return;
    }

    const cached = userFromStorage();
    if (cached) {
      setUser(cached);
      setBootstrapped(true);
      refreshSessionInBackground(setUser);
      return;
    }

    const fromToken = userFromToken(token);
    if (fromToken) {
      setSession(token, fromToken);
      setUser(fromToken);
      setBootstrapped(true);
      refreshSessionInBackground(setUser);
      return;
    }

    void getMe({ clearOnFailure: false }).then((res) => {
      if (res?.success) {
        setUser(res.user);
      } else {
        const fallback = userFromToken(token);
        if (fallback) {
          setSession(token, fallback);
          setUser(fallback);
        }
      }
      setBootstrapped(true);
    });
  }, []);

  const handleLogin = useCallback((loggedInUser) => {
    setUser(loggedInUser);
    setBootstrapped(true);
  }, []);

  const handleLogout = useCallback(async () => {
    await authLogout();
    setUser(null);
    redirectToPortalSignedOut();
  }, []);

  if (!bootstrapped) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100 text-slate-600">
        Loading...
      </div>
    );
  }

  return (
    <Router>
      <Routes>
        <Route
          path="/login"
          element={
            !isAuthenticated ? (
              <Login onLogin={handleLogin} />
            ) : (
              <Navigate to="/overview" replace />
            )
          }
        />

        <Route
          path="/"
          element={
            isAuthenticated ? (
              <Dashboard onLogout={handleLogout} user={user} displayName={displayName(user)} />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        >
          <Route index element={<Navigate to="/overview" replace />} />
          <Route path="overview" element={<Overview />} />
          <Route path="changes" element={<Changes />} />
          <Route path="console" element={<Console />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
