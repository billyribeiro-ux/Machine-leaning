/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        scanify: {
          primary: '#6366f1',    // Indigo
          secondary: '#8b5cf6',  // Purple
          accent: '#22d3ee',     // Cyan
          success: '#22c55e',    // Green
          warning: '#f59e0b',    // Amber
          danger: '#ef4444',     // Red
          dark: {
            900: '#0f0f12',
            800: '#16161d',
            700: '#1e1e28',
            600: '#262633',
          }
        }
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgb(99 102 241 / 0.5)' },
          '100%': { boxShadow: '0 0 20px rgb(99 102 241 / 0.8)' },
        }
      }
    },
  },
  plugins: [],
};
