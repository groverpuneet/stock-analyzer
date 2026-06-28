/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b1220",
        panel: "#111a2e",
        edge: "#1f2c44",
        buy: "#16a34a",
        sell: "#dc2626",
        watch: "#d97706",
      },
    },
  },
  plugins: [],
};
