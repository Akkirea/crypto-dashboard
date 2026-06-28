import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#f7f4ff",
        panel: "#15151c",
        panel2: "#1d1b26",
        line: "rgba(255,255,255,0.1)",
        muted: "#9d98ad",
        buy: "#5ee0a0",
        sell: "#ff6b7a",
        accent: "#c4b5fd",
        cyan: "#5be7ff",
        gold: "#e7d56f"
      }
    }
  },
  plugins: []
};

export default config;
