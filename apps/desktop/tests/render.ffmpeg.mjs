import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const FIX = fileURLToPath(new URL('./fixtures/sample.mp4', import.meta.url));
const OUT = fileURLToPath(new URL('./fixtures/render_out.mp4', import.meta.url));
const project = JSON.parse(readFileSync(OUT + '.json', 'utf8'));

const W = 1920, H = 1080;
const videoClip = project.tracks.find(t => t.kind === 'video').clips[0];
const audioClip = project.tracks.find(t => t.kind === 'audio').clips[0];

const inputs = [];
inputs.push('-ss', String(videoClip.inPoint), '-i', FIX);
inputs.push('-ss', String(audioClip.inPoint), '-i', FIX);

const filter =
  `[0:v]scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2,setsar=1[vout];` +
  `[1:a]aformat=sample_fmts=fltp,aresample=44100[aout]`;

const args = [
  '-y', ...inputs,
  '-filter_complex', filter,
  '-map', '[vout]', '-map', '[aout]',
  '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
  '-c:a', 'aac', '-b:a', '192k',
  '-t', String(Math.min(videoClip.duration, 8)),
  '-movflags', '+faststart', OUT,
];

console.log('ffmpeg', args.join(' '));
execFileSync('ffmpeg', args, { stdio: 'inherit' });
console.log('WROTE', OUT);
