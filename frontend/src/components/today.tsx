"use client";

import { useEffect, useState } from "react";
import { formatJalali } from "@/lib/format";

export function Today() {
  const [date, setDate] = useState("");
  useEffect(() => { setDate(formatJalali(new Date())); }, []);
  return <span className="today">{date}</span>;
}
