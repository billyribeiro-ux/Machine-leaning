import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

const isTauri = !!process.env.TAURI_PLATFORM;

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],

	// Tauri expects a fixed port during dev
	server: {
		port: 5173,
		strictPort: true,
	},

	// Expose TAURI_* env vars to the client bundle
	envPrefix: ['VITE_', 'TAURI_'],

	worker: {
		format: 'es'
	},

	optimizeDeps: {
		exclude: ['lightweight-charts']
	},

	build: {
		// Tauri webview targets
		...(isTauri && {
			target:
				process.env.TAURI_PLATFORM === 'windows'
					? 'chrome105'
					: 'safari13',
			minify: !process.env.TAURI_DEBUG ? 'esbuild' : false,
			sourcemap: !!process.env.TAURI_DEBUG,
		}),
	},
});
