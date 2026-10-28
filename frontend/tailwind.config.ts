import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        // Channel form so opacity modifiers (`bg-accent/15`) work.
        accent: "rgb(var(--accent-rgb) / <alpha-value>)",
        "accent-soft": "var(--accent-soft)",
        "accent-contrast": "var(--accent-contrast)",
        text: "var(--text)",
        "text-dim": "var(--text-dim)",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;