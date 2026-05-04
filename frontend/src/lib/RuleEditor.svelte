<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { EditorView, basicSetup } from 'codemirror';
  import { yaml } from '@codemirror/lang-yaml';
  import { oneDark } from '@codemirror/theme-one-dark';
  import {
    listRules, getRuleYaml, putRule, createRule, deleteRule, testMatch,
    type RuleSummary,
  } from './api';

  // ---- state ---------------------------------------------------------------
  let rules = $state<RuleSummary[]>([]);
  let selected = $state<string | null>(null);
  let editorYaml = $state('');
  let saving = $state(false);
  let saveError = $state('');
  let saveOk = $state(false);
  let loading = $state(true);
  let testFile = $state<File | null>(null);
  let testResult = $state<unknown>(null);
  let testError = $state('');
  let testLoading = $state(false);
  let testInputEl: HTMLInputElement | undefined = $state();

  // ---- CodeMirror ----------------------------------------------------------
  let editorContainer: HTMLElement | undefined = $state();
  let view: EditorView | undefined;

  const NEW_RULE_TEMPLATE = `name: My Custom Rule
description: ""
match:
  filament_settings_id_contains: null
  filament_vendor: null
  filament_type: null
overrides:
  outer_wall_speed: 150
priority: 0
enabled: true
`;

  function setupEditor(content: string) {
    if (view) { view.destroy(); view = undefined; }
    if (!editorContainer) return;
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    view = new EditorView({
      doc: content,
      extensions: [
        basicSetup,
        yaml(),
        ...(isDark ? [oneDark] : []),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) editorYaml = view!.state.doc.toString();
        }),
        EditorView.theme({ '&': { fontSize: '13px', height: '340px' } }),
      ],
      parent: editorContainer,
    });
  }

  async function load() {
    loading = true;
    try {
      rules = await listRules();
    } catch { /* keep old list */ }
    loading = false;
  }

  async function selectRule(fileKey: string) {
    selected = fileKey;
    saveError = ''; saveOk = false;
    await tick(); // wait for {#if selected} to render cm-host
    const r = await getRuleYaml(fileKey);
    editorYaml = r.yaml_text;
    setupEditor(r.yaml_text);
  }

  async function newRule() {
    selected = '__new__';
    editorYaml = NEW_RULE_TEMPLATE;
    saveError = ''; saveOk = false;
    await tick(); // wait for {#if selected} to render cm-host
    setupEditor(NEW_RULE_TEMPLATE);
  }

  async function save() {
    saving = true; saveError = ''; saveOk = false;
    try {
      if (selected === '__new__') {
        await createRule(editorYaml);
      } else if (selected) {
        await putRule(selected, editorYaml);  // selected is already file_key
      }
      saveOk = true;
      await load();
      setTimeout(() => (saveOk = false), 2000);
    } catch (e: unknown) {
      saveError = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }

  async function remove(name: string, fileKey: string) {
    if (!confirm(`Delete rule "${name}"?`)) return;
    await deleteRule(fileKey);
    if (selected === fileKey) { selected = null; if (view) { view.destroy(); view = undefined; } }
    await load();
  }

  async function runTest() {
    if (!testFile) return;
    testLoading = true; testResult = null; testError = '';
    try {
      testResult = await testMatch(testFile);
    } catch (e: unknown) {
      testError = e instanceof Error ? e.message : String(e);
    } finally {
      testLoading = false;
    }
  }

  onMount(async () => {
    await load();
    if (rules.length > 0) await selectRule(rules[0].file_key);
  });

  onDestroy(() => { if (view) view.destroy(); });
</script>

<div class="rule-editor">
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>Filament Rules</h2>
      <button class="primary" onclick={newRule}>+ New</button>
    </div>

    {#if loading}
      <p class="muted" style="padding:0 4px">Loading…</p>
    {:else if rules.length === 0}
      <p class="muted" style="padding:0 4px">No rules yet. Click + New to create one.</p>
    {:else}
      <ul class="rule-list" role="listbox" aria-label="Rules">
        {#each rules as r (r.file_key)}
          <li
            class="rule-item"
            class:active={selected === r.file_key}
            role="option"
            aria-selected={selected === r.file_key}
            tabindex="0"
            onclick={() => selectRule(r.file_key)}
            onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') selectRule(r.file_key); }}
          >
            <div class="rule-item-name">
              <span class:muted={!r.enabled}>{r.name}</span>
              {#if !r.enabled}<span class="pill">disabled</span>{/if}
            </div>
            <div class="rule-item-meta subtle">p{r.priority} · {Object.keys(r.overrides).length} overrides</div>
          </li>
        {/each}
      </ul>
    {/if}

    <div class="test-section">
      <div class="test-header">Test match against 3mf</div>
      <input
        bind:this={testInputEl}
        type="file" accept=".3mf"
        style="display:none"
        onchange={(e) => {
          const f = (e.currentTarget as HTMLInputElement).files?.[0];
          if (f) { testFile = f; testResult = null; testError = ''; }
        }}
      />
      <div class="test-controls">
        <button class="ghost" onclick={() => testInputEl?.click()}>
          {testFile ? testFile.name : 'Choose .3mf…'}
        </button>
        <button
          class="primary"
          disabled={!testFile || testLoading}
          onclick={runTest}
        >
          {testLoading ? 'Testing…' : 'Test'}
        </button>
      </div>
      {#if testError}
        <p class="err">{testError}</p>
      {/if}
      {#if testResult}
        {@const result = testResult as { matches: Array<{rule_name: string; priority: number}>; context: unknown }}
        <div class="test-result">
          {#if result.matches.length === 0}
            <p class="muted">No rules matched.</p>
          {:else}
            {#each result.matches as m}
              <div class="match-row">
                <span class="pill accent">✓</span> {m.rule_name}
                <span class="subtle">p{m.priority}</span>
              </div>
            {/each}
          {/if}
        </div>
      {/if}
    </div>
  </div>

  <div class="editor-pane">
    {#if selected}
      <div class="editor-header">
        <span class="editor-title">
          {selected === '__new__' ? 'New rule' : selected}
        </span>
        <div class="editor-actions">
          {#if saveError}<span class="err">{saveError}</span>{/if}
          {#if saveOk}<span class="ok">Saved ✓</span>{/if}
          {#if selected !== '__new__'}
            {@const rule = rules.find(r => r.file_key === selected)}
            <button class="ghost danger" onclick={() => rule && remove(rule.name, rule.file_key)}>Delete</button>
          {/if}
          <button class="primary" onclick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
      <div class="cm-host" bind:this={editorContainer}></div>
    {:else}
      <div class="empty-editor">
        <p class="muted">Select a rule from the list or create a new one.</p>
      </div>
    {/if}
  </div>
</div>

<style>
  .rule-editor {
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 16px;
    min-height: 560px;
  }

  .sidebar {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .sidebar-header h2 { margin: 0; font-size: 16px; }

  .rule-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .rule-item {
    padding: 10px 12px;
    border-radius: var(--radius);
    border: 1px solid transparent;
    cursor: pointer;
    transition: background var(--duration), border-color var(--duration);
  }
  .rule-item:hover { background: var(--bg-raised); }
  .rule-item.active {
    background: var(--accent-dim);
    border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  }
  .rule-item-name { font-weight: 500; font-size: 13px; display: flex; align-items: center; gap: 8px; }
  .rule-item-meta { font-size: 11.5px; margin-top: 2px; }

  .test-section {
    margin-top: auto;
    border-top: 1px solid var(--border);
    padding-top: 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .test-header { font-weight: 500; font-size: 13px; }
  .test-controls { display: flex; gap: 8px; }
  .test-controls .ghost {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 12px;
    text-align: left;
  }
  .test-result {
    background: var(--bg-raised);
    border-radius: var(--radius);
    padding: 10px 12px;
    font-size: 12.5px;
  }
  .match-row { display: flex; align-items: center; gap: 8px; padding: 3px 0; }

  .editor-pane {
    display: flex;
    flex-direction: column;
    gap: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    background: var(--bg-elev);
  }
  .editor-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    gap: 12px;
    flex-wrap: wrap;
  }
  .editor-title { font-weight: 500; }
  .editor-actions { display: flex; align-items: center; gap: 10px; }
  .empty-editor {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .cm-host { flex: 1; overflow: hidden; }
  /* Let CodeMirror fill the pane */
  :global(.cm-host .cm-editor) { height: 100%; min-height: 340px; }
  :global(.cm-host .cm-scroller) { overflow: auto; }

  .err { color: var(--danger); font-size: 12px; margin: 0; }
  .ok { color: var(--success); font-size: 12px; }
</style>
