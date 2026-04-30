/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#EFF6FF",
          100: "#DBEAFE",
          200: "#BFDBFE",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
          800: "#1E40AF",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.04)",
        cardLg: "0 4px 16px rgba(15, 23, 42, 0.06)",
      },
      keyframes: {
        "alert-in": {
          "0%":   { opacity: "0", transform: "translateY(-4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-red-border": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(220, 38, 38, 0.55)" },
          "50%":      { boxShadow: "0 0 0 6px rgba(220, 38, 38, 0)" },
        },
      },
      animation: {
        "alert-in": "alert-in 0.25s ease-out",
        "pulse-red-border": "pulse-red-border 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
