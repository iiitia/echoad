/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#ecfdf5',
          500: '#22c55e',
          900: '#14532d',
        }
      }
    },
  },
  plugins: [],
  darkMode: 'class',
}

