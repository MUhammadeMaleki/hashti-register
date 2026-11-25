"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Button, Card, Field } from "@/components/ui";
import { EventAttendanceTable } from "@/components/events/event-attendance-table";
import { EventRegistrationManager } from "@/components/events/event-registration-manager";
import { errorMessage } from "@/lib/api";
import { eventsApi, type EventRecord, type Location, type Secretary } from "@/lib/events";
import { isoToJalali, jalaliToIso } from "@/lib/format";
import styles from "./event-editor.module.css";

type Form = {
  event_number: string; title: string; description: string; event_date: string;
  start_time: string; time_text: string; time_mode: "exact" | "approximate" | "tba";
  location_id: string;
  location_mode: "exact" | "approximate" | "tba"; location_text: string;
  hosts: string; entry_fee: string; capacity: string; public_note: string;
  registration_status: "open" | "closed";
};

const emptyForm: Form = {
  event_number: "", title: "", description: "", event_date: "", start_time: "",
  time_text: "", time_mode: "tba", location_id: "", location_mode: "tba", location_text: "",
  hosts: "", entry_fee: "0", capacity: "", public_note: "", registration_status: "closed",
};

function fromEvent(event: EventRecord): Form {
  return {
    event_number: String(event.event_number), title: event.title,
    description: event.description ?? "", event_date: event.event_date ?
      isoToJalali(event.event_date) : "",
    start_time: event.start_time?.slice(0, 5) ?? "", time_text: event.time_text ?? "",
    time_mode: event.time_mode,
    location_id: event.location_id ? String(event.location_id) : "",
    location_mode: event.location_mode, location_text: event.location_text ?? "",
    hosts: event.hosts ?? "", entry_fee: String(event.entry_fee),
    capacity: event.capacity === null ? "" : String(event.capacity),
    public_note: event.public_note ?? "", registration_status: event.registration_status,
  };
}

function payload(form: Form) {
  return {
    event_number: Number(form.event_number), title: form.title.trim(),
    description: form.description.trim() || null,
    event_date: form.event_date ? jalaliToIso(form.event_date) : null,
    start_time: form.time_mode === "exact" ? form.start_time || null : null,
    time_text: form.time_mode === "approximate" ? form.time_text.trim() || null : null,
    time_mode: form.time_mode,
    location_id: form.location_mode === "exact" && form.location_id ?
      Number(form.location_id) : null,
    location_mode: form.location_mode,
    location_text: form.location_mode === "approximate" ? form.location_text.trim() || null : null,
    hosts: form.hosts.trim() || null, entry_fee: Number(form.entry_fee),
    capacity: form.capacity === "" ? null : Number(form.capacity),
    public_note: form.public_note.trim() || null,
    registration_status: form.registration_status,
  };
}

