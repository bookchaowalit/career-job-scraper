// Runs content.js's auto-scroll loop against a fake Facebook feed, with the
// fixed waits collapsed, and checks every stop condition and the batches.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SOURCE = fs.readFileSync(path.join(__dirname, '..', '..', 'chrome-extension', 'content.js'), 'utf8');

function fakeArticle(id) {
  const href = `https://www.facebook.com/groups/condo/posts/${id}/?__cft__[0]=load${Math.random()}`;
  const anchor = { href, getAttribute: (n) => (n === 'href' ? href : null), textContent: '1h', dispatchEvent() {} };
  return {
    innerText: `post ${id} ให้เช่าคอนโด`,
    querySelectorAll: (sel) => (sel === 'a[href]' ? [anchor] : []),
    querySelector: () => null,
  };
}

// feed[i] = post ids rendered after i scrolls (the last entry repeats).
function run(feed, request, onScroll, batchReply) {
  let scrolls = 0;
  const messages = [];
  let listener;
  const handlers = {};
  const window = {
    location: { href: 'https://www.facebook.com/groups/condo', hostname: 'www.facebook.com', pathname: '/groups/condo' },
    innerHeight: 800,
    scrollBy: () => { scrolls += 1; if (onScroll) onScroll(window, scrolls, listener); },
    addEventListener: (name, fn) => { (handlers[name] = handlers[name] || []).push(fn); },
    removeEventListener: (name, fn) => { handlers[name] = (handlers[name] || []).filter((h) => h !== fn); },
    dispatchEvent: (event) => { (handlers[event.type] || []).slice().forEach((fn) => fn(event)); },
  };
  const document = {
    readyState: 'complete',
    title: 'Condo group',
    body: { innerText: 'Public group' },
    querySelector: (sel) => (sel.startsWith('h1') ? { textContent: 'Condo group' } : null),
    querySelectorAll: (sel) => (sel === '[role="article"]'
      ? feed[Math.min(scrolls, feed.length - 1)].map(fakeArticle)
      : []),
  };
  const chrome = {
    runtime: {
      id: 'ext',
      onMessage: { addListener: (fn) => { listener = fn; } },
      sendMessage: (message) => { messages.push(message); return message.action === 'autoCaptureBatch' && batchReply ? Promise.resolve(batchReply()) : Promise.resolve({ ok: true }); },
    },
  };
  const context = {
    window, document, chrome, URL, URLSearchParams, Promise, Date, Math, Number, Array, Map, Set, String, console,
    Event: class { constructor(type) { this.type = type; } },
    MouseEvent: class { constructor(type) { this.type = type; } },
    setTimeout: (fn) => setImmediate(fn),
  };
  vm.runInNewContext(SOURCE, context);
  return new Promise((resolve) => {
    let started;
    listener({ action: 'autoCapture', ...request }, {}, (response) => { started = response; });
    const check = () => {
      const done = messages.find((m) => m.action === 'autoCaptureDone');
      if (done) resolve({ started, done, messages, scrolls });
      else setImmediate(check);
    };
    check();
  });
}

test('stops after 3 steps without new posts and sends canonical batches', async () => {
  const { started, done, messages } = await run([[1, 2], [2, 3], [3]], { maxPosts: 40, maxMinutes: 5 });
  assert.equal(started.ok, true);
  assert.equal(done.reason, 'no_new_posts');
  assert.equal(done.found, 3);
  const posts = messages.filter((m) => m.action === 'autoCaptureBatch').flatMap((m) => m.posts);
  assert.deepEqual([...new Set(posts.map((p) => p.post_url))], [1, 2, 3].map((id) => `https://facebook.com/groups/condo/posts/${id}`));
  assert.ok(posts.every((p) => p.capture_method === 'chrome_extension_auto_scroll'));
});

test('stops at maxPosts', async () => {
  const { done } = await run([[1, 2], [3, 4], [5, 6]], { maxPosts: 3 });
  assert.equal(done.reason, 'max_posts');
  assert.equal(done.found, 3, 'never more than maxPosts, even within one step');
});

test('stops at a post that was already saved', async () => {
  const { done, scrolls } = await run([[1, 2], [3, 4], [5, 6]], { knownPermalinks: ['https://facebook.com/groups/condo/posts/4'] });
  assert.equal(done.reason, 'reached_saved_post');
  assert.equal(scrolls, 1);
});

test('limits are clamped and a second start is refused', async () => {
  const { started } = await run([[1]], { maxPosts: 10000, maxMinutes: 999 });
  assert.equal(started.maxPosts, 200);
  assert.equal(started.maxMinutes, 15);
});

test('refuses to start on a /groups/ page that is not Facebook', () => {
  let listener;
  const window = { location: { href: 'https://www.linkedin.com/groups/123', hostname: 'www.linkedin.com', pathname: '/groups/123' }, addEventListener() {}, removeEventListener() {}, dispatchEvent() {} };
  vm.runInNewContext(SOURCE, {
    window, document: { readyState: 'complete' }, URL, URLSearchParams,
    chrome: { runtime: { id: 'x', onMessage: { addListener: (fn) => { listener = fn; } } } },
    Event: class { constructor(t) { this.type = t; } },
  });
  let response;
  listener({ action: 'autoCapture' }, {}, (r) => { response = r; });
  assert.equal(response.ok, false);
  assert.equal(response.error, 'not_a_group_page');
});

test('stops when Facebook navigates to another group mid-run', async () => {
  const { done, messages } = await run([[1, 2], [3, 4], [5, 6]], { maxPosts: 40 }, (win) => {
    win.location.pathname = '/groups/condo2';
    win.location.href = 'https://www.facebook.com/groups/condo2';
  });
  assert.equal(done.reason, 'left_group');
  const posts = messages.filter((m) => m.action === 'autoCaptureBatch').flatMap((m) => m.posts);
  assert.ok(posts.every((p) => p.post_url.includes('/groups/condo/')));
});

test('Stop during a step ends the run before another scroll', async () => {
  const { done, scrolls } = await run([[1, 2], [3, 4], [5, 6]], { maxPosts: 40 }, (win, count, listener) => {
    if (count === 1) listener({ action: 'autoCaptureStop' }, {}, () => {});
  });
  assert.equal(done.reason, 'stopped');
  assert.equal(scrolls, 1, 'no scroll after Stop');
});

test('a batch the background could not store stops the run as storage_failed', async () => {
  const { done } = await run([[1], [2], [3], [4], [5]], { maxPosts: 40 }, null, () => ({ ok: false }));
  assert.equal(done.reason, 'storage_failed');
});
