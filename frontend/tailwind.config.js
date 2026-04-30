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
    },
  },
  plugins: [],
};
