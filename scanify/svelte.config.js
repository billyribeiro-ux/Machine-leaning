import adapter from '@sveltejs/adapter-auto';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter(),
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
