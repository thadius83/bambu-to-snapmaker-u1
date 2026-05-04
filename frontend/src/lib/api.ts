// API client — thin wrapper around /api/* endpoints.
// Everything returns Promises; callers handle errors.

export interface ProfileDescriptor {
  id: string;
  display_name: string;
  path: string;
  source: 'bundled' | 'user';
  layer_height: string | null;
  printer_variant: string | null;
}

export interface RuleSummary {
  name: string;
  file_key: string;
  description: string;
  enabled: boolean;
  priority: number;
  match: Record<string, unknown>;
  overrides: Record<string, unknown>;
  source_path: string | null;
}

export interface DiffSection {
  title: string;
  summary: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  details: any[];
}

export interface DiffPayload {
  report: {
    source_filename: string;
    output_filename: string;
    reference_profile: string;
    identity_swaps: Array<{ key: string; from_value: unknown; to_value: unknown }>;
    gcode_swaps: Array<{ key: string; from_bytes: number; to_bytes: number }>;
    keys_dropped: Array<{ key: string; reason: string }>;
    values_clamped: Array<{ key: string; from_value: unknown; to_value: unknown; ceiling: unknown }>;
    rules_matched: Array<{ rule_name: string; priority: number; matched_on: Record<string, unknown>; overrides_applied: Record<string, unknown> }>;
    slot_remaps: Array<{ from_index: number; to_index: number; filament_id: string | null }>;
    slice_artifacts_stripped: string[];
    advanced_overrides_applied: Record<string, unknown>;
    swap_instructions: SwapInstruction[];
    swap_pauses_skipped_painted: boolean;
  };
  sections: DiffSection[];
  counts: Record<string, number>;
}

export interface ConvertResult {
  job_id: string;
  download_name: string;
  diff: DiffPayload;
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string;
    try {
      const body = await response.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      detail = await response.text();
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export async function listProfiles(): Promise<ProfileDescriptor[]> {
  return handle(await fetch('/api/profiles'));
}

export interface FilamentInfo {
  index: number;
  settings_id: string | null;
  filament_type: string | null;
  vendor: string | null;
  colour: string | null;
}

export async function suggestProfile(
  file: File,
): Promise<{ profile_id: string; display_name: string; source_printer: string; already_converted: boolean; filaments: FilamentInfo[]; is_painted_model: boolean; is_multiplate: boolean; is_oversized: boolean; matched_on: Record<string, unknown> }> {
  const form = new FormData();
  form.append('file', file);
  return handle(await fetch('/api/suggest-profile', { method: 'POST', body: form }));
}

export async function listRules(): Promise<RuleSummary[]> {
  return handle(await fetch('/api/rules'));
}

export async function getRuleYaml(name: string): Promise<{ name: string; yaml_text: string }> {
  return handle(await fetch(`/api/rules/${encodeURIComponent(name)}`));
}

export async function putRule(name: string, yamlText: string): Promise<unknown> {
  return handle(
    await fetch(`/api/rules/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaml_text: yamlText }),
    }),
  );
}

export async function createRule(yamlText: string): Promise<{ name: string }> {
  return handle(
    await fetch('/api/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaml_text: yamlText }),
    }),
  );
}

export async function deleteRule(name: string): Promise<unknown> {
  return handle(
    await fetch(`/api/rules/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  );
}

export async function testMatch(file: File): Promise<unknown> {
  const form = new FormData();
  form.append('file', file);
  return handle(
    await fetch('/api/rules/test-match', { method: 'POST', body: form }),
  );
}

export interface SwapInstruction {
  z: number;
  toolhead: number;
  from_slot: number;
  to_slot: number;
  from_colour: string;
  to_colour: string;
  label: string;
}

export interface ConvertOptions {
  file: File;
  reference_profile: string;
  apply_rules: boolean;
  clamp_speeds: boolean;
  preserve_color_painting: boolean;
  advanced_overrides: string;
  slot_map?: Record<number, number>;
  insert_swap_pauses: boolean;
}

export async function convert(opts: ConvertOptions): Promise<ConvertResult> {
  const form = new FormData();
  form.append('file', opts.file);
  form.append('reference_profile', opts.reference_profile);
  form.append('apply_rules', String(opts.apply_rules));
  form.append('clamp_speeds', String(opts.clamp_speeds));
  form.append('preserve_color_painting', String(opts.preserve_color_painting));
  form.append('advanced_overrides', opts.advanced_overrides);
  form.append('slot_map', JSON.stringify(opts.slot_map ?? {}));
  form.append('insert_swap_pauses', String(opts.insert_swap_pauses));
  return handle(await fetch('/api/convert', { method: 'POST', body: form }));
}

export async function listBambuPrinters(): Promise<Array<{id: string; name: string}>> {
  return handle(await fetch('/api/bambu-profiles'));
}

export async function convertBambu(opts: { file: File; reference_profile: string; clamp_speeds: boolean; insert_swap_pauses: boolean }): Promise<ConvertResult> {
  const form = new FormData();
  form.append('file', opts.file);
  form.append('reference_profile', opts.reference_profile);
  form.append('clamp_speeds', String(opts.clamp_speeds));
  form.append('insert_swap_pauses', String(opts.insert_swap_pauses));
  return handle(await fetch('/api/convert-bambu', { method: 'POST', body: form }));
}

export function downloadUrl(jobId: string): string {
  return `/api/download/${encodeURIComponent(jobId)}`;
}
