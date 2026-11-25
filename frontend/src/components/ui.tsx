import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { latinDigits, persianDigits } from "@/lib/format";

export function Button({ children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`button ${className}`} {...props}>{children}</button>;
}

export function Field({ label, hint, id, ...props }: InputHTMLAttributes<HTMLInputElement> & {
  label: string; hint?: string;
}) {
  return <div className="field"><label htmlFor={id}>{label}</label>
    <input id={id} {...props} />{hint && <small>{hint}</small>}</div>;
}

export function MoneyField({ value, onValueChange, ...props }: Omit<
  InputHTMLAttributes<HTMLInputElement>, "type" | "inputMode" | "value" | "onChange"
> & { label: string; value: string | number; onValueChange: (value: string) => void }) {
  return <Field {...props} type="text" inputMode="numeric" pattern="[۰-۹0-9]*"
    value={persianDigits(String(value))}
    onChange={(event) => onValueChange(latinDigits(event.target.value).replace(/[^0-9]/g, ""))} />;
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return <section className="card">{title && <h2>{title}</h2>}{children}</section>;
}

export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>;
}
