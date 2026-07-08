/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // The Dot's real brand red (sampled from the logo, #E30613),
        // extended into a full Tailwind-style ramp. Every component
        // references "brand", not a raw color, so this is the only place
        // that needs to change if the brand color ever moves again.
        brand: {
          50: "#FDF0F1",
          100: "#FBDFE0",
          200: "#F7B9BD",
          300: "#F2878E",
          400: "#EB4C55",
          500: "#E61F2B",
          600: "#E30613",
          700: "#B30711",
          800: "#8C080F",
          900: "#5C080D",
        },
      },
    },
  },
  plugins: [],
};
