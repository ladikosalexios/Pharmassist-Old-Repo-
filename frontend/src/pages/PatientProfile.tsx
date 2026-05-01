import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronLeftIcon, AlertCircleIcon, PhoneIcon } from "../components/Icons";
import { ApiError, getPatient } from "../lib/api";
import type { PatientProfile as Profile } from "../types";

export function PatientProfile() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getPatient(id)
      .then((data) => { if (active) setProfile(data); })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : "Could not load patient profile.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);

  return (
    <div className="p-8">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline"
      >
        <ChevronLeftIcon width={14} height={14} /> Back
      </button>
      <h1 className="mt-2 text-2xl font-bold text-slate-900">Patient Profile</h1>
      <p className="mt-1 text-sm text-slate-500">
        ID: <span className="font-mono">{id}</span>
      </p>

      {loading ? (
        <div className="mt-6 flex items-center gap-2 text-sm text-slate-500">
          <span className="spinner text-brand-600" /> Loading…
        </div>
      ) : error ? (
        <div className="mt-6 card flex items-start gap-2 px-4 py-3 text-sm text-red-700">
          <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : profile ? (
        <div className="mt-6 card max-w-xl p-5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Name</div>
            <div className="mt-1 text-base font-semibold text-slate-900">{profile.name}</div>
          </div>
          {profile.phone && (
            <div className="mt-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Phone</div>
              <a href={`tel:${profile.phone}`} className="mt-1 inline-flex items-center gap-2 text-sm text-brand-600 hover:underline">
                <PhoneIcon width={14} height={14} /> {profile.phone}
              </a>
            </div>
          )}
          <p className="mt-6 text-xs text-slate-500">
            Full medical history, allergies, and prescription log will appear here in a future update.
          </p>
        </div>
      ) : null}

      <div className="mt-6 text-xs text-slate-500">
        <Link to="/side-effects" className="text-brand-600 hover:underline">← Back to Side Effect Reports</Link>
      </div>
    </div>
  );
}
