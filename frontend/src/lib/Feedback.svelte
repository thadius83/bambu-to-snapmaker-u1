<script lang="ts">
  interface Props { currentPage: string; }
  let { currentPage }: Props = $props();

  let open = $state(false);
  let message = $state('');
  let email = $state('');
  let phase = $state<'idle' | 'sending' | 'sent' | 'error'>('idle');

  function toggle() {
    open = !open;
    if (!open) { message = ''; email = ''; phase = 'idle'; }
  }

  async function submit() {
    if (!message.trim()) return;
    phase = 'sending';
    try {
      const form = new FormData();
      form.append('page', currentPage);
      form.append('message', message);
      form.append('email', email);
      const r = await fetch('/api/feedback', { method: 'POST', body: form });
      if (!r.ok) throw new Error(await r.text());
      phase = 'sent';
      setTimeout(() => { open = false; phase = 'idle'; message = ''; email = ''; }, 2000);
    } catch {
      phase = 'error';
    }
  }
</script>

<div class="fb-wrap">
  {#if open}
    <div class="fb-panel card" role="dialog" aria-label="Feedback">
      {#if phase === 'sent'}
        <p class="sent-msg">Thanks for the feedback!</p>
      {:else}
        <div class="fb-header">
          <span class="fb-title">Feedback</span>
          <button class="ghost icon-sm" onclick={toggle} aria-label="Close">✕</button>
        </div>

        <textarea
          bind:value={message}
          placeholder="What could be better? (optional)"
          rows="3"
          disabled={phase === 'sending'}
        ></textarea>

        <input
          type="email"
          bind:value={email}
          placeholder="Email (optional)"
          disabled={phase === 'sending'}
        />

        {#if phase === 'error'}
          <p class="err">Failed to send — try again.</p>
        {/if}

        <button
          class="primary submit-btn"
          onclick={submit}
          disabled={!message.trim() || phase === 'sending'}
        >{phase === 'sending' ? 'Sending…' : 'Send'}</button>
      {/if}
    </div>
  {/if}

  <button class="fb-trigger" onclick={toggle} aria-label="Open feedback">
    {open ? '✕' : '💬'}
  </button>
</div>

<style>
  .fb-wrap { position: fixed; bottom: 24px; right: 24px; z-index: 500; display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }

  .fb-trigger {
    width: 44px; height: 44px; border-radius: 50%;
    background: var(--accent); color: #fff; border: none;
    font-size: 18px; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    display: flex; align-items: center; justify-content: center;
    transition: transform 0.15s;
  }
  .fb-trigger:hover { transform: scale(1.08); background: var(--accent); }

  .fb-panel {
    width: 280px; padding: 16px; display: flex; flex-direction: column; gap: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.25);
  }

  .fb-header { display: flex; align-items: center; justify-content: space-between; }
  .fb-title { font-size: 14px; font-weight: 600; }
  .icon-sm { padding: 2px 6px; font-size: 12px; border: none; color: var(--text-muted); }

  textarea { width: 100%; resize: vertical; min-height: 70px; font-size: 13px; box-sizing: border-box; }
  input[type="email"] { width: 100%; font-size: 13px; box-sizing: border-box; }

  .submit-btn { width: 100%; padding: 8px; font-size: 13px; font-weight: 600; }
  .sent-msg { text-align: center; font-size: 14px; font-weight: 500; padding: 8px 0; }
  .err { font-size: 12px; color: var(--danger); margin: 0; }
</style>
