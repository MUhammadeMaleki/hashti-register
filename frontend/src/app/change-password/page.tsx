"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { auth, errorMessage } from "@/lib/api";
import { useSession } from "@/hooks/use-session";
import { Button, Card, Field } from "@/components/ui";

export default function ChangePasswordPage() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (loading || done) return;
    if (!session || session.actor_type !== "guest") router.replace("/login");
    else if (!session.must_change_password) {
      const requested = new URLSearchParams(window.location.search).get("next");
      router.replace(requested && /^\/events\/\d+$/.test(requested) ? requested : "/account");
    }
  }, [loading, session, router, done]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try { await auth.changeGuestPassword(password); setDone(true); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }
  if (loading) return <main className="loading" role="status">در حال بررسی نشست…</main>;
  if (!session || session.actor_type !== "guest" || (!session.must_change_password && !done)) return null;
  return <main className="single-card"><Card title={done ? "رمز عبور تغییر کرد" : "انتخاب رمز شخصی"}>
    {done ? <><p>رمز موقت دیگر معتبر نیست. با رمز جدید وارد شوید.</p>
      <Button className="primary full" onClick={() => router.replace(`/login${window.location.search}`)}>رفتن به صفحهٔ ورود</Button></> :
      <><p className="muted">برای ادامه، رمز موقت را با رمزی دست‌کم ۱۲ نویسه‌ای جایگزین کنید.</p>
        <form onSubmit={submit} className="form-stack">
          <Field id="new-password" label="رمز عبور جدید" type="password" minLength={12}
            autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          {error && <p className="alert error" role="alert">{error}</p>}
          <Button type="submit" className="primary full" disabled={busy}>
            {busy ? "در حال ثبت…" : "ثبت رمز جدید"}</Button>
        </form></>}
  </Card></main>;
}
