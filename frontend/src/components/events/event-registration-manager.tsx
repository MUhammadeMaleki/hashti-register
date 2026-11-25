"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button, Card, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { latinDigits, persianDigits } from "@/lib/format";
import { guestsApi, type GuestSummary } from "@/lib/guests";
import { registrationsApi, type RegistrationMember } from "@/lib/registrations";
import styles from "./event-registration-manager.module.css";

export function EventRegistrationManager({ eventId, available, onAdded }: {
  eventId: number; available: boolean; onAdded?: () => void;
}) {
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<GuestSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [searching, setSearching] = useState(false);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [person, setPerson] = useState<RegistrationMember>({
    first_name: "", last_name: "", phone: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (selected !== null || query.trim().length < 2) return;
    let active = true;
    const timer = window.setTimeout(() => {
      setSearching(true);
      guestsApi.list(latinDigits(query.trim())).then((page) => {
        if (active) setMatches(page.items);
      }).catch((caught) => { if (active) setError(errorMessage(caught)); })
        .finally(() => { if (active) setSearching(false); });
    }, 300);
    return () => { active = false; window.clearTimeout(timer); };
  }, [query, selected]);

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || !available) return;
    if (mode === "existing" && selected === null) {
      setError("هشتی‌نشین را از نتایج جست‌وجو انتخاب کنید."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await registrationsApi.adminAdd(eventId, mode === "existing"
        ? { guest_id: selected! } : person);
      onAdded?.();
      setNotice("ثبت‌نام فعال با حضور نامشخص ثبت شد؛ هزینه‌ای ایجاد نشد.");
      setSelected(null);
      setQuery(""); setMatches([]); setResultsOpen(false);
      setPerson({ first_name: "", last_name: "", phone: "" });
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className={styles.panel}><Card title="افزودن هشتی‌نشین">
    <p className="muted">فقط برای هشتی فعال با ثبت‌نام باز. سوابق مالی و حضور بعداً مدیریت می‌شوند.</p>
    {!available && <p className="alert error">ابتدا هشتی را باز و فعال کنید.</p>}
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    <div className="tabs" role="tablist" aria-label="روش افزودن هشتی‌نشین">
      <button type="button" role="tab" aria-selected={mode === "existing"}
        onClick={() => { setMode("existing"); setError(""); }}>هشتی‌نشین موجود</button>
      <button type="button" role="tab" aria-selected={mode === "new"}
        onClick={() => { setMode("new"); setError(""); }}>هشتی‌نشین جدید</button>
    </div>
    <form className="form-stack" onSubmit={add}>
      {mode === "existing" ? <div className={`field ${styles.guestPicker}`}
        onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setResultsOpen(false); }}>
        <label htmlFor="registration-guest-search">جست‌وجو و انتخاب هشتی‌نشین</label>
        <div className={styles.inputWrap}>
        <input id="registration-guest-search" value={query} autoComplete="off"
          placeholder="نام، نام خانوادگی یا شمارهٔ موبایل"
          role="combobox" aria-autocomplete="list" aria-controls="registration-guest-results"
          aria-expanded={resultsOpen && selected === null && query.trim().length >= 2}
          onFocus={() => setResultsOpen(true)}
          onChange={(event) => { setQuery(persianDigits(latinDigits(event.target.value))); setSelected(null);
            setMatches([]); setSearching(event.target.value.trim().length >= 2);
            setResultsOpen(true); setError(""); }} />
        {resultsOpen && selected === null && query.trim().length >= 2 &&
          <div id="registration-guest-results" className={styles.results} role="listbox">
            {searching ? <p>در حال جست‌وجو…</p> : matches.length ? matches.map((guest) =>
              <button type="button" role="option" aria-selected={false} key={guest.id}
                className={styles.result} onClick={() => { setSelected(guest.id);
                  setQuery(`${guest.first_name} ${guest.last_name} — ${persianDigits(guest.phone)}`);
                  setMatches([]); setResultsOpen(false); }}>
                <strong>{guest.first_name} {guest.last_name}</strong><span dir="ltr">{persianDigits(guest.phone)}</span>
              </button>) : <p>هشتی‌نشینی پیدا نشد.</p>}
          </div>}
        </div>
        <small>{selected !== null ? "هشتی‌نشین انتخاب شد؛ اکنون می‌توانید او را اضافه کنید." :
          "حداقل دو نویسه بنویسید و فرد را از نتایج انتخاب کنید."}</small>
      </div> :
        <><div className="field-row"><Field id="registration-first" label="نام" required
          value={person.first_name} onChange={(event) => setPerson((old) => ({ ...old,
            first_name: event.target.value }))} />
          <Field id="registration-last" label="نام خانوادگی" required value={person.last_name}
            onChange={(event) => setPerson((old) => ({ ...old, last_name: event.target.value }))} />
        </div><Field id="registration-phone" label="شماره موبایل" required inputMode="tel"
          value={person.phone} onChange={(event) => setPerson((old) => ({ ...old,
            phone: event.target.value }))} /></>}
      <Button type="submit" className="primary" disabled={busy || !available}>افزودن هشتی‌نشین</Button>
    </form>
  </Card></div>;
}
