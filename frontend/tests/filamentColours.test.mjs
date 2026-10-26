import assert from 'node:assert/strict';
import test from 'node:test';
import { filamentBackground } from '../src/lib/filamentColours.ts';

test('a two-color filament has equally sized solid bands', () => {
  assert.equal(filamentBackground({
    colour: '#112233', colours: ['#112233', '#445566'], colour_mode: 'split',
  }), 'linear-gradient(135deg, #112233 0%, #112233 50%, #445566 50%, #445566 100%)');
});

test('a gradient includes all colors in palette order', () => {
  assert.equal(filamentBackground({
    colour: '#112233', colours: ['#112233', '#445566', '#778899'], colour_mode: 'gradient',
  }), 'linear-gradient(135deg, #112233, #445566, #778899)');
});

test('plain filaments and older API responses remain solid', () => {
  assert.equal(filamentBackground({ colour: '#112233' }), '#112233');
  assert.equal(filamentBackground({ colour: '#112233', colours: ['#445566'] }), '#445566');
  assert.equal(filamentBackground({ colour: null }), '#888888');
});

test('unknown modes use split bands and invalid CSS colors are discarded', () => {
  assert.equal(filamentBackground({
    colour: '#112233', colours: ['url(https://example.invalid/image)', '#112233', '#445566'],
  }), 'linear-gradient(135deg, #112233 0%, #112233 50%, #445566 50%, #445566 100%)');
  assert.equal(filamentBackground({ colour: 'url(https://example.invalid/image)' }), '#888888');
});
