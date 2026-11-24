"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button, Field } from "@/components/ui";
import { EventGuestPayment } from "@/components/event-guest-payment";
import { errorMessage } from "@/lib/api";
import { registrationsApi, type RegistrationMember, type RegistrationResult } from "@/lib/registrations";

const empty = (): RegistrationMember => ({ first_name: "", last_name: "", phone: "" });
const resultText: Record<string, string> = {
  invalid_phone: "شمارهٔ موبایل معتبر نیست.",
  invalid_registration: "نام و نام خانوادگی را بررسی کنید.",
  already_registered: "شما قبلاً در این رویداد ثبت‌نام کرده‌اید.",
  registration_closed: "ثبت‌نام این رویداد بسته شده است.",
  event_not_found: "این رویداد دیگر برای ثبت‌نام در دسترس نیست.",
};

export function PublicRegistrationForm({ eventId, registrationOpen, cardNumber, accountHolder }: {
  eventId: number; registrationOpen: boolean; cardNumber: string | null; accountHolder: string | null;
}) {
  const paymentDialog = useRef<HTMLDialogElement>(null);
  const [members, setMembers] = useState<RegistrationMember[]>([empty()]);
  const [results, setResults] = useState<(RegistrationResult | undefined)[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function update(index: number, field: keyof RegistrationMember, value: string) {
    setMembers((previous) => previous.map((member, position) => position === index
      ? { ...member, [field]: value } : member));
    setResults((previous) => previous.map((result, position) => position === index
      ? undefined : result));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const pending = members.map((_, index) => index).filter((index) =>
      results[index]?.status !== "created");
    if (!pending.length) return;
    setBusy(true); setError("");
    try {
      const response = await registrationsApi.publicGroup(eventId, pending.map((index) => members[index]));
      setResults((previous) => {
        const next = [...previous];
        response.results.forEach((result) => { next[pending[result.index]] = result; });
        return next;
      });
      if (response.results.some((result) => result.status === "created"))
        window.dispatchEvent(new Event("hashti:registration"));
    }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <section className="public-registration" id="registration">
    <h2>ثبت‌نام در رویداد</h2>
    {registrationOpen ? <>
      <p className="muted">برای هر نفر فقط نام، نام خانوادگی و موبایل لازم است؛ حساب ورود ساخته نمی‌شود.</p>
      {error && <p className="alert error" role="alert">{error}</p>}
      <form className="form-stack" onSubmit={submit}>
      {members.map((member, index) => <div className="registration-member" key={index}>
        <div className="section-heading"><h3>نفر {new Intl.NumberFormat("fa-IR").format(index + 1)}</h3>
          {index > 0 && <Button type="button" className="secondary" disabled={busy ||
            results[index]?.status === "created"}
            onClick={() => { setMembers((previous) => previous.filter((_, at) => at !== index));
              setResults((previous) => previous.filter((_, at) => at !== index)); }}>حذف نفر</Button>}</div>
        <div className="field-row"><Field id={`first-${index}`} label="نام" required
          disabled={results[index]?.status === "created"}
          value={member.first_name} onChange={(event) => update(index, "first_name", event.target.value)} />
          <Field id={`last-${index}`} label="نام خانوادگی" required
            disabled={results[index]?.status === "created"}
            value={member.last_name} onChange={(event) => update(index, "last_name", event.target.value)} /></div>
        <Field id={`phone-${index}`} label="شمارهٔ موبایل" required inputMode="tel"
          disabled={results[index]?.status === "created"}
          value={member.phone} onChange={(event) => update(index, "phone", event.target.value)} />
        {results[index] && <p role="status" className={`alert ${results[index].status === "created"
          ? "success" : "error"}`}>{results[index].status === "created"
          ? "ثبت‌نام انجام شد." : resultText[results[index].code ?? ""] ?? "ثبت‌نام این نفر انجام نشد."}</p>}
      </div>)}
      <div className="row-actions"><Button type="button" className="secondary" disabled={busy || members.length >= 20}
        onClick={() => setMembers((previous) => [...previous, empty()])}>
        افزودن نفر دیگر</Button>
        <Button type="submit" className="primary" disabled={busy || members.every((_, index) =>
          results[index]?.status === "created")}>{busy ? "در حال ثبت…" : "ثبت‌نام"}</Button></div>
      </form>
    </> : <p className="alert error">ثبت‌نام این رویداد بسته است؛ مهمان‌های ثبت‌نام‌شده همچنان می‌توانند پرداخت و تسویه را پیگیری کنند.</p>}
    <div className="registration-payment-action">
      <p>قبلاً ثبت‌نام کرده‌اید؟ رسید واریز و وضعیت تسویه را از همین‌جا پیگیری کنید.</p>
      <Button type="button" className="secondary" onClick={() => paymentDialog.current?.showModal()}>
        پرداخت و پیگیری <span aria-hidden="true">←</span>
      </Button>
    </div>
    <dialog ref={paymentDialog} className="event-payment-dialog" aria-label="پرداخت و پیگیری هشتی">
      <EventGuestPayment eventId={eventId} cardNumber={cardNumber} accountHolder={accountHolder}
        onClose={() => paymentDialog.current?.close()} />
    </dialog>
  </section>;
}
