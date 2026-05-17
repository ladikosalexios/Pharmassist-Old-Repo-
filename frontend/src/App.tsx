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
import { AdminShell } from "./components/AdminShell";
import { AdminLogin } from "./pages/admin/AdminLogin";
import { AdminInvitations } from "./pages/admin/AdminInvitations";
import { AdminPharmacies } from "./pages/admin/AdminPharmacies";
import { AdminPharmacists } from "./pages/admin/AdminPharmacists";
import { AdminStaff } from "./pages/admin/AdminStaff";
import { AdminDrugs } from "./pages/admin/AdminDrugs";
import { AdminSafetyRules } from "./pages/admin/AdminSafetyRules";
import { AdminDemoData } from "./pages/admin/AdminDemoData";
import { AdminAuditLog } from "./pages/admin/AdminAuditLog";

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

      <Route path="/admin/login" element={<AdminLogin />} />
      <Route path="/admin" element={<AdminShell />}>
        <Route index element={<Navigate to="/admin/invitations" replace />} />
        <Route path="invitations" element={<AdminInvitations />} />
        <Route path="pharmacies" element={<AdminPharmacies />} />
        <Route path="pharmacists" element={<AdminPharmacists />} />
        <Route path="staff" element={<AdminStaff />} />
        <Route path="drugs" element={<AdminDrugs />} />
        <Route path="safety-rules" element={<AdminSafetyRules />} />
        <Route path="demo" element={<AdminDemoData />} />
        <Route path="audit-logs" element={<AdminAuditLog />} />
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
