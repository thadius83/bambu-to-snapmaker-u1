<script lang="ts">
  import { onMount } from 'svelte';
  import Upload from './Upload.svelte';
  import DiffView from './DiffView.svelte';
  import { listBambuPrinters, convertBambu, suggestProfile, type ConvertResult } from './api';

  type Phase = 'idle' | 'ready' | 'converting' | 'done' | 'error';

  let phase = $state<Phase>('idle');
  let file = $state<File | null>(null);
  let result = $state<ConvertResult | null>(null);
  let error = $state('');

  let printers = $state<Array<{id: string; name: string}>>([]);
  let profilesError = $state('');
  let selectedProfile = $state('');
  let clampSpeeds = $state(true);
  let insertSwapPauses = $state(false);

  let detectedFilaments = $state<Array<{ colour: string | null; settings_id: string | null; filament_type: string | null }>>([]);
  let analysing = $state(false);

  onMount(async () => {
    try {
      printers = await listBambuPrinters();
      if (printers.length > 0) selectedProfile = printers[0].id;
    } catch (e: unknown) {
      profilesError = e instanceof Error ? e.message : String(e);
    }
  });

  async function onFile(f: File) {
    file = f;
    phase = f ? 'ready' : 'idle';
    result = null;
    error = '';
    detectedFilaments = [];
    if (f) {
      analysing = true;
      try {
        const s = await suggestProfile(f);
        detectedFilaments = s.filaments;
        insertSwapPauses = s.filaments.length > 4;
      } catch { /* keep defaults */ } finally {
        analysing = false;
      }
    }
  }

  async function runConvert() {
    if (!file || !selectedProfile) return;
    phase = 'converting';
    error = '';
    try {
      result = await convertBambu({ file, reference_profile: selectedProfile, clamp_speeds: clampSpeeds, insert_swap_pauses: insertSwapPauses });
      phase = 'done';
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : String(e);
      phase = 'error';
    }
  }

  function reset() {
    file = null; result = null; error = ''; phase = 'idle';
    detectedFilaments = [];
  }
</script>

{#if phase === 'done' && result}
  <DiffView diff={result.diff} jobId={result.job_id} downloadName={result.download_name} onreset={reset} />

{:else}
  <div class="page-header tight">
    <h1>Convert Bambu → Bambu</h1>
    <p class="muted">
      Cross-printer conversion. Upload a Bambu .3mf from any printer, select
      your target printer profile, and download a compatible file ready to
      re-slice.
    </p>
  </div>

  <div class="convert-layout" class:idle={phase === 'idle' && !analysing}>
    <div class="left-col">
      <Upload onfile={onFile} bind:file disabled={phase === 'converting' || analysing} />

      {#if analysing}
        <div class="analysing-toast" role="status" aria-live="polite">
          <span class="spinner-sm" aria-hidden="true"></span>
          Analysing file…
        </div>
      {/if}

      {#if error}
        <div class="error-banner" role="alert">
          <strong>Conversion failed:</strong> {error}
          <button class="ghost" onclick={() => (phase = 'ready')}>Retry</button>
        </div>
      {/if}

      {#if profilesError}
        <div class="error-banner" role="alert">Could not load profiles: {profilesError}</div>
      {/if}
    </div>

    {#if phase !== 'idle' && !analysing}
      <div class="right-col" class:converting={phase === 'converting'}>
        <div class="card card-padded settings-card">
          <label class="settings-label" for="bambu-profile">Target printer profile</label>
          <select id="bambu-profile" bind:value={selectedProfile} disabled={phase === 'converting'}>
            {#each printers as p}
              <option value={p.id}>{p.name}</option>
            {/each}
          </select>

          <div class="toggle-row">
            <label>
              <input type="checkbox" bind:checked={clampSpeeds} disabled={phase === 'converting'} />
              Clamp speeds to target ceilings
            </label>
          </div>

          <div class="toggle-row">
            <label>
              <input type="checkbox" bind:checked={insertSwapPauses} disabled={phase === 'converting'} />
              Insert swap pauses {#if detectedFilaments.length > 4}<span class="auto-badge">auto</span>{/if}
            </label>
          </div>
        </div>

        {#if detectedFilaments.length > 0}
          <div class="card card-padded filament-swatches">
            <span class="swatch-label-title">Detected filaments</span>
            <div class="swatch-row">
              {#each detectedFilaments as f}
                <div
                  class="swatch-chip"
                  style="background:{f.colour ?? '#888'}"
                  title="{f.settings_id ?? f.filament_type ?? 'Unknown'}"
                ></div>
              {/each}
            </div>
          </div>
        {/if}

        <button
          class="primary convert-btn"
          onclick={runConvert}
          disabled={!file || !selectedProfile || phase === 'converting'}
          aria-live="polite"
        >
          {#if phase === 'converting'}
            <span class="spinner" aria-hidden="true"></span>
            Converting…
          {:else}
            Convert
          {/if}
        </button>
      </div>
    {/if}
  </div>
{/if}

<style>
  .convert-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 28px;
    align-items: start;
  }
  .convert-layout.idle {
    grid-template-columns: 1fr;
    max-width: 480px;
    margin: 0 auto;
  }
  @media (max-width: 680px) { .convert-layout { grid-template-columns: 1fr; } }

  .analysing-toast {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px;
    background: color-mix(in srgb, var(--accent) 10%, var(--bg-elev));
    border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
    border-radius: var(--radius); font-size: 13px; color: var(--text-muted);
  }
  .spinner-sm {
    width: 13px; height: 13px; flex-shrink: 0;
    border: 2px solid color-mix(in srgb, var(--accent) 30%, transparent);
    border-top-color: var(--accent); border-radius: 50%;
    animation: spin 0.7s linear infinite; display: inline-block;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .left-col { display: flex; flex-direction: column; gap: 16px; }
  .right-col { display: flex; flex-direction: column; gap: 16px; transition: opacity var(--duration); }
  .right-col.converting { opacity: 0.7; pointer-events: none; }

  .page-header { margin-bottom: 28px; }
  .page-header.tight { margin-bottom: 20px; }
  .page-header h1 { margin: 0 0 8px; font-size: 24px; font-weight: 600; }
  .page-header p { margin: 0; font-size: 14px; max-width: 520px; }

  .settings-card { display: flex; flex-direction: column; gap: 14px; }
  .settings-label { font-size: 12px; font-weight: 500; color: var(--text-muted); }
  select { width: 100%; }
  .toggle-row label { display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer; }

  .auto-badge {
    font-size: 10px; font-weight: 600; padding: 1px 5px;
    background: var(--accent); color: #fff; border-radius: 4px;
  }

  .convert-btn {
    width: 100%; padding: 12px 20px; font-size: 15px; font-weight: 600;
    display: flex; align-items: center; justify-content: center; gap: 10px;
  }

  .spinner {
    width: 16px; height: 16px;
    border: 2px solid rgba(255,255,255,0.35);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    display: inline-block;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .filament-swatches { display: flex; flex-direction: column; gap: 8px; }
  .swatch-label-title { font-size: 12px; font-weight: 500; color: var(--text-muted); }
  .swatch-row { display: flex; flex-wrap: wrap; gap: 6px; }
  .swatch-chip { width: 28px; height: 28px; border-radius: var(--radius); border: 1px solid color-mix(in srgb, var(--border) 60%, transparent); }

  .error-banner {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 16px;
    background: color-mix(in srgb, var(--danger) 12%, var(--bg-elev));
    border: 1px solid color-mix(in srgb, var(--danger) 35%, transparent);
    border-radius: var(--radius); color: var(--danger); font-size: 13px;
  }
</style>
