/**
 * TypeScript mirrors of the FastAPI OpenAPI schemas.
 *
 * Source of truth: `api-contract.json` (OpenAPI 3.1, 67 schemas) served by the
 * backend. Field names match the wire format exactly - the backend uses
 * snake_case and so do we, which keeps the mapping layer trivially auditable.
 */

/* ------------------------------------------------------------------ */
/* Primitives                                                          */
/* ------------------------------------------------------------------ */

/** `SourceKind` - the provenance tag carried by every piece of evidence. */
export const EVIDENCE_KINDS = [
  'measured',
  'observed',
  'forecast',
  'retrieved_reference',
  'rule',
  'ml_prediction',
  'llm_narrative',
  'deterministic_narrative',
  'user_input',
  'simulated',
] as const;

export type EvidenceKind = (typeof EVIDENCE_KINDS)[number];

/** A single, provenance-tagged fact used to justify a recommendation. */
export interface Evidence {
  label: string;
  value?: string | number | boolean | null;
  kind: EvidenceKind;
  unit?: string | null;
  source?: string | null;
  reference?: string | null;
  note?: string | null;
  observed_at?: string | null;
}

/** Citation for retrieved reference material or an upstream data provider. */
export interface SourceReference {
  doc_key: string;
  title: string;
  category?: string;
  organisation?: string;
  url?: string | null;
  region?: string | null;
  score?: number | null;
  excerpt?: string | null;
}

export interface HealthComponent {
  name: string;
  status: string;
  detail?: string | null;
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  environment: string;
  database: string;
  ml: string;
  rag: string;
  weather_provider: string;
  llm_provider: string;
  components?: HealthComponent[];
  timestamp: string;
}

export interface Page {
  total: number;
  limit: number;
  offset: number;
}

/* ------------------------------------------------------------------ */
/* Farms and fields                                                    */
/* ------------------------------------------------------------------ */

export interface Farm {
  id: number;
  name: string;
  owner_name: string;
  location_name: string;
  latitude?: number | null;
  longitude?: number | null;
  village?: string | null;
  district?: string | null;
  state?: string | null;
  total_area_ha?: number | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
  /** Aggregates added by the list/detail endpoints. */
  field_count?: number;
  total_registered_area_ha?: number;
}

export interface FarmWithFields extends Farm {
  fields: Field[];
}

export interface FarmSummary {
  farm_id: number;
  farm_name: string;
  location_name: string;
  field_count: number;
  total_area_ha: number;
  fields_with_soil_data: number;
  fields_with_sensors: number;
  open_alert_count: number;
  pending_approval_count: number;
  latest_workflow_status?: string | null;
  last_observation_at?: string | null;
}

export interface FarmCreate {
  name: string;
  owner_name: string;
  location_name: string;
  latitude?: number | null;
  longitude?: number | null;
  village?: string | null;
  district?: string | null;
  state?: string | null;
  total_area_ha?: number | null;
  notes?: string | null;
}

export interface FarmUpdate {
  name?: string | null;
  owner_name?: string | null;
  location_name?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  village?: string | null;
  district?: string | null;
  state?: string | null;
  total_area_ha?: number | null;
  notes?: string | null;
}

