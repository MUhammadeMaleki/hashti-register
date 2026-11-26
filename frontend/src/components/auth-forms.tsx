"use client";

import { useState, type FormEvent } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { PublicHeader } from "@/components/public-header";
import { auth, errorMessage } from "@/lib/api";
import { normalizeMobile } from "@/lib/format";
import { Button, Card, Field } from "@/components/ui";

type Mode = "guest" | "admin" | "register";

export function AuthForms() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("guest");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");

  function choose(next: Mode) {
    setMode(next); setError(""); setIdentifier(""); setPassword("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      if (mode === "admin") {
        await auth.adminLogin(identifier.trim(), password);
        router.replace("/panel");
      } else {
        const phone = normalizeMobile(identifier);
        if (!/^09\d{9}$/.test(phone)) {
          setError("شماره موبایل باید با ۰۹ آغاز شود و ۱۱ رقم داشته باشد.");
          return;
        }
        if (mode === "register") {
          if (password.length < 12) {
            setError("رمز عبور باید دست‌کم ۱۲ نویسه باشد.");
            return;
          }
          await auth.guestRegister(firstName.trim(), lastName.trim(), phone, password);
        }
        const result = await auth.guestLogin(phone, password);
        const requested = new URLSearchParams(window.location.search).get("next");
        const destination = requested && /^\/events\/\d+$/.test(requested) ? requested : "/account";
        router.replace(result.must_change_password ?
          `/change-password?next=${encodeURIComponent(destination)}` : destination);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-page">
    <PublicHeader backHref="/" backLabel="بازگشت به صفحهٔ اصلی" hideAccountActions />
    <div className="auth-layout">
    <section className="auth-aside">
      <span className="auth-aside-kicker"><span aria-hidden="true">●</span> خوش آمدی به هشتی</span>
      <h1>بیا راجع بهش<br /><span>حرف بزنیم.</span></h1>
      <p>به جمع هشتی‌نشین‌ها بپیوند؛ هشتی‌های پیش رو، حضور و کیف پولت را یک‌جا دنبال کن.</p>
      <div className="auth-aside-art" aria-hidden="true"><span className="auth-art-ring" />
        <Image src="/hashti-mark.svg" alt="" width={270} height={190} unoptimized /></div>
      <div className="auth-aside-footer"><span>هشتی‌نشینی</span><span>گفت‌وگو</span><span>آشنایی</span></div>
    </section>
    <div className="auth-form-panel"><Card>
      <span className="auth-form-kicker">حساب کاربری هشتی</span>
      <h2>{mode === "register" ? "ساخت حساب هشتی‌نشینی" :
        mode === "admin" ? "ورود دبیر" : "ورود هشتی‌نشین"}</h2>
      <p className="muted auth-form-description">{mode === "admin" ?
        "با نام کاربری و رمز عبور دبیر وارد پنل مدیریت شوید." :
        mode === "register" ? "چند قدم کوتاه تا اولین هشتی‌نشینی." :
        "برای دیدن هشتی‌ها و پیگیری حسابت وارد شو."}</p>
      <div className="tabs" role="tablist" aria-label="نوع ورود">
        <button type="button" role="tab" aria-selected={mode === "guest"}
          onClick={() => choose("guest")}>ورود هشتی‌نشین</button>
        <button type="button" role="tab" aria-selected={mode === "admin"}
          onClick={() => choose("admin")}>ورود دبیر</button>
      </div>
      <form onSubmit={submit} className="form-stack">
        {mode === "register" && <div className="field-row">
          <Field id="first-name" label="نام" autoComplete="given-name" value={firstName}
            onChange={(event) => setFirstName(event.target.value)} required maxLength={100} />
          <Field id="last-name" label="نام خانوادگی" autoComplete="family-name" value={lastName}
            onChange={(event) => setLastName(event.target.value)} required maxLength={100} />
        </div>}
        <Field id="identifier" label={mode === "admin" ? "نام کاربری" : "شماره موبایل"}
          type={mode === "admin" ? "text" : "tel"} dir="ltr"
          inputMode={mode === "admin" ? "text" : "tel"}
          autoComplete={mode === "admin" ? "username" : "tel"}
          value={identifier} onChange={(event) => setIdentifier(event.target.value)} required />
        <Field id="password" label="رمز عبور" type="password"
          autoComplete={mode === "register" ? "new-password" : "current-password"}
          value={password} onChange={(event) => setPassword(event.target.value)} required
          minLength={mode === "register" ? 12 : undefined}
          hint={mode === "register" ? "حداقل ۱۲ نویسه" : undefined} />
        {error && <p className="alert error" role="alert">{error}</p>}
        <Button type="submit" disabled={busy} className="primary full">
          {busy ? "در حال بررسی…" : mode === "register" ? "ساخت حساب و ورود" : "ورود"}
        </Button>
      </form>
      {mode !== "admin" && <p className="auth-switch">
        {mode === "register" ? "قبلاً حساب ساخته‌اید؟" : "هنوز حساب ندارید؟"}{" "}
        <button type="button" onClick={() => choose(mode === "register" ? "guest" : "register")}>
          {mode === "register" ? "ورود هشتی‌نشین" : "ساخت حساب هشتی‌نشینی"}
        </button>
      </p>}
      <p className="help-text">رمز را فراموش کرده‌اید؟ برای دریافت رمز موقت با دبیر هشتی تماس بگیرید.</p>
    </Card></div>
    </div>
  </main>;
}
