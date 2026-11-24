"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AppShell } from "@/components/app-shell";
import { Button, Card, Field } from "@/components/ui";
import { GuestFinance } from "@/components/guests/guest-finance";
import { api, errorMessage } from "@/lib/api";
import { formatJalali, formatToman } from "@/lib/format";
import { guestsApi, type GuestInput, type GuestProfile, type InterestTag } from "@/lib/guests";

function formFrom(profile: GuestProfile): GuestInput {
  return { first_name: profile.first_name, last_name: profile.last_name, phone: profile.phone,
    age: profile.age, gender: profile.gender, education: profile.education,
    internal_note: profile.internal_note, debt_ceiling: profile.debt_ceiling };
}

function attendanceName(value: string) {
  return ({ pending: "نامشخص", present: "حاضر", absent_kept: "غایب، بدون هزینه",
    absent_forfeited: "غایب، با هزینه" } as Record<string, string>)[value] ?? value;
}

export function GuestProfileView({ guestId }: { guestId: number }) {
  const router = useRouter();
  const [profile, setProfile] = useState<GuestProfile | null>(null);
  const [form, setForm] = useState<GuestInput | null>(null);
  const [allTags, setAllTags] = useState<InterestTag[]>([]);
  const [selectedTags, setSelectedTags] = useState<number[]>([]);
  const [newTag, setNewTag] = useState("");
  const [noteType, setNoteType] = useState<"general" | "financial">("general");
  const [noteText, setNoteText] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tempPassword, setTempPassword] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([guestsApi.get(guestId), guestsApi.tags()]).then(([guest, tags]) => {
      if (!active) return;
      setProfile(guest); setForm(formFrom(guest)); setAllTags(tags);
      setSelectedTags(guest.tags.map((tag) => tag.id));
    }).catch((caught) => { if (active) setError(errorMessage(caught)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [guestId]);

  function set<K extends keyof GuestInput>(key: K, value: GuestInput[K]) {
    setForm((previous) => previous ? { ...previous, [key]: value } : previous);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!form || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await guestsApi.update(guestId, form);
      setProfile(updated); setForm(formFrom(updated)); setNotice("پروفایل ذخیره شد.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function saveTags() {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await guestsApi.setTags(guestId, selectedTags);
      setProfile(updated); setNotice("علاقه‌مندی‌ها ذخیره شدند.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function addTag(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!newTag.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const created = await guestsApi.createTag(newTag.trim());
      setAllTags((previous) => [...previous, created].sort((a, b) =>
        a.name.localeCompare(b.name, "fa")));
      setSelectedTags((previous) => [...previous, created.id]);
      setNewTag(""); setNotice("برچسب ساخته شد؛ برای انتساب، علاقه‌مندی‌ها را ذخیره کنید.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!noteText.trim() || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const note = await guestsApi.addNote(guestId, noteType, noteText.trim());
      setProfile((previous) => previous ? { ...previous, notes: [note, ...previous.notes] } : previous);
      setNoteText(""); setNotice("یادداشت به تاریخچه اضافه شد.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (busy || !window.confirm("پروفایل بی‌سابقه حذف شود؟ این کار قابل بازگشت نیست.")) return;
    setBusy(true); setError("");
    try { await guestsApi.remove(guestId); router.replace("/panel/guests"); }
    catch (caught) { setError(errorMessage(caught)); setBusy(false); }
  }

  async function refreshFinance() {
    const updated = await guestsApi.get(guestId);
    setProfile(updated);
  }

  async function issueTempPassword() {
    if (busy || !profile?.has_account || !window.confirm(
      "رمز موقت جدید صادر شود؟ نشست‌ها و رمز قبلی هشتی‌نشین باطل می‌شوند."
    )) return;
    setBusy(true); setError(""); setNotice(""); setTempPassword("");
    try {
      const result = await api<{ temporary_password: string; expires_in_hours: number }>(
        `/admin/guests/${guestId}/temp-password`, { method: "POST" }
      );
      setTempPassword(result.temporary_password);
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <AppShell kind="user"><div className="editor-stack">
    <div className="section-heading"><div><h2>پروفایل هشتی‌نشین</h2>
      {profile && <p className="muted">شناسهٔ {profile.id.toLocaleString("fa-IR")} · {profile.first_name} {profile.last_name}</p>}</div>
      <Link className="button secondary" href="/panel/guests">بانک هشتی‌نشین‌ها</Link></div>
    {loading && <p role="status">در حال دریافت پروفایل…</p>}
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    {profile && form && <>
      <div className="card-grid guest-summary"><Card title="کیف پول"><p>
        {profile.wallet_balance === null ? "ناموجود" : formatToman(profile.wallet_balance)}</p></Card>
        <Card title="حساب ورود"><p>{profile.has_account ? "فعال شده" : "هنوز ساخته نشده"}</p></Card>
        <Card title="هشتی‌ها"><p>{profile.registrations.length.toLocaleString("fa-IR")} ثبت‌نام در تاریخچه</p></Card></div>
      {profile.has_account && <Card title="رمز موقت حساب هشتی‌نشین">
        <p className="muted">صدور رمز تازه، نشست‌ها و رمز قبلی را باطل می‌کند. رمز فقط همین‌جا نشان داده می‌شود و تا ۲۴ ساعت اعتبار دارد؛ آن را از مسیر امن تحویل دهید.</p>
        <Button type="button" className="secondary" disabled={busy} onClick={issueTempPassword}>
          صدور رمز موقت</Button>
        {tempPassword && <div role="status" className="alert success">
          <p>رمز موقت: <code dir="ltr">{tempPassword}</code></p>
          <Button type="button" className="secondary" onClick={() => setTempPassword("")}>
            پنهان کردن رمز</Button></div>}
      </Card>}
      <GuestFinance profile={profile} onChanged={refreshFinance} />
      <Card title="اطلاعات هشتی‌نشین"><form className="form-stack" onSubmit={save}>
        <div className="field-row"><Field id="first-name" label="نام" required value={form.first_name}
          onChange={(event) => set("first_name", event.target.value)} />
          <Field id="last-name" label="نام خانوادگی" required value={form.last_name}
            onChange={(event) => set("last_name", event.target.value)} /></div>
        <div className="field-row"><Field id="phone" label="شماره موبایل" required
          inputMode="tel" value={form.phone} onChange={(event) => set("phone", event.target.value)} />
          <Field id="age" label="سن" type="number" min={0} max={130}
            value={form.age ?? ""} onChange={(event) => set("age",
              event.target.value === "" ? null : Number(event.target.value))} /></div>
        <div className="field-row"><Field id="gender" label="جنسیت" value={form.gender ?? ""}
          onChange={(event) => set("gender", event.target.value || null)} />
          <Field id="education" label="تحصیلات" value={form.education ?? ""}
            onChange={(event) => set("education", event.target.value || null)} /></div>
        <Field id="debt-ceiling" label="سقف بدهی اختصاصی (تومان)" type="number" min={0}
          value={form.debt_ceiling ?? ""} onChange={(event) => set("debt_ceiling",
            event.target.value === "" ? null : Number(event.target.value))} />
        <div className="field"><label htmlFor="internal-note">یادداشت عمومی داخلی</label>
          <textarea id="internal-note" rows={3} value={form.internal_note ?? ""}
            onChange={(event) => set("internal_note", event.target.value || null)} /></div>
        <Button type="submit" className="primary" disabled={busy}>ذخیرهٔ اطلاعات</Button>
      </form></Card>
      <Card title="علاقه‌مندی‌ها"><div className="checkbox-grid">{allTags.map((tag) =>
        <label className="checkbox-item" key={tag.id}><input type="checkbox"
          checked={selectedTags.includes(tag.id)} onChange={() => setSelectedTags((previous) =>
            previous.includes(tag.id) ? previous.filter((id) => id !== tag.id) : [...previous, tag.id])} />
          {tag.name}</label>)}</div>
        <Button type="button" className="secondary" disabled={busy} onClick={saveTags}>
          ذخیرهٔ علاقه‌مندی‌ها</Button>
        <form className="row-actions form-stack" onSubmit={addTag}>
          <Field id="new-tag" label="برچسب تازه" value={newTag}
            onChange={(event) => setNewTag(event.target.value)} />
          <Button type="submit" className="secondary" disabled={busy}>ساخت برچسب</Button>
        </form></Card>
      <Card title="یادداشت‌های پیگیری"><form className="form-stack" onSubmit={addNote}>
        <div className="field"><label htmlFor="note-type">نوع یادداشت</label>
          <select id="note-type" value={noteType} onChange={(event) =>
            setNoteType(event.target.value as "general" | "financial")}>
            <option value="general">عمومی</option><option value="financial">پیگیری مالی</option>
          </select></div>
        <div className="field"><label htmlFor="note-text">متن</label><textarea id="note-text"
          rows={3} required value={noteText} onChange={(event) => setNoteText(event.target.value)} /></div>
        <Button type="submit" className="secondary" disabled={busy}>افزودن یادداشت</Button>
      </form><div className="guest-history">{profile.notes.map((note) =>
        <div className="guest-history-item" key={note.id}><strong>
          {note.type === "financial" ? "پیگیری مالی" : "عمومی"}</strong>
          <small>{note.created_by} · {formatJalali(note.created_at)}</small>
          <p>{note.text}</p></div>)}</div>
        {!profile.notes.length && <p className="muted">هنوز یادداشتی ثبت نشده است.</p>}</Card>
      <Card title="تاریخچهٔ هشتی‌ها و حضور">
        {profile.registrations.map((item) => <div className="guest-history-item" key={item.id}>
          <h3>هشتی {item.event.event_number.toLocaleString("fa-IR")} · {item.event.title}</h3>
          <p>{item.event.event_date ? formatJalali(`${item.event.event_date}T12:00:00Z`) : "تاریخ نامشخص"}
            {item.event.hosts && ` · میزبان: ${item.event.hosts}`}</p>
          <p>ثبت‌نام: {item.status === "active" ? "فعال" : "لغوشده"} · حضور: {attendanceName(item.attendance)}</p>
          <p>دبیران: {item.event.secretaries.join("، ") || "—"}</p>
          {item.charges.map((charge) => <p key={charge.id}>
            {charge.type === "entry" ? "ورودی" : "سفارش"}: {charge.description} — {formatToman(charge.amount)}
            {charge.is_cancelled && " (لغوشده)"}</p>)}
          <p>هزینهٔ فعال: {formatToman(item.active_charge_total)} · تسویه‌شده: {formatToman(item.settled_total)}
            {` · مانده: ${formatToman(item.outstanding_total)}`}</p>
        </div>)}
        {!profile.registrations.length && <p className="muted">هنوز ثبت‌نامی ندارد.</p>}</Card>
      <Card title="گردش مالی"><p>پرداخت‌های ثبت‌شده: {profile.payments.length.toLocaleString("fa-IR")}</p>
        {profile.payments.map((payment) => <p key={payment.id}>
          رسید {payment.id.toLocaleString("fa-IR")} · {formatToman(payment.amount)} · {payment.status}
          {` · ${formatJalali(payment.created_at)}`}</p>)}
        <h3>تراکنش‌های کیف پول</h3>
        {profile.wallet_transactions.map((transaction) => <p key={transaction.id}>
          {transaction.type} · {formatToman(transaction.amount)}
          {transaction.note && ` · ${transaction.note}`}
          {transaction.reason && ` · دلیل: ${transaction.reason}`}
          {transaction.actor_name && ` · ثبت‌کننده: ${transaction.actor_name}`}
          {` · ${formatJalali(transaction.created_at)}`}</p>)}
        {!profile.payments.length && !profile.wallet_transactions.length &&
          <p className="muted">هنوز تراکنشی ندارد.</p>}</Card>
      <Card title="حذف پروفایل بی‌سابقه"><p className="muted">
        هشتی‌نشینِ دارای حساب ورود، یادداشت یا هر سابقهٔ هشتی و مالی حذف نمی‌شود.</p>
        <Button type="button" className="danger-button" disabled={busy} onClick={remove}>
          حذف هشتی‌نشین</Button></Card>
    </>}
  </div></AppShell>;
}
