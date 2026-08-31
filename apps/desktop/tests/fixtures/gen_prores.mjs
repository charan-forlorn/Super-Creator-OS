import { execSync } from 'node:child_process';
// Deterministic ProRes/PCM source that REQUIRES a cached H.264/AAC proxy.
// Mirrors gen.mjs; used only by the S1 proxy-cache GUI gate (gitignored).
const out = 'C:\\Workspace\\super-creator-os\\apps\\desktop\\e2e\\fixtures\\sample_prores.mov';
const cmd = `ffmpeg -y -hide_banner -loglevel error -f lavfi -i testsrc=size=640x360:rate=30:duration=3 -f lavfi -i sine=frequency=440:duration=3 -c:v prores -c:a pcm_s16le -t 3 "${out}"`;
console.log('RUN', cmd);
execSync(cmd, { stdio: 'inherit' });
console.log('WROTE', out);
