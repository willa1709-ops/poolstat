const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const config = JSON.parse(fs.readFileSync('config/pools.json'));
const remote = process.env.SITE_URL;
const clock = new Date().toISOString();
const fixture = process.env.DATA_FILE ? JSON.parse(fs.readFileSync(process.env.DATA_FILE)) : {generated_at: clock, timezone:'Europe/Prague', pools: config};
function expected(p) {
  const out = [];
  if (p.updates_url) out.push([p.updates_label || 'Aktuality', p.updates_url]);
  if (!p.updates_url || p.updates_url !== p.source_url) out.push(['Oficiální zdroj', p.source_url]);
  if (p.lane_source_url) out.push([p.lane_source_label || 'Rozpis drah', p.lane_source_url]);
  return out.map(([text, href]) => ({text: text + ' ↗', href: new URL(href).href}));
}
(async () => {
  let server, browser;
  try {
    if (!remote) {
      server = http.createServer((req,res) => {
        const filename = new URL(req.url, 'http://localhost').pathname;
        if (filename === '/data/pools.json') {res.setHeader('Content-Type','application/json');res.end(JSON.stringify(fixture));return;}
        const file = path.join(process.cwd(), filename === '/' ? 'index.html' : filename);
        if (!file.startsWith(process.cwd() + path.sep)) {res.writeHead(403).end();return;}
        try {res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));}
        catch {res.writeHead(404).end();}
      });
      await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    }
    browser = await chromium.launch({headless:true, ...(process.env.CHROMIUM_EXECUTABLE_PATH ? {executablePath:process.env.CHROMIUM_EXECUTABLE_PATH} : {})});
    const page = await browser.newPage();
    const errors = []; page.on('pageerror', error=>errors.push(error.message));
    const base = remote || 'http://127.0.0.1:' + server.address().port + '/';
    const response = await page.goto(base);
    assert.equal(response.status(),200);
    if (remote) {
      const dataUrl = new URL('data/pools.json',base);
      dataUrl.searchParams.set('ts', String(Date.now()));
      const payloadResponse = await page.request.get(dataUrl.href);
      assert.ok(payloadResponse.ok());
      const payload = await payloadResponse.json();
      const age = Date.now() - Date.parse(payload.generated_at);
      assert.ok(Number.isFinite(age) && age >= -300000 && age < 30*3600000, 'Published data must be fresh');
      if (process.env.EXPECTED_GENERATED_AT) {
        assert.equal(payload.generated_at, process.env.EXPECTED_GENERATED_AT, 'Pages must serve this workflow\'s validated snapshot');
      }
      assert.deepEqual(payload.pools.map(p=>p.id).sort(),config.map(p=>p.id).sort());
    }
    await page.locator('#grid .card').nth(config.length-1).waitFor();
    assert.equal(await page.locator('#grid .card').count(), config.length);
    for (const tab of ['Dnes','Zítra']) {
      await page.getByRole('tab',{name:tab,exact:true}).click();
      for (const p of config) {
        const card = page.locator('#grid .card').filter({has:page.getByRole('heading',{name:p.name,exact:true})}).filter({hasText:p.city});
        assert.equal(await card.count(),1,p.id);
        const links = await card.locator('.links a').evaluateAll(nodes=>nodes.map(a=>({text:a.textContent,href:a.href})));
        assert.deepEqual(links,expected(p),p.id + ' ' + tab);
      }
    }
    if (!remote) {
      const variants = [
        {id:'a',name:'No optional links',source_url:'https://example.org/'},
        {id:'b',name:'Same URL',source_url:'https://example.org/',updates_url:'https://example.org/'},
        {id:'c',name:'Different URL',source_url:'https://example.org/',updates_url:'https://example.org/news',lane_source_url:'https://example.org/lanes'}
      ];
      await page.route('**/data/pools.json*',route=>route.fulfill({json:{...fixture,pools:variants}}));
      await page.getByRole('button',{name:'Načíst znovu'}).click();
      await page.getByRole('heading',{name:'Different URL',exact:true}).waitFor();
      for (const p of variants) {
        const links = await page.locator('.card').filter({hasText:p.name}).locator('.links a').evaluateAll(nodes=>nodes.map(a=>({text:a.textContent,href:a.href})));
        assert.deepEqual(links,expected(p));
      }
    }
    if (!remote) {
      const uncertain = {...config[0], name:'Uncertain hours', hours_uncertain:true, date:new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Prague'}).format(new Date()), warning:'Ověřte hodiny'};
      await page.route('**/data/pools.json*',route=>route.fulfill({json:{...fixture,pools:[uncertain]}}));
      await page.getByRole('tab',{name:'Dnes',exact:true}).click();
      await page.getByRole('button',{name:'Načíst znovu'}).click();
      await page.getByRole('heading',{name:'Uncertain hours',exact:true}).waitFor();
      assert.match(await page.locator('#grid').innerText(), /aktuální hodiny nepotvrzené/);
      assert.match(await page.locator('#grid').innerText(), /Běžný rozvrh – nepotvrzený/iu);
      assert.match(await page.locator('#grid').innerText(), /\? \/ 4/);
    }
    if (!remote) {
      const today = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Prague'}).format(new Date());
      const tomorrow = new Date(today + 'T12:00:00Z'); tomorrow.setUTCDate(tomorrow.getUTCDate()+1);
      const next = tomorrow.toISOString().slice(0,10);
      const pool = {id:'time-test',name:'Time test',total_lanes:4,
        weekly_hours:Object.fromEntries(Array.from({length:7},(_,i)=>[i,[['08:00','20:00']]])),
        lane_availability:{days:{
          [today]:[{from:'08:00',to:'20:00',free:2}],
          [next]:[{from:'08:00',to:'20:00',free:3}]
        }}};
      await page.route('**/data/pools.json*',route=>route.fulfill({json:{...fixture,pools:[pool]}}));
      await page.reload();
      await page.getByRole('heading',{name:'Time test',exact:true}).waitFor();
      assert.equal(await page.locator('#visit-time').getAttribute('type'),'text');
      await page.locator('#visit-time').fill('1200');
      await page.locator('#visit-time').press('Tab');
      const selected = () => page.locator('.stat').filter({hasText:/Volné dráhy.*v 12:00/i});
      assert.match(await selected().textContent(), /2 \/ 4/);
      await page.getByRole('tab',{name:'Zítra',exact:true}).click();
      assert.match(await selected().textContent(), /3 \/ 4/);
      await page.reload();
      await page.getByRole('heading',{name:'Time test',exact:true}).waitFor();
      assert.equal(await page.locator('#visit-time').inputValue(),'12:00');
      assert.match(await selected().textContent(), /2 \/ 4/);
      await page.locator('#visit-time').fill('20:00');
      await page.locator('#visit-time').press('Tab');
      assert.match(await page.locator('.stat').filter({hasText:/Volné dráhy.*v 20:00/i}).textContent(), /0 \/ 4/);
      await page.getByRole('button',{name:'Teď',exact:true}).click();
      assert.equal(await page.evaluate(()=>localStorage.getItem('poolstat.visitTime')),null);
    }
    assert.deepEqual(errors,[]);
    console.log('Rendered links pass in both tabs' + (remote ? '; deployed data are fresh' : ' and optional-link fixtures'));
  } finally {if(browser) await browser.close();if(server) server.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