export interface Field {
  id: number;
  farm_id: number;
  field_code: string;
  name: string;
  area_ha: number;
  soil_type: string;
  latitude?: number | null;
  longitude?: number | null;
  effective_latitude?: number | null;
  effective_longitude?: number | null;
  previous_crop?: string | null;
  proposed_crop?: string | null;
  crop_stage?: string;
  planting_window_start?: string | null;
  irrigation_source?: string;
  water_availability?: string;
  water_availability_m3_per_day?: number | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface FieldCreate {
  field_code: string;
  name: string;
  area_ha: number;
  soil_type: string;
  latitude?: number | null;
  longitude?: number | null;
  previous_crop?: string | null;
  proposed_crop?: string | null;
  crop_stage?: string;
  planting_window_start?: string | null;
  irrigation_source?: string;
  water_availability?: string;
  water_availability_m3_per_day?: number | null;
  notes?: string | null;
}

export type FieldUpdate = Partial<Omit<FieldCreate, never>>;

export interface FieldCounts {
  field_count: number;
  total_area_ha: number;
  by_soil_type?: Record<string, number>;
}

/* ------------------------------------------------------------------ */
/* Dashboard                                                           */
/* ------------------------------------------------------------------ */

export interface DashboardRunSummary {
  id: number;
  field_id: number;
  crop?: string | null;
  status: string;
  agents_invoked: string[];
  duration_ms?: number | null;
  created_at: string;
}

export interface AgentInfo {
  name: string;
  responsibility: string;
  class?: string;
}

export interface RagDocumentSummary {
  doc_key: string;
  title: string;
  category: string;
  organisation?: string;
  source_url?: string | null;
  region?: string | null;
  year?: string | null;
  path?: string | null;
}

export interface DashboardResponse {
  generated_at: string;
  farms: number;
  fields: number;
  total_area_ha: number;
  soil_observations: number;
  sensor_readings: number;
  simulated_readings: number;
  open_alerts: number;
  pending_approvals: number;
  planned_activities: number;
  workflow_runs: {
    total: number;
    completed: number;
    recent: DashboardRunSummary[];
  };
  agents: AgentInfo[];
  components: {
    database: string;
    rag: {
      available: boolean;
      backend: string;
      documents: RagDocumentSummary[];
      chunks: number;
    };
    ml: { available: boolean; models: string[] };
    llm_configured: boolean;
  };
}

/* ------------------------------------------------------------------ */
/* Alerts                                                              */
/* ------------------------------------------------------------------ */

export const ALERT_STATUSES = ['open', 'acknowledged', 'resolved'] as const;
export type AlertStatus = (typeof ALERT_STATUSES)[number];

export interface Alert {
  id: number;
  farm_id: number;
  field_id: number;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  evidence: Evidence[];
  fingerprint: string;
  severity_rank: number;
  status: string;
  occurrence_count: number;
  triggered_at: string;
  last_observed_at: string;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  resolved_at?: string | null;
}

export interface AlertUpdate {
  status: AlertStatus;
  acknowledged_by?: string | null;
  note?: string | null;
}

export interface DedupPolicy {
  key: string;
  behaviour: string;
  auto_resolve: string;
}

/* ------------------------------------------------------------------ */
/* Soil                                                                */
/* ------------------------------------------------------------------ */

export interface SoilObservation {
  id: number;
  field_id: number;
  observed_at: string;
  sample_depth_cm?: number | null;
  soil_type?: string | null;
  ph?: number | null;
  nitrogen_available_kg_ha?: number | null;
  phosphorus_available_kg_ha?: number | null;
  potassium_available_kg_ha?: number | null;
  organic_carbon_percent?: number | null;
  soil_moisture_percent?: number | null;
  electrical_conductivity_ds_m?: number | null;
  data_source: string;
  lab_name?: string | null;
  notes?: string | null;
  created_at: string;
  missing_parameters?: string[];
}

export interface SoilRecommendation {
  action: string;
  detail: string;
  priority?: string | null;
  basis?: string | null;
}

export interface SoilInterpretation {
  id: number;
  soil_observation_id: number;
  agent_name: string;
  generated_by: string;
  ph_class: string;
  nutrient_status: Record<string, string>;
  organic_matter_status: string;
  summary: string;
  limitations: string[];
  recommendations: SoilRecommendation[];
  missing_parameters: string[];
  evidence: Evidence[];
  sources: SourceReference[];
  confidence?: number | null;
}

export interface SoilAnalysisResponse {
  observation: SoilObservation;
  interpretation?: SoilInterpretation | null;
  measured_values_note: string;
}

export interface SoilObservationCreate {
  field_id?: number | null;
  observed_at?: string | null;
  sample_depth_cm?: number | null;
  soil_type?: string | null;
  ph?: number | null;
  nitrogen_available_kg_ha?: number | null;
  phosphorus_available_kg_ha?: number | null;
  potassium_available_kg_ha?: number | null;
  organic_carbon_percent?: number | null;
  soil_moisture_percent?: number | null;
  electrical_conductivity_ds_m?: number | null;
  data_source: string;
  lab_name?: string | null;
  notes?: string | null;
}

export interface RatingBand {
  low_max: number;
  medium_max: number;
}

export interface SoilThresholds {
  nitrogen_available_kg_ha: RatingBand;
  phosphorus_available_kg_ha: RatingBand;
  potassium_available_kg_ha: RatingBand;
  organic_carbon_percent: RatingBand;
  ph_classes: Record<string, string>;
}

/* ------------------------------------------------------------------ */
/* Weather                                                             */
/* ------------------------------------------------------------------ */

export interface WeatherCurrent {
  observed_at?: string | null;
  temperature_c?: number | null;
  feels_like_c?: number | null;
  humidity_percent?: number | null;
  wind_speed_ms?: number | null;
  wind_direction_deg?: number | null;
  condition?: string | null;
}

export interface WeatherDay {
  forecast_date: string;
  temp_min_c?: number | null;
  temp_max_c?: number | null;
  temperature_mean_c?: number | null;
  precipitation_mm?: number | null;
  precipitation_probability_percent?: number | null;
  humidity_percent?: number | null;
  wind_speed_ms?: number | null;
  et0_mm?: number | null;
  condition?: string | null;
}

export interface WeatherBundle {
  field_id?: number | null;
  location_name?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  source: string;
  provider: string;
  is_simulated: boolean;
  fetched_at: string;
  current?: WeatherCurrent | null;
  daily: WeatherDay[];
  total_precipitation_mm: number;
  rainfall_next_3_days_mm: number;
  max_temp_c?: number | null;
  min_temp_c?: number | null;
  mean_humidity_percent?: number | null;
  total_et0_mm: number;
  notes: string[];
  fallback_used: boolean;
}

export interface WeatherEvidenceResponse {
  evidence?: Evidence[];
  sources?: SourceReference[];
  [key: string]: unknown;
}

/* ------------------------------------------------------------------ */
/* Sensors                                                             */
/* ------------------------------------------------------------------ */

export interface SensorReading {
  id: number;
  field_id: number;
  sensor_id: string;
  recorded_at: string;
  soil_moisture_percent?: number | null;
  soil_temperature_c?: number | null;
  air_humidity_percent?: number | null;
  air_temperature_c?: number | null;
  battery_percent?: number | null;
  is_simulated: boolean;
  quality_flags: string[];
  notes?: string | null;
}

export interface SensorTrendPoint {
  recorded_at: string;
  soil_moisture_percent?: number | null;
  soil_temperature_c?: number | null;
  air_humidity_percent?: number | null;
}

export interface LiveSoilSyncResponse {
  field_id: number;
  sensor_id: string;
  readings_created: number;
  replaced_readings: number;
  replaced_simulated_readings: number;
  dropped_future_hours: number;
  simulated: boolean;
  source: string;
  caveat: string;
  start_at: string;
  end_at: string;
  summary: Record<string, number | string | null>;
}

export interface SensorTrend {
  field_id: number;
  sensor_id?: string | null;
  points: SensorTrendPoint[];
  statistics: {
    sample_count: number;
    moisture_mean?: number | null;
    moisture_min?: number | null;
    moisture_max?: number | null;
    moisture_change_over_window?: number | null;
    soil_temperature_mean?: number | null;
    air_humidity_mean?: number | null;
    simulated_sample_count?: number | null;
  };
  quality_issue_count: number;
  latest_reading?: SensorReading | null;
}

export interface SensorQualityReport {
  field_id: number;
  available: boolean;
  sensor_id?: string | null;
  recorded_at?: string | null;
  quality_flags: string[];
  faults: unknown[];
  is_simulated: boolean;
  verdict: string;
  note?: string | null;
}

export interface SensorSimulationRequest {
  hours?: number;
  interval_hours?: number;
  sensor_id?: string;
  seed?: number | null;
  start_at?: string | null;
  initial_soil_moisture_percent?: number | null;
  rainfall_events?: boolean;
  inject_fault?: boolean;
  /**
   * Delete this sensor's existing simulated rows in the window first. Required by
   * the backend when simulated telemetry already overlaps, otherwise it returns 409.
   */
  replace_existing?: boolean;
}

export interface SensorSimulationResponse {
  field_id: number;
  sensor_id: string;
  readings_created: number;
  simulated?: boolean;
  start_at: string;
  end_at: string;
  readings: SensorReading[];
  summary: Record<string, unknown>;
}

/* ------------------------------------------------------------------ */
/* Crop suitability                                                    */
/* ------------------------------------------------------------------ */

export interface FactorScore {
  factor: string;
  label: string;
  verdict: string;
  score?: number | null;
  weight: number;
  detail: string;
  measured_value?: string | number | null;
  required_range?: string | null;
}

export interface Suitability {
  id: number;
  field_id: number;
  workflow_run_id?: number | null;
  crop: string;
  status: string;
  score?: number | null;
  confidence?: number | null;
  factor_scores: FactorScore[];
  favorable_factors: string[];
  limiting_factors: string[];
  missing_information: string[];
  requirements_used: Record<string, unknown>;
  evidence: Evidence[];
  sources: SourceReference[];
  narrative?: string | null;
  generated_by: string;
  created_at: string;
  /** Present on the condensed `run summary` embedding only. */
  evaluated_weight?: number;
}

export interface SuitabilityRequest {
  crop?: string | null;
  soil_observation_id?: number | null;
  include_evidence?: boolean;
}

export interface CropRequirement {
  name: string;
  aliases?: string[];
  season?: string;
  ph_optimal?: [number, number];
  ph_tolerable?: [number, number];
  temp_optimal?: [number, number];
  temp_absolute_max?: number;
  heat_stress_threshold_c?: number;
  season_rainfall_mm?: [number, number];
  water_requirement_mm?: [number, number];
  moisture_optimal?: [number, number];
  moisture_critical?: number;
  duration_days?: [number, number];
  critical_stages?: string[];
  suitable_soils?: string[];
  notes?: string;
  doc_key?: string;
}

export interface CropCatalogue {
  count: number;
  crops: CropRequirement[];
}

/* ------------------------------------------------------------------ */
/* Irrigation                                                          */
/* ------------------------------------------------------------------ */

export interface IrrigationRule {
  rule: string;
  outcome: string;
  detail: string;
  [key: string]: unknown;
}

export interface IrrigationSensorContext {
  latest_reading_at?: string | null;
  sensor_id?: string | null;
  is_simulated?: boolean;
  soil_moisture_percent?: number | null;
  soil_temperature_c?: number | null;
  air_humidity_percent?: number | null;
  quality_flags?: string[];
  refill_trigger_percent?: number | null;
  field_capacity_percent?: number | null;
}

export interface IrrigationWeatherContext {
  rainfall_next_48h_mm?: number | null;
  rainfall_next_3d_mm?: number | null;
  rainfall_7d_mm?: number | null;
  max_precipitation_probability_3d_percent?: number | null;
  max_temp_c?: number | null;
  total_et0_mm?: number | null;
  mean_humidity_percent?: number | null;
  source?: string | null;
  is_simulated?: boolean;
}

export interface Irrigation {
  id: number;
  field_id: number;
  workflow_run_id?: number | null;
  recommendation: string;
  urgency: string;
  requires_human_authorisation: boolean;
  authorisation_state: string;
  estimated_water_mm?: number | null;
  estimated_volume_m3?: number | null;
  rationale: string;
  rules_evaluated: IrrigationRule[];
  sensor_context: IrrigationSensorContext;
  weather_context: IrrigationWeatherContext;
  ml_prediction: Record<string, unknown> | null;
  evidence: Evidence[];
  sources: SourceReference[];
  generated_by: string;
  created_at: string;
  /** Present on the condensed `run summary` embedding only. */
  trend_stats?: Record<string, number> | null;
  water_availability_m3_per_day?: number | null;
}

export interface IrrigationAssessRequest {
  crop?: string | null;
  crop_stage?: string | null;
  soil_moisture_percent?: number | null;
}

/* ------------------------------------------------------------------ */
/* Crop risk                                                           */
/* ------------------------------------------------------------------ */

export interface RiskFinding {
  id: number;
  field_id: number;
  workflow_run_id?: number | null;
  risk_type: string;
  severity: string;
  /** Phrased as "Environmental conditions favourable for X" - render verbatim. */
  statement: string;
  potential_impact?: string | null;
  recommended_investigation?: string | null;
  evidence: Evidence[];
  sources: SourceReference[];
  observed_at: string;
  /** Always false in this system: it has no diagnostic capability. */
  is_diagnosis: boolean;
  review_status?: string;
}

export interface RiskScanResponse {
  field_id: number;
  findings: RiskFinding[];
  risk_level: string;
  disclaimer: string;
}

export interface RiskDisclaimer {
  disclaimer: string;
  wording_rule: string;
}

/* ------------------------------------------------------------------ */
/* Machine learning                                                    */
/* ------------------------------------------------------------------ */

export interface MLModelInfo {
  task: string;
  model_name: string;
  model_version: string;
  target: string;
  algorithm: string;
  features?: string[];
  hyperparameters?: Record<string, unknown>;
  train_samples?: number;
  test_samples?: number;
  metrics?: Record<string, unknown>;
  split?: Record<string, unknown>;
  dataset_summary?: Record<string, unknown>;
  limitations?: string[];
  trained_at?: string | null;
  available: boolean;
  artifact_path?: string | null;
  documentation?: string | null;
}

export interface MLPrediction {
  id: number;
  field_id: number;
  workflow_run_id?: number | null;
  model_name: string;
  model_version: string;
  task: string;
  status: string;
  prediction_value?: number | null;
  prediction_label?: string | null;
  confidence?: number | null;
  features: Record<string, number | null>;
  model_metadata: Record<string, unknown>;
  message?: string | null;
  created_at: string;
  /** Present on the condensed `run summary` embedding only. */
  unit?: string | null;
  horizon_days?: number | null;
  imputed_features?: string[];
  class_distribution?: Record<string, number> | null;
}

export interface MLStatus {
  available: boolean;
  moisture_model: boolean;
  risk_model: boolean;
  errors: string[];
  training_note?: string;
}

/* ------------------------------------------------------------------ */
/* Workflow runs                                                       */
/* ------------------------------------------------------------------ */

export interface WorkflowRun {
  id: number;
  farm_id: number;
  field_id: number;
  status: string;
  current_step?: string | null;
  crop?: string | null;
  agents_invoked: string[];
  warnings: string[];
  error?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  created_at: string;
  approval_request_id?: number | null;
  approval_status?: string | null;
}

export interface AgentTrace {
  id: number;
  sequence: number;
  agent_name: string;
  responsibility: string;
  status: string;
  input_summary: Record<string, unknown>;
  output: Record<string, unknown>;
  evidence: Evidence[];
  sources: SourceReference[];
  reasoning?: string | null;
  error?: string | null;
  duration_ms?: number | null;
  model_used?: string | null;
  created_at: string;
}

export interface AdvisoryState {
  advisory: string;
  narrative_source?: string;
  model?: string | null;
  deterministic_fallback?: string | null;
  warnings?: string[];
  safety_notes?: string[];
}

export interface WorkflowRunDetail extends WorkflowRun {
  state: {
    advisory?: AdvisoryState;
    soil?: Record<string, unknown>;
    telemetry?: Record<string, unknown>;
    weather?: WeatherBundle;
    suitability?: Suitability;
    irrigation?: Irrigation;
    risk?: Record<string, unknown>;
    evidence?: Evidence[];
    sources?: SourceReference[];
    [key: string]: unknown;
  };
  traces: AgentTrace[];
}

export interface RunApprovalSummary {
  id: number;
  title: string;
  action_type: string;
  status: string;
  reviewer_name?: string | null;
  decision_note?: string | null;
  observation?: string | null;
  reanalysis_requested: boolean;
  decided_at?: string | null;
  created_at: string;
}

export interface RunAlertSummary {
  id: number;
  alert_type: string;
  severity: string;
  status: string;
  occurrence_count: number;
  title: string;
  message: string;
}

export interface RunActivitySummary {
  id: number;
  field_id: number;
  activity_type: string;
  title: string;
  scheduled_date?: string | null;
  window_days: number;
  status: string;
  priority: string;
  responsible_person?: string | null;
  reason: string;
  approval_request_id?: number | null;
}

export interface WorkflowRunSummary {
  workflow_run_id: number;
  field_id: number;
  field_name: string;
  farm_name: string;
  crop: string;
  status: string;
  suitability?: Suitability | null;
  irrigation?: Irrigation | null;
  risk_level: string;
  risk_findings: RiskFinding[];
  ml_predictions: MLPrediction[];
  alerts: RunAlertSummary[];
  activities: RunActivitySummary[];
  approval?: RunApprovalSummary | null;
  sources: SourceReference[];
  evidence: Evidence[];
  warnings: string[];
  agents_invoked: string[];
  completed_at?: string | null;
  duration_ms?: number | null;
}

export interface WorkflowRunRequest {
  field_id: number;
  crop?: string | null;
  force_refresh_weather?: boolean;
  simulate_sensors_if_missing?: boolean;
  include_approved_only?: boolean;
  responsible_person?: string | null;
  notes?: string | null;
}

export interface ReanalysisRequest {
  notes?: string | null;
  force_refresh_weather?: boolean;
}

/* ------------------------------------------------------------------ */
/* Approvals                                                           */
/* ------------------------------------------------------------------ */

export const APPROVAL_STATUSES = ['pending', 'approved', 'rejected', 'modified'] as const;
export type ApprovalStatus = (typeof APPROVAL_STATUSES)[number];

export interface Approval {
  id: number;
  workflow_run_id: number;
  field_id: number;
  title: string;
  action_type: string;
  recommendation: Record<string, unknown>;
  evidence: Evidence[];
  status: string;
  reviewer_name?: string | null;
  decision_note?: string | null;
  modified_action?: Record<string, unknown> | null;
  observation?: string | null;
  reanalysis_requested: boolean;
  decided_at?: string | null;
  created_at: string;
}

export interface ApprovalDecision {
  status: ApprovalStatus;
  reviewer_name: string;
  decision_note?: string | null;
  modified_action?: Record<string, unknown> | null;
  observation?: string | null;
  reanalysis_requested?: boolean;
}

export interface SafetyContract {
  approved: string;
  rejected: string;
  modified: string;
  reanalysis_requested: string;
  never: string;
}

/* ------------------------------------------------------------------ */
/* Activities                                                          */
/* ------------------------------------------------------------------ */

export const ACTIVITY_STATUSES = [
  'planned',
  'scheduled',
  'in_progress',
  'completed',
  'cancelled',
] as const;
export type ActivityStatus = (typeof ACTIVITY_STATUSES)[number];

export const ACTIVITY_TYPES = [
  'field_preparation',
  'sowing',
  'irrigation',
  'soil_testing',
  'crop_observation',
  'nutrient_application',
  'harvest_planning',
  'field_scouting',
] as const;
export type ActivityType = (typeof ACTIVITY_TYPES)[number];

export interface FarmActivity {
  id: number;
  field_id: number;
  workflow_run_id?: number | null;
  approval_request_id?: number | null;
  activity_type: string;
  title: string;
  scheduled_date?: string | null;
  window_days: number;
  status: string;
  responsible_person?: string | null;
  reason: string;
  priority: string;
  evidence: Evidence[];
  notes?: string | null;
  created_at: string;
}

export interface FarmActivityUpdate {
  status?: ActivityStatus | null;
  scheduled_date?: string | null;
  responsible_person?: string | null;
  reason?: string | null;
  notes?: string | null;
}

export interface ActivityPlanRequest {
  workflow_run_id?: number | null;
  include_approved_only?: boolean;
  responsible_person?: string | null;
}

/* ------------------------------------------------------------------ */
/* Reports                                                             */
/* ------------------------------------------------------------------ */

export interface ReportSectionSummary {
  sections?: string[];
  section_count?: number;
  page_count?: number;
  evidence_items?: number;
  references?: number;
  workflow_run_id?: number;
  agents_invoked?: string[];
}

export interface Report {
  id: number;
  farm_id: number;
  field_id: number;
  workflow_run_id?: number | null;
  title: string;
  status: string;
  file_name?: string | null;
  size_bytes?: number | null;
  page_count?: number | null;
  section_summary: ReportSectionSummary;
  error?: string | null;
  created_at: string;
  /** Server-relative URL, e.g. `/api/v1/reports/1/download`. */
  download_url?: string | null;
}

export interface ReportCreate {
  workflow_run_id?: number | null;
  title?: string | null;
  include_evidence?: boolean;
}

/* ------------------------------------------------------------------ */
/* Knowledge base                                                      */
/* ------------------------------------------------------------------ */

export interface RagStatus {
  available: boolean;
  index_backend: string;
  documents: number;
  chunks: number;
  embedding: string;
  dimension?: number | null;
  built_at?: string | null;
  detail?: string | null;
}