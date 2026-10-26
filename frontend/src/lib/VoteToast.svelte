<script lang="ts">
  import { VOTE_URL, VOTE_ENTRY, ALSO_WORTH_A_VOTE, markVoted } from './vote';

  let { onclose }: { onclose: () => void } = $props();

  let paused = $state(false);
  let toastEl: HTMLElement | undefined;

  // Auto-dismiss, but not while the pointer is over it. Nothing worse than
  // a prompt vanishing mid-read.
  $effect(() => {
    if (paused) return;
    // The arrow is load-bearing: passing onclose directly reads the prop
    // during effect setup, making it a dependency, so any parent re-render
    // tears down the timer and restarts the countdown.
    const timer = setTimeout(() => onclose(), 10000);
    return () => clearTimeout(timer);
  });

  // A click anywhere outside closes it. Armed a tick late so the download
  // click that opened the toast does not immediately dismiss it.
  $effect(() => {
    let armed = false;
    const arm = setTimeout(() => (armed = true), 0);

    function onPointerDown(e: PointerEvent) {
      if (armed && toastEl && !toastEl.contains(e.target as Node)) onclose();
    }

    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      clearTimeout(arm);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  });

  // Both actions mean the same thing: stop asking. Passive dismissals
  // (outside click, Escape, ×, timeout) deliberately record nothing, so the
  // prompt returns on the next download.
  function voted() {
    markVoted();
    onclose();
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<!-- Wrapper centres the toast without a backdrop; pointer-events stay off it
     so the page underneath is still fully usable. -->
<div class="vote-toast-wrap">
  <div
    class="vote-toast"
    bind:this={toastEl}
    role="status"
    onmouseenter={() => (paused = true)}
    onmouseleave={() => (paused = false)}
  >
    <button class="toast-close" onclick={onclose} aria-label="Dismiss vote notice">×</button>

    <p class="toast-title">Mind a quick vote?</p>
    <p class="toast-body">
      U1 Converter is entered in the Snapmaker Innovation Fund as
      <strong>{VOTE_ENTRY}</strong>, on page 2 of the gallery.
    </p>
    <p class="toast-body muted">
      You get 5 picks; {ALSO_WORTH_A_VOTE.join(' and ')} are both worth one too.
    </p>

    <div class="toast-actions">
      <a
        href={VOTE_URL}
        target="_blank"
        rel="noopener noreferrer"
        class="toast-cta"
        onclick={voted}
      >
        Vote →
      </a>
      <button class="toast-secondary" onclick={voted}>Already voted</button>
    </div>
  </div>
</div>

<style>
  .vote-toast-wrap {
    position: fixed;
    inset: 0;
    z-index: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    pointer-events: none;
  }

  .vote-toast {
    position: relative;
    pointer-events: auto;
    width: 380px;
    max-width: 100%;
    padding: 18px 20px;
    background: var(--bg-elev);
    border: 1px solid color-mix(in srgb, var(--accent) 32%, var(--border));
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg);
    animation: toast-in 200ms ease-out;
  }

  @keyframes toast-in {
    from { opacity: 0; transform: translateY(8px) scale(0.98); }
    to   { opacity: 1; transform: none; }
  }

  .toast-close {
    position: absolute;
    top: 8px;
    right: 8px;
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-subtle);
    font-size: 18px;
    line-height: 1;
    padding: 2px 6px;
    border-radius: 4px;
    transition: color var(--duration);
  }

  .toast-close:hover {
    color: var(--text);
  }

  .toast-title {
    margin: 0 20px 8px 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
  }

  .toast-body {
    margin: 0 0 6px;
    font-size: 13px;
    line-height: 1.5;
    color: var(--text);
  }

  .toast-body strong {
    color: var(--accent);
    font-weight: 600;
  }

  .toast-body.muted {
    color: var(--text-muted);
  }

  .toast-actions {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-top: 10px;
  }

  .toast-cta {
    color: var(--accent);
    font-size: 13px;
    font-weight: 600;
    text-decoration: none;
  }

  .toast-cta:hover {
    color: var(--accent-hover);
    text-decoration: underline;
  }

  .toast-secondary {
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    font-family: inherit;
    font-size: 12px;
    color: var(--text-subtle);
    text-decoration: underline;
    transition: color var(--duration);
  }

  .toast-secondary:hover {
    color: var(--text-muted);
  }
</style>
