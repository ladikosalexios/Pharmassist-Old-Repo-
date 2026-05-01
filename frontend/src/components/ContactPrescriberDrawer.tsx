import { useEffect, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { PhoneIcon, MailIcon, SendIcon, MessageIcon, XIcon, AlertCircleIcon } from "./Icons";
import { ApiError, getMessages, sendMessage } from "../lib/api";
import { useToast } from "./Toast";
import type { Prescriber, PrescriptionMessage } from "../types";

interface ContactPrescriberDrawerProps {
  open: boolean;
  rxId: string;
  patientName: string;
  prescriber: Prescriber;
  onClose: () => void;
}

export function ContactPrescriberDrawer({
  open, rxId, patientName, prescriber, onClose,
}: ContactPrescriberDrawerProps) {
  const [messages, setMessages] = useState<PrescriptionMessage[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const { toast } = useToast();

  // Load thread when the drawer opens or rxId changes.
  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoadError(null);
    setMessages(null);
    getMessages(rxId)
      .then((items) => { if (active) setMessages(items); })
      .catch((e: unknown) => {
        if (!active) return;
        setLoadError(e instanceof ApiError ? e.message : "Could not load message thread.");
      });
    return () => { active = false; };
  }, [open, rxId]);

  // Close on Escape, focus the close button on open.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => closeBtnRef.current?.focus(), 0);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !sending) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, sending, onClose]);

  // Scroll the message list to the bottom when it (re)loads or grows.
  useEffect(() => {
    if (!messages) return;
    messagesEndRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages]);

  if (!open) return null;

  const mailtoHref =
    `mailto:${encodeURIComponent(prescriber.email)}` +
    `?subject=${encodeURIComponent(`Re: Prescription ${rxId} - ${patientName}`)}`;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (sending) return;
    if (!body.trim()) {
      setSendError("Message cannot be empty.");
      return;
    }
    setSending(true);
    setSendError(null);
    try {
      const newMsg = await sendMessage(prescriber.licenceId, rxId, body.trim());
      setMessages((cur) => (cur ? [...cur, newMsg] : [newMsg]));
      setBody("");
      toast(`Message sent to ${prescriber.name}`, "success");
    } catch (e) {
      setSendError(e instanceof ApiError ? e.message : "Could not send the message.");
    } finally {
      setSending(false);
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-slate-900/40 animate-fade-in"
        onClick={() => { if (!sending) onClose(); }}
        aria-hidden="true"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Contact Prescriber"
        className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-white shadow-cardLg animate-slide-in-right"
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Contact Prescriber</h2>
            <p className="text-xs text-slate-500">
              <span className="font-mono">{rxId}</span> — {patientName}
            </p>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            disabled={sending}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
            aria-label="Close contact panel"
          >
            <XIcon />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto">
          {/* Prescriber card */}
          <section className="border-b border-slate-200 px-5 py-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm font-semibold text-slate-900">{prescriber.name}</div>
              <div className="mt-0.5 text-xs text-slate-500">{prescriber.specialty}</div>
              <dl className="mt-3 space-y-2 text-[13px]">
                <Field label="Licence / ID" value={<span className="font-mono">{prescriber.licenceId}</span>} />
                <Field label="Phone" value={<a href={`tel:${prescriber.contact}`} className="text-brand-600 hover:underline">{prescriber.contact}</a>} />
                <Field label="Email" value={<a href={mailtoHref} className="text-brand-600 hover:underline">{prescriber.email}</a>} />
              </dl>
            </div>

            {/* Quick actions */}
            <div className="mt-4 grid grid-cols-3 gap-2">
              <a href={`tel:${prescriber.contact}`} className="btn btn-outline justify-center">
                <PhoneIcon /> Call
              </a>
              <a href={mailtoHref} className="btn btn-outline justify-center">
                <MailIcon /> Email
              </a>
              <a
                href="#compose"
                onClick={(e) => {
                  e.preventDefault();
                  document.getElementById("compose-textarea")?.focus();
                }}
                className="btn btn-primary justify-center"
              >
                <MessageIcon /> Message
              </a>
            </div>
          </section>

          {/* Message history */}
          <section className="px-5 py-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Message History</h3>
              {messages && <span className="text-xs text-slate-500">{messages.length} message{messages.length === 1 ? "" : "s"}</span>}
            </div>

            {loadError ? (
              <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
                <AlertCircleIcon width={14} height={14} className="mt-0.5 shrink-0" />
                <span>{loadError}</span>
              </div>
            ) : !messages ? (
              <div className="flex items-center gap-2 text-sm text-slate-500"><span className="spinner text-brand-600" /> Loading messages…</div>
            ) : messages.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
                No messages yet. Start the thread below.
              </div>
            ) : (
              <ul className="space-y-3">
                {messages.map((m) => <MessageRow key={m.id} message={m} />)}
                <div ref={messagesEndRef} />
              </ul>
            )}
          </section>
        </div>

        {/* Compose */}
        <form id="compose" onSubmit={onSubmit} className="border-t border-slate-200 bg-slate-50 px-5 py-4">
          {sendError && (
            <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
              {sendError}
            </div>
          )}
          <label htmlFor="compose-textarea" className="sr-only">New message</label>
          <textarea
            id="compose-textarea"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={`Write a message to ${prescriber.name}…`}
            className="w-full min-h-[88px] resize-vertical rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
          />
          <div className="mt-2 flex justify-end">
            <button
              type="submit"
              disabled={sending || !body.trim()}
              className="btn btn-primary disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {sending ? <span className="spinner" /> : <SendIcon />}
              {sending ? "Sending…" : "Send Message"}
            </button>
          </div>
        </form>
      </aside>
    </div>,
    document.body,
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="text-right text-sm text-slate-900">{value}</dd>
    </div>
  );
}

function MessageRow({ message }: { message: PrescriptionMessage }) {
  const fromPharmacist = message.from === "pharmacist";
  return (
    <li className={`flex ${fromPharmacist ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
        fromPharmacist
          ? "bg-brand-600 text-white"
          : "bg-white text-slate-800 border border-slate-200"
      }`}>
        <div className={`mb-1 flex items-baseline gap-2 text-[11px] ${fromPharmacist ? "text-white/80" : "text-slate-500"}`}>
          <span className="font-semibold">{message.fromName}</span>
          <span>{formatTimestamp(message.sentAt)}</span>
        </div>
        <div className="whitespace-pre-wrap">{message.body}</div>
      </div>
    </li>
  );
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
