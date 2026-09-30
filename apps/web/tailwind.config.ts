import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: "var(--bg-paper)",
          dark: "var(--bg-paper-dark)",
        },
        surface: {
          DEFAULT: "var(--bg-surface)",
          dark: "var(--bg-surface-dark)",
        },
        border: {
          DEFAULT: "var(--border-color)",
          dark: "var(--border-dark)",
        },
        ink: {
          DEFAULT: "var(--ink-text)",
          muted: "var(--ink-muted)",
          dark: "var(--ink-dark)",
          "muted-dark": "var(--ink-muted-dark)",
        },
        accent: {
          DEFAULT: "var(--accent-primary)",
          hover: "var(--accent-hover)",
          light: "var(--accent-light)",
        },
        status: {
          pass: "var(--status-pass)",
          partial: "var(--status-partial)",
          fail: "var(--status-fail)",
          unverified: "var(--status-unverified)",
        },
      },
      fontFamily: {
        serif: ["var(--font-display)", "Fraunces", "Instrument Serif", "Georgia", "serif"],
        sans: ["var(--font-ui)", "Geist", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "Geist Mono", "JetBrains Mono", "monospace"],
      },
      borderRadius: {
        sm: "6px",
        DEFAULT: "10px",
        md: "10px",
        lg: "14px",
      },
    },
  },
  plugins: [],
};

export default config;
