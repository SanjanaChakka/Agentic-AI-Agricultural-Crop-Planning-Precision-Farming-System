import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Map, MapPin, Plus, Ruler, Wheat } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { SkeletonTable } from '../components/ui/Skeleton';
import { FieldRow, FormGrid, TextArea, TextInput } from '../components/ui/Field';
import {
  useCreateFarm,
  useCreateField,
  useFarmSummary,
  useFarms,
  useFieldCounts,
  useFields,
} from '../hooks/useFarms';
import { useSelection } from '../context/SelectionContext';
import { useToast } from '../components/feedback/ToastProvider';
import type { Farm, Field } from '../api/types';
import { formatNumber, humaniseToken } from '../lib/format';

const SOIL_TYPES = [
  'black_soil',
  'red_laterite',
  'alluvial',
  'sandy_loam',
  'loam',
  'clay_loam',
  'red_soil',
];

const IRRIGATION_SOURCES = ['borewell', 'canal', 'tank', 'drip', 'rainfed', 'well', 'river'];
const WATER_AVAILABILITY = ['abundant', 'moderate', 'limited', 'seasonal', 'none'];
const CROP_STAGES = ['sowing', 'vegetative', 'flowering', 'fruit development', 'maturity', 'post-harvest'];

/**
 * Farms & Fields.
 *
 * GET /farms · GET /fields?farm_id= · GET /farms/{id}/summary · GET /fields/counts
 * POST /farms · POST /fields?farm_id=
 */
