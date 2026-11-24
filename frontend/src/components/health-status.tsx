"use client";

import { useEffect, useState } from "react";

type Health = "checking" | "ready" | "unavailable";

export function HealthStatus() {
  const [health, setHealth] = useState<Health>("checking");

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 6000);
    fetch("/api/health/ready", { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        const data: unknown = await response.json();
        const valid = response.ok && typeof data === "object" && data !== null &&
          "status" in data && data.status === "ok" &&
          "database" in data && data.database === "postgresql";
        setHealth(valid ? "ready" : "unavailable");
      })
      .catch(() => setHealth("unavailable"))
      .finally(() => window.clearTimeout(timeout));
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, []);

  const labels: Record<Health, string> = {
    checking: "در حال بررسی اتصال…",
    ready: "API و پایگاه داده در دسترس‌اند",
    unavailable: "اتصال برقرار نیست؛ اجرای Backend و تنظیمات پایگاه داده را بررسی کنید.",
  };

  return <p role="status" className={`health ${health}`}>{labels[health]}</p>;
}
