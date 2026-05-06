import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig, loadEnv, type Plugin } from 'vite';

function googleTagBootstrapScript(measurementId: string): string {
  const id = JSON.stringify(measurementId);
  return `window.dataLayer=window.dataLayer||[];
function gtag(){dataLayer.push(arguments);}
gtag('js',new Date());
gtag('config',${id});`;
}

function googleTagPlugin(measurementId: string): Plugin {
  return {
    name: 'google-tag-html',
    transformIndexHtml(html) {
      if (!measurementId) {
        return html.replace('    <!--GOOGLE_TAG-->\n\n', '');
      }
      const encodedId = encodeURIComponent(measurementId);
      const tag = [
        `    <script async src="https://www.googletagmanager.com/gtag/js?id=${encodedId}"></script>`,
        `    <script>${googleTagBootstrapScript(measurementId)}</script>`,
      ].join('\n');
      return html.replace('    <!--GOOGLE_TAG-->', tag);
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const gaMeasurementId = env.VITE_GA_MEASUREMENT_ID || '';

  return {
    plugins: [svelte(), googleTagPlugin(gaMeasurementId)],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://localhost:8080',
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      sourcemap: false,
    },
  };
});
