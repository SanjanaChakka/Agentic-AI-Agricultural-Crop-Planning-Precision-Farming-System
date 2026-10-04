import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AppRoot } from './App';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root element #root was not found in index.html');
}

createRoot(container).render(
  <StrictMode>
    <AppRoot />
  </StrictMode>,
);