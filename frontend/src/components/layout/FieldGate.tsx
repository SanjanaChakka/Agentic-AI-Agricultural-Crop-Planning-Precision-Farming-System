import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { MapPin } from 'lucide-react';
import { useSelection } from '../../context/SelectionContext';
import { EmptyState } from '../ui/EmptyState';

/**
 * Guards every field-scoped page. Without a field there is nothing meaningful to
 * query, so we say so instead of firing requests that would 404.
 */
export function FieldGate({ children }: { children: ReactNode }) {
  const { fieldId, fieldLabel } = useSelection();

  if (fieldId === null) {
    return (
      <EmptyState
        title="Select a field to continue"
        description={
          <>
            This page works on one field at a time. Use the farm and field selectors in the
            header, or pick a field from the{' '}
            <Link to="/farms" className="font-medium text-brand-800 underline underline-offset-2">
              Farms &amp; Fields
            </Link>{' '}
            page.
          </>
        }
        icon={<MapPin className="h-5 w-5" aria-hidden="true" />}
      />
    );
  }

  return (
    <div data-testid="field-gate" data-field-id={fieldId}>
      {fieldLabel ? <span className="sr-only">Selected field: {fieldLabel}</span> : null}
      {children}
    </div>
  );
}

export default FieldGate;