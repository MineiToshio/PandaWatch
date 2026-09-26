const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('web/cover-preview.html', 'utf8');
const source = html.match(/<script>\s*(function previewApp\(\)[\s\S]*?)<\/script>/)[1];
function setup(fetch) {
  const context = vm.createContext({fetch, confirm: () => {throw Error('Native dialog forbidden');}});
  vm.runInContext(source, context);
  const app = context.previewApp();
  app.entries = [{candidates:[{status:'approved'}, {status:'rejected'}, {status:'pending'}]}];
  app.loadedMtime = '123';
  app.messages = [];
  app.showToast = msg => app.messages.push(msg);
  app.loadEntries = async () => {app.loaded = true;};
  return app;
}
test('opening or cancelling confirmation never sends a request', async () => {
  const app = setup(() => assert.fail('unexpected request'));
  app.requestApplyApproved();
  assert.equal(app.showApplyConfirmation, true);
  app.showApplyConfirmation = false;
  await app.applyApproved();
  assert.equal(app.isApplying, false);
  assert.equal((html.match(/@click="requestApplyApproved\(\)"/g)||[]).length, 3);
});
test('apply waits for saves and blocks double submission', async () => {
  let release, calls = 0;
  const app = setup(async (url, opts) => {
    calls++;
    assert.equal(url, '/api/apply-cover-preview');
    assert.equal(JSON.parse(opts.body).expected_mtime, '456');
    return {ok:true, status:200, json:async()=>({ok:true, applied:1, rejected:1})};
  });
  app._saveQueue = new Promise(r => {release = () => {app.loadedMtime='456';r();};});
  app.requestApplyApproved();
  const pending = app.applyApproved();
  await app.applyApproved();
  assert.equal(app.isApplying,true);
  assert.equal(calls,0);
  release(); await pending;
  assert.equal(calls,1);
  assert.equal(app.loaded,true);
  assert.equal(app.isApplying,false);
});
test('conflict reloads the queue and releases loading state', async () => {
  const app=setup(async()=>({status:409}));
  app.requestApplyApproved(); await app.applyApproved();
  assert.equal(app.loaded,true);
  assert.equal(app.isApplying,false);
});
test('network failure is visible and allows retry', async () => {
  const app=setup(async()=>{throw Error('offline');});
  app.requestApplyApproved(); await app.applyApproved();
  assert.match(app.messages.at(-1),/offline/);
  assert.equal(app.isApplying,false);
  app.requestApplyApproved();
  assert.equal(app.showApplyConfirmation,true);
});
