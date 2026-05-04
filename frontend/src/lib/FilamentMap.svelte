<script lang="ts">
  interface FilamentInfo {
    index: number;
    settings_id: string | null;
    filament_type: string | null;
    vendor: string | null;
    colour: string | null;
  }

  interface Props {
    filaments: FilamentInfo[];
    slotMap: Record<number, number>;
    disabled?: boolean;
  }

  let { filaments, slotMap = $bindable(), disabled = false }: Props = $props();

  const U1_TOOLHEADS = 4;

  function label(f: FilamentInfo): string {
    if (!f.settings_id) return `Slot ${f.index + 1}`;
    // Strip the "@printer" suffix for brevity: "Bambu PLA Matte @BBL H2S" → "Bambu PLA Matte"
    return f.settings_id.replace(/\s*@\S+.*$/, '').trim();
  }

  function isDark(hex: string | null): boolean {
    if (!hex) return true;
    const c = hex.replace('#', '');
    const r = parseInt(c.slice(0, 2), 16);
    const g = parseInt(c.slice(2, 4), 16);
    const b = parseInt(c.slice(4, 6), 16);
    return (r * 299 + g * 587 + b * 114) / 1000 < 128;
  }

  function onSelect(srcIndex: number, value: string) {
    const m = { ...slotMap };
    m[srcIndex] = parseInt(value, 10);
    slotMap = m;
  }

  function isDropped(srcIndex: number): boolean {
    return (slotMap[srcIndex] ?? srcIndex) < 0;
  }
</script>

<div class="filament-map card card-padded">
  <div class="fm-header">
    <span class="fm-title">Filament → U1 toolhead</span>
    <span class="subtle fm-hint">Assign each source filament to a U1 toolhead — multiple can share one</span>
  </div>

  <div class="fm-rows">
    {#each filaments as f (f.index)}
      {@const colour = f.colour ?? '#888888'}
      {@const dark = isDark(colour)}
      {@const dropped = isDropped(f.index)}
      <div class="fm-row" class:fm-row-dropped={dropped}>
        <div class="swatch" style="background:{colour}" class:swatch-dropped={dropped}>
          <span class="swatch-label" class:dark class:light={!dark}>
            {f.filament_type ?? '?'}
          </span>
        </div>
        <div class="fm-name">
          <span class="fm-id">{label(f)}</span>
          {#if f.vendor}
            <span class="subtle fm-vendor">{f.vendor}</span>
          {/if}
          {#if dropped}
            <span class="fm-drop-warning">will be dropped — U1 has 4 toolheads</span>
          {/if}
        </div>
        <div class="fm-arrow">{dropped ? '✕' : '→'}</div>
        <select
          value={slotMap[f.index] ?? f.index}
          onchange={(e) => onSelect(f.index, (e.currentTarget as HTMLSelectElement).value)}
          {disabled}
          class="fm-select"
          class:fm-select-dropped={dropped}
        >
          {#each Array.from({length: U1_TOOLHEADS}, (_, i) => i) as t}
            <option value={t}>T{t + 1}</option>
          {/each}
          <option value={-1}>Drop</option>
        </select>
      </div>
    {/each}
  </div>
</div>

<style>
  .filament-map { display: flex; flex-direction: column; gap: 12px; }

  .fm-header { display: flex; flex-direction: column; gap: 2px; }
  .fm-title { font-weight: 500; font-size: 13px; }
  .fm-hint { font-size: 11px; }

  .fm-rows { display: flex; flex-direction: column; gap: 8px; }

  .fm-row {
    display: grid;
    grid-template-columns: 56px 1fr 20px 56px;
    align-items: center;
    gap: 10px;
  }

  .swatch {
    height: 38px;
    border-radius: var(--radius);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .swatch-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }
  .swatch-label.dark { color: #fff; }
  .swatch-label.light { color: #000; }

  .fm-name {
    display: flex;
    flex-direction: column;
    gap: 1px;
    overflow: hidden;
  }
  .fm-id {
    font-size: 12.5px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .fm-vendor { font-size: 11px; }

  .fm-arrow { color: var(--text-muted); text-align: center; font-size: 14px; }

  .fm-row-dropped { opacity: 0.65; }
  .swatch-dropped { filter: grayscale(60%); }
  .fm-drop-warning { font-size: 10.5px; color: var(--warn); font-weight: 500; }

  .fm-select {
    font-size: 13px;
    font-weight: 500;
    text-align: center;
  }
  .fm-select-dropped { color: var(--warn); }
</style>
