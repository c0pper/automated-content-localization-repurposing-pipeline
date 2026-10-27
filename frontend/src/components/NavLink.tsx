import { useState } from "react";

export interface NavLinkProps {
  to: string;
  size?: string;
  underline?: "hover" | "always" | "never";
  children: React.ReactNode;
}

export function NavLink({ to, size = "text-sm", underline = "hover", children }: NavLinkProps) {
  const [hover, setHover] = useState(false);
  const underlineClass =
    underline === "hover" ? (hover ? "underline" : "no-underline") : underline === "always" ? "underline" : "no-underline";
  return (
    <button
      className={`text-accent ${size} ${underlineClass} hover:opacity-80 transition`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => {
        window.location.hash = to;
      }}
    >
      {children}
    </button>
  );
}