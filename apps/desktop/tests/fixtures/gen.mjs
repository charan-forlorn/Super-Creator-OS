import { execSync } from 'node:child_process';
const out = 'C:\\Workspace\\super-creator-os\\apps\\desktop\\tests\\fixtures\\sample.mp4';
const cmd = `ffmpeg -y -f lavfi -i testsrc=size=640x360:rate=30:duration=10 -f lavfi -i sine=frequency=440:duration=10 -c:v libx264 -pix_fmt yuv420p -preset ultrafast -c:a aac -b:a 128k -t 10 "${out}"`;
console.log('RUN', cmd);
execSync(cmd, { stdio: 'inherit' });
console.log('WROTE', out);
