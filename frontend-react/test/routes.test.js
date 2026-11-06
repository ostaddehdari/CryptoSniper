import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolvePage} from '../src/routes.js';
test('Stage24 bookmarks and new-trade links reach the restored workspace',()=>{
  assert.equal(resolvePage('#/overview'), 'dashboard');
  assert.equal(resolvePage('#/newtrade?signal=12'), 'manual');
  assert.equal(resolvePage('#/system'), 'operations');
});
test('unknown and empty bookmarks recover without a blank screen',()=>{
  assert.equal(resolvePage('#/deleted-page'), 'dashboard');
  assert.equal(resolvePage('', 'exchanges'), 'exchanges');
  assert.equal(resolvePage('#/inbox'), 'inbox');
});
test('Stage33 owner routes and controls remain wired without legacy Paper UI',()=>{
  for (const page of ['dashboard','trades','inbox','exchanges','telegram','alerts','reports','operations','settings']) {
    assert.equal(resolvePage(`#/${page}`), page);
  }
  const source=readFileSync(new URL('../src/main.jsx',import.meta.url),'utf8');
  assert.equal(source.includes('+function Alerts'), false);
  assert.equal(source.includes('["paper","آزمایشی"]'), false);
  assert.match(source,/page==="alerts"&&<Alerts/);
  assert.match(source,/page==="reports"&&<Reports/);
  assert.match(source,/aria-label="نمایش فشرده"/);
});
test('Stage34 live header shows the requested market pairs with freshness state',()=>{
  const source=readFileSync(new URL('../src/main.jsx',import.meta.url),'utf8');
  assert.match(source,/name="btc_usdt" label="BTC \/ USDT"/);
  assert.match(source,/name="usdt_toman" label="USDT \/ تومان"/);
  assert.match(source,/refresh_after_seconds/);
  assert.match(source,/visibilitychange/);
  assert.equal(source.includes('label="USDT / USD"'), false);
});
test('Stage34 manual trade applies live price and Fix Loss automatically',()=>{
  const source=readFileSync(new URL('../src/main.jsx',import.meta.url),'utf8');
  assert.match(source,/setEntry\(String\(liveEntry\)\)/);
  assert.match(source,/Entry · سفارش Limit/);
  assert.match(source,/SL → Entry پس از TP1/);
  assert.match(source,/setCapital\(suggested\)/);
  assert.match(source,/ریسک محاسبه‌شده با کارمزد/);
  assert.match(source,/تتر آزاد زنده/);
});
