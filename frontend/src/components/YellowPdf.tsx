import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
GlobalWorkerOptions.workerSrc = workerUrl;
export function YellowPdf({ id }: { id: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");
  useEffect(() => {
    setDoc(null);
    setPage(1);
    setError("");
    const task = getDocument({ url: `/yellow-cards/artifacts/${id}`, withCredentials: true });
    let active = true;
    task.promise
      .then((pdf) => {
        if (active) setDoc(pdf);
      })
      .catch(() => {
        if (active) setError("Αδυναμία εμφάνισης PDF. Ανοίξτε το σε νέα καρτέλα.");
      });
    return () => {
      active = false;
      void task.destroy();
    };
  }, [id]);
  useEffect(() => {
    if (!doc || !canvas.current) return;
    const target = canvas.current;
    let cancelled = false;
    let renderTask:
      | ReturnType<Awaited<ReturnType<PDFDocumentProxy["getPage"]>>["render"]>
      | undefined;
    doc
      .getPage(page)
      .then((pdfPage) => {
        if (cancelled) return;
        const viewport = pdfPage.getViewport({ scale: zoom });
        const ratio = window.devicePixelRatio || 1;
        target.width = viewport.width * ratio;
        target.height = viewport.height * ratio;
        target.style.width = `${viewport.width}px`;
        target.style.height = `${viewport.height}px`;
        renderTask = pdfPage.render({
          canvas: target,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        });
        return renderTask.promise;
      })
      .catch((e) => {
        if (!cancelled && e.name !== "RenderingCancelledException")
          setError("Αδυναμία απόδοσης σελίδας PDF.");
      });
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [doc, page, zoom]);
  return (
    <div>
      <div className="yc-actions">
        <button disabled={!doc || page === 1} onClick={() => setPage(page - 1)}>
          Προηγούμενη
        </button>
        <span>
          Σελίδα {page} / {doc?.numPages ?? "…"}
        </span>
        <button disabled={!doc || page === doc.numPages} onClick={() => setPage(page + 1)}>
          Επόμενη
        </button>
        <label>
          Μεγέθυνση{" "}
          <select value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
            <option value={0.75}>75%</option>
            <option value={1}>100%</option>
            <option value={1.5}>150%</option>
          </select>
        </label>
        <a href={`/yellow-cards/artifacts/${id}`} target="_blank" rel="noreferrer">
          Άνοιγμα PDF σε νέα καρτέλα
        </a>
      </div>
      {error && (
        <p role="alert" className="yc-error">
          {error}
        </p>
      )}
      <div className="yc-pdf">
        <canvas ref={canvas} aria-label={`Προεπισκόπηση Κίτρινης Κάρτας, σελίδα ${page}`} />
      </div>
    </div>
  );
}
