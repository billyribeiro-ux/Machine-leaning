import adapterAuto from '@sveltejs/adapter-auto';
import adapterStatic from '@sveltejs/adapter-static';

const isTauri = !!process.env.TAURI_PLATFORM;

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: isTauri
			? adapterStatic({ fallback: 'index.html' })
			: adapterAuto(),
		alias: {
			$components: 'src/lib/components',
			$stores: 'src/lib/stores',
			$utils: 'src/lib/utils',
			$types: 'src/lib/types',
			$gpu: 'src/lib/gpu',
			$workers: 'src/lib/workers',
			$wasm: 'src/lib/wasm'
		}
	}
};

export default config;
