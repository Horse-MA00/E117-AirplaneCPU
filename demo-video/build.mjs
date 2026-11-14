// node build.mjs tts | compose | render
//   tts      narration.json -> out/narration/*.wav + durations.json (local Kokoro via HyperFrames)
//   compose  out/timeline.json + frames -> out/project (screen.mp4, index.html, audio)
//   render   out/project -> out/uoption-demo.mp4
import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, 'out');
const NAR = path.join(OUT, 'narration');
const PROJECT = path.join(OUT, 'project');
const OUTRO_SECONDS = 3.2;
const FPS = 30;

const run = (cmd, args, opts = {}) => execFileSync(cmd, args, { stdio: 'inherit', ...opts });
const probe = file => Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file]).toString().trim());
const hyperframes = path.join(HERE, 'node_modules', '.bin', 'hyperframes');

function tts() {
  const { voice, speed, lines } = JSON.parse(fs.readFileSync(path.join(HERE, 'narration.json'), 'utf8'));
  fs.mkdirSync(NAR, { recursive: true });
  const env = { ...process.env };
  const venv = path.join(OUT, 'venv', 'bin', 'python');
  if (!env.HYPERFRAMES_PYTHON && fs.existsSync(venv)) env.HYPERFRAMES_PYTHON = venv;
  const durations = {};
  for (const line of lines) {
    const wav = path.join(NAR, `${line.id}.wav`), stamp = wav + '.sha256';
    const hash = crypto.createHash('sha256').update(JSON.stringify([voice, speed, line.say])).digest('hex');
    if (!fs.existsSync(wav) || !fs.existsSync(stamp) || fs.readFileSync(stamp, 'utf8') !== hash) {
      run(hyperframes, ['tts', line.say, '-v', voice, '-s', String(speed), '-o', wav], { env });
      fs.writeFileSync(stamp, hash);
    }
    durations[line.id] = +probe(wav).toFixed(3);
  }
  fs.writeFileSync(path.join(NAR, 'durations.json'), JSON.stringify(durations, null, 1));
  console.log(durations);
}

function compose() {
  const timeline = JSON.parse(fs.readFileSync(path.join(OUT, 'timeline.json'), 'utf8'));
  const { lines } = JSON.parse(fs.readFileSync(path.join(HERE, 'narration.json'), 'utf8'));
  const outro = timeline.events.find(e => e.type === 'outro');
  const total = +((outro ? outro.t : timeline.end) + OUTRO_SECONDS).toFixed(3);
  fs.rmSync(PROJECT, { recursive: true, force: true });
  fs.mkdirSync(path.join(PROJECT, 'audio'), { recursive: true });

  // Screen recording: each screencast frame lasts until the next one.
  const frames = timeline.frames.filter((f, i, all) => i === all.length - 1 || all[i + 1].t > f.t);
  const list = [];
  frames.forEach((f, i) => {
    const start = i === 0 ? 0 : f.t, next = i + 1 < frames.length ? frames[i + 1].t : total;
    list.push(`file '${path.join(OUT, 'frames', f.file)}'`, `duration ${Math.max(0.001, next - start).toFixed(4)}`);
  });
  list.push(`file '${path.join(OUT, 'frames', frames.at(-1).file)}'`);
  fs.writeFileSync(path.join(OUT, 'frames.txt'), list.join('\n'));
  const { width, height, dsf } = timeline.size;
  run('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', path.join(OUT, 'frames.txt'),
    '-vf', `scale=${width * dsf}:${height * dsf}:flags=lanczos,fps=${FPS},format=yuv420p`, '-t', String(total),
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '14', path.join(PROJECT, 'screen.mp4')]);

  // Audio: narration, a soft click per click, optional music.
  const audio = [];
  for (const e of timeline.events.filter(e => e.type === 'line')) {
    fs.copyFileSync(path.join(NAR, `${e.id}.wav`), path.join(PROJECT, 'audio', `${e.id}.wav`));
    audio.push({ src: `audio/${e.id}.wav`, start: e.t, duration: timeline.durations[e.id], volume: 1 });
  }
  run('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'anoisesrc=d=0.035:c=pink:a=0.5', '-f', 'lavfi', '-i', 'sine=f=1800:d=0.035',
    '-filter_complex', '[0][1]amix=inputs=2,highpass=f=900,afade=t=out:st=0:d=0.035', '-ar', '48000', path.join(PROJECT, 'audio', 'click.wav')]);
  for (const e of timeline.events.filter(e => e.type === 'click')) audio.push({ src: 'audio/click.wav', start: e.t, duration: 0.05, volume: 0.35 });
  const music = ['mp3', 'wav', 'm4a'].map(ext => path.join(HERE, 'assets', `music.${ext}`)).find(f => fs.existsSync(f));
  if (music) {
    fs.copyFileSync(music, path.join(PROJECT, 'audio', path.basename(music)));
    audio.push({ src: `audio/${path.basename(music)}`, start: 0, duration: total, volume: 0.12, fadeIn: 1, fadeOut: 2.5 });
  }

  const captions = Object.fromEntries(lines.map(l => [l.id, l.caption]));
  const data = { ...timeline, frames: undefined, total, captions };
  const media = [
    `<video id="screen" class="clip" src="screen.mp4" muted playsinline data-start="0" data-duration="${total}" data-track-index="0"></video>`,
    ...audio.map((a, i) => `<audio id="audio-${i + 1}" data-start="${a.start}" data-duration="${a.duration}" data-track-index="${i + 1}" data-volume="${a.volume}"` +
      `${a.fadeIn ? ` data-fade-in="${a.fadeIn}"` : ''}${a.fadeOut ? ` data-fade-out="${a.fadeOut}"` : ''} src="${a.src}"></audio>`),
  ].join('\n      ');
  const html = fs.readFileSync(path.join(HERE, 'composition', 'template.html'), 'utf8')
    .replaceAll('{{TOTAL}}', String(total))
    .replace('{{MEDIA}}', media)
    .replace('{{TIMELINE}}', JSON.stringify(data).replaceAll('<', '\\u003c'));
  fs.writeFileSync(path.join(PROJECT, 'index.html'), html);
  fs.copyFileSync(path.join(HERE, 'node_modules', 'gsap', 'dist', 'gsap.min.js'), path.join(PROJECT, 'gsap.min.js'));
  console.log(`composition ready: ${total} s, ${frames.length} frames, ${audio.length} audio clips${music ? '' : ' (no music: add assets/music.mp3)'}`);
}

function render() {
  const output = path.join(OUT, 'uoption-demo.mp4');
  run(hyperframes, ['render', PROJECT, '-o', output, '--fps', String(FPS), '--quality', 'delivery', '--video-frame-format', 'jpg']);
  console.log(`rendered ${output}`);
}

const steps = { tts, compose, render };
const step = steps[process.argv[2]];
if (!step) { console.error('usage: node build.mjs tts|compose|render'); process.exit(1); }
step();
