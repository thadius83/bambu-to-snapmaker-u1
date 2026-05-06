import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';

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
