import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/auth";
import {
  yc,
  isDefiniteRejection,
  emptyReport,
  medicine,
  reaction,
  withReporterDefaults,
  removedReporterDetails,
  asPharmacistReporter,
  isPharmacistReporter,
  PHARMACIST_REPORTERS,
  REPORTER_TYPES,
  type ReportData,
  type Report,
  type Signature,
  type Preview,
  type Submission,
  type Medicine,
  type Reaction,
} from "../lib/yellowCards";
import { YellowSignature } from "../components/YellowSignature";
import { YellowPdf } from "../components/YellowPdf";
import "./yellowCards.css";

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string | number | null;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label>
      {label}
      <input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
function Select({
  label,
  value,
  onChange,
  children,
  disabled = false,
}: {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label>
      {label}
      <select disabled={disabled} value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </select>
    </label>
  );
}
const seriousness = [
  ["death", "Θάνατος"],
  ["life_threatening", "Απειλή για τη ζωή"],
  ["hospitalisation", "Νοσηλεία / παράταση νοσηλείας"],
  ["disability", "Αναπηρία / ανικανότητα"],
  ["congenital", "Συγγενής ανωμαλία"],
  ["other", "Άλλο σημαντικό ιατρικό συμβάν"],
];
const statuses: Record<string, string> = {
  QUEUED: "Σε αναμονή τοπικής αποστολής",
  SENDING: "Αποστέλλεται στο τοπικό inbox…",
  CAPTURED_LOCAL: "Παραδόθηκε στο τοπικό inbox — δεν υποβλήθηκε στον ΕΟΦ",
  FAILED: "Αποτυχία — δείτε την τοπική υπηρεσία email",
  UNKNOWN: "Άγνωστο αποτέλεσμα — ελέγξτε το Mailpit πριν νέα αποστολή",
  CANCELLED: "Ακυρώθηκε πριν την αποστολή",
};
export function YellowCards() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const location = useLocation();
  const imported = (location.state as { report?: Report } | null)?.report;
  const [data, setData] = useState(() =>
    imported
      ? withReporterDefaults(imported.data)
      : emptyReport(user?.name ?? "", user?.email ?? ""),
  );
  const [report, setReport] = useState<Report | null>(imported ?? null);
  const [reports, setReports] = useState<Report[]>([]);
  const [signature, setSignature] = useState<Signature | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [approved, setApproved] = useState(false);
  const [synthetic, setSynthetic] = useState(false);
  const [useSignature, setUseSignature] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [sendKey, setSendKey] = useState("");
  const [sent, setSent] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [statusError, setStatusError] = useState(false);
  const currentSubmission = submissions.find((s) => s.preview_id === preview?.id);
  useEffect(() => {
    let active = true;
    Promise.all([
      yc<Report[]>(),
      yc<Signature | null>("/signature"),
      yc<Submission[]>("/submissions"),
    ])
      .then(([a, b, c]) => {
        if (active) {
          setReports(a);
          setSignature(b);
          setSubmissions(c);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    // Schedule after completion so slow requests cannot overwrite newer statuses.
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const rows = await yc<Submission[]>("/submissions");
        if (active) {
          setSubmissions(rows);
          setStatusError(false);
        }
      } catch {
        if (active) setStatusError(true);
      } finally {
        if (active) timer = setTimeout(refresh, 3000);
      }
    }
    timer = setTimeout(refresh, 3000);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
  function invalidate() {
    setPreview(null);
    setApproved(false);
    setNotice("");
    setSent(false);
    setUncertain(false);
  }
  function change<K extends keyof ReportData>(key: K, value: ReportData[K]) {
    setData((old) => ({ ...old, [key]: value }));
    setDirty(true);
    invalidate();
  }
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    const saved = report
      ? await yc<Report>(`/${report.id}`, "PATCH", { revision: report.revision, data })
      : await yc<Report>("", "POST", data);
    setReport(saved);
    setDirty(false);
    setReports((old) => [saved, ...old.filter((r) => r.id !== saved.id)]);
    return saved;
  }
  function load(value: Report | null) {
    if (dirty && !window.confirm("Υπάρχουν μη αποθηκευμένες αλλαγές. Να απορριφθούν;")) return;
    setReport(value);
    setData(
      value ? withReporterDefaults(value.data) : emptyReport(user?.name ?? "", user?.email ?? ""),
    );
    setDirty(false);
    setSynthetic(false);
    setUseSignature(false);
    invalidate();
  }
  function reporterName(value: unknown) {
    return REPORTER_TYPES.includes(value as ReportData["reporter_type"])
      ? t(`yellowCards.reporter.types.${value}`)
      : t("yellowCards.reporter.unrecognized", { value: String(value) });
  }
  // Only a deliberate choice converts a saved non-pharmacist role, after naming what it removes.
  function chooseReporter(value: string) {
    if (!isPharmacistReporter(value)) return;
    const removed = removedReporterDetails(data);
    if (
      removed.length &&
      !window.confirm(
        t("yellowCards.reporter.confirmConvert", {
          role: reporterName(value),
          details: removed
            .map(([key, text]) => `${t(`yellowCards.reporter.${key}`)}: «${text}»`)
            .join(", "),
        }),
      )
    )
      return;
    setData((old) => asPharmacistReporter(old, value));
    setDirty(true);
    invalidate();
  }
  function medicineFields(kind: "suspected" | "concomitant") {
    return (
      <>
        {data[kind].map((m, index) => (
          <div className="yc-row" key={index}>
            <h3>Φάρμακο {index + 1}</h3>
            <div className="yc-grid">
              {(
                [
                  ["name", "Εμπορική ονομασία / δραστική ουσία"],
                  ["lot", "Αριθμός παρτίδας"],
                  ["route", "Οδός χορήγησης"],
                  ["dose", "Δόση και συχνότητα"],
                  ["start", "Έναρξη χορήγησης"],
                  ["end", "Λήξη χορήγησης"],
                  ["indication", "Ένδειξη χορήγησης"],
                ] as [keyof Medicine, string][]
              ).map(([key, label]) => (
                <Field
                  key={key}
                  label={label}
                  value={m[key]}
                  type={key === "start" || key === "end" ? "date" : "text"}
                  onChange={(value) =>
                    change(
                      kind,
                      data[kind].map((row, i) =>
                        i === index
                          ? {
                              ...row,
                              [key]: value || (key === "start" || key === "end" ? null : ""),
                            }
                          : row,
                      ),
                    )
                  }
                />
              ))}
            </div>
            <button
              onClick={() =>
                change(
                  kind,
                  data[kind].filter((_, i) => i !== index),
                )
              }
            >
              Αφαίρεση φαρμάκου
            </button>
          </div>
        ))}
        <button
          disabled={data[kind].length >= 30}
          onClick={() => change(kind, [...data[kind], medicine()])}
        >
          Προσθήκη {kind === "suspected" ? "ύποπτου" : "συγχορηγούμενου"} φαρμάκου
        </button>
      </>
    );
  }
  return (
    <div className="yc-workspace">
      <div className="yc-banner">
        Τοπική δοκιμή · Μόνο συνθετικά δεδομένα · Δεν αποστέλλεται στον ΕΟΦ
      </div>
      <header>
        <p>PHARMASSIST / ΦΑΡΜΑΚΟΕΠΑΓΡΥΠΝΗΣΗ</p>
        <h1>Κίτρινη Κάρτα</h1>
        <p>
          Συμπληρώστε την αναφορά, ελέγξτε το υπογεγραμμένο PDF και δείτε το email στο τοπικό inbox.
        </p>
      </header>
      {error && (
        <div className="yc-error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="yc-notice" role="status">
          {notice}
        </div>
      )}
      <div className="yc-actions">
        <button disabled={busy || uncertain} onClick={() => load(null)}>
          Νέα αναφορά
        </button>
        <Select
          disabled={busy || uncertain}
          label="Αποθηκευμένα προσχέδια"
          value={report?.id ?? ""}
          onChange={(id) => load(reports.find((r) => r.id === id) ?? null)}
        >
          <option value="">Επιλέξτε προσχέδιο</option>
          {reports.map((r) => (
            <option key={r.id} value={r.id}>
              {r.data.initials || "Χωρίς αρχικά"} · {r.data.report_date || "Χωρίς ημερομηνία"} · v
              {r.revision}
            </option>
          ))}
        </Select>
        <a href="http://127.0.0.1:8026" target="_blank" rel="noreferrer">
          Τοπικό inbox Mailpit ↗
        </a>
      </div>
      <fieldset disabled={busy || uncertain} className="yc-editor">
        <section className="yc-card">
          <h2>1. Στοιχεία ασθενούς</h2>
          <p>Μόνο αρχικά. Δεν συλλέγεται ΑΜΚΑ ή αριθμός συνταγής.</p>
          <button
            onClick={() => {
              setData((old) => ({
                ...emptyReport(user?.name ?? "", user?.email ?? ""),
                // The example never replaces the saved reporter role or its details.
                reporter_type: old.reporter_type,
                reporter_specialty: old.reporter_specialty,
                reporter_other: old.reporter_other,
                initials: "Δ.Α.",
                age: "67",
                weight: "88",
                height: "190",
                sex: "male",
                serious: false,
                reactions: [
                  {
                    ...reaction(),
                    description: "Δοκιμαστική αναφορά δερματικού εξανθήματος.",
                    onset: "2026-10-01",
                  },
                ],
                suspected: [
                  { ...medicine(), name: "Δοκιμαστικό φάρμακο Α", dose: "Όπως αναφέρθηκε" },
                ],
                reporter_phone: "2100000000",
              }));
              setDirty(true);
              invalidate();
            }}
          >
            Συμπλήρωση συνθετικού παραδείγματος
          </button>
          <div className="yc-grid">
            {(
              [
                ["initials", "Αρχικά ασθενούς"],
                ["age", "Ηλικία (έτη)"],
                ["weight", "Βάρος (kg, προαιρετικό)"],
                ["height", "Ύψος (cm, προαιρετικό)"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label} value={data[key]} onChange={(v) => change(key, v)} />
            ))}
            <Select label="Φύλο" value={data.sex} onChange={(v) => change("sex", v)}>
              <option value="">Δεν καταγράφηκε</option>
              <option value="male">Άρρεν</option>
              <option value="female">Θήλυ</option>
            </Select>
          </div>
        </section>
        <section className="yc-card">
          <h2>2. Ανεπιθύμητες ενέργειες</h2>
          {data.reactions.map((r, index) => {
            const update = <K extends keyof Reaction>(key: K, value: Reaction[K]) =>
              change(
                "reactions",
                data.reactions.map((row, i) => (i === index ? { ...row, [key]: value } : row)),
              );
            return (
              <div className="yc-row" key={index}>
                <h3>Αντίδραση {index + 1}</h3>
                <label>
                  Περιγραφή αντίδρασης
                  <textarea
                    value={r.description}
                    onChange={(e) => update("description", e.target.value)}
                  />
                </label>
                <div className="yc-grid">
                  <Field
                    label="Ημερομηνία έναρξης"
                    type="date"
                    value={r.onset}
                    onChange={(v) =>
                      change(
                        "reactions",
                        data.reactions.map((row, i) =>
                          i === index ? { ...row, onset: v || null, onset_unknown: false } : row,
                        ),
                      )
                    }
                  />
                  <Field
                    label="Ημερομηνία λήξης"
                    type="date"
                    value={r.end}
                    onChange={(v) => update("end", v || null)}
                  />
                  <Select
                    label="Έκβαση"
                    value={r.outcome}
                    onChange={(v) => update("outcome", Number(v))}
                  >
                    {[
                      "Θάνατος",
                      "Δεν έχει ακόμη αναρρώσει",
                      "Ίαση χωρίς βλάβες",
                      "Ίαση με μόνιμες βλάβες",
                      "Υπό ανάρρωση",
                      "Άγνωστη",
                    ].map((label, i) => (
                      <option key={i} value={i + 1}>
                        {i + 1} — {label}
                      </option>
                    ))}
                  </Select>
                </div>
                <label className="yc-check">
                  <input
                    type="checkbox"
                    checked={r.onset_unknown}
                    onChange={(e) =>
                      change(
                        "reactions",
                        data.reactions.map((row, i) =>
                          i === index
                            ? { ...row, onset_unknown: e.target.checked, onset: null }
                            : row,
                        ),
                      )
                    }
                  />
                  Η έναρξη είναι άγνωστη
                </label>
                <button
                  onClick={() =>
                    change(
                      "reactions",
                      data.reactions.filter((_, i) => i !== index),
                    )
                  }
                >
                  Αφαίρεση αντίδρασης
                </button>
              </div>
            );
          })}
          <button
            disabled={data.reactions.length >= 30}
            onClick={() => change("reactions", [...data.reactions, reaction()])}
          >
            Προσθήκη αντίδρασης
          </button>
          <Select
            label="Θεωρείτε κάποια αντίδραση σοβαρή;"
            value={data.serious === null ? "" : String(data.serious)}
            onChange={(v) => {
              setData((old) => ({
                ...old,
                serious: v === "" ? null : v === "true",
                seriousness: v === "true" ? old.seriousness : [],
              }));
              setDirty(true);
              invalidate();
            }}
          >
            <option value="">Επιλέξτε</option>
            <option value="false">Όχι</option>
            <option value="true">Ναι</option>
          </Select>
          {data.serious && (
            <div>
              {seriousness.map(([key, label]) => (
                <label className="yc-check" key={key}>
                  <input
                    type="checkbox"
                    checked={data.seriousness.includes(key)}
                    onChange={(e) =>
                      change(
                        "seriousness",
                        e.target.checked
                          ? [...data.seriousness, key]
                          : data.seriousness.filter((v) => v !== key),
                      )
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
          )}
          <div className="yc-grid">
            <Field
              label="Ημερομηνία θανάτου, εφόσον εφαρμόζεται"
              type="date"
              value={data.death_date}
              onChange={(v) => change("death_date", v || null)}
            />
            <Field
              label="Αιτία θανάτου, εφόσον εφαρμόζεται"
              value={data.death_cause}
              onChange={(v) => change("death_cause", v)}
            />
          </div>
        </section>
        <section className="yc-card">
          <h2>3. Φάρμακα</h2>
          <h3>Ύποπτα φάρμακα</h3>
          {medicineFields("suspected")}
          <h3>Συγχορηγούμενα φάρμακα</h3>
          {medicineFields("concomitant")}
        </section>
        <section className="yc-card">
          <h2>4. Συμπληρωματικές παρατηρήσεις</h2>
          <label>
            Ιστορικό, αλλεργίες, πορεία, εργαστηριακά ευρήματα και αντιμετώπιση
            <textarea
              rows={5}
              value={data.observations}
              onChange={(e) => change("observations", e.target.value)}
            />
          </label>
        </section>
        <section className="yc-card">
          <h2>5. Στοιχεία αναφέροντος</h2>
          <div className="yc-grid">
            <Select
              label={t("yellowCards.reporter.label")}
              value={String(data.reporter_type ?? "")}
              onChange={chooseReporter}
            >
              {!isPharmacistReporter(data.reporter_type) && (
                <option value={String(data.reporter_type ?? "")}>
                  {t("yellowCards.reporter.savedRole", { role: reporterName(data.reporter_type) })}
                </option>
              )}
              {PHARMACIST_REPORTERS.map((value) => (
                <option key={value} value={value}>
                  {t(`yellowCards.reporter.types.${value}`)}
                </option>
              ))}
            </Select>
          </div>
          {!isPharmacistReporter(data.reporter_type) && (
            <p role="note">{t("yellowCards.reporter.savedNotice")}</p>
          )}
          {removedReporterDetails(data).map(([key, text]) => (
            <p key={key}>
              {t(`yellowCards.reporter.${key}`)}: {text}
            </p>
          ))}
          <div className="yc-grid">
            {(
              [
                ["reporter_name", "Ονοματεπώνυμο"],
                ["reporter_address", "Διεύθυνση"],
                ["reporter_institution", "Ίδρυμα / φαρμακείο"],
                ["reporter_phone", "Τηλέφωνο"],
                ["reporter_email", "Email"],
                ["report_date", "Ημερομηνία αναφοράς"],
              ] as const
            ).map(([key, label]) => (
              <Field
                key={key}
                label={label}
                value={data[key]}
                type={key === "report_date" ? "date" : "text"}
                onChange={(v) => change(key, v || (key === "report_date" ? null : ""))}
              />
            ))}
          </div>
        </section>
      </fieldset>
      <YellowSignature
        saved={signature}
        disabled={busy || uncertain}
        onChange={(value) => {
          setSignature(value);
          setUseSignature(false);
          invalidate();
        }}
      />
      <section className="yc-card">
        <h2>6. Έλεγχος και τοπική αποστολή</h2>
        <label className="yc-check">
          <input
            type="checkbox"
            checked={synthetic}
            disabled={busy || uncertain}
            onChange={(e) => {
              setSynthetic(e.target.checked);
              invalidate();
            }}
          />
          Χρησιμοποιώ μόνο συνθετικά στοιχεία σε αυτή τη δοκιμή.
        </label>
        <label className="yc-check">
          <input
            type="checkbox"
            checked={useSignature}
            disabled={!signature || busy || uncertain}
            onChange={(e) => {
              setUseSignature(e.target.checked);
              invalidate();
            }}
          />
          Χρήση της αποθηκευμένης υπογραφής μου σε αυτή την αναφορά.
        </label>
        <div className="yc-actions">
          <button
            disabled={busy || uncertain}
            onClick={() =>
              action(async () => {
                await save();
                invalidate();
                setNotice("Το προσχέδιο αποθηκεύτηκε.");
              })
            }
          >
            Αποθήκευση προσχεδίου
          </button>
          <button
            className="yc-primary"
            disabled={busy || !synthetic || !useSignature || !signature || uncertain}
            onClick={() =>
              action(async () => {
                const saved = await save();
                // The save superseded any earlier preview and approval, even if this one fails.
                invalidate();
                const p = await yc<Preview>(`/${saved.id}/previews`, "POST", {
                  revision: saved.revision,
                  signature_id: signature!.id,
                  synthetic_data: true,
                });
                setPreview(p);
                setApproved(false);
                setSent(false);
                setSendKey(crypto.randomUUID());
                setNotice("Ελέγξτε όλες τις σελίδες και την υπογραφή πριν την τοπική αποστολή.");
              })
            }
          >
            {busy ? "Παρακαλώ περιμένετε…" : "Δημιουργία και προεπισκόπηση PDF"}
          </button>
        </div>
        {preview && (
          <div>
            <YellowPdf id={preview.id} />
            <div className="yc-email">
              <h3>Προεπισκόπηση email</h3>
              <p>Από: {preview.envelope.from}</p>
              <p>Προς: {preview.envelope.to}</p>
              <p>Απάντηση: {preview.envelope.reply_to}</p>
              <p>Θέμα: {preview.envelope.subject}</p>
              <p>{preview.envelope.body}</p>
              <p>Συνημμένο: yellow-card.pdf</p>
            </div>
            <label className="yc-check">
              <input
                type="checkbox"
                checked={approved}
                disabled={busy || sent || uncertain}
                onChange={(e) => setApproved(e.target.checked)}
              />
              Έλεγξα το PDF, εγκρίνω τη χρήση της υπογραφής μου και την αποστολή αυτού του email στο
              τοπικό inbox.
            </label>
            <button
              className="yc-primary"
              disabled={busy || !approved || sent}
              onClick={() =>
                action(async () => {
                  setUncertain(true);
                  let submission: Submission;
                  try {
                    submission = await yc<Submission>(
                      "/submissions",
                      "POST",
                      { preview_id: preview.id, approved: true },
                      sendKey,
                    );
                  } catch (e) {
                    // A rejected first attempt is safe to edit. A rejection on a
                    // retry cannot settle the outcome of the earlier lost response.
                    if (!uncertain && isDefiniteRejection(e)) {
                      setUncertain(false);
                      setApproved(false);
                    }
                    throw e;
                  }
                  setSubmissions((old) => [
                    submission,
                    ...old.filter((s) => s.id !== submission.id),
                  ]);
                  setSent(true);
                  setUncertain(false);
                  setNotice("");
                })
              }
            >
              {sent
                ? "Το αίτημα αποστολής καταχωρήθηκε"
                : uncertain
                  ? "Έλεγχος / επανάληψη του ίδιου αιτήματος"
                  : "Αποστολή στο τοπικό inbox"}
            </button>
            {sent && currentSubmission && (
              <div className="yc-notice" role="status">
                {statuses[currentSubmission.status] ?? currentSubmission.status}
                {currentSubmission.status === "CAPTURED_LOCAL" && (
                  <a href="http://127.0.0.1:8026" target="_blank" rel="noreferrer">
                    Άνοιγμα τοπικού inbox Mailpit ↗
                  </a>
                )}
              </div>
            )}
            {uncertain && (
              <p role="status">
                Η απάντηση της αποστολής εκκρεμεί. Χρησιμοποιήστε το ίδιο κουμπί για ασφαλή
                επανάληψη του αιτήματος.
              </p>
            )}
          </div>
        )}
      </section>
      <section className="yc-card">
        <h2>Ιστορικό τοπικών αποστολών</h2>
        {statusError && (
          <p className="yc-error" role="alert">
            Δεν είναι δυνατή η ενημέρωση της κατάστασης. Οι παρακάτω ενδείξεις μπορεί να είναι
            παλιές. Ελέγξτε το τοπικό inbox Mailpit. Θα προσπαθήσουμε ξανά αυτόματα.
          </p>
        )}
        {submissions.length === 0 ? (
          <p>Δεν υπάρχουν τοπικές αποστολές.</p>
        ) : (
          submissions.map((s) => (
            <div className="yc-row" key={s.id}>
              <strong>{statuses[s.status] ?? s.status}</strong>
              <p>
                {new Date(s.approved_at).toLocaleString("el-GR")} · {s.id}
              </p>
              <a target="_blank" rel="noreferrer" href={`/yellow-cards/artifacts/${s.preview_id}`}>
                Το εγκεκριμένο PDF
              </a>
              {s.status === "CAPTURED_LOCAL" && (
                <a href="http://127.0.0.1:8026" target="_blank" rel="noreferrer">
                  Άνοιγμα τοπικού inbox Mailpit ↗
                </a>
              )}
              {s.status === "QUEUED" && (
                <button
                  disabled={busy}
                  onClick={() =>
                    action(async () => {
                      await yc(`/submissions/${s.id}/cancel`, "POST");
                      setSubmissions(await yc<Submission[]>("/submissions"));
                    })
                  }
                >
                  Ακύρωση πριν την αποστολή
                </button>
              )}
            </div>
          ))
        )}
      </section>
    </div>
  );
}
