<script lang="ts">
  interface Props {
    source: number[];
    target: number[];
    completed?: boolean;
  }

  let { source, target, completed = false }: Props = $props();
  const changed = $derived(source.length > 0 && target.length > 0 && source.join(',') !== target.join(','));
</script>

{#if changed}
  <div class="nozzle-warning" role="status">
    <strong>{completed ? 'Nozzle size changed' : 'Selected profile changes nozzle size'}: {source.join(' / ')} mm → {target.join(' / ')} mm</strong>
    <span>Review layer height and line widths in Orca before printing.</span>
  </div>
{/if}

<style>
  .nozzle-warning {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px 16px;
    background: color-mix(in srgb, var(--warn) 12%, var(--bg-elev));
    border: 1px solid color-mix(in srgb, var(--warn) 35%, transparent);
    border-radius: var(--radius);
    color: var(--warn);
    font-size: 13px;
  }
</style>
