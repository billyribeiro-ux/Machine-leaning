/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        scanify: {
          primary: '#6366f1',
          secondary: '#8b5cf6',
          accent: '#22d3ee',
          success: '#22c55e',
          warning: '#f59e0b',
          danger: '#ef4444',
          dark: {
            900: '#0f0f12',
            800: '#16161d',
            700: '#1e1e28',
            600: '#262633',
          }
        }
      },
    },
  },
  plugins: [],
};
