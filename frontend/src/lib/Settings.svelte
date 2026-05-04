<script lang="ts">
  import type { ProfileDescriptor } from './api';

  interface Props {
    profiles: ProfileDescriptor[];
    selectedProfile: string;
    applyRules: boolean;
    insertSwapPauses: boolean;
    advancedOverrides: string;
    autoMatched?: boolean;
    disabled?: boolean;
  }

  let {
    profiles,
    selectedProfile = $bindable(),
    applyRules = $bindable(),
    insertSwapPauses = $bindable(),
    advancedOverrides = $bindable(),
    autoMatched = false,
    disabled = false,
  }: Props = $props();

  let showAdvanced = $state(false);
</script>

<div class="settings card card-padded">
  <div class="row">
    <div class="profile-label-row">
      <label for="profile">Reference profile</label>
      {#if autoMatched}
        <span class="auto-badge">auto-matched</span>
      {/if}
    </div>
    <select
      id="profile"
      bind:value={selectedProfile}
      {disabled}
    >
      {#if profiles.length === 0}
        <option value="">No profiles found</option>
      {/if}
      {#each profiles as p (p.id)}
        <option value={p.id}>
          {p.display_name}
          {p.source === 'user' ? '(user)' : ''}
        </option>
      {/each}
    </select>
  </div>

  <div class="toggles">
    <label class="toggle">
      <input type="checkbox" bind:checked={applyRules} {disabled} />
      <span class="toggle-track"><span class="toggle-thumb"></span></span>
      <span class="toggle-label">
        <span class="toggle-title">Apply filament rules</span>
        <span class="subtle">Match YAML rules against source filament + tune speeds/accel</span>
      </span>
    </label>

    <label class="toggle">
      <input type="checkbox" bind:checked={insertSwapPauses} {disabled} />
      <span class="toggle-track"><span class="toggle-thumb"></span></span>
      <span class="toggle-label">
        <span class="toggle-title">Insert filament swap pauses</span>
        <span class="subtle">For &gt;4 colour prints: pause before a toolhead switches filament so you can re-spool. Works best when colours are separated by clear layer boundaries — avoid if colours are interleaved throughout the print.</span>
      </span>
    </label>

  </div>

  <button
    class="ghost advanced-trigger"
    onclick={() => (showAdvanced = !showAdvanced)}
    aria-expanded={showAdvanced}
  >
    {showAdvanced ? '▾' : '▸'} Advanced per-key overrides
  </button>

  {#if showAdvanced}
    <div class="advanced">
      <p class="subtle">
        YAML object of overrides to apply last (after rules). Winning precedence: overrides &gt; rules &gt; clamp &gt; filter &gt; source. Example:
      </p>
      <pre class="example mono">
layer_height: "0.24"
outer_wall_speed: 150</pre>
      <textarea
        bind:value={advancedOverrides}
        rows="6"
        spellcheck="false"
        placeholder="key: value"
        {disabled}
      ></textarea>
    </div>
  {/if}
</div>

<style>
  .settings { display: flex; flex-direction: column; gap: 18px; }
  .row { display: flex; flex-direction: column; gap: 6px; }
  .row label { font-weight: 500; font-size: 13px; }
  .profile-label-row { display: flex; align-items: center; gap: 8px; }
  .auto-badge {
    font-size: 10px;
    font-weight: 500;
    padding: 2px 7px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--accent) 15%, transparent);
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
    letter-spacing: 0.02em;
  }

  .toggles {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding-top: 4px;
  }

  .toggle {
    display: grid;
    grid-template-columns: 38px 1fr;
    align-items: center;
    gap: 12px;
    cursor: pointer;
    padding: 6px 0;
  }
  .toggle input { position: absolute; opacity: 0; pointer-events: none; }
  .toggle.disabled-toggle { cursor: not-allowed; opacity: 0.7; }

  .toggle-track {
    width: 34px; height: 20px;
    background: var(--border);
    border-radius: 999px;
    position: relative;
    transition: background var(--duration);
  }
  .toggle-thumb {
    position: absolute;
    top: 2px; left: 2px;
    width: 16px; height: 16px;
    background: var(--text);
    border-radius: 50%;
    transition: transform var(--duration);
  }
  .toggle input:checked ~ .toggle-track { background: var(--accent); }
  .toggle input:checked ~ .toggle-track .toggle-thumb {
    transform: translateX(14px);
    background: #fff;
  }
  .toggle input:focus-visible ~ .toggle-track {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .toggle-label {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .toggle-title { font-weight: 500; }
  .toggle-label .subtle { font-size: 12px; }

  .advanced-trigger {
    align-self: flex-start;
    padding: 4px 8px;
    font-size: 13px;
  }

  .advanced {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
    background: var(--bg-raised);
    border-radius: var(--radius);
    border: 1px solid var(--border);
  }
  .advanced p { margin: 0; font-size: 12px; }
  .example {
    margin: 0;
    font-size: 12px;
    background: var(--bg);
    padding: 10px 12px;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    color: var(--text-muted);
  }
  textarea { font-family: var(--font-mono); font-size: 12px; resize: vertical; }
</style>
