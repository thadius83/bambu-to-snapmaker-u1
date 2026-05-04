<script lang="ts">
  import type { FilamentInfo } from './api';

  interface Props {
    filaments: FilamentInfo[];
    onconfirm: (map: Record<number, number>) => void;
    onskip: () => void;
  }

  let { filaments, onconfirm, onskip }: Props = $props();

  // Colours 1-4 default to T1-T4; colours 5+ start unassigned.
  const initial: Record<number, number> = {};
  filaments.forEach((f) => { if (f.index < 4) initial[f.index] = f.index; });
  let assignments = $state<Record<number, number>>({ ...initial });

  const toolheads = [0, 1, 2, 3];

  import { onMount } from 'svelte';

  let modalEl: HTMLDivElement;
  let firstFocusable: HTMLElement | null = null;
  let lastFocusable: HTMLElement | null = null;

  onMount(() => {
    const focusable = modalEl.querySelectorAll<HTMLElement>(
      'button, select, [tabindex]:not([tabindex="-1"])'
    );
    firstFocusable = focusable[0] ?? null;
    lastFocusable = focusable[focusable.length - 1] ?? null;
    firstFocusable?.focus();
  });

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') { onskip(); return; }
    if (e.key === 'Tab') {
      if (e.shiftKey) {
        if (document.activeElement === firstFocusable) { e.preventDefault(); lastFocusable?.focus(); }
      } else {
        if (document.activeElement === lastFocusable) { e.preventDefault(); firstFocusable?.focus(); }
      }
    }
  }

  function assign(sourceIdx: number, value: string) {
    const next = { ...assignments };
    if (value === '') {
      delete next[sourceIdx];
    } else {
      next[sourceIdx] = parseInt(value, 10);
    }
    assignments = next;
  }

  function confirm() {
    onconfirm(assignments);
  }

  const overflowCount = filaments.filter((f) => f.index >= 4).length;
  const unassignedOverflow = $derived(
    filaments.filter((f) => f.index >= 4 && assignments[f.index] === undefined).length
  );
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="th-title" onkeydown={onKeydown}>
  <div class="modal" bind:this={modalEl}>
    <h2 class="modal-title" id="th-title">Assign colours to toolheads</h2>
    <p class="modal-desc">
      This file has <strong>{filaments.length} colours</strong> and no per-layer colour data — it appears to use painted geometry. Assign each colour to a physical toolhead, or skip to bring all colours through for Snapmaker Orca to handle at re-slice time.
      Colours left unassigned will be dropped if you confirm.
    </p>

    <div class="rows">
      {#each filaments as f}
        {@const isOverflow = f.index >= 4}
        {@const assigned = assignments[f.index] !== undefined}
        <div class="row" class:overflow={isOverflow && !assigned}>
          <span
            class="swatch"
            style="background:{f.colour ?? '#888'}"
            title={f.settings_id ?? f.filament_type ?? 'Unknown'}
          ></span>
          <span class="label">
            {f.filament_type ?? f.settings_id ?? `Colour ${f.index + 1}`}
          </span>
          {#if isOverflow && !assigned}
            <span class="drop-badge">will drop</span>
          {/if}
          <select
            class="sel"
            class:unset={isOverflow && !assigned}
            value={assigned ? String(assignments[f.index]) : ''}
            onchange={(e) => assign(f.index, (e.target as HTMLSelectElement).value)}
          >
            {#if isOverflow}<option value="">— unassigned</option>{/if}
            {#each toolheads as t}
              <option value={String(t)}>T{t + 1}</option>
            {/each}
          </select>
        </div>
      {/each}
    </div>

    {#if unassignedOverflow > 0}
      <p class="warn-note">
        {unassignedOverflow} colour{unassignedOverflow > 1 ? 's' : ''} will be dropped — assign {unassignedOverflow > 1 ? 'them' : 'it'} to a toolhead above to keep {unassignedOverflow > 1 ? 'them' : 'it'}.
      </p>
    {/if}

    <div class="actions">
      <button class="primary" onclick={onskip}>
        Bring all {filaments.length} colours through
      </button>
      <button class="ghost" onclick={confirm}>Assign to toolheads</button>
    </div>
  </div>
</div>

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 24px;
  }

  .modal {
    background: var(--bg-elev);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    width: 100%;
    max-width: 440px;
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    gap: 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    overflow: hidden;
  }

  .modal-title { margin: 0; font-size: 16px; font-weight: 600; }

  .modal-desc { margin: 0; font-size: 13px; color: var(--text-muted); line-height: 1.5; }

  .rows {
    display: flex;
    flex-direction: column;
    gap: 8px;
    overflow-y: auto;
    flex-shrink: 1;
    min-height: 0;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
  }

  .row.overflow { opacity: 0.65; }

  .swatch {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    flex-shrink: 0;
    border: 1px solid rgba(255, 255, 255, 0.12);
  }

  .label {
    flex: 1;
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .drop-badge {
    font-size: 10px;
    color: var(--warn);
    background: color-mix(in srgb, var(--warn) 15%, transparent);
    border-radius: 3px;
    padding: 1px 6px;
    flex-shrink: 0;
  }

  .sel {
    font-size: 12px;
    padding: 3px 6px;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    background: var(--bg-elev);
    color: var(--text);
    cursor: pointer;
    width: 88px;
    flex-shrink: 0;
  }

  .sel.unset { border-color: color-mix(in srgb, var(--warn) 50%, transparent); }

  .warn-note {
    margin: 0;
    font-size: 12px;
    color: var(--warn);
    background: color-mix(in srgb, var(--warn) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--warn) 25%, transparent);
    border-radius: var(--radius);
    padding: 8px 12px;
  }

  .actions {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
    align-items: center;
    padding-top: 4px;
    flex-shrink: 0;
    flex-wrap: wrap;
  }
</style>
