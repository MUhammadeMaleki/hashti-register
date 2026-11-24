"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, errorMessage } from "@/lib/api";
import { Button, Field } from "@/components/ui";
import { persianDigits } from "@/lib/format";

type User = { id: number; username: string; full_name: string;
  role: "super_admin" | "secretary"; is_active: boolean };

export function UsersList() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [resetUser, setResetUser] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    api<User[]>("/admin/users").then((value) => { if (active) setUsers(value); })
      .catch((caught) => { if (active) setError(errorMessage(caught)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const created = await api<User>("/admin/users", { method: "POST", body: JSON.stringify({
        username: username.trim(), full_name: fullName.trim(), password,
      }) });
      setUsers((previous) => [...previous, created]);
      setUsername(""); setFullName(""); setPassword("");
      setNotice("حساب دبیر ساخته شد. رمز را فقط از مسیر امن به دبیر تحویل دهید.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function toggle(user: User) {
    if (busy || user.role !== "secretary") return;
    const next = !user.is_active;
    if (!next && !window.confirm(`حساب ${user.full_name} غیرفعال شود؟ نشست‌های او باطل می‌شوند.`))
      return;
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await api<User>(`/admin/users/${user.id}`, {
        method: "PATCH", body: JSON.stringify({ is_active: next }),
      });
      setUsers((previous) => previous.map((row) => row.id === updated.id ? updated : row));
      setNotice(next ? "حساب دبیر فعال شد." : "حساب دبیر غیرفعال و نشست‌هایش باطل شد.");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function resetPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resetUser || busy) return;
    if (newPassword !== confirmPassword) {
      setError("تکرار رمز جدید با رمز واردشده یکسان نیست."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api<User>(`/admin/users/${resetUser.id}`, {
        method: "PATCH", body: JSON.stringify({ new_password: newPassword }),
      });
      setNotice(`رمز ${resetUser.full_name} تغییر کرد و نشست‌های قبلی او باطل شدند. رمز را فقط از مسیر امن تحویل دهید.`);
      setResetUser(null); setNewPassword(""); setConfirmPassword("");
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className="management-users">
    <section className="management-panel" aria-labelledby="management-users-title">
      <div className="management-panel-heading"><div><span>تیم هشتی</span>
        <h3 id="management-users-title">حساب‌های مدیریتی</h3>
        <p>مدیر هشتی و دبیرها؛ غیرفعال‌سازی، سوابق حساب را حذف نمی‌کند.</p></div>
        <strong>{persianDigits(String(users.length))} حساب</strong></div>
      {error && <p role="alert" className="alert error">{error}</p>}
      {notice && <p role="status" className="alert success">{notice}</p>}
      {loading ? <p role="status">در حال دریافت فهرست…</p> :
        <div className="management-users-list">{users.map((user) =>
          <div className="management-user" key={user.id}>
            <span className="management-user-avatar" aria-hidden="true">{user.full_name.slice(0, 1)}</span>
            <div className="management-user-identity"><strong>{user.full_name}</strong>
              <small dir="ltr">{user.username}</small></div>
            <span className="management-user-role">{user.role === "super_admin" ? "مدیر هشتی" : "دبیر"}</span>
            <span className={`management-user-status ${user.is_active ? "is-active" : "is-inactive"}`}>
              {user.is_active ? "فعال" : "غیرفعال"}</span>
            <div className="management-user-actions">{user.role === "secretary" && <>
              <Button type="button" className="secondary" disabled={busy}
                onClick={() => { setResetUser(user); setNewPassword(""); setConfirmPassword(""); setError(""); }}>
                تغییر رمز</Button>
              <Button type="button" className="secondary" disabled={busy} onClick={() => toggle(user)}>
                {user.is_active ? "غیرفعال‌سازی" : "فعال‌سازی"}</Button>
            </>}</div>
          </div>)}
          {!users.length && <p className="muted">هنوز حسابی ثبت نشده است.</p>}</div>}
      {resetUser && <form className="management-reset-form" onSubmit={resetPassword}>
        <div className="management-panel-heading"><div><span>بازنشانی رمز دبیر</span>
          <h3>رمز جدید برای {resetUser.full_name}</h3>
          <p>بعد از تغییر، نشست‌های فعلی این دبیر باطل می‌شوند.</p></div>
          <Button type="button" className="secondary" onClick={() => { setResetUser(null); setError(""); }}>
            انصراف</Button></div>
        <div className="management-form-grid">
          <Field id="reset-password" label="رمز جدید (حداقل ۱۲ نویسه)" type="password"
            required minLength={12} autoComplete="new-password" value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)} />
          <Field id="reset-password-confirm" label="تکرار رمز جدید" type="password"
            required minLength={12} autoComplete="new-password" value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)} />
        </div><Button type="submit" disabled={busy}>ثبت رمز جدید</Button>
      </form>}
    </section>
    <section className="management-panel management-create" aria-labelledby="create-secretary-title">
      <div className="management-panel-heading"><div><span>عضو جدید</span>
        <h3 id="create-secretary-title">ساخت حساب دبیر</h3>
        <p>برای دبیر یک رمز اولیهٔ امن تعیین کنید و خصوصی به او تحویل دهید.</p></div></div>
      <form className="management-create-form" onSubmit={create}>
      <div className="management-form-grid"><Field id="secretary-name" label="نام دبیر" required
        maxLength={200} value={fullName} onChange={(event) => setFullName(event.target.value)} />
        <Field id="secretary-username" label="نام کاربری" required maxLength={100}
          value={username} onChange={(event) => setUsername(event.target.value)} /></div>
      <Field id="secretary-password" label="رمز اولیه (حداقل ۱۲ نویسه)" type="password"
        required minLength={12} autoComplete="new-password" value={password}
        onChange={(event) => setPassword(event.target.value)} />
      <Button type="submit" className="primary" disabled={busy}>ساخت حساب</Button>
      </form>
    </section>
  </div>;
}
