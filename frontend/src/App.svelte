<script lang="ts">
  import { onMount } from 'svelte';
  import Upload from './lib/Upload.svelte';
  import Settings from './lib/Settings.svelte';
  import DiffView from './lib/DiffView.svelte';
  import BambuConvert from './lib/BambuConvert.svelte';
  import Feedback from './lib/Feedback.svelte';
  import RuleEditor from './lib/RuleEditor.svelte';
  import Help from './lib/Help.svelte';
  import { listProfiles, suggestProfile, convert, type ProfileDescriptor, type ConvertResult } from './lib/api';
  import ToolheadAssign from './lib/ToolheadAssign.svelte';

  // ---- routing (hash-based, zero deps) ------------------------------------
  type Route = 'convert' | 'blconvert' | 'rules' | 'help';
  let route = $state<Route>('convert');

  function navigate(r: Route) {
    route = r;
    window.location.hash = r === 'convert' ? '' : r;
  }

  onMount(() => {
    const check = () => {
      const h = window.location.hash;
      route = h === '#rules' ? 'rules' : h === '#help' ? 'help' : h === '#blconvert' ? 'blconvert' : 'convert';
    };
    check();
    window.addEventListener('hashchange', check);
    return () => window.removeEventListener('hashchange', check);
  });

  // ---- theme toggle --------------------------------------------------------
  let theme = $state<'dark' | 'light'>('dark');

  function toggleTheme() {
    theme = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('u13mf-theme', theme); } catch { /* ok */ }
  }

  onMount(() => {
    try {
      const saved = localStorage.getItem('u13mf-theme') as 'dark' | 'light' | null;
      if (saved) { theme = saved; document.documentElement.setAttribute('data-theme', theme); }
    } catch { /* ok */ }
  });

  // ---- profiles -----------------------------------------------------------
  let profiles = $state<ProfileDescriptor[]>([]);
  let profilesError = $state('');

  onMount(async () => {
    try {
      profiles = await listProfiles();
    } catch (e: unknown) {
      profilesError = e instanceof Error ? e.message : String(e);
    }
  });

  // ---- converter state machine --------------------------------------------
  type ConvertPhase = 'idle' | 'ready' | 'converting' | 'done' | 'error';
  let phase = $state<ConvertPhase>('idle');
  let analysing = $state(false);
  let analyseAttempted = $state(false);
  let file = $state<File | null>(null);
  let result = $state<ConvertResult | null>(null);
  let convertError = $state('');
  let analyseError = $state('');

  // settings
  let selectedProfile = $state('');
  let profileAutoMatched = $state(false);
  let alreadyConverted = $state(false);
  let isPaintedModel = $state(false);
  let isMultiplate = $state(false);
  let isOversized = $state(false);
  let isColourMixed = $state(false);
  let sourceSlicer = $state<string | null>(null);
  let paintedSlotMap = $state<Record<number, number>>({});
  let detectedFilaments = $state<Array<{index:number;settings_id:string|null;filament_type:string|null;vendor:string|null;colour:string|null}>>([]);
  let applyRules = $state(true);
  let insertSwapPauses = $state(false);
  let showSlotModal = $state(false);
  let advancedOverrides = $state('{}');

  // ---- conversion progress simulation ------------------------------------
  let convertProgress = $state(0);
  let _progressTimer: ReturnType<typeof setInterval> | null = null;

  function _startProgress(fileSize: number) {
    convertProgress = 0;
    const tau = fileSize < 1e6 ? 1500 : fileSize < 10e6 ? 4000 : fileSize < 50e6 ? 10000 : 18000;
    const start = Date.now();
    _progressTimer = setInterval(() => {
      const t = Date.now() - start;
      convertProgress = Math.min(89, 89 * (1 - Math.exp(-t / tau)));
    }, 80);
  }

  function _stopProgress() {
    if (_progressTimer) { clearInterval(_progressTimer); _progressTimer = null; }
  }

  const _progressStage = $derived(
    convertProgress < 12 ? 'Uploading…' :
    convertProgress < 28 ? 'Reading source settings…' :
    convertProgress < 46 ? 'Swapping printer identity & G-code…' :
    convertProgress < 62 ? 'Filtering keys & clamping speeds…' :
    convertProgress < 76 ? 'Applying filament rules…' :
    convertProgress < 89 ? 'Building output archive…' :
    'Finalising…'
  );

  $effect(() => {
    if (profiles.length > 0 && !selectedProfile) {
      const def = profiles.find((p) => p.id.includes('0.20') && p.id.includes('standard'))
        ?? profiles[0];
      selectedProfile = def.id;
    }
    // If a file was dropped before profiles finished loading, run analysis now.
    if (profiles.length > 0 && file && !profileAutoMatched && !analyseAttempted && !analysing && phase === 'ready') {
      analyseFile(file);
    }
  });

  async function analyseFile(f: File) {
    analysing = true;
    analyseAttempted = true;
    try {
      const s = await suggestProfile(f);
      selectedProfile = s.profile_id;
      profileAutoMatched = true;
      alreadyConverted = s.already_converted;
      isPaintedModel = s.is_painted_model;
      isMultiplate = s.is_multiplate;
      isOversized = s.is_oversized;
      isColourMixed = s.is_colour_mixed;
      sourceSlicer = s.source_slicer ?? null;
      detectedFilaments = s.filaments;
      insertSwapPauses = s.filaments.length > 4 && !s.is_painted_model;
    } catch (err) {
      const message = err instanceof Error ? err.message.replace(/^\d+:\s*/, '') : '';
      analyseError = message || 'Could not read file — is this a valid .3mf file?';
      phase = 'error';
    } finally {
      analysing = false;
    }
  }

  async function onFile(f: File) {
    file = f;
    phase = f ? 'ready' : 'idle';
    result = null;
    convertError = '';
    analyseError = '';
    profileAutoMatched = false;
    analyseAttempted = false;
    alreadyConverted = false;
    isPaintedModel = false;
    isMultiplate = false;
    isOversized = false;
    sourceSlicer = null;
    paintedSlotMap = {};
    detectedFilaments = [];
    if (f && profiles.length > 0) {
      await analyseFile(f);
    }
  }

  function handleConvert() {
    if (isPaintedModel && detectedFilaments.length > 4) {
      showSlotModal = true;
    } else {
      runConvert({});
    }
  }

  async function runConvert(slotMap: Record<number, number>) {
    if (!file || !selectedProfile) return;
    showSlotModal = false;
    paintedSlotMap = slotMap;
    phase = 'converting';
    convertError = '';
    _startProgress(file.size);
    try {
      result = await convert({
        file,
        reference_profile: selectedProfile,
        apply_rules: applyRules,
        clamp_speeds: true,
        preserve_color_painting: true,
        insert_swap_pauses: insertSwapPauses,
        advanced_overrides: advancedOverrides,
        slot_map: Object.keys(slotMap).length > 0 ? slotMap : undefined,
      });
      _stopProgress();
      convertProgress = 100;
      await new Promise(r => setTimeout(r, 350));
      phase = 'done';
    } catch (e: unknown) {
      _stopProgress();
      convertProgress = 0;
      convertError = e instanceof Error ? e.message : String(e);
      phase = 'error';
    }
  }

  function reset() {
    file = null;
    result = null;
    convertError = '';
    analyseError = '';
    phase = 'idle';
    detectedFilaments = [];
    profileAutoMatched = false;
    analyseAttempted = false;
    alreadyConverted = false;
    isPaintedModel = false;
    isMultiplate = false;
    isOversized = false;
    sourceSlicer = null;
    paintedSlotMap = {};
  }
