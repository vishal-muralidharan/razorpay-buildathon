/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#081428",
          900: "#0B1F3A",
          800: "#122A4C",
          700: "#1B3A63",
        },
        paper: {
          50: "#FBF9F4",
          100: "#F6F3EC",
          200: "#EDE7D8",
        },
        moss: {
          500: "#2E7D5B",
          600: "#256349",
        },
        amber: {
          400: "#D9A441",
          500: "#C98A2C",
        },
        clay: {
          500: "#B23B3B",
          600: "#96302F",
        },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'IBM Plex Sans'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
    },
  },
  plugins: [],
}
