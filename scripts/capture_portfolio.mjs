// Reproduce public screenshots from the already-redacted, committed demo.
// Requires ffmpeg. Never opens a browser or accesses customer accounts.
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const directory = resolve(root, 'docs/assets/portfolio');
const manifest = JSON.parse(readFileSync(resolve(directory, 'frames.json'), 'utf8'));
if (process.argv.includes('--preview')) {
  const cuts = [[2, 1.5], [16.7, 2.5], [29, 2], [66.5, 2], [101.6, 2], [137, 2]];
  const labels = cuts.map((_, index) => `[input${index}]`).join('');
  const filters = [
    `[0:v]split=${cuts.length}${labels}`,
    ...cuts.map(([start, duration], index) =>
      `[input${index}]trim=start=${start}:duration=${duration},setpts=PTS-STARTPTS,fps=8,scale=960:540:flags=lanczos[cut${index}]`),
    `${cuts.map((_, index) => `[cut${index}]`).join('')}concat=n=${cuts.length}:v=1:a=0,split[preview][palette]`,
    '[palette]palettegen=stats_mode=diff[colors]',
    '[preview][colors]paletteuse=dither=bayer:bayer_scale=3[out]',
  ].join(';');
  const result = spawnSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-i', resolve(root, manifest.video), '-filter_complex', filters,
    '-map', '[out]', '-loop', '0', resolve(directory, 'demo-preview.gif'),
  ], { encoding: 'utf8' });
  if (result.error || result.status !== 0) throw new Error(result.error?.message || result.stderr);
  console.log('demo-preview.gif: short looping preview, not the complete demo');
  process.exit(0);
}
for (const frame of manifest.frames) {
  const result = spawnSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-ss', String(frame.seconds), '-i', resolve(root, manifest.video),
    '-frames:v', '1', '-update', '1', resolve(directory, frame.file),
  ], { encoding: 'utf8' });
  if (result.error || result.status !== 0) {
    throw new Error(result.error?.message || result.stderr || 'Frame extraction failed');
  }
  console.log(`${frame.file}: ${frame.purpose}`);
}
