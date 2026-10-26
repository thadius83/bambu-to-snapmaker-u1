import type { FilamentInfo } from './api';

type Palette = Pick<FilamentInfo, 'colour' | 'colours' | 'colour_mode'>;

function isHex(colour: unknown): colour is string {
  return typeof colour === 'string' && /^#(?:[\da-f]{3}|[\da-f]{4}|[\da-f]{6}|[\da-f]{8})$/i.test(colour);
}

export function filamentBackground(filament: Palette): string {
  const colours = (filament.colours ?? []).filter(isHex);
  if (colours.length === 0) return isHex(filament.colour) ? filament.colour : '#888888';
  if (colours.length === 1) return colours[0];
  const stops = filament.colour_mode === 'gradient'
    ? colours
    : colours.flatMap((colour, i) => [
        `${colour} ${i * 100 / colours.length}%`,
        `${colour} ${(i + 1) * 100 / colours.length}%`,
      ]);
  return `linear-gradient(135deg, ${stops.join(', ')})`;
}
