# Demo inputs for exercising all six agents.
#
#   .\scripts\demo-inputs.ps1
#   .\scripts\demo-inputs.ps1 -Api http://127.0.0.1:8001/api/v1
#
# Each scenario creates its own farm, field, soil observation and sensor
# readings, then runs the workflow and prints what the six agents decided. The
# script is idempotent in effect - every run creates fresh records, so you can
# run it as often as you like and compare the outputs.
#
# Weather comes from a live provider (Open-Meteo). That makes the irrigation and
# risk agents the only two whose output can shift between runs: if the forecast
# calls for rain, the irrigation agent will defer to rainfall even when the soil
# is dry. Everything else is driven purely by the values below.

param(
    [string]$Api = 'http://127.0.0.1:8001/api/v1'
)

$ErrorActionPreference = 'Stop'

function Post($path, $body) {
    $json = $body | ConvertTo-Json -Depth 5 -Compress
    Invoke-RestMethod "$Api$path" -Method Post -Body $json -ContentType 'application/json'
}

function New-Farm($name, $owner, $loc, $lat, $lon) {
    $f = @{ name = $name; owner_name = $owner; location_name = $loc }
    if ($null -ne $lat) { $f.latitude = $lat; $f.longitude = $lon }
    Post '/farms' $f
}

function New-Field($farmId, $code, $name, $ha, $soil, $crop, $prevCrop, $stage, $source, $water, $m3, $lat, $lon) {
    $f = @{
        farm_id = $farmId; field_code = $code; name = $name; area_ha = $ha
        soil_type = $soil; proposed_crop = $crop; previous_crop = $prevCrop
        crop_stage = $stage; irrigation_source = $source; water_availability = $water
        water_availability_m3_per_day = $m3
    }
    if ($null -ne $lat) { $f.latitude = $lat; $f.longitude = $lon }
    # farm_id is a query parameter on this endpoint, not a body field.
    Post "/fields?farm_id=$farmId" $f
}

function Add-Soil($fieldId, $ph, $n, $p, $k, $oc, $vwc, $ec, $source) {
    Post '/soil/observations' @{
        field_id = $fieldId; sample_depth_cm = 15; soil_type = $null
        ph = $ph; nitrogen_available_kg_ha = $n; phosphorus_available_kg_ha = $p
        potassium_available_kg_ha = $k; organic_carbon_percent = $oc
        soil_moisture_percent = $vwc; electrical_conductivity_ds_m = $ec
        data_source = $source
        lab_name = 'Demo lab (synthetic record for testing)'
        notes = 'Created by scripts/demo-inputs.ps1. Not a real laboratory report.'
    } | Out-Null
}

function Add-Sensor($fieldId, $id, $vwc, $soilT, $humidity, $airT, $simulated, $battery) {
    Post '/sensors/readings' @{
        field_id = $fieldId; sensor_id = $id
        soil_moisture_percent = $vwc; soil_temperature_c = $soilT
        air_humidity_percent = $humidity; air_temperature_c = $airT
        battery_percent = $battery; is_simulated = $simulated
    } | Out-Null
}

function Run-Scenario($title, $fieldId, $crop, $simulate, $person) {
    Write-Host ''
    Write-Host ('=' * 78) -ForegroundColor DarkCyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host ('=' * 78) -ForegroundColor DarkCyan

    $run = Post '/workflow/runs' @{
        field_id = $fieldId; crop = $crop
        simulate_sensors_if_missing = $simulate
        force_refresh_weather = $true
        responsible_person = $person
    }

    $id = $run.workflow_run_id
    Write-Host "run_id=$id  status=$($run.status)  agents=$($run.agents_invoked.Count)  $($run.duration_ms)ms"

    $detail = Invoke-RestMethod "$Api/workflow/runs/$id"
    foreach ($t in $detail.traces) {
        $steps = if ($t.output.steps) { ($t.output.steps | ForEach-Object { "$($_.step):$($_.status)" }) -join ' > ' } else { '' }
        $line = "  $($t.agent_name.PadRight(28)) $($t.status.PadRight(10)) $($t.duration_ms)ms"
        if ($steps) { $line += "  [$steps]" }
        Write-Host $line
    }

    $s = Invoke-RestMethod "$Api/workflow/runs/$id/summary"
    $suit = if ($s.suitability) { "$($s.suitability.status) ($($s.suitability.score))" } else { 'n/a' }
    Write-Host "  suitability : $suit"
    if ($s.suitability.limiting_factors) {
        Write-Host "  limiting     : $(($s.suitability.limiting_factors) -join '; ')"
    }
    Write-Host "  irrigation   : $($s.irrigation.recommendation) / $($s.irrigation.urgency) / $($s.irrigation.estimated_water_mm)mm"
    Write-Host "  risk_level   : $($s.risk_level)"
    if ($s.risk_findings) { Write-Host "  risk         : $(($s.risk_findings | ForEach-Object { "$($_.risk_type)/$($_.severity)" }) -join ', ')" }
    Write-Host "  ml           : $(($s.ml_predictions | ForEach-Object { "$($_.task)=$($_.prediction_value)" }) -join ', ')"
    Write-Host "  citations    : $($s.sources.Count)  evidence: $($s.evidence.Count)  activities: $($s.activities.Count)  alerts: $($s.alerts.Count)"
    if ($s.approval) { Write-Host "  approval     : $($s.approval.status) - human sign-off required before anything is applied" }
    foreach ($w in $s.warnings) { Write-Host "  ! $w" -ForegroundColor DarkYellow }
    return $id
}

