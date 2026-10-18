// Offline tests for chrome-extension/sheet.js.  Run: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const sheetApi = require(path.join(__dirname, '..', '..', 'chrome-extension', 'sheet.js'));

const URL_OK = 'https://script.google.com/macros/s/AKfycbTEST_123-abc/exec';

function fakeChrome(settings, extra) {
  const data = { sheetSettings: settings, ...(extra || {}) };
  return {
    data,
    storage: {
      local: {
        async get(keys) {
          const out = {};
          keys.forEach((k) => { if (data[k] !== undefined) out[k] = JSON.parse(JSON.stringify(data[k])); });
          return out;
        },
        async set(values) { Object.assign(data, JSON.parse(JSON.stringify(values))); },
      },
    },
  };
}

function reply(status, body) {
  return { ok: status >= 200 && status < 300, status, async text() { return typeof body === 'string' ? body : JSON.stringify(body); } };
}

function post(id, visibility, extra) {
  return {
    post_url: `https://facebook.com/groups/g/posts/${id}`,
    group_url: 'https://facebook.com/groups/g',
    group_name: 'คอนโดให้เช่า',
    author_name: 'Somchai',
    posted_at: '18 October at 09:12',
    text: `post ${id}`,
    text_complete: true,
    visibility,
    captured_at: '2026-10-18T02:00:00.000Z',
    ...(extra || {}),
  };
}

const ENABLED = { enabled: true, url: URL_OK, secret: 's3cret' };

test('off by default and URL must be an Apps Script /exec URL', async () => {
  const chrome = fakeChrome(undefined);
  const sheet = sheetApi.createSheet({ chrome, fetch: () => { throw new Error('no fetch'); } });
  assert.equal(await sheet.sendPosts([post(1, 'public')]), null);
  assert.equal(sheetApi.normaliseSettings({ url: 'https://evil.example/exec' }).url, '');
  assert.equal(sheetApi.normaliseSettings({ url: `${URL_OK}?x=1` }).url, '');
  assert.equal(sheetApi.normaliseSettings({ url: URL_OK }).url, URL_OK);
});

test('sends only public rows as text/plain JSON with the agreed fields', async () => {
  const chrome = fakeChrome(ENABLED);
  const calls = [];
  const fetch = async (url, options) => { calls.push({ url, options }); return reply(200, { ok: true, added: 1 }); };
  const sheet = sheetApi.createSheet({ chrome, fetch });
  const result = await sheet.sendPosts([post(1, 'public'), post(2, 'private'), post(3, 'unknown')]);

  assert.deepEqual(result, { ok: true, sent: 1, added: 1, skipped: 2, pending: 0 });
  assert.equal(calls[0].url, URL_OK);
  assert.equal(calls[0].options.headers['Content-Type'], 'text/plain;charset=utf-8');
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.secret, 's3cret');
  assert.deepEqual(body.rows, [{
    collected_at: '2026-10-18T09:00:00+07:00',
    group_name: 'คอนโดให้เช่า',
    group_url: 'https://facebook.com/groups/g',
    permalink: 'https://facebook.com/groups/g/posts/1',
    poster: 'Somchai',
    posted: '18 October at 09:12',
    text: 'post 1',
    text_complete: true,
  }]);
});

test('failure retries once, then queues rows for the next send', async () => {
  const chrome = fakeChrome(ENABLED);
  let calls = 0;
  const failing = sheetApi.createSheet({ chrome, fetch: async () => { calls += 1; throw new Error('network down'); } });
  const first = await failing.sendPosts([post(1, 'public')]);
  assert.equal(calls, 2);
  assert.equal(first.ok, false);
  assert.equal(first.pending, 1);
  assert.equal(chrome.data.sheetPendingRows.length, 1);

  const bodies = [];
  const working = sheetApi.createSheet({ chrome, fetch: async (url, options) => { bodies.push(JSON.parse(options.body)); return reply(200, { added: 2 }); } });
  const second = await working.sendPosts([post(2, 'public')]);
  assert.equal(second.ok, true);
  assert.deepEqual(bodies[0].rows.map((r) => r.permalink.split('/').pop()), ['1', '2']);
  assert.deepEqual(chrome.data.sheetPendingRows, []);
});

test('a wrong secret is not retried and keeps the rows queued', async () => {
  const chrome = fakeChrome(ENABLED);
  let calls = 0;
  const sheet = sheetApi.createSheet({ chrome, fetch: async () => { calls += 1; return reply(200, 'forbidden'); } });
  const result = await sheet.sendPosts([post(1, 'public')]);
  assert.equal(calls, 1);
  assert.match(result.error, /^sheet_rejected:forbidden/);
  assert.equal(result.pending, 1);
});

test('connection test sends an empty batch', async () => {
  const chrome = fakeChrome(ENABLED);
  let body;
  const sheet = sheetApi.createSheet({ chrome, fetch: async (url, options) => { body = JSON.parse(options.body); return reply(200, { ok: true, added: 0 }); } });
  assert.deepEqual(await sheet.testConnection(), { ok: true });
  assert.deepEqual(body.rows, []);
});

