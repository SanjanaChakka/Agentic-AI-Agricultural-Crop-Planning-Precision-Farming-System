import { useMemo, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import type { Evidence, SourceReference } from '../../api/types';
import { EVIDENCE_KINDS, type EvidenceKind } from '../../api/types';
import { EvidenceKindBadge } from '../ui/EvidenceKindBadge';
import { EmptyState } from '../ui/EmptyState';
import { Select } from '../ui/Field';
import { Card, CardHeader } from '../ui/Card';
import { formatDateTime, formatNumber, humaniseToken } from '../../lib/format';

export interface EvidenceLedgerProps {
  evidence: Evidence[];
  title?: string;
  subtitle?: string;
  /** Group by provenance tag instead of showing a flat list. */
  groupByKind?: boolean;
}

/**
 * The provenance ledger: every fact the system used, with its `kind` tag so a
 * reviewer can tell a measurement from a simulation at a glance.
 */
export function EvidenceLedger({
  evidence,
  title = 'Evidence ledger',
  subtitle,
  groupByKind = false,
}: EvidenceLedgerProps) {
  const [kindFilter, setKindFilter] = useState<string>('all');

  const kindsPresent = useMemo(() => {
    const seen = new Set<string>();
    evidence.forEach((item) => seen.add(item.kind));
    return Array.from(seen).sort();
  }, [evidence]);

  const filtered = useMemo(
    () => (kindFilter === 'all' ? evidence : evidence.filter((item) => item.kind === kindFilter)),
    [evidence, kindFilter],
  );

  const grouped = useMemo(() => {
    if (!groupByKind) return null;
    const buckets = new Map<string, Evidence[]>();
    filtered.forEach((item) => {
      const list = buckets.get(item.kind) ?? [];
      list.push(item);
      buckets.set(item.kind, list);
    });
    return Array.from(buckets.entries());
  }, [filtered, groupByKind]);

  return (
    <Card flush>
      <CardHeader
        title={`${title} (${evidence.length})`}
        subtitle={subtitle ?? 'Every fact used to reach the recommendation, tagged with its provenance.'}
        actions={
          kindsPresent.length > 1 ? (
            <label className="flex items-center gap-2 text-[11px] text-slate-500">
              Filter
              <Select
                aria-label="Filter evidence by provenance"
                className="h-8 py-1 text-xs"
                value={kindFilter}
                onChange={(event) => setKindFilter(event.target.value)}
              >
                <option value="all">All kinds ({evidence.length})</option>
                {kindsPresent.map((kind) => (
                  <option key={kind} value={kind}>
                    {humaniseToken(kind)} (
                    {evidence.filter((item) => item.kind === kind).length})
                  </option>
                ))}
              </Select>
            </label>
          ) : null
        }
      />
      <div className="p-5">
        {evidence.length === 0 ? (
          <EmptyState
            title="No evidence recorded"
            description="The agents did not attach provenance-tagged evidence to this result."
            icon={<span className="text-xs">0</span>}
          />
        ) : grouped ? (
          <div className="space-y-5">
            {grouped.map(([kind, items]) => (
              <div key={kind}>
                <div className="mb-2 flex items-center gap-2">
                  <EvidenceKindBadge kind={kind} showRaw />
                  <span className="text-xs text-slate-500">({items.length})</span>
                </div>
                <ul className="space-y-2">
                  {items.map((item, index) => (
                    <EvidenceRow key={`${kind}-${index}`} item={item} />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {filtered.map((item, index) => (
              <EvidenceRow key={`${item.label}-${index}`} item={item} />
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function renderValue(value: Evidence['value']): string {
  if (value === null || value === undefined) return 'not recorded';
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'number') return formatNumber(value, 2);
  return String(value);
}

function EvidenceRow({ item }: { item: Evidence }) {
  return (
    <li className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2.5">
      <EvidenceKindBadge kind={item.kind} className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-slate-800">{item.label}</p>
        <p className="tabular mt-0.5 text-sm text-slate-700">
          {renderValue(item.value)}
          {item.unit ? <span className="ml-1 text-xs text-slate-500">{item.unit}</span> : null}
        </p>
        {item.note ? <p className="mt-0.5 text-xs text-slate-500">{item.note}</p> : null}
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-400">
          {item.source ? <span>source: {item.source}</span> : null}
          {item.reference ? <span>reference: {item.reference}</span> : null}
          {item.observed_at ? <span>observed {formatDateTime(item.observed_at)}</span> : null}
        </div>
      </div>
    </li>
  );
}

export interface ReferenceListProps {
  sources: SourceReference[];
  title?: string;
  subtitle?: string;
}

/** Citation list. Only renders a link when the source actually provides a URL. */
export function ReferenceList({ sources, title = 'References', subtitle }: ReferenceListProps) {
  return (
    <Card flush>
      <CardHeader
        title={`${title} (${sources.length})`}
        subtitle={subtitle ?? 'Retrieved reference material cited by the agents.'}
      />
      <div className="p-5">
        {sources.length === 0 ? (
          <EmptyState
            title="No references retrieved"
            description="The retrieval step did not return any cited documents for this result."
          />
        ) : (
          <ul className="space-y-3">
            {sources.map((source) => (
              <li key={source.doc_key} className="rounded-lg border border-slate-200 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800">
                      {source.url ? (
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="inline-flex items-center gap-1 text-brand-800 underline decoration-brand-300 underline-offset-2 hover:text-brand-900"
                        >
                          {source.title}
                          <ExternalLink className="h-3 w-3" aria-hidden="true" />
                        </a>
                      ) : (
                        source.title
                      )}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      <span className="font-mono">{source.doc_key}</span>
                      {source.category ? ` · ${humaniseToken(source.category)}` : null}
                      {source.organisation ? ` · ${source.organisation}` : null}
                      {source.region ? ` · ${source.region}` : null}
                    </p>
                    {source.excerpt ? (
                      <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-slate-500">
                        {source.excerpt}
                      </p>
                    ) : null}
                  </div>
                  {source.score !== null && source.score !== undefined ? (
                    <span className="tabular shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                      score {formatNumber(source.score, 3)}
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

export { EVIDENCE_KINDS };
export type { EvidenceKind };
export default EvidenceLedger;