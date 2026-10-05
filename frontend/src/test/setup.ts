import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

/**
 * Shared test setup.
 *
 * `globals: false` in vite.config.ts, so every suite imports `describe`/`it`/
 * `expect` explicitly. This file only handles DOM matchers and unmounting so a
 * failed assertion cannot leak rendered nodes into the next test.
 */
afterEach(() => {
  cleanup();
  window.localStorage.clear();
});