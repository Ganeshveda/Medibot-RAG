export default {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        medibot: {
          50: "#eef7fb",
          100: "#d9eef7",
          200: "#b8dfee",
          300: "#88cbe1",
          400: "#4ea8cc",
          500: "#2f7cac",
          600: "#265f8c",
          700: "#214c73",
          800: "#1b405d",
          900: "#16324a",
        },
      },
      boxShadow: {
        glass: "0 12px 40px rgba(15, 23, 42, 0.12)",
      },
    },
  },
  plugins: [],
};
