import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { THEME_STORAGE_KEY } from './clientTools';
import './styles.css';

// Restore the theme the agent (or the user) chose last time, before first paint.
try {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  if (saved === 'light' || saved === 'dark') document.documentElement.dataset.theme = saved;
} catch {
  /* storage unavailable: fall back to the OS preference in CSS */
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
