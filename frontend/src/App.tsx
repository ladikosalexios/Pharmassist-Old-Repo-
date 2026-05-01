import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { PrescriptionVerification } from "./pages/PrescriptionVerification";
import { Documentation } from "./pages/Documentation";
import { SideEffects } from "./pages/SideEffects";
import { PatientProfile } from "./pages/PatientProfile";
import { Placeholder } from "./pages/Placeholder";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/prescription/:rxId" element={<PrescriptionVerification />} />
        <Route path="/documentation" element={<Documentation />} />
        <Route path="/side-effects"  element={<SideEffects />} />
        <Route path="/patients/:id"  element={<PatientProfile />} />
        <Route path="/prescriptions" element={<Placeholder title="Prescriptions" />} />
        <Route path="/patients"      element={<Placeholder title="Patients" />} />
        <Route path="/history"       element={<Placeholder title="History" />} />
        <Route path="/settings"      element={<Placeholder title="Settings" />} />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
