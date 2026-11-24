import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function Button({ children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`button ${className}`} {...props}>{children}</button>;
}

export function Field({ label, hint, id, ...props }: InputHTMLAttributes<HTMLInputElement> & {
  label: string; hint?: string;
}) {
  return <div className="field"><label htmlFor={id}>{label}</label>
    <input id={id} {...props} />{hint && <small>{hint}</small>}</div>;
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return <section className="card">{title && <h2>{title}</h2>}{children}</section>;
}

export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>;
}
