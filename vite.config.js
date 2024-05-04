import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    target: 'esnext',
    lib: {
      entry: path.resolve(__dirname, 'frontend/main.js'),
      name: 'OWL',
      fileName: (format) => `owl.${format}.js`
    },
  },
    /* rollupOptions: {
      external: ['vue', 'leaflet'],
	  output: {
        // Provide global variables to use in the UMD build
        // for externalized deps
        globals: {
          vue: 'Vue',
          leaflet: 'L',
        }
      }
	}, */
  // },
})
