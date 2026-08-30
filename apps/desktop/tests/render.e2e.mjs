import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const FIX = fileURLToPath(new URL('./fixtures/sample.mp4', import.meta.url));
const OUT = fileURLToPath(new URL('./fixtures/render_out.mp4', import.meta.url));
const project = {
  schemaVersion: 1,
  id: 'p-e2e', name: 'E2E', createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
  assets: [{ id: 'a1', name: 'sample.mp4', sourcePath: FIX, kind: 'video', durationSec: 10, width: 640, height: 360, fps: 30, hasAudio: true, createdAt: new Date().toISOString() }],
  tracks: [
    { id: 'tv', kind: 'video', clips: [{ id: 'c1', assetId: 'a1', inPoint: 1, duration: 4, start: 0, trackId: 'tv', transform: { scale: 1, x: 0, y: 0, opacity: 1 } }], captions: [] },
    { id: 'ta', kind: 'audio', clips: [{ id: 'c2', assetId: 'a1', inPoint: 1, duration: 4, start: 0, trackId: 'ta', transform: { scale: 1, x: 0, y: 0, opacity: 1 } }], captions: [] },
  ],
  durationSec: 4, aspectRatio: '1920x1080',
};
writeFileSync(OUT + '.json', JSON.stringify(project, null, 2));
console.log('project written');
