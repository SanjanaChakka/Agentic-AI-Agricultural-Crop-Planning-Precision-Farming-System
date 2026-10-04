import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { DashboardPage } from './pages/DashboardPage';
import { FarmsFieldsPage } from './pages/FarmsFieldsPage';
import { FieldDetailPage } from './pages/FieldDetailPage';
import { FieldEditPage } from './pages/FieldEditPage';
import { SoilPage } from './pages/SoilPage';
import { WeatherPage } from './pages/WeatherPage';
import { CropPlannerPage } from './pages/CropPlannerPage';
import { SensorsPage } from './pages/SensorsPage';
import { IrrigationPage } from './pages/IrrigationPage';
import { CropRiskPage } from './pages/CropRiskPage';
import { ActivitiesPage } from './pages/ActivitiesPage';
import { AdvisoryPage } from './pages/AdvisoryPage';
import { ReportsPage } from './pages/ReportsPage';
import { NotFoundPage } from './pages/NotFoundPage';

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="farms" element={<FarmsFieldsPage />} />
        <Route path="fields/:fieldId" element={<FieldDetailPage />} />
        <Route path="fields/:fieldId/edit" element={<FieldEditPage />} />
        <Route path="soil" element={<SoilPage />} />
        <Route path="weather" element={<WeatherPage />} />
        <Route path="planner" element={<CropPlannerPage />} />
        <Route path="sensors" element={<SensorsPage />} />
        <Route path="irrigation" element={<IrrigationPage />} />
        <Route path="risk" element={<CropRiskPage />} />
        <Route path="activities" element={<ActivitiesPage />} />
        <Route path="advisory" element={<AdvisoryPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export default App;