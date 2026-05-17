import { Outlet, Navigate } from "react-router-dom";
import { AdminSidebar } from "./AdminSidebar";
import { useAdminAuth } from "../lib/adminAuth";

export function AdminShell() {
  const { admin, loading } = useAdminAuth();

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-slate-500">
        <span className="spinner mr-2 text-brand-600" /> Loading…
      </div>
    );
  }
  if (!admin) return <Navigate to="/admin/login" replace />;
  return (
    <div className="flex h-full overflow-hidden">
      <AdminSidebar />
      <main className="flex-1 overflow-y-auto bg-slate-50">
        <Outlet />
      </main>
    </div>
  );
}
