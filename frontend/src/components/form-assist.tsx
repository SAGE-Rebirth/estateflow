"use client";

import { LoaderCircle, Mic, Sparkles, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import {
  fieldLabel, fieldValue, fillableFields, flash, setFieldValue, type FillableField,
} from "@/lib/form-fill";
import {
  englishCity, matchOption, parseSpokenNumber, spokenBoolean, spokenEmail, spokenPhone, spokenText, voiceCommand,
} from "@/lib/voice";

// Web Speech API (Chrome, Edge, Safari). Not in every TS DOM lib, so typed minimally here.
type Alternative = { transcript: string };
type Result = { isFinal: boolean; 0: Alternative };
type ResultEvent = { resultIndex: number; results: ArrayLike<Result> };
interface Recognition {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((e: ResultEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void; stop(): void; abort(): void;
}
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

// Indian English and Hindi. The choice is remembered per device.
const LANGS = { "en-IN": "EN", "hi-IN": "हिंदी" } as const;
type Lang = keyof typeof LANGS;
const LANG_KEY = "estateflow.voice-lang";
const HINTS: Record<Lang, string> = {
  "en-IN": "Say “next” to skip · “back” · “clear” · “submit form” · “stop” (or Esc)",
  "hi-IN": "“अगला” आगे · “पीछे” · “साफ़ करो” · “जमा करो” · “रुको” (या Esc)",
};

function savedLang(): Lang {
  try {
    const v = localStorage.getItem(LANG_KEY);
    return v === "hi-IN" ? "hi-IN" : "en-IN";
  } catch {
    return "en-IN";
  }
}

function LangSwitch({ value, onChange, dark = false }: { value: Lang; onChange: (l: Lang) => void; dark?: boolean }) {
  return (
    <span role="group" aria-label="Voice language" className={`inline-flex overflow-hidden rounded-md border text-xs ${dark ? "border-white/25" : "border-rule"}`}>
      {(Object.keys(LANGS) as Lang[]).map((l) => (
        <button
          key={l} type="button" aria-pressed={value === l} onClick={() => onChange(l)}
          className={`px-2 py-1 font-medium ${value === l ? (dark ? "bg-paper text-ink" : "bg-registry text-white") : dark ? "text-paper/80 hover:bg-white/10" : "bg-paper text-ink-soft hover:text-ink"}`}
        >
          {LANGS[l]}
        </button>
      ))}
    </span>
  );
}
const PASTE_FORMS = { property: "a listing", contact: "a lead's details" } as const;
type PasteKind = keyof typeof PASTE_FORMS;

/** Turns spoken words into a value for this field. `advance` moves on to the next field. */
function interpret(el: FillableField, said: string): { value?: string | boolean; advance: boolean; problem?: string } {
  const name = fieldLabel(el);
  if (el instanceof HTMLSelectElement) {
    const value = matchOption(said, Array.from(el.options).map((o) => ({ value: o.value, label: o.text })));
    return value === null ? { advance: false, problem: `No “${name}” option matches “${said}”.` } : { value, advance: true };
  }
  if (el instanceof HTMLTextAreaElement) {
    const before = el.value.trim();
    const sentence = spokenText(said);
    return { value: before ? `${before}${/[.!?]$/.test(before) ? "" : "."} ${sentence}` : sentence, advance: false };
  }
  if (el.type === "checkbox") {
    const value = spokenBoolean(said);
    return value === null ? { advance: false, problem: `Say “yes” or “no” for “${name}”.` } : { value, advance: true };
  }
  if (el.type === "number") {
    const n = parseSpokenNumber(said);
    return n === null ? { advance: false, problem: `Didn’t catch a number for “${name}”. Try again.` } : { value: String(n), advance: true };
  }
  if (el.type === "email" || /email/i.test(el.name)) return { value: spokenEmail(said), advance: true };
  if (el.type === "tel" || /phone|mobile|whatsapp/i.test(el.name + el.autocomplete)) return { value: spokenPhone(said), advance: true };
  if (el.name === "city") return { value: englishCity(spokenText(said)), advance: true };
  return { value: spokenText(said), advance: true };
}

type Toast = { tone: "info" | "ok" | "error"; text: string; undo?: () => void; busy?: boolean };

/**
 * Drop inside any <form>. Adds "Fill by voice" (speak each field in turn) and, with `paste`,
 * smart paste: pasting a block of text from anywhere fills the matching fields. `compact`
 * renders just a mic button, for one-line forms.
 */
export function FormAssist({ paste, compact = false }: { paste?: PasteKind; compact?: boolean }) {
  const anchor = useRef<HTMLDivElement>(null);
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [current, setCurrent] = useState("");
  const [heard, setHeard] = useState("");
  const [toast, setToast] = useState<Toast | null>(null);
  const [lang, setLangState] = useState<Lang>("en-IN");
  const langRef = useRef<Lang>("en-IN");
  const rec = useRef<Recognition | null>(null);
  const active = useRef(false);
  const index = useRef(0);
  const toastTimer = useRef<number>(undefined);

  const form = useCallback(() => anchor.current?.closest("form") ?? null, []);

  const show = useCallback((t: Toast | null, ms = 8000) => {
    window.clearTimeout(toastTimer.current);
    setToast(t);
    if (t && !t.busy) toastTimer.current = window.setTimeout(() => setToast(null), ms);
  }, []);

  useEffect(() => {
    setSupported(recognitionCtor() !== null);
    langRef.current = savedLang();
    setLangState(langRef.current);
  }, []);

  const setLang = useCallback((l: Lang) => {
    langRef.current = l;
    setLangState(l);
    try { localStorage.setItem(LANG_KEY, l); } catch { /* private mode: not remembered */ }
    rec.current?.abort(); // onend restarts it in the new language
  }, []);

  // --- Voice fill ---------------------------------------------------------------------

  const fields = useCallback(() => { const f = form(); return f ? fillableFields(f) : []; }, [form]);

  const focusField = useCallback((i: number) => {
    const list = fields();
    list.forEach((el) => el.removeAttribute("data-voice-active"));
    const el = list[i];
    if (!el) return;
    index.current = i;
    el.setAttribute("data-voice-active", "");
    el.focus({ preventScroll: true });
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    setCurrent(fieldLabel(el));
    setHeard("");
  }, [fields]);

  const stop = useCallback((message?: Toast) => {
    active.current = false;
    rec.current?.abort();
    rec.current = null;
    fields().forEach((el) => el.removeAttribute("data-voice-active"));
    setListening(false);
    setHeard("");
    if (message) show(message);
  }, [fields, show]);

  const move = useCallback((step: number) => {
    const next = index.current + step;
    if (next >= fields().length) {
      stop({ tone: "ok", text: "That was the last field. Check the form, then save." });
      return;
    }
    focusField(Math.max(next, 0));
  }, [fields, focusField, stop]);

  const handleSpeech = useCallback((said: string) => {
    const el = fields()[index.current];
    if (!el || !said.trim()) return;
    const command = voiceCommand(said);
    if (command === "next") return move(1);
    if (command === "previous") return move(-1);
    if (command === "clear") { setFieldValue(el, el instanceof HTMLInputElement && el.type === "checkbox" ? false : ""); return; }
    if (command === "stop") return stop();
    if (command === "submit") { const f = form(); stop(); f?.requestSubmit(); return; }
    const { value, advance, problem } = interpret(el, said);
    if (problem) { show({ tone: "error", text: problem }, 5000); return; }
    setFieldValue(el, value!);
    flash(el);
    setToast(null);
    if (advance) move(1);
  }, [fields, form, move, stop, show]);

  const start = useCallback(() => {
    const Ctor = recognitionCtor();
    const list = fields();
    if (!Ctor || list.length === 0) return;
    // Start where the cursor is; otherwise at the first empty field.
    const focused = list.indexOf(document.activeElement as FillableField);
    const empty = list.findIndex((el) => fieldValue(el) === "");
    focusField(focused >= 0 ? focused : Math.max(empty, 0));

    const r = new Ctor();
    r.lang = langRef.current;
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) handleSpeech(res[0].transcript);
        else interim += res[0].transcript;
      }
      setHeard(interim);
    };
    r.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        stop({ tone: "error", text: "Microphone access is blocked. Allow it in your browser’s site settings, then try again." });
      } else if (e.error === "network") {
        stop({ tone: "error", text: "The browser’s speech service is unreachable. Check your connection." });
      } else if (e.error === "audio-capture") {
        stop({ tone: "error", text: "No microphone found." });
      } // "no-speech" and "aborted" are normal pauses
    };
    // Browsers end recognition after a silence; keep going until the user stops.
    r.onend = () => {
      if (!active.current) return;
      r.lang = langRef.current;
      try { r.start(); } catch { stop(); }
    };
    rec.current = r;
    active.current = true;
    setListening(true);
    r.start();
  }, [fields, focusField, handleSpeech, stop]);

  // Clicking or tabbing into another field moves voice input there.
  useEffect(() => {
    const f = form();
    if (!f || !listening) return;
    const onFocus = (e: FocusEvent) => {
      const i = fields().indexOf(e.target as FillableField);
      if (i >= 0 && i !== index.current) focusField(i);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") stop(); };
    f.addEventListener("focusin", onFocus);
    window.addEventListener("keydown", onKey);
    return () => { f.removeEventListener("focusin", onFocus); window.removeEventListener("keydown", onKey); };
  }, [listening, fields, form, focusField, stop]);

  useEffect(() => () => { active.current = false; rec.current?.abort(); window.clearTimeout(toastTimer.current); }, []);

  // --- Smart paste ---------------------------------------------------------------------

  useEffect(() => {
    const f = form();
    if (!f || !paste) return;
    const onPaste = (e: ClipboardEvent) => {
      const text = e.clipboardData?.getData("text/plain") ?? "";
      // Short or single-line pastes (a name, a number) behave normally.
      if (text.trim().length < 60 || (!text.includes("\n") && text.length < 120)) return;
      const target = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement ? e.target : null;
      // Into a text area the paste lands as usual; anywhere else we fill the form instead.
      const keepPaste = target instanceof HTMLTextAreaElement;
      if (!keepPaste) e.preventDefault();
      show({ tone: "info", text: "Reading the pasted text…", busy: true });
      api<{ fields: Record<string, unknown> }>("/assist/extract", { method: "POST", json: { form: paste, text } })
        .then(({ fields: found }) => {
          const previous: [FillableField, string | boolean][] = [];
          for (const [name, raw] of Object.entries(found)) {
            const el = f.elements.namedItem(name);
            if (!(el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement)) continue;
            if (keepPaste && el === target) continue;
            const value = Array.isArray(raw) ? raw.join(", ") : typeof raw === "boolean" ? raw : String(raw);
            if (el instanceof HTMLSelectElement && !Array.from(el.options).some((o) => o.value === value)) continue;
            previous.push([el, fieldValue(el)]);
            setFieldValue(el, value);
            flash(el);
          }
          if (previous.length === 0) {
            if (!keepPaste && target) setFieldValue(target, `${target.value}${text}`);
            show({ tone: "error", text: `Couldn’t find ${PASTE_FORMS[paste]} in that text, so it was pasted as is.` });
            return;
          }
          show({
            tone: "ok",
            text: `Filled ${previous.length} field${previous.length === 1 ? "" : "s"} from the pasted text. Check them before saving.`,
            undo: () => { previous.forEach(([el, v]) => setFieldValue(el, v)); show({ tone: "info", text: "Undone." }, 3000); },
          }, 15000);
        })
        .catch((err: unknown) => {
          if (!keepPaste && target) setFieldValue(target, `${target.value}${text}`);
          const why = err instanceof ApiError ? err.message : "The request failed.";
          show({ tone: "error", text: `Couldn’t auto-fill (${why}) The text was pasted as is.` });
        });
    };
    f.addEventListener("paste", onPaste, true);
    return () => f.removeEventListener("paste", onPaste, true);
  }, [form, paste, show]);

  if (!supported && !paste) return <div ref={anchor} hidden />;

  const micButton = supported && (
    <button
      type="button" aria-pressed={listening} aria-label={compact ? (listening ? "Stop voice input" : "Speak instead of typing") : undefined}
      title={compact ? "Speak instead of typing" : undefined}
      onClick={() => (listening ? stop() : start())}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border font-medium ${compact ? "h-10 px-2.5" : "px-3 py-1.5"} ${listening ? "border-brick bg-brick text-white" : "border-rule bg-paper text-ink hover:border-registry"}`}
    >
      <Mic size={15} aria-hidden />{!compact && (listening ? " Stop voice" : " Fill by voice")}
    </button>
  );

  return (
    <div ref={anchor} className={compact ? "contents" : "flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed border-rule bg-stone/60 px-3 py-2 text-sm"}>
      {!compact && (
        <p className="text-ink-soft">
          {paste ? <><Sparkles size={14} className="mr-1 inline text-marigold" aria-hidden />Paste {PASTE_FORMS[paste]} from anywhere to fill this form{supported ? ", or fill it by voice." : "."}</>
            : "Speak instead of typing: each answer fills a field and moves to the next."}
        </p>
      )}
      {!compact && supported && (
        <span className="inline-flex items-center gap-2">
          <LangSwitch value={lang} onChange={setLang} />
          {micButton}
        </span>
      )}
      {compact && micButton}

      {(listening || toast) && (
        <div className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-lg space-y-2" role="status" aria-live="polite">
          {toast && (
            <div className={`flex items-start gap-2 rounded-md border px-3 py-2 shadow-lg ${toast.tone === "error" ? "border-brick/30 bg-brick-tint text-brick" : toast.tone === "ok" ? "border-registry/30 bg-registry-tint text-registry-deep" : "border-rule bg-paper text-ink"}`}>
              {toast.busy && <LoaderCircle size={16} className="mt-0.5 shrink-0 animate-spin" aria-hidden />}
              <span className="flex-1">{toast.text}</span>
              {toast.undo && (
                <button type="button" onClick={toast.undo} className="inline-flex items-center gap-1 font-semibold underline">
                  <Undo2 size={14} aria-hidden /> Undo
                </button>
              )}
              {!toast.busy && <button type="button" onClick={() => show(null)} aria-label="Dismiss"><X size={16} /></button>}
            </div>
          )}
          {listening && (
            <div className="rounded-md bg-ink px-4 py-3 text-paper shadow-lg">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-brick" aria-hidden />
                <span className="flex-1 truncate">{lang === "hi-IN" ? "सुन रहे हैं:" : "Listening for"} <strong>{current}</strong></span>
                <LangSwitch value={lang} onChange={setLang} dark />
                <button type="button" onClick={() => stop()} className="rounded px-2 py-0.5 text-sm hover:bg-white/10">Stop</button>
              </div>
              <p className="mt-1 min-h-5 truncate italic text-paper/80">{heard}</p>
              <p className="mt-1 text-xs text-paper/60">{HINTS[lang]}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
