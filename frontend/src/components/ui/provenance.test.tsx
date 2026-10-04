import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { EvidenceKindBadge, EVIDENCE_KIND_META, evidenceKindMeta } from './EvidenceKindBadge';
import { RiskBadge, safeSeverityLabel } from './RiskBadge';
import { EVIDENCE_KINDS } from '../../api/types';

/**
 * Two guarantees are asserted by rendering, not by calling helpers:
 *
 *  1. Every provenance tag the backend can emit has a distinct human label, so
 *     "simulated" can never be mistaken for "measured" on screen.
 *  2. The severity badge shows severity and nothing else - it must not be able
 *     to render a diagnosis.
 */
describe('EvidenceKindBadge', () => {
  it('labels a measured value distinctly from a simulated one', () => {
    const { unmount } = render(<EvidenceKindBadge kind="measured" />);
    const measured = screen.getByText('Measured');
    const measuredLabel = measured.textContent;
    unmount();

    render(<EvidenceKindBadge kind="simulated" />);
    const simulated = screen.getByText('Simulated');

    expect(measuredLabel).not.toBe(simulated.textContent);
  });

  it('labels a forecast value as forecast', () => {
    render(<EvidenceKindBadge kind="forecast" />);

    expect(screen.getByText('Forecast')).toBeInTheDocument();
  });

  it('labels a retrieved reference as a reference, not as a measurement', () => {
    render(<EvidenceKindBadge kind="retrieved_reference" />);

    expect(screen.getByText('Reference')).toBeInTheDocument();
    expect(screen.queryByText('Measured')).not.toBeInTheDocument();
  });

  it('labels an unrecognised tag with its own name so the gap is visible', () => {
    render(<EvidenceKindBadge kind="totally_new_kind" />);

    expect(screen.getByText('Totally new kind')).toBeInTheDocument();
  });

  it('degrades a missing tag to a neutral "Unlabelled" badge', () => {
    render(<EvidenceKindBadge kind="" />);

    expect(screen.getByText('Unlabelled')).toBeInTheDocument();
  });

  it('can show the raw enum value for auditing', () => {
    render(<EvidenceKindBadge kind="ml_prediction" showRaw />);

    expect(screen.getByText('(ml_prediction)')).toBeInTheDocument();
  });
});

describe('EVIDENCE_KIND_META coverage', () => {
  it('defines a label, description and icon for every backend kind', () => {
    for (const kind of EVIDENCE_KINDS) {
      const meta = EVIDENCE_KIND_META[kind];
      expect(meta, `${kind} has no metadata`).toBeDefined();
      expect(meta.label).toBeTruthy();
      expect(meta.description).toBeTruthy();
      expect(meta.Icon).toBeTruthy();
    }
  });

  it('gives every kind a distinct label', () => {
    const labels = EVIDENCE_KINDS.map((kind) => EVIDENCE_KIND_META[kind].label.toLowerCase());

    expect(new Set(labels).size).toBe(labels.length);
  });

  it('states plainly that simulated evidence is not a measurement', () => {
    expect(EVIDENCE_KIND_META.simulated.description.toLowerCase()).toContain('not a physical measurement');
  });
});

describe('evidenceKindMeta', () => {
  it('returns the documented metadata for a known kind', () => {
    expect(evidenceKindMeta('measured').label).toBe('Measured');
  });

  it('humanises an unknown kind but flags it as undocumented', () => {
    const meta = evidenceKindMeta('mystery_kind');

    expect(meta.label).toBe('Mystery kind');
    expect(meta.description).toMatch(/not part of the documented/);
  });
});

describe('RiskBadge', () => {
  it('renders severity with an environmental-conditions qualifier', () => {
    render(<RiskBadge severity="high" />);

    expect(screen.getByTestId('risk-badge')).toHaveTextContent('High conditions severity');
  });

  it('states in its tooltip that the system does not diagnose', () => {
    render(<RiskBadge severity="moderate" />);

    expect(screen.getByTestId('risk-badge')).toHaveAttribute(
      'title',
      expect.stringContaining('does not diagnose'),
    );
  });

  it('renders "Unrated" for a missing severity', () => {
    render(<RiskBadge severity={undefined} />);

    expect(screen.getByTestId('risk-badge')).toHaveTextContent('Unrated');
  });

  it('refuses to render diagnosis language smuggled in as a severity', () => {
    render(<RiskBadge severity="disease confirmed" />);

    expect(screen.getByTestId('risk-badge')).toHaveTextContent('Unrated');
  });
});

describe('safeSeverityLabel', () => {
  it('maps known severities to readable labels', () => {
    expect(safeSeverityLabel('high')).toBe('High');
    expect(safeSeverityLabel('none')).toBe('None expected');
    expect(safeSeverityLabel('moderate')).toBe('Moderate');
  });

  it('refuses any diagnosis-flavoured severity', () => {
    expect(safeSeverityLabel('confirmed')).toBe('Unrated');
    expect(safeSeverityLabel('diagnosed')).toBe('Unrated');
    expect(safeSeverityLabel('infection detected')).toBe('Unrated');
  });

  it('never returns a diagnosis claim for any input', () => {
    const hostile = [
      'disease present',
      'positively identified',
      'detected',
      'positive for blight',
      'diagnosed with blight',
    ];

    for (const value of hostile) {
      expect(safeSeverityLabel(value)).toBe('Unrated');
    }
  });
});