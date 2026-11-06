/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        cyber: {
          black: "#000000",
          charcoal: "#111827",
          darker: "#070b14",
          card: "#0d1322",
          border: "#1e293b",
          neonGreen: "#10b981",
          neonGreenGlow: "#059669",
          neonCyan: "#06b6d4",
          neonCyanGlow: "#00f0ff",
          neonRed: "#ef4444",
          neonRedGlow: "#dc2626",
          neonOrange: "#f59e0b",
          neonPurple: "#8b5cf6",
          gold: "#facc15"
        }
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      },
      boxShadow: {
        'neon-red': '0 0 25px rgba(239, 68, 68, 0.75)',
        'neon-cyan': '0 0 20px rgba(6, 182, 212, 0.5)',
        'neon-green': '0 0 20px rgba(16, 185, 129, 0.5)',
        'card-glow': '0 4px 24px rgba(0, 0, 0, 0.6)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'scanline': 'scan 8s linear infinite',
      },
      keyframes: {
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(1000%)' },
        }
      }
    },
  },
  plugins: [],
}

