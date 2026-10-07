import { useEffect, useRef, useState } from "react";
import SignaturePad from "signature_pad";
import { yc, type Signature } from "../lib/yellowCards";

export function YellowSignature({
  saved,
  onChange,
  disabled,
}: {
  saved: Signature | null;
  onChange: (value: Signature | null) => void;
  disabled: boolean;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const pad = useRef<SignaturePad | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!drawing || !canvas.current) return;
    const element = canvas.current;
    const instance = new SignaturePad(element, {
      penColor: "black",
      backgroundColor: "rgba(0,0,0,0)",
    });
    pad.current = instance;
    let previousWidth = 600,
      previousHeight = 200;
    const resize = () => {
      const strokes = instance.toData();
      const width = element.clientWidth,
        height = element.clientHeight;
      const ratio = Math.max(window.devicePixelRatio || 1, 1);
      element.width = Math.round(width * ratio);
      element.height = Math.round(height * ratio);
      element.getContext("2d")?.scale(ratio, ratio);
      instance.clear();
      instance.fromData(
        strokes.map((group) => ({
          ...group,
          points: group.points.map((point) => ({
            ...point,
            x: (point.x * width) / previousWidth,
            y: (point.y * height) / previousHeight,
          })),
        })),
      );
      previousWidth = width;
      previousHeight = height;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    return () => {
      observer.disconnect();
      instance.off();
      pad.current = null;
    };
  }, [drawing]);
  async function save() {
    if (!pad.current || pad.current.isEmpty()) {
      setError("Σχεδιάστε την υπογραφή σας.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const blob = await new Promise<Blob>((resolve, reject) =>
        canvas.current!.toBlob(
          (value) => (value ? resolve(value) : reject(new Error("Αποτυχία εικόνας"))),
          "image/png",
        ),
      );
      const body = new FormData();
      body.append("file", blob, "signature.png");
      onChange(await yc<Signature>("/signature", "POST", body));
      setDrawing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="yc-card">
      <h2>Η υπογραφή μου</h2>
      <p>
        Σχεδιάστε με ποντίκι, δάχτυλο ή γραφίδα. Αποθηκεύεται για επόμενες αναφορές· κάθε αποστολή
        χρειάζεται τη δική σας έγκριση.
      </p>
      {saved && (
        <div>
          <img
            className="yc-saved-signature"
            src={`/yellow-cards/signature/${saved.id}/image`}
            alt="Η αποθηκευμένη υπογραφή σας"
          />
          <button
            disabled={disabled || busy}
            onClick={async () => {
              setBusy(true);
              try {
                await yc("/signature", "DELETE");
                onChange(null);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Διαγραφή αποθηκευμένης υπογραφής
          </button>
        </div>
      )}
      {!drawing ? (
        <button disabled={disabled} onClick={() => setDrawing(true)}>
          {saved ? "Αντικατάσταση υπογραφής" : "Σχεδίαση υπογραφής"}
        </button>
      ) : (
        <div>
          <canvas ref={canvas} className="yc-signature" aria-label="Περιοχή σχεδίασης υπογραφής" />
          <div className="yc-actions">
            <button
              disabled={busy}
              onClick={() => {
                const strokes = pad.current?.toData() ?? [];
                strokes.pop();
                pad.current?.clear();
                pad.current?.fromData(strokes);
              }}
            >
              Αναίρεση
            </button>
            <button disabled={busy} onClick={() => pad.current?.clear()}>
              Καθαρισμός
            </button>
            <button disabled={busy || disabled} onClick={save}>
              Αποθήκευση υπογραφής
            </button>
            <button
              disabled={busy}
              onClick={() => {
                setDrawing(false);
                setError("");
              }}
            >
              Ακύρωση
            </button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="yc-error">
          {error}
        </p>
      )}
    </section>
  );
}