# ---------------------------------------------------------------------------
# Scenario 1 - dry black soil at flowering. Soil chemistry drives the soil
# agent, the real sensor reading drives the irrigation agent, and the shallow
# water supply plus low moisture drives a high water-stress risk finding.
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host 'Scenario 1: dry black soil, cotton at flowering, borewell with limited water' -ForegroundColor Yellow

$farm = New-Farm 'Demo Dryland Farm' 'Demo Farmer' 'Nanded, Maharashtra' 19.15 77.32
$field = New-Field $farm.id 'DMY-01' 'Dry Cotton Plot' 3.8 'black_soil' 'cotton' 'cotton' 'flowering' 'borewell' 'limited' 60 19.151 77.321
Add-Soil $field.id 7.6 90 8 120 0.40 12.0 0.30 'lab_test'
Add-Sensor $field.id 'SM-DRY-01' 14.2 28.4 45 33.5 $false 88
$run1 = Run-Scenario '1. Water stress -> irrigation proposal awaiting approval' $field.id 'cotton' $false 'Karth'

# ---------------------------------------------------------------------------
# Scenario 2 - well-fertilised alluvial soil near field capacity. This is the
# contrast case: the irrigation agent should decline to propose water.
# ---------------------------------------------------------------------------
$farm2 = New-Farm 'Demo Canal Farm' 'Demo Farmer' 'Thanjavur, Tamil Nadu' 10.79 79.14
$field2 = New-Field $farm2.id 'DMY-02' 'Canal Wheat Plot' 5.2 'alluvial' 'wheat' 'rice' 'vegetative' 'canal' 'abundant' 400 10.792 79.141
Add-Soil $field2.id 6.8 260 24 300 0.80 42.0 0.35 'lab_test'
Add-Sensor $field2.id 'SM-WET-01' 38.0 24.1 70 26.0 $false 95
$run2 = Run-Scenario '2. Fertile alluvial soil -> irrigation deferred' $field2.id 'wheat' $false 'Karth'

# ---------------------------------------------------------------------------
# Scenario 3 - strongly acidic soil with every nutrient low. The EC of 4.8 dS/m
# is saline, but note the gap: it lands in the evidence ledger and nothing
# classifies it, so no salinity recommendation appears. See the note at the end.
$farm3 = New-Farm 'Demo Coastal Farm' 'Demo Farmer' 'Saurashtra, Gujarat' 22.24 70.37
$field3 = New-Field $farm3.id 'DMY-03' 'Acidic Groundnut Plot' 2.4 'red_laterite' 'groundnut' 'maize' 'sowing' 'drip' 'limited' 90 22.241 70.371
Add-Soil $field3.id 4.6 70 6 90 0.30 18.0 4.80 'lab_test'
Add-Sensor $field3.id 'SM-SALT-01' 20.0 26.0 80 29.0 $false 71
$run3 = Run-Scenario '3. Strongly acidic soil -> amendments required' $field3.id 'groundnut' $false 'Karth'

# ---------------------------------------------------------------------------
# Scenario 4 - no coordinates anywhere. Weather cannot be resolved, so the
# agents must degrade gracefully and say so instead of inventing a forecast.
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host 'Scenario 4: farm and field with no coordinates -> weather degrades gracefully' -ForegroundColor Yellow

$farm4 = New-Farm 'Demo No-Geo Farm' 'Demo Farmer' 'Location not recorded' $null $null
$field4 = New-Field $farm4.id 'DMY-04' 'No-Coordinate Plot' 1.9 'loam' 'pigeonpea' 'sorghum' 'flowering' 'rainfed' 'seasonal' 40 $null $null
Add-Soil $field4.id 6.5 180 18 200 0.55 30.0 0.40 'lab_test'
$run4 = Run-Scenario '4. Missing geolocation -> no forecast, advisory says so' $field4.id 'pigeonpea' $true 'Karth'

Write-Host ''
Write-Host ('=' * 78) -ForegroundColor DarkCyan
Write-Host '  Done. Runs created:' -ForegroundColor Cyan
Write-Host "    1  water stress + irrigation proposal   run_id=$run1"
Write-Host "    2  fertile soil, irrigation deferred    run_id=$run2"
Write-Host "    3  strongly acidic soil, amendments     run_id=$run3"
Write-Host "    4  no coordinates, weather unavailable  run_id=$run4"
Write-Host ''
Write-Host "  Approve a proposal:  POST $Api/approvals/<id>/decision"
Write-Host '  body: {"status":"approved","reviewer_name":"...","decision_note":"..."}'
Write-Host "  Agent audit trail:   GET  $Api/workflow/runs/<id>"
Write-Host ''
Write-Host '  Known gap: soil salinity (electrical conductivity) is recorded in the'
Write-Host '  evidence ledger but no EC threshold is classified anywhere, so a saline'
Write-Host '  field does not yet produce a salinity recommendation. Scenario 3 sends'
Write-Host '  EC 4.8 dS/m to prove the number is captured even though it is not acted on.'
Write-Host ('=' * 78) -ForegroundColor DarkCyan
