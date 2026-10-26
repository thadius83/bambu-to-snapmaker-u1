/** Snapmaker Innovation Fund vote prompt. Shared config for the landing
 *  banner and the post-download toast.
 *
 *  The ballot lands on a listing rather than the entry itself, so both
 *  surfaces must name the entry and the page it sits on.
 */

/** Snapmaker's own page, which embeds the Easy Promos ballot. Preferred over
 *  linking the raw gallery: better trust signal and it carries the rules. */
export const VOTE_URL = 'https://www.snapmaker.com/innovation-fund#vote';
export const VOTE_ENTRY = 'bambu-to-snapmaker-u1';

/** Voters get 5 picks from 67 projects, so naming others costs us nothing. */
export const ALSO_WORTH_A_VOTE = ['Paxx', 'Sidecar'];

/** Voting runs 22 to 30 Sep 2026; everything self-hides once it closes. */
const VOTE_CLOSES = Date.UTC(2026, 8, 30, 23, 59, 0);

/** The only stored state. Passive dismissals are deliberately not recorded,
 *  so the prompt returns until someone says they have actually voted. */
const DONE = 'u13mf-vote-done';

function flag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

function setFlag(key: string): void {
  try {
    localStorage.setItem(key, '1');
  } catch {
    /* private mode / storage disabled, prompt just reappears next visit */
  }
}

/** Master switch. To bring the prompt back, set true and move VOTE_CLOSES. */
const VOTE_ENABLED = false;

const voteOpen = (): boolean => VOTE_ENABLED && Date.now() < VOTE_CLOSES;

/** One gate for both surfaces. */
export const canShowVotePrompt = (): boolean => voteOpen() && !flag(DONE);

/** Set by clicking through to vote or by saying "Already voted". Callers read
 *  their visibility once at init, so the prompt survives the click that sets
 *  this and only disappears on the next load. */
export const markVoted = (): void => setFlag(DONE);
