<script lang="ts">
  interface Props { onNavigate: (route: string) => void; }
  let { onNavigate }: Props = $props();
</script>

<div class="help">

  <!-- Workflow strip -->
  <section class="card card-padded workflow-card">
    <h2>How it works</h2>
    <div class="steps">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-body">
          <div class="step-label">Upload</div>
          <div class="step-desc">Drop your <code>.3mf</code> project file</div>
        </div>
      </div>
      <div class="step-arrow">→</div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-body">
          <div class="step-label">Profile matched</div>
          <div class="step-desc">Layer height and quality auto-selected from your file</div>
        </div>
      </div>
      <div class="step-arrow">→</div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-body">
          <div class="step-label">Convert</div>
          <div class="step-desc">Settings, G-code, and filament data rewritten for U1</div>
        </div>
      </div>
      <div class="step-arrow">→</div>
      <div class="step">
        <div class="step-num">4</div>
        <div class="step-body">
          <div class="step-label">Download & re-slice</div>
          <div class="step-desc">Review settings and re-slice in Snapmaker Orca</div>
        </div>
      </div>
    </div>
  </section>

  <!-- Supported printers -->
  <section class="card card-padded">
    <h2>Snapmaker U1 3MF Converter <span class="badge beta">BETA</span></h2>
    <p>
      Convert MakerWorld and Bambu Studio projects, plus OrcaSlicer, PrusaSlicer and Cura
      <code>.3mf</code> files for the <strong>Snapmaker U1</strong>.
      Review the converted settings and re-slice in Snapmaker Orca before printing.
    </p>
    <h3>Supported source printers</h3>
    <table>
      <thead><tr><th>Printer</th><th>Status</th></tr></thead>
      <tbody>
        <tr><td>Bambu Lab X1C / X1E</td><td><span class="badge ok">Tested</span></td></tr>
        <tr><td>Bambu Lab P1S / P1P</td><td><span class="badge ok">Tested</span></td></tr>
        <tr><td>Bambu Lab H2S</td><td><span class="badge ok">Tested</span></td></tr>
        <tr><td>Bambu Lab A1 / A1 Mini</td><td><span class="badge ok">Tested</span></td></tr>
        <tr><td>Bambu Lab H2D</td><td><span class="badge ok">Tested</span></td></tr>
      </tbody>
    </table>
    <h3>Additional source formats</h3>
    <table>
      <thead><tr><th>Format</th></tr></thead>
      <tbody>
        <tr><td>PrusaSlicer <code>.3mf</code>, including MMU painting</td></tr>
        <tr><td>OrcaSlicer and other Orca-based <code>.3mf</code> files</td></tr>
        <tr><td>Cura / basic geometry <code>.3mf</code> files</td></tr>
      </tbody>
    </table>
  </section>

  <!-- Multi-colour -->
  <section class="card card-padded">
    <h2>Multi-colour prints (&gt;4 colours)</h2>
    <p>
      The U1 has 4 physical toolheads. When your source file has more than 4 colours
      the converter detects the colour method and handles each case differently.
    </p>
    <div class="colour-grid">
      <div class="colour-card">
        <div class="colour-card-title">
          <span class="colour-icon">▤</span> Layer-based
        </div>
        <p>
          Each colour occupies a distinct layer range. The converter can insert automatic
          pause markers so you can re-spool a toolhead mid-print — enable
          <em>Insert filament swap pauses</em> in settings.
        </p>
        <p class="tip">Works best when colour boundaries are clear. Avoid if colours are
        interleaved across many layers — pauses will fire too frequently to be practical.</p>
      </div>
      <div class="colour-card">
        <div class="colour-card-title">
          <span class="colour-icon">✦</span> Painted models
        </div>
        <p>
          Colour information is stored in mesh geometry rather than per-layer G-code.
          Swap pauses cannot be pre-inserted — the slicer generates colour changes at
          re-slice time.
        </p>
        <p>
          For &gt;4 colours, pressing <em>Convert</em> opens a toolhead assignment step.
          Assign source colours to T1–T4, or skip to bring all colours through and let
          Snapmaker Orca handle assignment.
        </p>
        <p class="tip">PrusaSlicer MMU face painting is converted into
        Snapmaker Orca paint data during import.</p>
      </div>
    </div>
  </section>

  <!-- FAQ -->
  <section class="card card-padded">
    <h2>Frequently Asked Questions</h2>
    <div class="faq">
      <details>
        <summary>What file format does the converter accept?</summary>
        <p>The converter accepts <code>.3mf</code> project files from MakerWorld, Bambu Studio, OrcaSlicer, PrusaSlicer and Cura. Sliced <code>.gcode.3mf</code> files are not supported when they contain no editable model geometry — upload the original project <code>.3mf</code> instead.</p>
      </details>
      <details>
        <summary>Which Snapmaker models does it support?</summary>
        <p>The converter targets the Snapmaker U1 printer. Review the converted file and re-slice it in Snapmaker Orca before printing.</p>
      </details>
      <details>
        <summary>Which Bambu Lab printers are supported as a source?</summary>
        <p>Tested: X1C, X1E, P1S, P1P, H2S, H2D, A1, and A1 Mini.</p>
      </details>
      <details>
        <summary>Is it free to use?</summary>
        <p>Yes, the converter is completely free with no account or sign-up required.</p>
      </details>
      <details>
        <summary>Do I need to re-slice the file after conversion?</summary>
        <p>Yes. Open the converted <code>.3mf</code> in Snapmaker Orca, review the settings and re-slice before printing.</p>
      </details>
      <details>
        <summary>Can it handle more than 4 colours?</summary>
        <p>Yes. The U1 has 4 physical toolheads. For layer-based colour changes, enable <em>Insert filament swap pauses</em> in settings. For painted models, colour assignment is handled at re-slice time in Snapmaker Orca. For more than 4 colours, a toolhead assignment step is shown after upload.</p>
      </details>
      <details>
        <summary>What happens to my uploaded files?</summary>
        <p>Files are temporarily stored for processing and download. See the <a href="/privacy.html">Privacy Policy</a> for details.</p>
      </details>
      <details>
        <summary>What is the maximum file size?</summary>
        <p>300 MB.</p>
      </details>
    </div>
  </section>

  <!-- General + Feedback -->
  <section class="card card-padded">
    <h2>General</h2>
    <ul>
      <li>Download your file before leaving — files are removed shortly after conversion.</li>
      <li>Maximum upload size: 300 MB.</li>
      <li>Upload a <code>.3mf</code> project file, then review the converted settings and re-slice in Snapmaker Orca before printing.</li>
      <li>Sliced <code>.gcode.3mf</code> files are not supported when they contain no editable model geometry. Upload the original project <code>.3mf</code> instead.</li>
    </ul>
    <h3>Something not working?</h3>
    <p>
      If Snapmaker Orca reports G-code outside the plate, this is usually a
      slicer issue. Try disabling the prime tower, slicing once, then enabling
      it again. If it still fails, move the model slightly on the plate and
      slice again.
    </p>
    <p>
      Use the <strong>feedback button</strong> in the bottom-right corner. A short
      description is enough — leave an email if you'd like a follow-up.
    </p>
  </section>

