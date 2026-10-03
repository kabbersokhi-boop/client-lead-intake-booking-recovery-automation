// Offline integrity checks for the public portfolio package. No account access.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const assetDir = resolve(root, 'docs/assets/portfolio');
const proof = JSON.parse(readFileSync(resolve(assetDir, 'verification.json'), 'utf8'));
const manifest = JSON.parse(readFileSync(resolve(assetDir, 'frames.json'), 'utf8'));
const withinRepo = (path) => {
  const target = resolve(root, path);
  const rel = relative(root, target);
  assert(!rel.startsWith('..') && !isAbsolute(rel), `Path leaves repository: ${path}`);
  return target;
};
assert.equal(manifest.video, proof.video.path);
const videoPath = withinRepo(proof.video.path);
const video = readFileSync(videoPath);
assert.equal(video.length, proof.video.bytes, 'Video size mismatch');
assert.equal(createHash('sha256').update(video).digest('hex'), proof.video.sha256, 'Video checksum mismatch');
assert.equal(video.subarray(4, 8).toString('ascii'), 'ftyp', 'Expected an MP4 container');
assert(video.length < 12 * 1024 * 1024, 'Keep the portfolio video lightweight');
const preview = readFileSync(resolve(assetDir, 'demo-preview.gif'));
assert.equal(preview.subarray(0, 6).toString('ascii'), 'GIF89a');
assert.equal(preview.readUInt16LE(6), 960);
assert.equal(preview.readUInt16LE(8), 540);
assert(preview.length < 5 * 1024 * 1024, 'Keep the README preview lightweight');

const frameNames = new Set();
for (const frame of manifest.frames) {
  assert(!frameNames.has(frame.file), `Duplicate frame: ${frame.file}`);
  frameNames.add(frame.file);
  assert(Number.isFinite(frame.seconds) && frame.seconds >= 0 && frame.seconds < proof.video.duration_seconds);
  const path = withinRepo(`docs/assets/portfolio/${frame.file}`);
  const png = readFileSync(path);
  assert.equal(png.subarray(0, 8).toString('hex'), '89504e470d0a1a0a', `Not PNG: ${frame.file}`);
  assert.equal(png.subarray(12, 16).toString('ascii'), 'IHDR');
  assert.equal(png.readUInt32BE(16), proof.video.width, `Width mismatch: ${frame.file}`);
  assert.equal(png.readUInt32BE(20), proof.video.height, `Height mismatch: ${frame.file}`);
}

const slug = (heading) => heading.toLowerCase().replace(/[^\p{L}\p{N}_\- ]/gu, '').replace(/ /g, '-');
for (const doc of ['README.md', 'docs/portfolio-demo.md']) {
  const text = readFileSync(resolve(root, doc), 'utf8');
  // These two documents use simple inline Markdown links without space-containing targets.
  for (const match of text.matchAll(/!?\[[^\]\n]*\]\(([^\s)]+)\)/g)) {
    const destination = match[1];
    if (/^(?:https?:|mailto:)/.test(destination)) continue;
    const [file, anchor] = destination.split('#');
    const target = file ? resolve(root, dirname(doc), decodeURIComponent(file)) : resolve(root, doc);
    withinRepo(relative(root, target));
    assert(existsSync(target), `${doc}: missing target ${destination}`);
    assert(statSync(target).isFile(), `${doc}: expected file ${destination}`);
    if (anchor) {
      const headings = [...readFileSync(target, 'utf8').matchAll(/^#{1,6} (.+)$/gm)].map((m) => slug(m[1]));
      assert(headings.includes(decodeURIComponent(anchor)), `${doc}: missing heading ${destination}`);
    }
  }
}

assert.equal(proof.n8n_executions.length, 4);
assert(proof.n8n_executions.every((execution) => execution.verified_status === 'success'));
assert.equal(proof.reporting.duplicate_report_rows, 0);
assert.notEqual(proof.reporting.first_generated_at, proof.reporting.refreshed_generated_at);
console.log(`Portfolio checks passed: ${manifest.frames.length} full-HD frames, video checksum, timing, and documentation links.`);