</script>

<div class="layout">
  <!-- ---- nav ------------------------------------------------------------ -->
  <header class="nav">
    <div class="wordmark-wrap">
      <button class="wordmark ghost" onclick={() => navigate('convert')} aria-label="Home">
        <svg aria-hidden="true" width="22" height="22" viewBox="0 0 32 32">
          <rect width="32" height="32" rx="6" fill="var(--accent)"/>
          <path d="M8 24 L16 7 L24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linejoin="round"/>
        </svg>
        U1 Converter
      </button>
      <div class="wordmark-tooltip" role="tooltip">
        Convert a Bambu Studio <code>.3mf</code> project file for use with the
        <strong>Snapmaker U1</strong>. Upload, pick a quality profile, download —
        then re-slice in Snapmaker Orca. No manual edits needed.
      </div>
    </div>

    <nav aria-label="Main navigation">
      <button
        class="nav-link"
        class:active={route === 'convert'}
        onclick={() => navigate('convert')}
      >
        <span class="nav-label-full">Bambu Labs → Snapmaker U1</span>
        <span class="nav-label-short">Convert</span>
        <span class="nav-badge beta">BETA</span>
      </button>
      <button
        class="nav-link"
        class:active={route === 'help'}
        onclick={() => navigate('help')}
      >Help</button>
    </nav>

    <div class="nav-right">
      <a
        href="https://buymeacoffee.com/jdau"
        target="_blank"
        rel="noopener noreferrer"
        class="bmc-nav-link"
      >
        <span class="bmc-label-full">Support this site ☕ Buy me a coffee</span>
        <span class="bmc-label-short">Buy me a coffee</span>
      </a>
      <a
        href="https://github.com/thadius83/bambu-to-snapmaker-u1"
        target="_blank"
        rel="noopener noreferrer"
        class="gh-nav-link"
        aria-label="View source on GitHub"
        title="View source on GitHub"
      >
        <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" focusable="false">
          <path fill="currentColor" fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
        </svg>
      </a>
      <button
        class="ghost icon-btn"
        onclick={toggleTheme}
        aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
      >
        {theme === 'dark' ? '☀' : '☽'}
      </button>
    </div>
  </header>

  <!-- ---- main ----------------------------------------------------------- -->
  <main>
    {#if route === 'blconvert'}
      <BambuConvert />

    {:else if route === 'help'}
      <div class="page-header">
        <h1>Help &amp; Support</h1>
        <p class="muted">Supported printers, how conversion works, and known limitations.</p>
      </div>
      <Help onNavigate={navigate} />

    {:else if route === 'rules'}
      <div class="page-header">
        <h1>Filament Rules</h1>
        <p class="muted">
          YAML rules that match on filament type / vendor / profile name and apply
          per-key speed, accel, and temperature overrides during conversion.
        </p>
      </div>
      <RuleEditor />

    {:else}
      <!-- convert flow -->
      {#if phase === 'done' && result}
        <DiffView
          diff={result.diff}
          jobId={result.job_id}
          downloadName={result.download_name}
          onreset={reset}
        />

      {:else}
        <div class="page-header tight">
          <h1>Convert Bambu → U1</h1>
          <p class="muted">
            Drop a Bambu Studio .3mf. We swap the printer identity, G-code,
            and drop incompatible keys. Re-slice in Snapmaker Orca.
          </p>
        </div>

        <div class="convert-layout" class:idle={phase === 'idle' && !analysing}>
          <!-- left: upload + status -->
          <div class="left-col">
            <Upload
              onfile={onFile}
              bind:file
              disabled={phase === 'converting' || analysing}
            />

            {#if analysing}
              <div class="status-toast" role="status" aria-live="polite">
                <span class="spinner-sm" aria-hidden="true"></span>
                Analysing file…
              </div>
            {/if}

            {#if alreadyConverted}
              <div class="warn-banner" role="alert">
                <strong>Already converted:</strong> this file's printer is already set to Snapmaker U1. Upload the original source file to convert again.
              </div>
            {/if}

            {#if isPaintedModel && detectedFilaments.length > 4}
              <div class="warn-banner" role="alert">
                <strong>No per-layer colour data found:</strong> this looks like a painted model — colour changes will be generated by Snapmaker Orca at re-slice time. Filament swap pauses cannot be pre-inserted.
                If this file uses layer-based colour changes and was flagged incorrectly, convert anyway — the output will be correct.
              </div>
            {/if}

            {#if isMultiplate}
              <div class="warn-banner" role="alert">
                <strong>Multi-plate project:</strong> this file contains multiple plates. Only the first plate will be automatically positioned on the U1 bed — use Orca's arrange tool for remaining plates after conversion.
              </div>
            {/if}

            {#if isOversized}
              <div class="warn-banner" role="alert">
                <strong>Large build plate:</strong> this file was designed for a bed larger than the U1's 270×270mm build area. Check model placement in Orca after conversion.
              </div>
            {/if}

            {#if isColourMixed}
              <div class="warn-banner" role="alert">
                <strong>Colour mixing detected:</strong> this file uses Bambu's sub-layer colour blending feature. The U1 does not support colour mixing natively — conversion has not been tested with these files and results may vary. Blended colours will be treated as separate filament slots.
              </div>
            {/if}

            {#if sourceSlicer}
              <div class="warn-banner" role="alert">
                <strong>Experimental — non-Bambu file:</strong> source detected as <em>{sourceSlicer}</em>. Profile auto-selected from layer height. Re-slice in Snapmaker Orca before printing and verify all settings.
              </div>
            {/if}

            {#if phase === 'error' && analyseError}
              <div class="error-banner" role="alert">
                <strong>Unrecognised file:</strong> {analyseError}
              </div>
            {:else if phase === 'error' && convertError}
              <div class="error-banner" role="alert">
                <strong>Conversion failed:</strong> {convertError}
                <button class="ghost" onclick={() => (phase = 'ready')}>Retry</button>
              </div>
            {/if}

            {#if profilesError}
              <div class="error-banner" role="alert">
                Could not load profiles: {profilesError}
              </div>
            {/if}
          </div>

          <!-- right: settings + convert button (only show when a file is picked and analysed) -->
          {#if phase !== 'idle' && !analysing}
            <div class="right-col">
              <Settings
                {profiles}
                bind:selectedProfile
                bind:applyRules
                bind:insertSwapPauses
                bind:advancedOverrides
                autoMatched={profileAutoMatched}
                disabled={phase === 'converting' || analysing}
              />

              {#if detectedFilaments.length > 0}
                <div class="filament-swatches card card-padded">
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
                onclick={handleConvert}
                disabled={!file || !selectedProfile || phase === 'converting' || analysing || alreadyConverted}
              >
                Convert to U1
              </button>
            </div>
          {/if}
        </div>
      {/if}

      {#if phase === 'idle' && !analysing}
        <div class="how-it-works-bar">
          <div class="hiw-step">
            <div class="hiw-num">1</div>
            <div class="hiw-body"><div class="hiw-label">Upload</div><div class="hiw-desc">Drop your Bambu Studio <code>.3mf</code> project file</div></div>
          </div>
          <div class="hiw-arrow">→</div>
          <div class="hiw-step">
            <div class="hiw-num">2</div>
            <div class="hiw-body"><div class="hiw-label">Profile matched</div><div class="hiw-desc">Layer height and quality auto-selected</div></div>
          </div>
          <div class="hiw-arrow">→</div>
          <div class="hiw-step">
            <div class="hiw-num">3</div>
            <div class="hiw-body"><div class="hiw-label">Convert</div><div class="hiw-desc">Settings, G-code, and filament data rewritten for U1</div></div>
          </div>
          <div class="hiw-arrow">→</div>
          <div class="hiw-step">
            <div class="hiw-num">4</div>
            <div class="hiw-body"><div class="hiw-label">Download & re-slice</div><div class="hiw-desc">Open in Snapmaker Orca — no manual edits needed</div></div>
          </div>
        </div>
      {/if}
    {/if}
  </main>

  <footer>
    <div class="footer-links">
      <span class="subtle">Bambu → Snapmaker U1 3mf Converter</span>
      <span class="subtle">·</span>
      <a href="#help" onclick={() => navigate('help')}>Help</a>
      <span class="subtle">·</span>
      <a href="/privacy.html">Privacy</a>
    </div>
  </footer>
</div>

<Feedback currentPage={route} />

{#if phase === 'converting'}
  <div class="convert-overlay" role="status" aria-live="polite">
    <div class="convert-overlay-card">
      <div class="overlay-header">
        <span class="overlay-title">Converting</span>
        <span class="overlay-pct">{Math.round(convertProgress)}%</span>
      </div>
      <span class="overlay-file">{file?.name ?? ''}</span>
      <div class="progress-track">
        <div class="progress-fill" style="width:{convertProgress}%"></div>
      </div>
      <span class="overlay-stage">{_progressStage}</span>
    </div>
  </div>
{/if}

{#if showSlotModal}
  <ToolheadAssign
    filaments={detectedFilaments}
    onconfirm={(map) => runConvert(map)}
    onskip={() => runConvert({})}
  />
{/if}

<style>
  .layout {
    min-height: 100vh;
    display: grid;
    grid-template-rows: auto 1fr auto;
  }

  /* ---- nav ---- */
  .nav {
    position: sticky;
    top: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 0 24px;
    min-height: 52px;
    border-bottom: 1px solid var(--border);
    background: color-mix(in srgb, var(--bg) 92%, transparent);
    backdrop-filter: blur(8px);
  }
  .wordmark-wrap { position: relative; margin-right: 8px; }
  .wordmark-wrap:hover .wordmark-tooltip { opacity: 1; pointer-events: auto; }

  .wordmark-tooltip {
    position: absolute;
    top: calc(100% + 10px);
    left: 0;
    width: 260px;
    background: var(--bg-elev);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 10px 14px;
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--text-muted);
    box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.15s;
    z-index: 200;
  }
  .wordmark-tooltip strong { color: var(--text); }
  .wordmark-tooltip code { font-family: var(--font-mono); font-size: 11px; background: var(--bg-raised); padding: 1px 4px; border-radius: 3px; }

  .wordmark {
    display: flex;
    align-items: center;
    gap: 9px;
    white-space: nowrap;
    font-weight: 600;
    font-size: 15px;
    color: var(--text);
    background: transparent;
    border: none;
    padding: 6px 8px;
  }
  .wordmark:hover { background: transparent; }

  nav {
    display: flex;
    gap: 2px;
    min-width: 0;
  }
  .nav-link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: transparent;
    border: none;
    font-size: 13.5px;
    color: var(--text-muted);
    padding: 6px 12px;
    border-radius: var(--radius);
    font-weight: 500;
    transition: color var(--duration), background var(--duration);
  }
  .nav-link:hover { background: var(--bg-raised); color: var(--text); border-color: transparent; }
  .nav-link.active { color: var(--text); background: var(--bg-raised); }
  .nav-label-short { display: none; }

  .nav-badge {
    font-size: 9px; font-weight: 700; letter-spacing: 0.04em;
    padding: 1px 4px; border-radius: 3px; vertical-align: middle;
  }
  .nav-badge.beta { background: color-mix(in srgb, var(--accent) 20%, transparent); color: var(--accent); }
  .nav-badge.alpha { background: color-mix(in srgb, var(--warn) 20%, transparent); color: var(--warn); }

  .nav-right {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
  }
  .icon-btn { padding: 6px 10px; font-size: 16px; border: none; }
  .bmc-nav-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 6px 14px;
    background: color-mix(in srgb, #b45309 12%, var(--bg-elev));
    border: 1px solid color-mix(in srgb, #b45309 35%, transparent);
    border-radius: var(--radius);
    color: #b45309;
    text-decoration: none;
    font-size: 13px;
    font-weight: 500;
    white-space: nowrap;
    transition: background var(--duration), border-color var(--duration);
  }
  .bmc-nav-link:hover {
    background: color-mix(in srgb, #b45309 22%, var(--bg-elev));
    border-color: color-mix(in srgb, #b45309 55%, transparent);
  }
  .bmc-label-short { display: none; }

  .gh-nav-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: var(--radius);
    color: var(--text-muted);
    border: 1px solid transparent;
    transition: color var(--duration), background var(--duration), border-color var(--duration);
  }
  .gh-nav-link:hover {
    color: var(--text);
    background: var(--bg-raised);
    border-color: var(--border);
  }

  /* ---- main ---- */
  main { max-width: 960px; margin: 0 auto; padding: 40px 24px; width: 100%; }

  .page-header { margin-bottom: 28px; }
  .page-header.tight { margin-bottom: 20px; }
  .page-header h1 { margin: 0 0 8px; font-size: 24px; font-weight: 600; }
  .page-header p { margin: 0; font-size: 14px; max-width: 520px; }

  /* ---- convert layout ---- */
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
  @media (max-width: 680px) {
    .convert-layout { grid-template-columns: 1fr; }
  }

  @media (max-width: 720px) {
    .nav {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      grid-template-areas:
        "brand actions"
        "tabs tabs";
      gap: 6px 8px;
      padding: 8px 16px;
    }
    .wordmark-wrap {
      grid-area: brand;
      min-width: 0;
      margin-right: 0;
    }
    .wordmark {
      max-width: 100%;
      padding-left: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .wordmark-tooltip {
      display: none;
    }
    nav {
      grid-area: tabs;
      width: 100%;
      gap: 6px;
    }
    .nav-link {
      flex: 1 1 0;
      justify-content: center;
      min-height: 36px;
      padding: 7px 10px;
    }
    .nav-label-full,
    .bmc-label-full {
      display: none;
    }
    .nav-label-short,
    .bmc-label-short {
      display: inline;
    }
    .nav-right {
      grid-area: actions;
      margin-left: 0;
      justify-content: flex-end;
    }
    .bmc-nav-link {
      min-height: 34px;
      padding: 6px 10px;
    }
    .icon-btn {
      min-width: 34px;
      min-height: 34px;
      padding: 6px 8px;
    }
    .gh-nav-link {
      width: 34px;
      height: 34px;
    }
  }

  @media (max-width: 380px) {
    .nav {
      padding-left: 12px;
      padding-right: 12px;
    }
    .wordmark {
      font-size: 14px;
      gap: 7px;
    }
    .bmc-nav-link {
      padding-left: 8px;
      padding-right: 8px;
    }
  }

  .left-col { display: flex; flex-direction: column; gap: 16px; }
  .right-col {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .convert-btn {
    width: 100%;
    padding: 12px 20px;
    font-size: 15px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  .filament-swatches { display: flex; flex-direction: column; gap: 8px; }
  .swatch-label-title { font-size: 12px; font-weight: 500; color: var(--text-muted); }
  .swatch-row { display: flex; flex-wrap: wrap; gap: 6px; }
  .swatch-chip { width: 28px; height: 28px; border-radius: var(--radius); border: 1px solid color-mix(in srgb, var(--border) 60%, transparent); }

  .status-toast {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    background: color-mix(in srgb, var(--accent) 10%, var(--bg-elev));
    border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
    border-radius: var(--radius);
    font-size: 13px;
    color: var(--text-muted);
  }
  .status-toast.converting {
    background: color-mix(in srgb, var(--accent) 15%, var(--bg-elev));
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
    color: var(--text);
  }
  .spinner-sm {
    width: 13px; height: 13px; flex-shrink: 0;
    border: 2px solid color-mix(in srgb, var(--accent) 30%, transparent);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    display: inline-block;
  }

  .warn-banner {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: color-mix(in srgb, var(--warn) 12%, var(--bg-elev));
    border: 1px solid color-mix(in srgb, var(--warn) 35%, transparent);
    border-radius: var(--radius);
    color: var(--warn);
    font-size: 13px;
  }

  .error-banner {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: color-mix(in srgb, var(--danger) 12%, var(--bg-elev));
    border: 1px solid color-mix(in srgb, var(--danger) 35%, transparent);
    border-radius: var(--radius);
    color: var(--danger);
    font-size: 13px;
  }

  /* ---- how it works bar ---- */
  .how-it-works-bar {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    flex-wrap: wrap;
    padding: 16px 20px;
    margin-top: 48px;
    background: var(--bg-elev);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .hiw-step {
    flex: 1;
    min-width: 140px;
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }
  .hiw-num {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: color-mix(in srgb, #b45309 18%, transparent);
    border: 1px solid color-mix(in srgb, #b45309 40%, transparent);
    color: #b45309;
    font-size: 11px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-top: 1px;
  }
  .hiw-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 2px;
  }
  .hiw-desc {
    font-size: 11.5px;
    color: var(--text-muted);
    line-height: 1.4;
  }
  .hiw-arrow {
    color: color-mix(in srgb, #b45309 50%, transparent);
    font-size: 16px;
    margin-top: 3px;
    flex-shrink: 0;
  }

  @media (max-width: 600px) {
    .how-it-works-bar {
      flex-direction: column;
      gap: 4px;
      padding: 14px 16px;
    }
    .hiw-step { flex: none; width: 100%; }
    .hiw-arrow {
      margin-top: 0;
      margin-left: 34px;
      transform: rotate(90deg);
      font-size: 14px;
    }
  }

  footer {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 16px 24px;
    border-top: 1px solid var(--border);
    font-size: 12px;
  }
  .footer-links {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  /* ---- converting overlay ---- */
  .convert-overlay {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    z-index: 800;
  }
  .convert-overlay-card {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 28px 32px;
    background: var(--bg-elev);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: 0 12px 48px rgba(0, 0, 0, 0.45);
    width: 380px;
    max-width: calc(100vw - 48px);
  }
  .overlay-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }
  .overlay-title { font-size: 16px; font-weight: 600; color: var(--text); }
  .overlay-pct { font-size: 20px; font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; }
  .overlay-file { font-size: 12px; color: var(--text-muted); word-break: break-all; line-height: 1.4; margin-top: -4px; }
  .progress-track {
    width: 100%; height: 8px;
    background: var(--bg-raised);
    border-radius: 4px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 4px;
    transition: width 0.15s ease-out;
  }
  .overlay-stage { font-size: 12px; color: var(--text-muted); }
</style>
