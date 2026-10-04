import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { SkeletonBlock } from '../components/ui/Skeleton';
import { FieldRow, FormGrid, TextArea, TextInput } from '../components/ui/Field';
import { useField, useUpdateField } from '../hooks/useFarms';
import { useToast } from '../components/feedback/ToastProvider';
import type { FieldUpdate } from '../api/types';

const optionalNumber = (value: string): number | null => (value.trim() === '' ? null : Number(value));
const optionalString = (value: string): string | null => (value.trim() === '' ? null : value.trim());

/**
 * Edit a field. `PATCH /fields/{field_id}` - only the fields the reviewer
 * actually changed are sent, so untouched values are never overwritten.
 */
export function FieldEditPage() {
  const { fieldId: fieldIdParam } = useParams();
  const fieldId = fieldIdParam ? Number(fieldIdParam) : null;
  const navigate = useNavigate();
  const toast = useToast();
  const field = useField(fieldId);
  const updateFieldMutation = useUpdateField();

  const [form, setForm] = useState<Record<string, string>>({});
  const [loadedFor, setLoadedFor] = useState<number | null>(null);

  useEffect(() => {
    const data = field.data;
    if (!data || data.id === loadedFor) return;
    setForm({
      field_code: data.field_code ?? '',
      name: data.name ?? '',
      area_ha: data.area_ha !== null && data.area_ha !== undefined ? String(data.area_ha) : '',
      soil_type: data.soil_type ?? '',
      previous_crop: data.previous_crop ?? '',
      proposed_crop: data.proposed_crop ?? '',
      crop_stage: data.crop_stage ?? '',
      planting_window_start: data.planting_window_start ?? '',
      irrigation_source: data.irrigation_source ?? '',
      water_availability: data.water_availability ?? '',
      water_availability_m3_per_day:
        data.water_availability_m3_per_day !== null && data.water_availability_m3_per_day !== undefined
          ? String(data.water_availability_m3_per_day)
          : '',
      notes: data.notes ?? '',
    });
    setLoadedFor(data.id);
  }, [field.data, loadedFor]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (fieldId === null) return;

    const payload: FieldUpdate = {
      field_code: form.field_code.trim(),
      name: form.name.trim(),
      area_ha: Number(form.area_ha),
      soil_type: form.soil_type.trim(),
      previous_crop: optionalString(form.previous_crop),
      proposed_crop: optionalString(form.proposed_crop),
      crop_stage: form.crop_stage.trim(),
      planting_window_start: optionalString(form.planting_window_start),
      irrigation_source: form.irrigation_source.trim(),
      water_availability: form.water_availability.trim(),
      water_availability_m3_per_day: optionalNumber(form.water_availability_m3_per_day),
      notes: optionalString(form.notes),
    };

    updateFieldMutation.mutate(
      { fieldId, payload },
      {
        onSuccess: (updated) => {
          toast.push({ tone: 'success', title: 'Field updated', message: updated.name });
          navigate(`/fields/${updated.id}`);
        },
        onError: (error) => toast.pushError(error, 'Could not update the field'),
      },
    );
  };

  if (field.isLoading) {
    return (
      <div>
        <PageHeader title="Edit field" />
        <Card>
          <SkeletonBlock lines={6} />
        </Card>
      </div>
    );
  }

  if (field.error) {
    return (
      <div>
        <PageHeader title="Edit field" />
        <ErrorBanner
          title="Could not load this field"
          error={field.error}
          onRetry={() => void field.refetch()}
        />
      </div>
    );
  }

  if (!field.data || fieldId === null) {
    return (
      <div>
        <PageHeader title="Edit field" />
        <ErrorBanner title="Field not found" error={new Error(`No field with id ${fieldId}.`)} />
      </div>
    );
  }

  const set = (key: string) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={field.data.field_code}
        title={`Edit ${field.data.name}`}
        description={`PATCH /fields/${fieldId}`}
        actions={
          <Link to={`/fields/${fieldId}`}>
            <Button variant="ghost" icon={<ArrowLeft className="h-4 w-4" aria-hidden="true" />}>
              Back to field
            </Button>
          </Link>
        }
      />

      <Card>
        <CardHeader title="Field details" subtitle="Changes take effect on the next assessment." />
        <form onSubmit={submit} className="space-y-5 p-5">
          {updateFieldMutation.error ? (
            <ErrorBanner title="Update failed" error={updateFieldMutation.error} />
          ) : null}
          <FormGrid>
            <FieldRow label="Field code" required>
              {(id) => (
                <TextInput id={id} required value={form.field_code ?? ''} onChange={set('field_code')} />
              )}
            </FieldRow>
            <FieldRow label="Field name" required>
              {(id) => <TextInput id={id} required value={form.name ?? ''} onChange={set('name')} />}
            </FieldRow>
            <FieldRow label="Area (ha)" required>
              {(id) => (
                <TextInput
                  id={id}
                  required
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={form.area_ha ?? ''}
                  onChange={set('area_ha')}
                />
              )}
            </FieldRow>
            <FieldRow label="Soil type" required>
              {(id) => (
                <TextInput id={id} required value={form.soil_type ?? ''} onChange={set('soil_type')} />
              )}
            </FieldRow>
            <FieldRow label="Previous crop">
              {(id) => (
                <TextInput
                  id={id}
                  value={form.previous_crop ?? ''}
                  onChange={set('previous_crop')}
                />
              )}
            </FieldRow>
            <FieldRow label="Proposed crop">
              {(id) => (
                <TextInput
                  id={id}
                  value={form.proposed_crop ?? ''}
                  onChange={set('proposed_crop')}
                />
              )}
            </FieldRow>
            <FieldRow label="Crop stage">
              {(id) => (
                <TextInput id={id} value={form.crop_stage ?? ''} onChange={set('crop_stage')} />
              )}
            </FieldRow>
            <FieldRow label="Planting window start" hint="ISO date or datetime, e.g. 2026-11-01.">
              {(id) => (
                <TextInput
                  id={id}
                  value={form.planting_window_start ?? ''}
                  onChange={set('planting_window_start')}
                />
              )}
            </FieldRow>
            <FieldRow label="Irrigation source">
              {(id) => (
                <TextInput
                  id={id}
                  value={form.irrigation_source ?? ''}
                  onChange={set('irrigation_source')}
                />
              )}
            </FieldRow>
            <FieldRow label="Water availability">
              {(id) => (
                <TextInput
                  id={id}
                  value={form.water_availability ?? ''}
                  onChange={set('water_availability')}
                />
              )}
            </FieldRow>
            <FieldRow label="Daily water available (m3)">
              {(id) => (
                <TextInput
                  id={id}
                  type="number"
                  min="0"
                  value={form.water_availability_m3_per_day ?? ''}
                  onChange={set('water_availability_m3_per_day')}
                />
              )}
            </FieldRow>
          </FormGrid>
          <FieldRow label="Notes">
            {(id) => <TextArea id={id} value={form.notes ?? ''} onChange={set('notes')} />}
          </FieldRow>
          <div className="flex justify-end gap-2">
            <Link to={`/fields/${fieldId}`}>
              <Button variant="secondary">Cancel</Button>
            </Link>
            <Button
              type="submit"
              variant="primary"
              loading={updateFieldMutation.isPending}
              icon={<Save className="h-4 w-4" aria-hidden="true" />}
            >
              Save changes
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

export default FieldEditPage;