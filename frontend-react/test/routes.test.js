import {test} from 'node:test';
import assert from 'node:assert/strict';
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
