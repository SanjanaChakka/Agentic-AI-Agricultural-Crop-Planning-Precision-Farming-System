import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

export interface DataTableColumn<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  /** Extra classes on the cell, e.g. `w-32 text-right`. */
  className?: string;
  headerClassName?: string;
}

export interface DataTableProps<T> {
  columns: Array<DataTableColumn<T>>;
  rows: T[];
  rowKey: (row: T) => string | number;
  caption?: ReactNode;
  empty?: ReactNode;
  className?: string;
  /** Sticky header for long tables inside a scroll container. */
  dense?: boolean;
}

/**
 * Server-agnostic table. Columns are declared by the caller; there is no
 * client-side sorting/paging so what you see is exactly what the API returned.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  empty,
  className,
  dense = false,
}: DataTableProps<T>) {
  if (rows.length === 0 && empty) {
    return <>{empty}</>;
  }

  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="w-full min-w-full border-collapse text-left text-sm">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr className="border-b border-slate-200">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn(
                  'label-caps whitespace-nowrap px-5 py-3',
                  dense ? 'py-2' : undefined,
                  column.headerClassName,
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={rowKey(row)} className="align-top transition-colors hover:bg-slate-50/70">
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cn('px-5 text-slate-700', dense ? 'py-2.5' : 'py-3.5', column.className)}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default DataTable;