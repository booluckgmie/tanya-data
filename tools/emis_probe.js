#!/usr/bin/env node
/**
 * Probe an interactive map/dashboard page: list its controls, click what you name, and record every
 * network call and download, so the data endpoint behind the page can be found.
 *
 * Built for https://emisonline.moe.gov.my/risalahmap/ (Ministry of Education EMIS), which cannot be
 * reached from the cloud sandbox. Run it from a network that can open the page:
 *
 *   npm i playwright && npx playwright install chromium
 *   node tools/emis_probe.js --url https://emisonline.moe.gov.my/risalahmap/ --out emis_out
 *   node tools/emis_probe.js --url ... --out emis_out --click "Table" --click "Download"
 *   node tools/emis_probe.js --url ... --out emis_out --headed      # watch it, then add --click steps
 *
 * It writes to --out: controls.json (clickable things whose text looks like table/download/export),
 * network.json (every XHR/fetch with URL, method, status, type, size), responses/ (JSON and CSV bodies,
 * first 2 MB), downloads/ (files the page offered), and a screenshot after each step.
 * Share network.json and controls.json: the data endpoint is usually the biggest JSON response.
 * It only observes and clicks what you name. It does not log in, solve captchas or change anything.
 */
const fs = require('fs'), path = require('path');
const { chromium } = require('playwright');

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : d; };
const clicks = args.flatMap((a, i) => (a === '--click' ? [args[i + 1]] : []));
const url = opt('url'), out = opt('out', 'probe_out'), headed = args.includes('--headed');
if (!url) { console.error('usage: node emis_probe.js --url <page> [--out dir] [--click "text" ...] [--headed]'); process.exit(2); }
for (const d of ['responses', 'downloads']) fs.mkdirSync(path.join(out, d), { recursive: true });

const WANT = /table|jadual|senarai|list|download|muat\s*turun|export|eksport|excel|xls|csv|data|paparan|view/i;
const net = [];
let n = 0;

(async () => {
  const browser = await chromium.launch({ headless: !headed });
  const ctx = await browser.newContext({ acceptDownloads: true, viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();
  page.on('response', async (r) => {
    const req = r.request();
    if (!['xhr', 'fetch', 'document'].includes(req.resourceType())) return;
    const type = (r.headers()['content-type'] || '').split(';')[0];
    let size = null, saved = null;
    try {
      const body = await r.body();
      size = body.length;
      if (/json|csv|xml|text\/plain/.test(type) && size > 0) {
        saved = `responses/${String(++n).padStart(3, '0')}_${req.method()}.${type.includes('csv') ? 'csv' : type.includes('json') ? 'json' : 'txt'}`;
        fs.writeFileSync(path.join(out, saved), body.subarray(0, 2 * 1024 * 1024));
      }
    } catch (e) { /* redirects and aborted requests have no body */ }
    net.push({ url: req.url(), method: req.method(), status: r.status(), type, size, saved, postData: req.postData() ? req.postData().slice(0, 500) : null });
  });
  page.on('download', async (d) => {
    const dest = path.join(out, 'downloads', d.suggestedFilename());
    await d.saveAs(dest);
    console.log('download saved:', dest);
  });

  await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
  await page.screenshot({ path: path.join(out, 'step0_loaded.png'), fullPage: true });

  const controls = await page.evaluate((src) => {
    const re = new RegExp(src, 'i');
    return [...document.querySelectorAll('a,button,[role=button],[role=tab],li,label,input[type=button],input[type=submit],.btn,.tab')]
      .map((e) => ({ tag: e.tagName.toLowerCase(), text: (e.innerText || e.value || e.title || e.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 80), href: e.href || null, id: e.id || null, cls: (e.className && e.className.toString().slice(0, 60)) || null }))
      .filter((c) => c.text && re.test(c.text + ' ' + (c.href || '')));
  }, WANT.source);
  fs.writeFileSync(path.join(out, 'controls.json'), JSON.stringify(controls, null, 1));
  console.log('controls that look relevant:', controls.length);
  controls.slice(0, 25).forEach((c) => console.log('  -', c.tag, JSON.stringify(c.text), c.href || ''));

  let step = 0;
  for (const text of clicks) {
    step++;
    const target = page.getByText(text, { exact: false }).first();
    try {
      await target.click({ timeout: 15000 });
      await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
      console.log(`step ${step}: clicked "${text}"`);
    } catch (e) { console.log(`step ${step}: could not click "${text}": ${e.message.split('\n')[0]}`); }
    await page.screenshot({ path: path.join(out, `step${step}_${text.replace(/\W+/g, '_').slice(0, 20)}.png`), fullPage: true });
    const tables = await page.$$eval('table', (ts) => ts.map((t) => ({ rows: t.rows.length, cols: t.rows[0] ? t.rows[0].cells.length : 0, head: [...(t.rows[0] ? t.rows[0].cells : [])].map((c) => c.innerText.trim()).slice(0, 12) })));
    if (tables.length) { console.log('  tables on page:', JSON.stringify(tables.slice(0, 5))); fs.writeFileSync(path.join(out, `step${step}_tables.json`), JSON.stringify(tables, null, 1)); }
  }
  fs.writeFileSync(path.join(out, 'network.json'), JSON.stringify(net, null, 1));
  const big = net.filter((x) => x.saved).sort((a, b) => b.size - a.size).slice(0, 5);
  console.log('largest data responses:'); big.forEach((x) => console.log(' ', x.size, x.method, x.url.slice(0, 110)));
  await browser.close();
})().catch((e) => { console.error('probe failed:', e.message.split('\n')[0]); process.exit(1); });
