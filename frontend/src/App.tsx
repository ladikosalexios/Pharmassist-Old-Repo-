import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Login } from "./pages/Login";
import { AcceptInvite } from "./pages/AcceptInvite";
import { Dashboard } from "./pages/Dashboard";
import { PrescriptionVerification } from "./pages/PrescriptionVerification";
import { Documentation } from "./pages/Documentation";
import { SideEffects } from "./pages/SideEffects";
import { PatientProfile } from "./pages/PatientProfile";
import { Instructions } from "./pages/Instructions";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/accept-invite" element={<AcceptInvite />} />
      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/prescription/:rxId" element={<PrescriptionVerification />} />
        <Route path="/documentation" element={<Documentation />} />
        <Route path="/side-effects" element={<SideEffects />} />
        <Route path="/patients/:id" element={<PatientProfile />} />
        <Route path="/instructions" element={<Instructions />} />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