export function FarmsFieldsPage() {
  const farms = useFarms();
  const { farmId, setFarm, setField } = useSelection();
  const fields = useFields(farmId ?? undefined);
  const counts = useFieldCounts(farmId ?? undefined);
  const summary = useFarmSummary(farmId);
  const [showFarmForm, setShowFarmForm] = useState(false);
  const [showFieldForm, setShowFieldForm] = useState(false);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Farms & Fields"
        description="Register farms and the fields inside them. Every analysis page in this app is scoped to one field, so this is where the scope is established."
        actions={
          <>
            <Button
              variant="secondary"
              icon={<Plus className="h-4 w-4" aria-hidden="true" />}
              onClick={() => setShowFarmForm((value) => !value)}
            >
              Register farm
            </Button>
            <Button
              variant="primary"
              disabled={farmId === null}
              title={farmId === null ? 'Select a farm first' : undefined}
              icon={<Plus className="h-4 w-4" aria-hidden="true" />}
              onClick={() => setShowFieldForm((value) => !value)}
            >
              Add field
            </Button>
          </>
        }
      />

      {showFarmForm ? (
        <CreateFarmForm
          onDone={() => setShowFarmForm(false)}
          onCreated={(farm) => {
            setFarm(farm.id, farm);
            setShowFarmForm(false);
          }}
        />
      ) : null}

      {showFieldForm && farmId !== null ? (
        <CreateFieldForm
          farmId={farmId}
          onDone={() => setShowFieldForm(false)}
          onCreated={(field) => {
            setField(field.id, field);
            setShowFieldForm(false);
          }}
        />
      ) : null}

      <div className="grid gap-6 xl:grid-cols-5">
        <Card flush className="xl:col-span-2">
          <CardHeader
            title={`Farms (${farms.data?.length ?? 0})`}
            subtitle="Select a farm to scope the field list."
            icon={<Map className="h-4 w-4" aria-hidden="true" />}
          />
          {farms.isLoading ? (
            <SkeletonTable rows={3} columns={2} />
          ) : farms.error ? (
            <ErrorBanner
              className="m-5"
              title="Could not load farms"
              error={farms.error}
              onRetry={() => void farms.refetch()}
            />
          ) : (farms.data?.length ?? 0) === 0 ? (
            <div className="p-5">
              <EmptyState
                title="No farms registered"
                description="Register the first farm to start collecting field data."
                icon={<Map className="h-5 w-5" aria-hidden="true" />}
              />
            </div>
          ) : (
            <ul className="divide-y divide-slate-100" data-testid="farm-list">
              {farms.data?.map((farm) => (
                <li key={farm.id}>
                  <button
                    type="button"
                    onClick={() => setFarm(farm.id, farm)}
                    aria-pressed={farmId === farm.id}
                    className={`flex w-full items-start gap-3 px-5 py-4 text-left transition-colors hover:bg-slate-50 ${
                      farmId === farm.id ? 'bg-brand-50/60' : ''
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 text-sm font-medium text-slate-900">
                        {farm.name}
                        {farmId === farm.id ? <Badge tone="brand">Selected</Badge> : null}
                      </p>
                      <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                        <MapPin className="h-3 w-3" aria-hidden="true" />
                        {farm.location_name}
                        {farm.state ? `, ${farm.state}` : ''}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-400">
                        {farm.owner_name} · {formatNumber(farm.field_count ?? 0, 0)} fields ·{' '}
                        {formatNumber(farm.total_registered_area_ha ?? 0, 1)} ha registered
                      </p>
                    </div>
                    <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-slate-300" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-6 xl:col-span-3">
          {summary.data ? (
            <Card>
              <CardHeader
                title={`${summary.data.farm_name} summary`}
                subtitle={summary.data.location_name}
              />
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
                <SummaryStat label="Fields" value={formatNumber(summary.data.field_count, 0)} />
                <SummaryStat label="Area" value={`${formatNumber(summary.data.total_area_ha, 1)} ha`} />
                <SummaryStat
                  label="With soil"
                  value={formatNumber(summary.data.fields_with_soil_data, 0)}
                />
                <SummaryStat
                  label="With sensors"
                  value={formatNumber(summary.data.fields_with_sensors, 0)}
                />
                <SummaryStat
                  label="Open alerts"
                  value={formatNumber(summary.data.open_alert_count, 0)}
                />
              </div>
            </Card>
          ) : null}

          <Card flush>
            <CardHeader
              title={
                farmId === null
                  ? 'Fields'
                  : `Fields in the selected farm (${fields.data?.length ?? 0})`
              }
              subtitle={
                farmId === null
                  ? 'Select a farm to list its fields.'
                  : counts.data
                    ? `${formatNumber(counts.data.field_count, 0)} fields · ${formatNumber(counts.data.total_area_ha, 1)} ha`
                    : undefined
              }
              icon={<Wheat className="h-4 w-4" aria-hidden="true" />}
            />
            {farmId === null ? (
              <div className="p-5">
                <EmptyState
                  title="Select a farm"
                  description="Fields are listed per farm. Choose one on the left to continue."
                  icon={<Wheat className="h-5 w-5" aria-hidden="true" />}
                />
              </div>
            ) : fields.isLoading ? (
              <SkeletonTable rows={4} columns={5} />
            ) : fields.error ? (
              <ErrorBanner
                className="m-5"
                title="Could not load fields"
                error={fields.error}
                onRetry={() => void fields.refetch()}
              />
            ) : (fields.data?.length ?? 0) === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No fields in this farm"
                  description="Add a field to begin collecting soil, sensor and weather data."
                  icon={<Wheat className="h-5 w-5" aria-hidden="true" />}
                />
              </div>
            ) : (
              <DataTable<Field>
                columns={[
                  {
                    key: 'code',
                    header: 'Code',
                    render: (field) => (
                      <span className="font-mono text-xs font-medium text-slate-800">
                        {field.field_code}
                      </span>
                    ),
                  },
                  {
                    key: 'name',
                    header: 'Field',
                    render: (field) => (
                      <div className="min-w-0">
                        <Link
                          to={`/fields/${field.id}`}
                          className="text-sm font-medium text-brand-800 underline-offset-2 hover:underline"
                        >
                          {field.name}
                        </Link>
                        <p className="mt-0.5 text-[11px] text-slate-500">
                          {humaniseToken(field.soil_type)} · {formatNumber(field.area_ha, 2)} ha
                        </p>
                      </div>
                    ),
                  },
                  {
                    key: 'crop',
                    header: 'Crop',
                    render: (field) => (
                      <div>
                        <p className="text-xs text-slate-700">
                          {humaniseToken(field.proposed_crop ?? 'not set')}
                        </p>
                        <p className="text-[11px] text-slate-400">
                          {humaniseToken(field.crop_stage ?? 'stage unknown')}
                        </p>
                      </div>
                    ),
                  },
                  {
                    key: 'water',
                    header: 'Water',
                    render: (field) => (
                      <div>
                        <p className="text-xs text-slate-700">
                          {humaniseToken(field.irrigation_source ?? 'unknown')}
                        </p>
                        <p className="text-[11px] text-slate-400">
                          {humaniseToken(field.water_availability ?? 'unknown')}
                          {field.water_availability_m3_per_day
                            ? ` · ${formatNumber(field.water_availability_m3_per_day, 0)} m3/day`
                            : ''}
                        </p>
                      </div>
                    ),
                  },
                  {
                    key: 'actions',
                    header: '',
                    className: 'w-24 text-right',
                    headerClassName: 'w-24 text-right',
                    render: (field) => (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setFarm(field.farm_id);
                          setField(field.id, field);
                        }}
                      >
                        Select
                      </Button>
                    ),
                  },
                ]}
                rows={fields.data ?? []}
                rowKey={(field) => field.id}
                dense
              />
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="label-caps">{label}</p>
      <p className="tabular mt-1 text-lg font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function CreateFarmForm({
  onDone,
  onCreated,
}: {
  onDone: () => void;
  onCreated: (farm: Farm) => void;
}) {
  const createFarm = useCreateFarm();
  const toast = useToast();
  const [form, setForm] = useState({
    name: '',
    owner_name: '',
    location_name: '',
    village: '',
    district: '',
    state: '',
    total_area_ha: '',
    latitude: '',
    longitude: '',
    notes: '',
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    createFarm.mutate(
      {
        name: form.name.trim(),
        owner_name: form.owner_name.trim(),
        location_name: form.location_name.trim(),
        village: form.village.trim() || null,
        district: form.district.trim() || null,
        state: form.state.trim() || null,
        total_area_ha: form.total_area_ha ? Number(form.total_area_ha) : null,
        latitude: form.latitude ? Number(form.latitude) : null,
        longitude: form.longitude ? Number(form.longitude) : null,
        notes: form.notes.trim() || null,
      },
      {
        onSuccess: (farm) => {
          toast.push({ tone: 'success', title: 'Farm registered', message: farm.name });
          setForm({
            name: '',
            owner_name: '',
            location_name: '',
            village: '',
            district: '',
            state: '',
            total_area_ha: '',
            latitude: '',
            longitude: '',
            notes: '',
          });
          onCreated(farm);
        },
        onError: (error) => toast.pushError(error, 'Could not register the farm'),
      },
    );
  };

  return (
    <Card>
      <CardHeader
        title="Register a farm"
        subtitle="POST /farms - name, owner and location are required."
        icon={<Map className="h-4 w-4" aria-hidden="true" />}
        actions={
          <Button size="sm" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        }
      />
      <form onSubmit={submit} className="space-y-4 p-5">
        {createFarm.error ? <ErrorBanner title="Registration failed" error={createFarm.error} /> : null}
        <FormGrid>
          <FieldRow label="Farm name" required>
            {(id) => (
              <TextInput
                id={id}
                required
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Ravi Kisan Farms"
              />
            )}
          </FieldRow>
          <FieldRow label="Owner name" required>
            {(id) => (
              <TextInput
                id={id}
                required
                value={form.owner_name}
                onChange={(event) => setForm({ ...form, owner_name: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow label="Location name" required>
            {(id) => (
              <TextInput
                id={id}
                required
                value={form.location_name}
                onChange={(event) => setForm({ ...form, location_name: event.target.value })}
                placeholder="Raichur, Karnataka"
              />
            )}
          </FieldRow>
          <FieldRow label="Village">
            {(id) => (
              <TextInput
                id={id}
                value={form.village}
                onChange={(event) => setForm({ ...form, village: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow label="District">
            {(id) => (
              <TextInput
                id={id}
                value={form.district}
                onChange={(event) => setForm({ ...form, district: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow label="State">
            {(id) => (
              <TextInput
                id={id}
                value={form.state}
                onChange={(event) => setForm({ ...form, state: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow label="Total area (ha)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.01"
                min="0"
                value={form.total_area_ha}
                onChange={(event) => setForm({ ...form, total_area_ha: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow
            label="Latitude"
            hint="Optional. Every field on this farm inherits it when the field has no coordinates of its own."
          >
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.01"
                min="-90"
                max="90"
                value={form.latitude}
                placeholder="16.99"
                onChange={(event) => setForm({ ...form, latitude: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow label="Longitude" hint="Optional. Both coordinates must be set together.">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.01"
                min="-180"
                max="180"
                value={form.longitude}
                placeholder="82.25"
                onChange={(event) => setForm({ ...form, longitude: event.target.value })}
              />
            )}
          </FieldRow>
        </FormGrid>
        <FieldRow label="Notes">
          {(id) => (
            <TextArea
              id={id}
              value={form.notes}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
              placeholder="Irrigation infrastructure, cropping history, anything a reviewer should know."
            />
          )}
        </FieldRow>
        <div className="flex justify-end">
          <Button type="submit" variant="primary" loading={createFarm.isPending}>
            Register farm
          </Button>
        </div>
      </form>
    </Card>
  );
}

function CreateFieldForm({
  farmId,
  onDone,
  onCreated,
}: {
  farmId: number;
  onDone: () => void;
  onCreated: (field: Field) => void;
}) {
  const createField = useCreateField();
  const toast = useToast();
  const [form, setForm] = useState({
    field_code: '',
    name: '',
    area_ha: '',
    soil_type: SOIL_TYPES[0],
    previous_crop: '',
    proposed_crop: '',
    crop_stage: CROP_STAGES[0],
    irrigation_source: IRRIGATION_SOURCES[0],
    water_availability: WATER_AVAILABILITY[1],
    water_availability_m3_per_day: '',
    latitude: '',
    longitude: '',
    notes: '',
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    createField.mutate(
      {
        farmId,
        payload: {
          field_code: form.field_code.trim(),
          name: form.name.trim(),
          area_ha: Number(form.area_ha),
          soil_type: form.soil_type,
          previous_crop: form.previous_crop.trim() || null,
          proposed_crop: form.proposed_crop.trim() || null,
          crop_stage: form.crop_stage,
          irrigation_source: form.irrigation_source,
          water_availability: form.water_availability,
          water_availability_m3_per_day: form.water_availability_m3_per_day
            ? Number(form.water_availability_m3_per_day)
            : null,
          latitude: form.latitude ? Number(form.latitude) : null,
          longitude: form.longitude ? Number(form.longitude) : null,
          notes: form.notes.trim() || null,
        },
      },
      {
        onSuccess: (field) => {
          toast.push({ tone: 'success', title: 'Field added', message: field.name });
          onCreated(field);
        },
        onError: (error) => toast.pushError(error, 'Could not add the field'),
      },
    );
  };

  return (
    <Card>
      <CardHeader
        title="Add a field"
        subtitle={`POST /fields?farm_id=${farmId} - field code, name, area and soil type are required.`}
        icon={<Ruler className="h-4 w-4" aria-hidden="true" />}
        actions={
          <Button size="sm" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        }
      />
      <form onSubmit={submit} className="space-y-4 p-5">
        {createField.error ? (
          <ErrorBanner title="Could not add the field" error={createField.error} />
        ) : null}
        <FormGrid>
          <FieldRow label="Field code" required>
            {(id) => (
              <TextInput
                id={id}
                required
                value={form.field_code}
                onChange={(event) => setForm({ ...form, field_code: event.target.value })}
                placeholder="RKF-04"
              />
            )}
          </FieldRow>
          <FieldRow label="Field name" required>
            {(id) => (
              <TextInput
                id={id}
                required
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow label="Area (ha)" required>
            {(id) => (
              <TextInput
                id={id}
                required
                type="number"
                step="0.01"
                min="0.01"
                value={form.area_ha}
                onChange={(event) => setForm({ ...form, area_ha: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow label="Soil type" required>
            {(id) => (
              <TextInput
                id={id}
                list="soil-types"
                required
                value={form.soil_type}
                onChange={(event) => setForm({ ...form, soil_type: event.target.value })}
              />
            )}
          </FieldRow>
          <datalist id="soil-types">
            {SOIL_TYPES.map((type) => (
              <option key={type} value={type} />
            ))}
          </datalist>
          <FieldRow label="Previous crop">
            {(id) => (
              <TextInput
                id={id}
                value={form.previous_crop}
                onChange={(event) => setForm({ ...form, previous_crop: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow
            label="Latitude"
            hint="Optional. With longitude it unlocks the forecast; without it weather falls back to offline climatology."
          >
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.01"
                min="-90"
                max="90"
                value={form.latitude}
                placeholder="16.99"
                onChange={(event) => setForm({ ...form, latitude: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow label="Longitude" hint="Optional. Both coordinates must be set together.">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.01"
                min="-180"
                max="180"
                value={form.longitude}
                placeholder="82.25"
                onChange={(event) => setForm({ ...form, longitude: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow label="Proposed crop">
            {(id) => (
              <TextInput
                id={id}
                value={form.proposed_crop}
                onChange={(event) => setForm({ ...form, proposed_crop: event.target.value })}
              />
            )}
          </FieldRow>
          <FieldRow label="Crop stage">
            {(id) => (
              <TextInput
                id={id}
                list="crop-stages"
                value={form.crop_stage}
                onChange={(event) => setForm({ ...form, crop_stage: event.target.value })}
              />
            )}
          </FieldRow>
          <datalist id="crop-stages">
            {CROP_STAGES.map((stage) => (
              <option key={stage} value={stage} />
            ))}
          </datalist>
          <FieldRow label="Irrigation source">
            {(id) => (
              <TextInput
                id={id}
                list="irrigation-sources"
                value={form.irrigation_source}
                onChange={(event) => setForm({ ...form, irrigation_source: event.target.value })}
              />
            )}
          </FieldRow>
          <datalist id="irrigation-sources">
            {IRRIGATION_SOURCES.map((source) => (
              <option key={source} value={source} />
            ))}
          </datalist>
          <FieldRow label="Water availability">
            {(id) => (
              <TextInput
                id={id}
                list="water-availability"
                value={form.water_availability}
                onChange={(event) => setForm({ ...form, water_availability: event.target.value })}
              />
            )}
          </FieldRow>
          <datalist id="water-availability">
            {WATER_AVAILABILITY.map((level) => (
              <option key={level} value={level} />
            ))}
          </datalist>
          <FieldRow label="Water available (m3/day)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                min="0"
                value={form.water_availability_m3_per_day}
                onChange={(event) =>
                  setForm({ ...form, water_availability_m3_per_day: event.target.value })
                }
              />
            )}
          </FieldRow>
        </FormGrid>
        <FieldRow label="Notes">
          {(id) => (
            <TextArea
              id={id}
              value={form.notes}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
            />
          )}
        </FieldRow>
        <div className="flex justify-end">
          <Button type="submit" variant="primary" loading={createField.isPending}>
            Add field
          </Button>
        </div>
      </form>
    </Card>
  );
}

export default FarmsFieldsPage;