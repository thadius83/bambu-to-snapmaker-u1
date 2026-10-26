<script lang="ts">
  import { VOTE_URL, VOTE_ENTRY, canShowVotePrompt, markVoted } from './vote';

  // Not dismissible by design: the strip runs for the whole voting window and
  // only clicking through clears it. Read once at init so the entry name stays
  // on screen while they are off voting in the new tab.
  const visible = canShowVotePrompt();
</script>

{#if visible}
  <div class="vote-strip">
    <span class="vote-text">
      Like U1 Converter? It's entered in the Snapmaker Innovation Fund as
      <strong>{VOTE_ENTRY}</strong>, on page 2 of the gallery. Voting closes 30 Sep.
    </span>
    <a
      href={VOTE_URL}
      target="_blank"
      rel="noopener noreferrer"
      class="vote-link"
      onclick={markVoted}
    >
      Vote →
    </a>
  </div>
{/if}

<style>
  .vote-strip {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    padding: 10px 14px;
    margin-bottom: 20px;
    background: color-mix(in srgb, var(--accent) 12%, var(--bg-elev));
    border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
    border-radius: var(--radius);
    font-size: 13px;
    color: var(--text);
  }

  .vote-text {
    flex: 1 1 280px;
    line-height: 1.5;
  }

  .vote-text strong {
    color: var(--accent);
    font-weight: 600;
  }

  .vote-link {
    color: var(--accent);
    font-weight: 600;
    text-decoration: none;
    white-space: nowrap;
  }

  .vote-link:hover {
    color: var(--accent-hover);
    text-decoration: underline;
  }
</style>
