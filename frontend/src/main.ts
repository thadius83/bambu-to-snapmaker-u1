import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';

const gaId = import.meta.env.VITE_GA_MEASUREMENT_ID;
if (gaId) {
  const tag = document.createElement('script');
  tag.async = true;
  tag.src = `https://www.googletagmanager.com/gtag/js?id=${gaId}`;
  document.head.appendChild(tag);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = window as any;
  w.dataLayer = w.dataLayer || [];
  w.gtag = function gtag() { w.dataLayer.push(arguments); };
  w.gtag('js', new Date());
  w.gtag('config', gaId);
}

const cfBeaconToken = import.meta.env.VITE_CF_BEACON_TOKEN;
if (cfBeaconToken) {
  const beacon = document.createElement('script');
  beacon.defer = true;
  beacon.src = 'https://static.cloudflareinsights.com/beacon.min.js';
  beacon.setAttribute('data-cf-beacon', JSON.stringify({ token: cfBeaconToken }));
  document.head.appendChild(beacon);
}

const app = mount(App, {
  target: document.getElementById('app')!,
});

export default app;
