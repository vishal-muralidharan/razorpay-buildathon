/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        rzp: {
          navy: "#012652",
          blue: "#0D94FB",
          lightblue: "#E6F3FF",
          bg: "#F8F9FA",
          gray: "#F4F8FB",
          surface: "#FFFFFF",
          border: "#E2E8F0"
        },
        status: {
          success: "#10B981",
          success_bg: "#D1FAE5",
          error: "#EF4444",
          error_bg: "#FEE2E2",
          warning: "#F59E0B",
          warning_bg: "#FEF3C7"
        }
      },
      fontFamily: {
        display: ["'Inter'", "sans-serif"],
        body: ["'Inter'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
    },
  },
  plugins: [],
}
