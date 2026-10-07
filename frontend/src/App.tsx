import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Login } from "./pages/Login";
import { AcceptInvite } from "./pages/AcceptInvite";
import { Dashboard } from "./pages/Dashboard";
import { PrescriptionVerification } from "./pages/PrescriptionVerification";
import { History } from "./pages/History";
import { SideEffects } from "./pages/SideEffects";
import { Patients } from "./pages/Patients";
import { PatientProfile } from "./pages/PatientProfile";
import { Instructions } from "./pages/Instructions";
const YellowCards = lazy(() =>
  import("./pages/YellowCards").then((module) => ({ default: module.YellowCards })),
);
import { Settings } from "./pages/Settings";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/accept-invite" element={<AcceptInvite />} />
      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/prescription/:rxId" element={<PrescriptionVerification />} />
        <Route path="/history" element={<History />} />
        <Route path="/documentation" element={<Navigate to="/history" replace />} />
        <Route path="/side-effects" element={<SideEffects />} />
        <Route path="/patients" element={<Patients />} />
        <Route path="/patients/:id" element={<PatientProfile />} />
        <Route path="/instructions" element={<Instructions />} />
        <Route
          path="/yellow-cards"
          element={
            <Suspense fallback={<p className="p-6">Φόρτωση Κίτρινης Κάρτας…</p>}>
              <YellowCards />
            </Suspense>
          }
        />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