</div>

<style>
  .help { display: flex; flex-direction: column; gap: 16px; }

  h2 { margin: 0 0 10px; font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
  h3 { margin: 14px 0 6px; font-size: 13px; font-weight: 600; color: var(--text-muted); }
  p { margin: 0 0 10px; font-size: 13.5px; line-height: 1.6; }
  p:last-child { margin-bottom: 0; }
  ul { margin: 0; padding-left: 20px; font-size: 13.5px; line-height: 1.7; }
  code { font-family: var(--font-mono); font-size: 12px; background: var(--bg-raised); padding: 1px 5px; border-radius: 3px; }

  /* Workflow strip */
  .workflow-card h2 { margin-bottom: 16px; }
  .steps {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    flex-wrap: wrap;
  }
  .step {
    flex: 1;
    min-width: 130px;
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }
  .step-num {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: color-mix(in srgb, #b45309 20%, transparent);
    border: 1px solid color-mix(in srgb, #b45309 40%, transparent);
    color: #b45309;
    font-size: 12px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-top: 1px;
  }
  .step-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 3px;
  }
  .step-desc {
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.5;
  }
  .step-arrow {
    color: color-mix(in srgb, #b45309 60%, transparent);
    font-size: 18px;
    margin-top: 4px;
    flex-shrink: 0;
    align-self: flex-start;
  }

  /* Multi-colour grid */
  .colour-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-top: 12px;
  }
  .colour-card {
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px;
  }
  .colour-card-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .colour-icon {
    color: #b45309;
    font-size: 14px;
  }
  .colour-card p { font-size: 13px; }
  .tip { color: var(--text-muted); font-size: 12px !important; }

  /* Table */
  table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 4px; }
  th { text-align: left; font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em; color: var(--text-subtle); padding: 6px 8px 6px 0; border-bottom: 1px solid var(--border); }
  td { padding: 7px 8px 7px 0; border-bottom: 1px solid color-mix(in srgb, var(--border) 50%, transparent); }

  .badge { display: inline-block; font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 999px; letter-spacing: 0.02em; vertical-align: middle; }
  .badge.ok { background: color-mix(in srgb, var(--success) 15%, transparent); color: var(--success); }
  .badge.beta { background: color-mix(in srgb, var(--accent) 15%, transparent); color: var(--accent); }

  /* FAQ accordion */
  .faq { display: flex; flex-direction: column; gap: 4px; }
  details { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
  details[open] { background: var(--bg-raised); }
  summary { font-size: 13.5px; font-weight: 500; padding: 10px 12px; cursor: pointer; list-style: none; display: flex; justify-content: space-between; align-items: center; }
  summary::-webkit-details-marker { display: none; }
  summary::after { content: '+'; color: var(--text-muted); font-size: 16px; font-weight: 400; flex-shrink: 0; margin-left: 12px; }
  details[open] summary::after { content: '−'; }
  details p { margin: 0; padding: 0 12px 12px; font-size: 13px; color: var(--text-muted); line-height: 1.6; }

  @media (max-width: 600px) {
    .colour-grid { grid-template-columns: 1fr; }
    .steps { flex-direction: column; }
    .step-arrow { transform: rotate(90deg); align-self: center; }
  }
</style>