export function EventEditor({ eventId }: { eventId?: number }) {
  const router = useRouter();
  const [form, setForm] = useState<Form>(emptyForm);
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [secretaries, setSecretaries] = useState<Secretary[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [posterFile, setPosterFile] = useState<File | null>(null);
  const [attendanceRefresh, setAttendanceRefresh] = useState(0);
  const [feeInput, setFeeInput] = useState("0");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [places, people, existing, next] = await Promise.all([
          eventsApi.allLocations(), eventsApi.secretaries(),
          eventId ? eventsApi.get(eventId) : Promise.resolve(null),
          eventId ? Promise.resolve(null) : eventsApi.nextNumber(),
        ]);
        if (!active) return;
        setLocations(places); setSecretaries(people);
        if (existing) {
          setEvent(existing); setForm(fromEvent(existing));
          setFeeInput(String(existing.entry_fee));
          setSelected(existing.secretaries.filter((person) => person.is_active)
            .map((person) => person.id));
        } else if (next) setForm({ ...emptyForm, event_number: String(next.suggested_number) });
      } catch (caught) { if (active) setError(errorMessage(caught)); }
      finally { if (active) setLoading(false); }
    }
    load();
    return () => { active = false; };
  }, [eventId]);

  useEffect(() => {
    if (eventId && new URLSearchParams(window.location.search)
      .get("poster_upload_failed") === "1") {
      setError("رویداد ساخته شد، اما پوستر بارگذاری نشد. فایل را دوباره انتخاب و بارگذاری کنید.");
    }
  }, [eventId]);

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }

  function setTimeMode(mode: Form["time_mode"]) {
    setForm((previous) => ({ ...previous, time_mode: mode,
      event_date: mode === "exact" ? previous.event_date : "",
      start_time: mode === "exact" ? previous.start_time : "",
      time_text: mode === "approximate" ? previous.time_text : "",
    }));
  }

  function setLocationMode(mode: Form["location_mode"]) {
    setForm((previous) => ({ ...previous, location_mode: mode,
      location_id: mode === "exact" ? previous.location_id : "",
      location_text: mode === "approximate" ? previous.location_text : "",
    }));
  }

  function toggleSecretary(id: number) {
    setSelected((previous) => previous.includes(id) ? previous.filter((item) => item !== id) :
      [...previous, id]);
  }

  async function save(eventSubmit: FormEvent<HTMLFormElement>) {
    eventSubmit.preventDefault(); if (busy) return;
    setError(""); setNotice("");
    if (!Number.isInteger(Number(form.event_number)) || Number(form.event_number) < 1 ||
        !form.title.trim()) {
      setError("شمارهٔ مثبت و عنوان رویداد الزامی‌اند."); return;
    }
    if (form.event_date && !jalaliToIso(form.event_date)) {
      setError("تاریخ شمسی معتبر نیست؛ نمونه: ۱۴۰۵/۰۹/۰۲."); return;
    }
    if (posterFile && posterFile.size > 5 * 1024 * 1024) {
      setError("حجم پوستر باید کمتر از ۵ مگابایت باشد."); return;
    }
    setBusy(true);
    try {
      const body = payload(form);
      if (eventId) {
        const { entry_fee: _entryFee, ...eventFields } = body;
        const updated = await eventsApi.update(eventId, eventFields);
        setEvent(updated); setForm(fromEvent(updated)); setNotice("اطلاعات رویداد ذخیره شد.");
      } else {
        const created = await eventsApi.create({ ...body, secretary_ids: selected });
        if (posterFile) {
          try { await eventsApi.uploadPoster(created.id, posterFile); }
          catch {
            router.replace(`/panel/events/${created.id}?poster_upload_failed=1`);
            return;
          }
        }
        router.replace(`/panel/events/${created.id}`);
      }
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function saveSecretaries() {
    if (!eventId || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await eventsApi.setSecretaries(eventId, selected);
      setEvent(updated); setNotice("فهرست دبیران ذخیره شد.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function saveEntryFee() {
    if (!eventId || !event || busy) return;
    const amount = Number(feeInput);
    if (!Number.isSafeInteger(amount) || amount < 0 || feeInput.trim() === "") {
      setError("مبلغ ورودی باید عدد صحیح نامنفی باشد."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await eventsApi.updateEntryFee(eventId, amount, crypto.randomUUID());
      const updated = { ...event, entry_fee: result.entry_fee };
      setEvent(updated); setForm(fromEvent(updated)); setFeeInput(String(updated.entry_fee));
      setAttendanceRefresh((value) => value + 1);
      setNotice(`ورودی ذخیره شد؛ ${result.registrations} ثبت‌نام بررسی و ${result.refunds} تومان برگشت داده شد.`);
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function uploadPoster() {
    if (!eventId || !posterFile || busy) return;
    if (posterFile.size > 5 * 1024 * 1024) {
      setError("حجم پوستر باید کمتر از ۵ مگابایت باشد."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await eventsApi.uploadPoster(eventId, posterFile);
      setEvent(updated); setPosterFile(null); setNotice("پوستر ذخیره شد.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!eventId || busy || !window.confirm("رویداد بدون سابقه حذف شود؟ این کار قابل بازگشت نیست."))
      return;
    setBusy(true); setError("");
    try { await eventsApi.remove(eventId); router.replace("/panel/events"); }
    catch (caught) { setError(errorMessage(caught)); setBusy(false); }
  }

  async function changeCancellation(reactivate: boolean) {
    if (!eventId || !event || busy) return;
    if (!reactivate && !window.confirm(
      "رویداد و همهٔ ثبت‌نام‌های فعال لغو شوند؟ هزینه‌ها لغو و تسویه‌ها به کیف پول برگردانده می‌شوند."
    )) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = reactivate ? await eventsApi.reactivate(eventId) :
        await eventsApi.cancel(eventId);
      setEvent({ ...event, is_cancelled: result.is_cancelled });
      setAttendanceRefresh((value) => value + 1);
      setNotice(reactivate ?
        "رویداد دوباره فعال شد؛ ثبت‌نام‌های قبلی همچنان لغوشده‌اند و باید جداگانه فعال شوند." :
        `${result.registrations} ثبت‌نام لغو و ${result.refunded_total} تومان به کیف پول‌ها برگشت داده شد.`);
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  if (loading) return <p role="status">در حال دریافت اطلاعات رویداد…</p>;
  const posterFields = <>
    {event?.poster_url && <img className="poster-preview" src={event.poster_url}
      alt={`پوستر ${event.title}`} />}
    <div className="field"><label htmlFor="event-poster">تصویر پوستر (حداکثر ۵ مگابایت)</label>
      <input id="event-poster" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
        onChange={(change) => setPosterFile(change.target.files?.[0] ?? null)} />
      <small>{eventId ? "JPG، PNG، WebP، HEIC یا HEIF؛ پس از انتخاب، بارگذاری پوستر را بزنید." :
        "پوستر اختیاری است و همراه با ساخت هشتی بارگذاری می‌شود."}</small></div>
    {eventId && <Button type="button" className="secondary"
      disabled={!posterFile || busy || event?.is_cancelled}
      onClick={uploadPoster}>بارگذاری پوستر</Button>}
  </>;
  const secretaryFields = <>
    <p className="muted">هنگام ساخت، دبیر ایجادکننده خودکار اضافه می‌شود.
      حداقل یک دبیر فعال باید باقی بماند.</p>
    <div className="checkbox-grid">{secretaries.map((person) =>
      <label key={person.id} className="checkbox-item"><input type="checkbox"
        checked={selected.includes(person.id)} onChange={() => toggleSecretary(person.id)} />
        {person.full_name}</label>)}</div>
    {secretaries.length === 0 && <p className="muted">دبیر فعالی وجود ندارد.</p>}
    {event?.secretaries.filter((person) => !person.is_active).map((person) =>
      <p className="muted" key={person.id}>{person.full_name} — غیرفعال؛ انتساب تاریخی حفظ می‌شود.</p>)}
    {eventId && <Button type="button" className="secondary" disabled={busy}
      onClick={saveSecretaries}>ذخیره دبیران</Button>}
  </>;
  return <div className={`editor-stack ${styles.editorPage}`}>
    <div className={`section-heading ${styles.editorHero}`}><div>
      <span className={styles.heroEyebrow}>پنل مدیریت / {eventId ? "ویرایش هشتی" : "ساخت هشتی"}</span>
      <h2>{eventId ? "ویرایش هشتی" : "یک هشتی تازه بسازیم"}</h2>
      <p className="muted">{eventId ? "اطلاعات و ظاهر این هشتی را از همین صفحه به‌روز کنید." :
        "شمارهٔ پیشنهادی قابل تغییر است؛ تکراری‌بودن هنگام ذخیره کنترل می‌شود."}</p></div>
      <Link className="button secondary" href="/panel/events">بازگشت به هشتی‌ها</Link></div>
    {error && <p role="alert" className="alert error">{error}</p>}
    {notice && <p role="status" className="alert success">{notice}</p>}
    {event?.is_cancelled && <p className="alert error">این رویداد لغو شده است و ویرایش اطلاعات آن فعلاً بسته است.</p>}
    <Card title="اطلاعات هشتی"><form onSubmit={save} className="form-stack">
      <section className={styles.formSection}>
        <div className={styles.sectionIntro}><span>۰۱</span><div><h3>هویت هشتی</h3><p>نام و موضوعی که هشتی‌نشین‌ها می‌بینند.</p></div></div>
      <div className="field-row"><Field id="event-number" label="شماره هشتی" type="number" min={1}
        value={form.event_number} onChange={(e) => set("event_number", e.target.value)} required />
        <Field id="event-title" label="عنوان" value={form.title}
          onChange={(e) => set("title", e.target.value)} required maxLength={255} /></div>
      <div className="field"><label htmlFor="event-description">توضیحات</label><textarea
        id="event-description" rows={3} value={form.description}
        onChange={(e) => set("description", e.target.value)} /></div>
      </section>
      <section className={styles.formSection}>
        <div className={styles.sectionIntro}><span>۰۲</span><div><h3>زمان و مکان</h3><p>برای هرکدام، وضعیت اعلام را جداگانه مشخص کنید.</p></div></div>
      <div className={styles.scheduleGrid}><div className={styles.scheduleBlock}>
      <div className="field"><label htmlFor="time-mode">نحوهٔ اعلام زمان</label>
        <select id="time-mode" value={form.time_mode}
          onChange={(e) => setTimeMode(e.target.value as Form["time_mode"])}>
          <option value="tba">اعلام بعدی</option><option value="approximate">تقریبی</option>
          <option value="exact">دقیق</option></select></div>
      {form.time_mode === "exact" && <div className={styles.exactTimeGroup}>
        <div className={`field-row ${styles.exactTimeFields}`}><Field id="event-date" label="تاریخ برگزاری (شمسی)"
        inputMode="numeric" placeholder="۱۴۰۵/۰۹/۰۲"
        value={form.event_date} onChange={(e) => set("event_date", e.target.value)} required />
        <Field id="event-time" label="ساعت شروع" type="time" value={form.start_time}
          onChange={(e) => set("start_time", e.target.value)} required /></div>
        <small className={styles.scheduleHint}>تاریخ را به شکل سال/ماه/روز بنویسید؛ تاریخ گذشته هم مجاز است.</small>
      </div>}
      {form.time_mode === "approximate" && <Field id="time-text" label="شرح زمان تقریبی"
        value={form.time_text} onChange={(e) => set("time_text", e.target.value)}
        hint="تاریخ یا ساعت حدودی، یا «در حال هماهنگی» را آزادانه بنویسید." required />}
      </div><div className={styles.scheduleBlock}>
      <div className="field"><label htmlFor="location-mode">نحوهٔ اعلام مکان</label>
        <select id="location-mode" value={form.location_mode}
          onChange={(e) => setLocationMode(e.target.value as Form["location_mode"])}>
          <option value="tba">اعلام بعدی</option><option value="approximate">تقریبی</option>
          <option value="exact">دقیق</option></select></div>
      {form.location_mode === "approximate" && <Field id="location-text"
        label="شرح محدودهٔ مکان" value={form.location_text}
        onChange={(e) => set("location_text", e.target.value)} required />}
      {form.location_mode === "exact" && <div className="field"><label htmlFor="location-id">مکان ذخیره‌شده</label>
        <select id="location-id" value={form.location_id}
          onChange={(e) => set("location_id", e.target.value)} required>
          <option value="">انتخاب مکان</option>
          {locations.map((place) => <option value={place.id} key={place.id}>{place.title}</option>)}
        </select><small><Link className="text-link" href="/panel/locations">مدیریت کافه‌ها</Link></small></div>}
      </div></div>
      </section>
      <section className={styles.formSection}>
        <div className={styles.sectionIntro}><span>۰۳</span><div><h3>میزبانی و ثبت‌نام</h3><p>ظرفیت، مبلغ ورودی و وضعیت ثبت‌نام را تنظیم کنید.</p></div></div>
      <div className="field-row"><Field id="hosts" label="میزبان یا میزبانان" value={form.hosts}
        onChange={(e) => set("hosts", e.target.value)} />
        <Field id="capacity" label="ظرفیت پیشنهادی (غیرالزام‌آور)" type="number" min={0}
          value={form.capacity} onChange={(e) => set("capacity", e.target.value)} /></div>
      <div className="field-row">{!eventId && <Field id="entry-fee" label="ورودی (تومان)" type="number" min={0}
        value={form.entry_fee} onChange={(e) => set("entry_fee", e.target.value)} required />}
        <div className="field"><label htmlFor="registration-status">ثبت‌نام</label>
          <select id="registration-status" value={form.registration_status}
            onChange={(e) => set("registration_status", e.target.value as Form["registration_status"])}>
            <option value="closed">بسته</option><option value="open">باز</option></select></div></div>
      <div className="field"><label htmlFor="public-note">یادداشت عمومی</label><textarea
        id="public-note" rows={3} value={form.public_note}
        onChange={(e) => set("public_note", e.target.value)} /></div>
      </section>
      <div className={styles.mediaGrid}>
        <section className={styles.supportSection}>
          <div className={styles.sectionIntro}><span>۰۴</span><div><h3>پوستر هشتی</h3>
            <p>تصویری برای معرفی هشتی انتخاب کنید.</p></div></div>
          {posterFields}
        </section>
        <section className={styles.supportSection}>
          <div className={styles.sectionIntro}><span>۰۵</span><div><h3>دبیران هشتی</h3>
            <p>افرادی که این هشتی را مدیریت می‌کنند.</p></div></div>
          {secretaryFields}
        </section>
      </div>
      <div className={styles.saveBar}><p>{eventId ?
        "تغییر پوستر، دبیران و مبلغ ورودی دکمهٔ ذخیرهٔ جداگانه دارند." :
        "پس از ساخت، می‌توانید ثبت‌نام‌ها و حضور هشتی‌نشین‌ها را مدیریت کنید."}</p>
        <Button className="primary" type="submit" disabled={busy || event?.is_cancelled}>
          {busy ? "در حال ذخیره…" : eventId ? "ذخیره اطلاعات" : "ساخت هشتی"}</Button></div>
    </form></Card>
    {eventId && event && <div className={styles.managementGrid}>
    <Card title="وضعیت هشتی"><p className="muted">
      فعال‌سازی مجدد، وضعیت باز/بسته ثبت‌نام و سوابق مالی پیشین را تغییر نمی‌دهد.</p>
      {event.is_cancelled ? <Button type="button" className="secondary" disabled={busy}
        onClick={() => changeCancellation(true)}>فعال‌سازی مجدد هشتی</Button> :
        <Button type="button" className="danger-button" disabled={busy}
          onClick={() => changeCancellation(false)}>لغو هشتی و ثبت‌نام‌های فعال</Button>}
    </Card>
    <Card title="هزینهٔ ورودی"><p className="muted">تغییر مبلغ روی هشتی‌نشین‌های حاضر و غایب با هزینه اعمال می‌شود؛ مازاد تسویه به کیف پول برمی‌گردد.</p>
      <div className="field-row"><Field id="new-entry-fee" label="ورودی جدید (تومان)" type="number" min={0}
        value={feeInput} onChange={(e) => setFeeInput(e.target.value)} />
        <Button type="button" className="secondary" disabled={busy || event?.is_cancelled}
          onClick={saveEntryFee}>ذخیره ورودی</Button></div></Card></div>}
    {eventId && <EventRegistrationManager eventId={eventId}
      available={event?.registration_status === "open" && !event?.is_cancelled}
      onAdded={() => setAttendanceRefresh((value) => value + 1)} />}
    {eventId && <EventAttendanceTable eventId={eventId} cancelled={event?.is_cancelled ?? false}
      registrationOpen={event?.registration_status === "open"}
      refresh={attendanceRefresh} />}
    {eventId && <Card title="حذف هشتی بدون سابقه"><p className="muted">هشتی دارای ثبت‌نام یا پرداخت حذف نمی‌شود.</p>
      <Button type="button" className="danger-button" disabled={busy} onClick={remove}>حذف هشتی</Button></Card>}
  </div>;
}
