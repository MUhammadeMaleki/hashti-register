"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AppShell } from "@/components/app-shell";
import { Button, Card, Field, MoneyField } from "@/components/ui";
import { GuestFinance } from "@/components/guests/guest-finance";
import { api, errorMessage } from "@/lib/api";
import { formatJalali, formatToman, persianDigits } from "@/lib/format";
import { guestsApi, type GuestInput, type GuestProfile, type InterestTag } from "@/lib/guests";
import styles from "./guest-profile.module.css";

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

  return <AppShell kind="user"><div className={styles.page}>
    <header className={styles.hero}>
      <div className={styles.heroIdentity}>
        <span className={styles.avatar} aria-hidden="true">
          {profile ? `${profile.first_name[0] ?? ""}${profile.last_name[0] ?? ""}` : "ه"}
        </span>
        <div><span className={styles.eyebrow}>پروندهٔ هشتی‌نشین</span>
          <h2>{profile ? `${profile.first_name} ${profile.last_name}` : "پروفایل هشتی‌نشین"}</h2>
          {profile && <div className={styles.heroMeta}>
            <span>شناسهٔ {profile.id.toLocaleString("fa-IR")}</span>
            <span dir="ltr">{persianDigits(profile.phone)}</span>
            <span className={profile.has_account ? styles.accountActive : styles.accountInactive}>
              {profile.has_account ? "حساب فعال" : "بدون حساب ورود"}</span>
          </div>}
        </div>
      </div>
      <Link className={styles.backLink} href="/panel/guests">بازگشت به بانک هشتی‌نشین‌ها <span aria-hidden="true">←</span></Link>
    </header>
    {loading && <p role="status">در حال دریافت پروفایل…</p>}
    {error && <p className="alert error" role="alert">{error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    {profile && form && <>
      <div className={styles.summary} aria-label="خلاصهٔ وضعیت هشتی‌نشین">
        <div><span>موجودی کیف پول</span><strong>{profile.wallet_balance === null ? "ناموجود" :
          formatToman(profile.wallet_balance)}</strong></div>
        <div><span>بدهی هشتی‌ها</span><strong>{formatToman(profile.finance_overview.total_debt)}</strong></div>
        <div><span>ماندهٔ بدهی پس از اعتبار</span><strong>{formatToman(profile.finance_overview.net_debt)}</strong></div>
        <div><span>هشتی‌های ثبت‌نام‌شده</span><strong>{profile.registrations.length.toLocaleString("fa-IR")}</strong></div>
      </div>
      <nav className={styles.quickNav} aria-label="بخش‌های پرونده">
        <a href="#guest-information">اطلاعات</a><a href="#guest-finance">مالی</a>
        <a href="#guest-interests">علاقه‌مندی‌ها</a><a href="#guest-registrations">هشتی‌ها</a>
        <a href="#guest-activity">سوابق و یادداشت‌ها</a>
      </nav>
      <div className={styles.contentGrid}>
      <div id="guest-information" className={styles.sectionCard}><Card title="اطلاعات هشتی‌نشین"><form className="form-stack" onSubmit={save}>
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
        <MoneyField id="debt-ceiling" label="سقف بدهی اختصاصی (تومان)"
          value={form.debt_ceiling ?? ""} onValueChange={(value) => set("debt_ceiling",
            value === "" ? null : Number(value))} />
        <div className="field"><label htmlFor="internal-note">یادداشت عمومی داخلی</label>
          <textarea id="internal-note" rows={3} value={form.internal_note ?? ""}
            onChange={(event) => set("internal_note", event.target.value || null)} /></div>
        <Button type="submit" className="primary" disabled={busy}>ذخیرهٔ اطلاعات</Button>
      </form></Card></div>
      <div id="guest-interests" className={styles.sectionCard}><Card title="علاقه‌مندی‌ها"><div className="checkbox-grid">{allTags.map((tag) =>
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
        </form></Card></div>
      </div>
      <div id="guest-finance" className={`${styles.sectionCard} ${styles.financeSection}`}>
        <GuestFinance profile={profile} onChanged={refreshFinance} />
      </div>
      <div id="guest-registrations" className={styles.sectionCard}><Card title="هشتی‌ها و وضعیت حضور">
        <div className={styles.registrationList}>{profile.registrations.map((item) =>
          <details className={styles.registration} key={item.id}>
            <summary><span className={styles.registrationNumber}>هشتی {item.event.event_number.toLocaleString("fa-IR")}</span>
              <strong>{item.event.title}</strong>
              <span className={item.status === "active" ? styles.activeBadge : styles.inactiveBadge}>
                {item.status === "active" ? "ثبت‌نام فعال" : "لغوشده"}</span></summary>
            <div className={styles.registrationDetails}>
              <div><small>زمان</small><span>{item.event.event_date ?
                formatJalali(`${item.event.event_date}T12:00:00Z`) : "تاریخ نامشخص"}</span></div>
              <div><small>حضور</small><span>{attendanceName(item.attendance)}</span></div>
              <div><small>میزبان</small><span>{item.event.hosts || "—"}</span></div>
              <div><small>دبیران</small><span>{item.event.secretaries.join("، ") || "—"}</span></div>
              <div><small>هزینهٔ فعال</small><span>{formatToman(item.active_charge_total)}</span></div>
              <div><small>تخفیف</small><span>{formatToman(item.discount_total)}</span></div>
              <div><small>تسویه‌شده</small><span>{formatToman(item.settled_total)}</span></div>
              <div><small>مانده</small><span>{formatToman(item.outstanding_total)}</span></div>
            </div>
            {item.charges.length > 0 && <div className={styles.chargeList}>
              <strong>ریز هزینه‌ها</strong>{item.charges.map((charge) => <p key={charge.id}>
                {charge.type === "entry" ? "ورودی" : "سفارش"}: {charge.description} — {formatToman(charge.amount)}
                {charge.is_cancelled && " (لغوشده)"}</p>)}
            </div>}
            {item.discounts.length > 0 && <div className={styles.chargeList}>
              <strong>تاریخچهٔ تخفیف</strong>{item.discounts.map((discount) => <p key={discount.id}>
                {discount.amount > 0 ? "تخفیف" : "اصلاح تخفیف"}: {formatToman(Math.abs(discount.amount))}
                {" "}— {discount.reason} · {discount.actor_name} · {formatJalali(discount.created_at)}</p>)}
            </div>}
          </details>)}</div>
        {!profile.registrations.length && <p className="muted">هنوز ثبت‌نامی ندارد.</p>}
      </Card></div>
      <div id="guest-activity" className={styles.activityGrid}>
      <div className={styles.sectionCard}><Card title="یادداشت‌های پیگیری"><form className="form-stack" onSubmit={addNote}>
        <div className="field"><label htmlFor="note-type">نوع یادداشت</label>
          <select id="note-type" value={noteType} onChange={(event) =>
            setNoteType(event.target.value as "general" | "financial")}>
            <option value="general">عمومی</option><option value="financial">پیگیری مالی</option>
          </select></div>
        <div className="field"><label htmlFor="note-text">متن</label><textarea id="note-text"
          rows={3} required value={noteText} onChange={(event) => setNoteText(event.target.value)} /></div>
        <Button type="submit" className="secondary" disabled={busy}>افزودن یادداشت</Button>
      </form><div className={styles.timeline}>{profile.notes.map((note) =>
        <div className={styles.timelineItem} key={note.id}><strong>
          {note.type === "financial" ? "پیگیری مالی" : "عمومی"}</strong>
          <small>{note.created_by} · {formatJalali(note.created_at)}</small>
          <p>{note.text}</p></div>)}</div>
        {!profile.notes.length && <p className="muted">هنوز یادداشتی ثبت نشده است.</p>}</Card></div>
      <div className={styles.sectionCard}><Card title="گردش مالی">
        <h3>رسیدهای واریز <span>{profile.payments.length.toLocaleString("fa-IR")}</span></h3>
        <div className={styles.timeline}>{profile.payments.map((payment) =>
          <div className={styles.timelineItem} key={payment.id}>
            <strong>رسید {payment.id.toLocaleString("fa-IR")} · {formatToman(payment.amount)}</strong>
            <small>{payment.status} · {formatJalali(payment.created_at)}</small>
          </div>)}</div>
        <h3>تراکنش‌های کیف پول <span>{profile.wallet_transactions.length.toLocaleString("fa-IR")}</span></h3>
        <div className={styles.timeline}>{profile.wallet_transactions.map((transaction) =>
          <div className={styles.timelineItem} key={transaction.id}>
            <strong>{transaction.type} · {formatToman(transaction.amount)}</strong>
            <small>{formatJalali(transaction.created_at)}</small>
            {transaction.note && <p>{transaction.note}</p>}
            {transaction.reason && <p>دلیل: {transaction.reason}</p>}
            {transaction.actor_name && <p>ثبت‌کننده: {transaction.actor_name}</p>}
          </div>)}</div>
        {!profile.payments.length && !profile.wallet_transactions.length &&
          <p className="muted">هنوز تراکنشی ندارد.</p>}</Card></div>
      </div>
      {profile.has_account && <div className={styles.sectionCard}><Card title="رمز موقت حساب هشتی‌نشین">
        <p className="muted">صدور رمز تازه، نشست‌ها و رمز قبلی را باطل می‌کند. رمز فقط همین‌جا نشان داده می‌شود و تا ۲۴ ساعت اعتبار دارد؛ آن را از مسیر امن تحویل دهید.</p>
        <Button type="button" className="secondary" disabled={busy} onClick={issueTempPassword}>
          صدور رمز موقت</Button>
        {tempPassword && <div role="status" className="alert success">
          <p>رمز موقت: <code dir="ltr">{tempPassword}</code></p>
          <Button type="button" className="secondary" onClick={() => setTempPassword("")}>
            پنهان کردن رمز</Button></div>}
      </Card></div>}
      <div className={`${styles.sectionCard} ${styles.dangerZone}`}><Card title="حذف پروفایل بی‌سابقه"><p className="muted">
        هشتی‌نشینِ دارای حساب ورود، یادداشت یا هر سابقهٔ هشتی و مالی حذف نمی‌شود.</p>
        <Button type="button" className="danger-button" disabled={busy} onClick={remove}>
          حذف هشتی‌نشین</Button></Card></div>
    </>}
  </div></AppShell>;
}
