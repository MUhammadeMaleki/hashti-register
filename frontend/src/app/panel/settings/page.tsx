"use client";

import { AppShell } from "@/components/app-shell";
import { AdminPasswordEditor } from "@/components/admin-password-editor";
import { SettingsEditor } from "@/components/settings-editor";
import { UsersList } from "@/components/users-list";
import { useSession } from "@/hooks/use-session";

function ManagementContent() {
  const { session, loading } = useSession();
  if (loading) return <p role="status">در حال بررسی دسترسی…</p>;
  return <div className="management-page">
    <div className="management-intro"><div><span>مدیریت هشتی</span>
      <h2>حساب‌ها و تنظیمات</h2>
      <p>دسترسی‌های تیم، تنظیمات مالی و امنیت حساب خود را از اینجا مدیریت کنید.</p></div>
      <span className="management-intro-mark" aria-hidden="true">✳</span></div>
    {session?.role === "super_admin" && <><UsersList /><SettingsEditor /></>}
    <AdminPasswordEditor />
  </div>;
}

export default function SettingsPage() {
  return <AppShell kind="user"><ManagementContent /></AppShell>;
}
