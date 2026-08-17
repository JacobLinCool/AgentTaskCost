import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
	// Relative base keeps the build portable to any GitHub Pages sub-path.
	base: "./",
	plugins: [svelte()],
	build: {
		target: "es2022",
		cssCodeSplit: false,
		// One chunk, and it is mostly ECharts — nothing here renders without it.
		chunkSizeWarningLimit: 700,
	},
});
