import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-conic": "conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))",
      },
      colors: {
        background: "#090d16",
        foreground: "#f8fafc",
        card: "rgba(17, 24, 39, 0.7)",
        border: "rgba(255, 255, 255, 0.08)",
        primary: {
          DEFAULT: "#0ea5e9",
          hover: "#0284c7",
          glow: "rgba(14, 165, 233, 0.15)",
        },
        accent: {
          green: "#10b981",
          purple: "#8b5cf6",
          red: "#ef4444",
          orange: "#f97316",
        }
      },
      boxShadow: {
        glass: "0 8px 32px 0 rgba(0, 0, 0, 0.37)",
        "glow-blue": "0 0 15px rgba(14, 165, 233, 0.25)",
        "glow-green": "0 0 15px rgba(16, 185, 129, 0.25)",
      },
    },
  },
  plugins: [],
};

export default config;
