"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button, Card, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { guestsApi, type GuestSummary } from "@/lib/guests";
import { registrationsApi, type RegistrationMember } from "@/lib/registrations";

export function EventRegistrationManager({ eventId, available, onAdded }: {
  eventId: number; available: boolean; onAdded?: () => void;
}) {
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<GuestSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [person, setPerson] = useState<RegistrationMember>({
    first_name: "", last_name: "", phone: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setSelected(null);
    setBusy(true);
    try { setMatches((await guestsApi.list(query)).items); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || !available) return;
    if (mode === "existing" && selected === null) {
      setError("مخاطب را از نتایج جست‌وجو انتخاب کنید."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await registrationsApi.adminAdd(eventId, mode === "existing"
        ? { guest_id: selected! } : person);
      onAdded?.();
      setNotice("ثبت‌نام فعال با حضور نامشخص ثبت شد؛ هزینه‌ای ایجاد نشد.");
      setSelected(null);
      setPerson({ first_name: "", last_name: "", phone: "" });
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <Card title="افزودن مهمان به رویداد">
    <p className="muted">فقط برای ثبت‌نام باز و رویداد لغونشده. سوابق مالی و حضور بعداً مدیریت می‌شوند.</p>
    {!available && <p className="alert error">ابتدا رویداد را باز و فعال کنید.</p>}
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    <div className="tabs" role="tablist" aria-label="روش افزودن مهمان">
      <button type="button" role="tab" aria-selected={mode === "existing"}
        onClick={() => { setMode("existing"); setError(""); }}>مخاطب موجود</button>
      <button type="button" role="tab" aria-selected={mode === "new"}
        onClick={() => { setMode("new"); setError(""); }}>مخاطب جدید</button>
    </div>
    {mode === "existing" && <form className="row-actions" onSubmit={search}>
      <div className="field guest-search"><label htmlFor="registration-guest-search">نام یا موبایل</label>
        <input id="registration-guest-search" value={query}
          onChange={(event) => setQuery(event.target.value)} /></div>
      <Button type="submit" className="secondary" disabled={busy}>جست‌وجو</Button>
    </form>}
    <form className="form-stack" onSubmit={add}>
      {mode === "existing" ? <div className="field"><label htmlFor="registration-guest">مخاطب</label>
        <select id="registration-guest" value={selected ?? ""}
          onChange={(event) => setSelected(event.target.value ? Number(event.target.value) : null)}>
          <option value="">انتخاب مخاطب</option>
          {matches.map((guest) => <option key={guest.id} value={guest.id}>
            {guest.first_name} {guest.last_name} — {guest.phone}</option>)}
        </select><small><Link className="text-link" href="/panel/guests">بانک مخاطبان</Link></small></div> :
        <><div className="field-row"><Field id="registration-first" label="نام" required
          value={person.first_name} onChange={(event) => setPerson((old) => ({ ...old,
            first_name: event.target.value }))} />
          <Field id="registration-last" label="نام خانوادگی" required value={person.last_name}
            onChange={(event) => setPerson((old) => ({ ...old, last_name: event.target.value }))} />
        </div><Field id="registration-phone" label="شماره موبایل" required inputMode="tel"
          value={person.phone} onChange={(event) => setPerson((old) => ({ ...old,
            phone: event.target.value }))} /></>}
      <Button type="submit" className="primary" disabled={busy || !available}>افزودن به رویداد</Button>
    </form>
  </Card>;
}
