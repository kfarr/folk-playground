// End-to-end test of the phone table, no phone or camera required: synthesize
// "photos" of a table with real tag36h11 tags on it (gen.html), feed them to
// camera.html?img= through the real server.py, and assert on the card positions
// that would reach Folk via /tmp/browser-table-cards.json.
//
//   cd browser-table/test && npm i playwright-core && node test.mjs
//
// Needs a Chromium; set CHROME=/path/to/chrome if playwright-core can't find one.
import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import https from 'node:https';

const TESTDIR = path.dirname(new URL(import.meta.url).pathname);
const REPO = path.resolve(TESTDIR, '../..');
const OUT = path.join(TESTDIR, 'out');
const CARDS = '/tmp/browser-table-cards.json';
const SCENE = '/tmp/browser-table-scene.json';
fs.mkdirSync(OUT, { recursive: true });

let CHROME = process.env.CHROME;
if (!CHROME) { try { CHROME = chromium.executablePath(); } catch (e) {} }

let failures = 0;
function check(name, ok, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!ok) failures++;
}
const near = (a, b, tol) => Math.abs(a - b) <= tol;
const nearAngle = (a, b, tol) => Math.abs(((a - b + 540) % 360) - 180) <= tol;

function parseCards(txt) {
  const out = {};
  for (const m of txt.matchAll(/\{(\w+) ([\d.eE+-]+) ([\d.eE+-]+) ([\d.eE+-]+)\}/g))
    out[m[1]] = { x: +m[2], y: +m[3], angle: +m[4] };
  return out;
}
async function waitCards(pred, ms = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try {
      const c = parseCards(fs.readFileSync(CARDS, 'utf8'));
      if (pred(c)) return c;
    } catch (e) {}
    await new Promise(r => setTimeout(r, 200));
  }
  try { return parseCards(fs.readFileSync(CARDS, 'utf8')); } catch (e) { return {}; }
}

