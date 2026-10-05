import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DataSourceLabel } from './DataSourceLabel';
import { SimulatedBanner } from './SimulatedBanner';

/**
 * These two components carry the "never present invented data as live" promise
 * into the browser, so they are asserted by rendering rather than by unit test:
 * a fallback number that is not visibly labelled is indistinguishable from a
 * measurement once it reaches a farmer.
 */
describe('SimulatedBanner', () => {
  it('renders nothing when the data is live', () => {
    const { container } = render(<SimulatedBanner isSimulated={false} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('simulated-banner')).not.toBeInTheDocument();
  });

  it('renders an alert banner when the backend served fallback data', () => {
    render(<SimulatedBanner isSimulated />);

    const banner = screen.getByTestId('simulated-banner');
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveAttribute('role', 'alert');
  });

  it('says the numbers are not live data', () => {
    render(<SimulatedBanner isSimulated subject="weather" />);

    expect(screen.getByText(/not live data/i)).toBeInTheDocument();
    expect(screen.getByText(/Simulated \/ fallback weather/i)).toBeInTheDocument();
  });

  it('states that the values are not measurements from this field', () => {
    render(<SimulatedBanner isSimulated />);

    expect(screen.getByText(/not measurements from this field/i)).toBeInTheDocument();
  });

  it('surfaces the backend fallback reason when given one', () => {
    render(<SimulatedBanner isSimulated detail="no API key configured" />);

    expect(screen.getByText('no API key configured')).toBeInTheDocument();
  });
});

describe('DataSourceLabel', () => {
  it('always names the provider', () => {
    render(<DataSourceLabel source="open-meteo" provider="Open-Meteo (live)" />);

    expect(screen.getByText('Open-Meteo (live)')).toBeInTheDocument();
    expect(screen.getByText('(open-meteo)')).toBeInTheDocument();
  });

  it('marks live provider data as live', () => {
    render(<DataSourceLabel source="open-meteo" provider="Open-Meteo" isSimulated={false} />);

    expect(screen.getByTestId('data-source-mode')).toHaveTextContent('Live provider data');
  });

  it('marks fallback data as simulated rather than live', () => {
    render(
      <DataSourceLabel source="offline-climatology" provider="Offline climatology" isSimulated fallbackUsed />,
    );

    expect(screen.getByTestId('data-source-mode')).toHaveTextContent(
      'Simulated fallback - not live provider data',
    );
    expect(screen.getByText('fallback_used: true')).toBeInTheDocument();
  });

  it('never shows the live label for a simulated bundle', () => {
    render(<DataSourceLabel source="offline-climatology" provider="Offline climatology" isSimulated />);

    expect(screen.queryByText('Live provider data')).not.toBeInTheDocument();
  });

  it('treats a missing is_simulated flag as simulated, not live', () => {
    render(<DataSourceLabel source="offline-climatology" provider="Offline climatology" />);

    expect(screen.getByTestId('data-source-mode')).toHaveTextContent(/simulated/i);
  });

  it('falls back to an explicit "unknown provider" rather than a blank', () => {
    render(<DataSourceLabel source={null} provider={null} />);

    expect(screen.getByText('unknown provider')).toBeInTheDocument();
  });
});