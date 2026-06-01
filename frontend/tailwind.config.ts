import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Inter", "sans-serif"],
      },
      colors: {
        ink: "#05060a",
      },
      backdropBlur: { xs: "2px" },
    },
  },
  plugins: [],
};

export default config;
