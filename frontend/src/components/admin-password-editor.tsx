"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { auth, errorMessage } from "@/lib/api";
import { Button, Field } from "@/components/ui";

export function AdminPasswordEditor() {
  const router = useRouter();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (next !== confirm) { setError("تکرار رمز جدید با رمز واردشده یکسان نیست."); return; }
    setBusy(true); setError("");
    try {
      await auth.changeAdminPassword(current, next);
      router.replace("/login");
    } catch (caught) { setError(errorMessage(caught)); setBusy(false); }
  }

  return <section className="management-panel management-password" aria-labelledby="own-password-title">
    <div className="management-panel-heading"><div><span>امنیت حساب</span>
      <h3 id="own-password-title">تغییر رمز خودم</h3>
      <p>با ثبت رمز جدید، همهٔ نشست‌های قبلی خارج می‌شوند و باید دوباره وارد شوید.</p></div></div>
    <form className="management-password-form" onSubmit={save}>
      <Field id="admin-current-password" label="رمز فعلی" type="password" required
        autoComplete="current-password" value={current}
        onChange={(event) => setCurrent(event.target.value)} />
      <Field id="admin-next-password" label="رمز جدید (حداقل ۱۲ نویسه)" type="password"
        required minLength={12} autoComplete="new-password" value={next}
        onChange={(event) => setNext(event.target.value)} />
      <Field id="admin-confirm-password" label="تکرار رمز جدید" type="password"
        required minLength={12} autoComplete="new-password" value={confirm}
        onChange={(event) => setConfirm(event.target.value)} />
      {error && <p className="alert error" role="alert">{error}</p>}
      <Button type="submit" disabled={busy}>{busy ? "در حال تغییر…" : "تغییر رمز و خروج"}</Button>
    </form>
  </section>;
}