function startServer(port, testImg) {
  const p = spawn('python3', [path.join(REPO, 'browser-table/server.py')], {
    env: { ...process.env, PORT: String(port), HOST: '127.0.0.1',
           FOLK_TABLE: path.join(REPO, 'folkville/browser-table.tcl'),
           BROWSER_TABLE_TEST_IMG: testImg },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  p.stdout.on('data', d => process.stdout.write('  [server] ' + d));
  p.stderr.on('data', d => process.stdout.write('  [server!] ' + d));
  return p;
}

const browser = await chromium.launch({ executablePath: CHROME });

// ---- synthesize the two test photos ---------------------------------------
const gen = await browser.newPage();
await gen.goto('file://' + path.join(TESTDIR, 'gen.html'));
const CAL_BASE = await gen.evaluate(() => window.CAL_BASE);

// photo 1: straight-down view, uncalibrated mapping. display 1200x760 fits a
// 1600x1200 frame with k=4/3, offX=0, offY=93.333: cam = (x*k, y*k+93.333)
const K = 4 / 3, OY = (1200 - 760 * K) / 2;
const straight = [
  { id: 0, d: [300, 200], angle: 0 },     // bulldozer
  { id: 1, d: [600, 400], angle: 90 },    // paver
  { id: 2, d: [900, 600], angle: 225 },   // crane
];
const url1 = await gen.evaluate(({ tags }) => window.gen(1600, 1200, tags), {
  tags: straight.map(t => ({ id: t.id, x: t.d[0] * K, y: t.d[1] * K + OY, size: 110, angle: t.angle })),
});
fs.writeFileSync(path.join(OUT, 'test1.png'), Buffer.from(url1.split(',')[1], 'base64'));

// photo 2: the whole table rotated 10° and scaled 0.55 in frame — only a
// calibration homography can undo this. Corner tags sit AT the display corners.
const TH = 10 * Math.PI / 180, S = 0.55, TX = 350, TY = 250;
const warp = (x, y) => ({
  x: (x * Math.cos(TH) - y * Math.sin(TH)) * S + TX,
  y: (x * Math.sin(TH) + y * Math.cos(TH)) * S + TY,
});
const cornerPts = [[0, 0], [1200, 0], [1200, 760], [0, 760]];
const warpedTags = cornerPts.map(([x, y], i) =>
  ({ id: CAL_BASE + i, ...warp(x, y), size: 80, angle: 10 }));
warpedTags.push({ id: 1, ...warp(600, 380), size: 80, angle: 30 + 10 });   // paver @ display (600,380) 30°
const url2 = await gen.evaluate(({ tags }) => window.gen(1600, 1200, tags), { tags: warpedTags });
fs.writeFileSync(path.join(OUT, 'test2.png'), Buffer.from(url2.split(',')[1], 'base64'));
await gen.close();
console.log('synthesized test1.png (straight) and test2.png (warped + corner tags)');

// ---- scenario A: uncalibrated straight-down view ---------------------------
fs.rmSync(CARDS, { force: true });
fs.writeFileSync(SCENE, JSON.stringify({ items: [
  { t: 'line', pts: [[300, 200], [600, 400], [900, 600]], w: 34, color: '#8a8578' },
  { t: 'line', pts: [[300, 200], [600, 400], [900, 600]], w: 4, color: '#e8e2cf' },
  { t: 'circle', c: [[600, 400]], r: 26, thickness: 3, color: '#8fd6a8' },
  { t: 'text', x: 60, y: 60, text: 'folkville', color: '#8fd6a8', scale: 24 },
] }));
const s1 = startServer(4380, path.join(OUT, 'test1.png'));
await new Promise(r => setTimeout(r, 800));

const ctxA = await browser.newContext({ viewport: { width: 1000, height: 750 } });
const pageA = await ctxA.newPage();
pageA.on('pageerror', e => console.log('  [pageerror]', e.message));
await pageA.goto('http://127.0.0.1:4380/camera?img=/test.png');

const cardsA = await waitCards(c => c.bulldozer && c.paver && c.crane);
check('A: all three cards detected', !!(cardsA.bulldozer && cardsA.paver && cardsA.crane),
      JSON.stringify(cardsA));
for (const t of straight) {
  const kind = ['bulldozer', 'paver', 'crane'][t.id];
  const c = cardsA[kind];
  if (!c) continue;
  check(`A: ${kind} position ≈ (${t.d[0]},${t.d[1]})`,
        near(c.x, t.d[0], 6) && near(c.y, t.d[1], 6), `got (${c.x},${c.y})`);
  check(`A: ${kind} angle ≈ ${t.angle}°`, nearAngle(c.angle, t.angle, 5), `got ${c.angle}°`);
}
await new Promise(r => setTimeout(r, 400));
await pageA.screenshot({ path: path.join(OUT, 'phone-screenshot.png') });

// tags page renders every card + the four corners
const pageT = await ctxA.newPage();
await pageT.goto('http://127.0.0.1:4380/tags');
await pageT.waitForFunction(() => document.querySelectorAll('svg').length >= 8, null, { timeout: 5000 })
  .catch(() => {});
const nsvg = await pageT.evaluate(() => document.querySelectorAll('svg').length);
check('tags page renders 4 cards + 4 corners', nsvg === 8, `${nsvg} svgs`);

// HTTPS side (the origin the phone actually uses)
const httpsOk = await new Promise(res => {
  https.get('https://127.0.0.1:4381/table.json', { rejectUnauthorized: false },
    r => res(r.statusCode === 200)).on('error', () => res(false));
});
check('HTTPS serves on PORT+1 with self-signed cert', httpsOk);
await ctxA.close();
s1.kill();

// ---- scenario B: keystoned view, folk-style corner-tag calibration ---------
fs.rmSync(CARDS, { force: true });
fs.writeFileSync(SCENE, '{"items":[]}');
const s2 = startServer(4390, path.join(OUT, 'test2.png'));
await new Promise(r => setTimeout(r, 800));

const ctxB = await browser.newContext({ viewport: { width: 1000, height: 750 } });
const pageB = await ctxB.newPage();
pageB.on('pageerror', e => console.log('  [pageerror]', e.message));
await pageB.goto('http://127.0.0.1:4390/camera?img=/test.png');
await pageB.waitForFunction(() => window.PHONE && window.PHONE.state.srcW > 0);

// uncalibrated, the warped paver lands far from (600,380) — prove it, then calibrate
const before = await waitCards(c => c.paver);
check('B: uncalibrated position is wrong (as expected)',
      before.paver && !(near(before.paver.x, 600, 20) && near(before.paver.y, 380, 20)),
      JSON.stringify(before.paver));
await pageB.evaluate(() => window.PHONE.startCal());
await pageB.waitForFunction(() =>
  !document.getElementById('clearcal').classList.contains('hidden'), null, { timeout: 15000 });
fs.rmSync(CARDS, { force: true });
const after = await waitCards(c => c.paver && near(c.paver.x, 600, 8));
check('B: calibrated paver position ≈ (600,380)',
      after.paver && near(after.paver.x, 600, 8) && near(after.paver.y, 380, 8),
      JSON.stringify(after.paver));
check('B: calibrated paver angle ≈ 30° (10° keystone removed)',
      after.paver && nearAngle(after.paver.angle, 30, 5), `got ${after.paver?.angle}°`);
await ctxB.close();
s2.kill();

await browser.close();
console.log(failures ? `\n${failures} FAILURES` : '\nall tests passed');
process.exit(failures ? 1 : 0);