test('re-labelling a queued post as private withdraws it from the queue', async () => {
  const chrome = fakeChrome(ENABLED);
  const down = sheetApi.createSheet({ chrome, fetch: async () => { throw new Error('down'); } });
  await down.sendPosts([post(1, 'public')]);
  const bodies = [];
  const up = sheetApi.createSheet({ chrome, fetch: async (u, o) => { bodies.push(JSON.parse(o.body)); return reply(200, { ok: true, added: 0 }); } });
  const result = await up.sendPosts([post(1, 'private')]);
  assert.equal(result.skipped, 1);
  assert.equal(bodies.length, 0, 'nothing left to send');
  assert.deepEqual(chrome.data.sheetPendingRows, []);
});

test('rows are queued before the request starts', async () => {
  const chrome = fakeChrome(ENABLED);
  let queuedDuringRequest;
  const sheet = sheetApi.createSheet({ chrome, fetch: async () => { queuedDuringRequest = chrome.data.sheetPendingRows.length; return reply(200, { ok: true, added: 1 }); } });
  await sheet.sendPosts([post(1, 'public')]);
  assert.equal(queuedDuringRequest, 1);
  assert.deepEqual(chrome.data.sheetPendingRows, []);
});

test('overlapping sends are serialised and never drop an unsent row', async () => {
  const chrome = fakeChrome(ENABLED);
  const seen = [];
  const sheet = sheetApi.createSheet({ chrome, fetch: async (u, o) => {
    const links = JSON.parse(o.body).rows.map((r) => r.permalink.split('/').pop());
    seen.push(links);
    if (links.includes('A') && !links.includes('B')) throw new Error('A fails');
    return reply(200, { ok: true, added: links.length });
  } });
  const [a, b] = await Promise.all([sheet.sendPosts([post('A', 'public')]), sheet.sendPosts([post('B', 'public')])]);
  assert.equal(a.ok, false);
  assert.equal(b.ok, true);
  assert.deepEqual(seen.at(-1), ['A', 'B'], 'B carries the queued A');
  assert.deepEqual(chrome.data.sheetPendingRows, []);
});

test('a queue write failure is reported, not hidden', async () => {
  const chrome = fakeChrome(ENABLED);
  chrome.storage.local.set = async () => { throw new Error('QUOTA_BYTES'); };
  const originalWarn = console.warn;
  console.warn = () => {};
  try {
    const sheet = sheetApi.createSheet({ chrome, fetch: async () => reply(200, { ok: true, added: 1 }) });
    assert.equal((await sheet.sendPosts([post(1, 'public')])).error, 'sheet_queue_not_saved');
  } finally {
    console.warn = originalWarn;
  }
});

test('withdrawal happens even while the sink is disabled', async () => {
  const chrome = fakeChrome(ENABLED);
  const down = sheetApi.createSheet({ chrome, fetch: async () => { throw new Error('down'); } });
  await down.sendPosts([post(1, 'public')]);
  chrome.data.sheetSettings = { ...ENABLED, enabled: false };
  assert.equal(await down.sendPosts([post(1, 'private')]), null);
  assert.deepEqual(chrome.data.sheetPendingRows, []);
});

test('a truncated recapture does not replace a complete queued copy', async () => {
  const chrome = fakeChrome(ENABLED);
  const down = sheetApi.createSheet({ chrome, fetch: async () => { throw new Error('down'); } });
  await down.sendPosts([post(1, 'public', { text: 'full text of the listing', text_complete: true })]);
  await down.sendPosts([post(1, 'public', { text: 'full… See more', text_complete: false })]);
  assert.equal(chrome.data.sheetPendingRows[0].text, 'full text of the listing');
});

test('a pre-1.4 queued row (with __cft__) is withdrawn by its canonical private save', async () => {
  const chrome = fakeChrome(ENABLED, {
    sheetPendingRows: [{ permalink: 'https://facebook.com/groups/g/posts/1?__cft__[0]=old', text: 'x' }],
  });
  const canonical = (url) => url.split('?')[0];
  const sent = [];
  const sheet = sheetApi.createSheet({ chrome, canonical, fetch: async (u, o) => { sent.push(o); return reply(200, { ok: true, added: 0 }); } });
  await sheet.sendPosts([post(1, 'private')]);
  assert.equal(sent.length, 0);
  assert.deepEqual(chrome.data.sheetPendingRows, []);
});

test('merging pre-1.4 queue variants keeps the fullest copy', async () => {
  const chrome = fakeChrome(ENABLED, {
    sheetPendingRows: [
      { permalink: 'https://facebook.com/groups/g/posts/1?__cft__=a', text: 'complete listing text', text_complete: true },
      { permalink: 'https://facebook.com/groups/g/posts/1?__cft__=b', text: 'short…', text_complete: false },
    ],
  });
  let body;
  const sheet = sheetApi.createSheet({ chrome, canonical: (u) => u.split('?')[0], fetch: async (u, o) => { body = JSON.parse(o.body); return reply(200, { ok: true, added: 1 }); } });
  await sheet.sendPosts([]);
  assert.equal(body.rows.length, 1);
  assert.equal(body.rows[0].text, 'complete listing text');
});
