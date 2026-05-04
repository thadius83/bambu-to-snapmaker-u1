<script lang="ts">
  interface Props {
    onfile: (file: File) => void;
    file: File | null;
    disabled?: boolean;
  }

  let { onfile, file = $bindable(), disabled = false }: Props = $props();

  let dragOver = $state(false);
  let inputEl: HTMLInputElement | undefined = $state();

  function pick(ev: Event) {
    const target = ev.currentTarget as HTMLInputElement;
    const f = target.files?.[0];
    if (f) onfile(f);
  }

  function drop(ev: DragEvent) {
    ev.preventDefault();
    dragOver = false;
    if (disabled) return;
    const f = ev.dataTransfer?.files?.[0];
    if (f && f.name.toLowerCase().endsWith('.3mf')) onfile(f);
  }

  function over(ev: DragEvent) {
    ev.preventDefault();
    if (!disabled) dragOver = true;
  }
</script>

<div
  class="dropzone"
  class:drag-over={dragOver}
  class:has-file={!!file}
  class:disabled
  ondragover={over}
  ondragleave={() => (dragOver = false)}
  ondrop={drop}
  onclick={() => !disabled && inputEl?.click()}
  onkeydown={(e) => {
    if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      inputEl?.click();
    }
  }}
  role="button"
  tabindex={disabled ? -1 : 0}
  aria-label="Upload a Bambu .3mf file"
  aria-disabled={disabled}
>
  <input
    bind:this={inputEl}
    type="file"
    accept=".3mf"
    onchange={pick}
    {disabled}
    hidden
  />

  {#if file}
    <div class="summary">
      <div class="icon" aria-hidden="true">📦</div>
      <div class="filename">{file.name}</div>
      <div class="meta subtle">{(file.size / 1024 / 1024).toFixed(2)} MB</div>
      <button class="ghost" onclick={(e) => { e.stopPropagation(); onfile(null as unknown as File); }}>
        Replace
      </button>
    </div>
  {:else}
    <div class="prompt">
      <div class="icon" aria-hidden="true">↑</div>
      <div class="title">Drop your Bambu .3mf here</div>
      <div class="subtle">or click to choose a file</div>
    </div>
  {/if}
</div>

<style>
  .dropzone {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 180px;
    border: 1.5px dashed var(--border-strong);
    border-radius: var(--radius-lg);
    background: var(--bg-elev);
    padding: 28px;
    cursor: pointer;
    transition: border-color var(--duration), background var(--duration), transform var(--duration);
  }
  .dropzone:hover:not(.disabled) {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 4%, var(--bg-elev));
  }
  .dropzone.drag-over {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 10%, var(--bg-elev));
    transform: scale(1.005);
  }
  .dropzone.has-file {
    border-style: solid;
    border-color: var(--border);
  }
  .dropzone.disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .prompt { text-align: center; }
  .prompt .icon {
    font-size: 28px;
    color: var(--text-muted);
    margin-bottom: 8px;
  }
  .prompt .title {
    font-size: 16px;
    font-weight: 500;
    margin-bottom: 4px;
  }

  .summary {
    display: flex;
    align-items: center;
    gap: 14px;
    width: 100%;
  }
  .summary .icon { font-size: 24px; }
  .summary .filename {
    font-weight: 500;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .summary .meta { flex-shrink: 0; font-size: 12px; }
</style>
