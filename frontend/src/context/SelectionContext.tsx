import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { Farm, Field } from '../api/types';

const STORAGE_KEY = 'agri.selection.v1';

export interface SelectionState {
  farmId: number | null;
  fieldId: number | null;
  farmLabel: string;
  fieldLabel: string;
}

interface SelectionContextValue extends SelectionState {
  setFarm: (farmId: number | null, farm?: Farm | null) => void;
  setField: (fieldId: number | null, field?: Field | null) => void;
}

const defaultState: SelectionState = {
  farmId: null,
  fieldId: null,
  farmLabel: '',
  fieldLabel: '',
};

const SelectionContext = createContext<SelectionContextValue>({
  ...defaultState,
  setFarm: () => undefined,
  setField: () => undefined,
});

const readStored = (): SelectionState => {
  if (typeof window === 'undefined') return defaultState;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return defaultState;
    const record = parsed as Record<string, unknown>;
    return {
      farmId: typeof record.farmId === 'number' ? record.farmId : null,
      fieldId: typeof record.fieldId === 'number' ? record.fieldId : null,
      farmLabel: typeof record.farmLabel === 'string' ? record.farmLabel : '',
      fieldLabel: typeof record.fieldLabel === 'string' ? record.fieldLabel : '',
    };
  } catch {
    return defaultState;
  }
};

/**
 * Single source of truth for the farm/field chosen in the header. Persisted to
 * localStorage so a reload lands back on the same field, and shared by every
 * field-scoped page.
 */
export function SelectionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SelectionState>(readStored);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Storage can be unavailable (private mode); selection is still usable in-memory.
    }
  }, [state]);

  const setFarm = useCallback((farmId: number | null, farm?: Farm | null) => {
    setState((previous) => ({
      ...previous,
      farmId,
      farmLabel: farm ? farm.name : farmId ? `#${farmId}` : '',
      // A different farm invalidates the field selection.
      fieldId: null,
      fieldLabel: '',
    }));
  }, []);

  const setField = useCallback((fieldId: number | null, field?: Field | null) => {
    setState((previous) => ({
      ...previous,
      fieldId,
      fieldLabel: field ? field.name : fieldId ? `#${fieldId}` : '',
    }));
  }, []);

  const value = useMemo<SelectionContextValue>(
    () => ({ ...state, setFarm, setField }),
    [state, setFarm, setField],
  );

  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

export function useSelection(): SelectionContextValue {
  return useContext(SelectionContext);
}

export default SelectionContext;