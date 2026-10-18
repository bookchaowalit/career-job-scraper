// escapeCsv formula guard (background.js) and the Facebook extractor's
// poster/time selection (content.js), run against small fakes.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const EXT = path.join(__dirname, '..', '..', 'chrome-extension');

function loadEscapeCsv() {
  const source = fs.readFileSync(path.join(EXT, 'background.js'), 'utf8');
  const fn = source.match(/function escapeCsv\(value\) \{[\s\S]*?\n\}/);
  return vm.runInNewContext(`(${fn[0]})`);
}

test('escapeCsv guards formulas and quotes CR/LF/commas', () => {
  const escapeCsv = loadEscapeCsv();
  assert.equal(escapeCsv('=HYPERLINK("x")'), `"'=HYPERLINK(""x"")"`);
  assert.equal(escapeCsv('+66 81 234 5678'), "'+66 81 234 5678");
  assert.equal(escapeCsv('-ขายด่วน'), "'-ขายด่วน");
  assert.equal(escapeCsv('@home'), "'@home");
  assert.equal(escapeCsv('a\rb'), '"a\rb"');
  assert.equal(escapeCsv('a,b'), '"a,b"');
  assert.equal(escapeCsv('ok'), 'ok');
  assert.equal(escapeCsv(0), '0');
  assert.equal(escapeCsv(null), '');
});

// Minimal DOM fakes for one article.
function el(attrs, text, children) {
  return {
    attrs: attrs || {},
    textContent: text || '',
    children: children || [],
    getAttribute(name) { return this.attrs[name] === undefined ? null : this.attrs[name]; },
  };
}

function runExtractor(article) {
  const source = fs.readFileSync(path.join(EXT, 'content.js'), 'utf8');
  const start = source.indexOf('  function extractFacebookGroupPosts()');
  const end = source.indexOf('  // Add floating save button');
  const document = {
    querySelector: (sel) => (sel.startsWith('h1') ? { textContent: 'Test Group' } : null),
    querySelectorAll: () => [article.node],
    body: { innerText: 'Public group' },
    title: 'Test Group',
  };
  const window = { location: { href: 'https://www.facebook.com/groups/testgroup' } };
  return vm.runInNewContext(`${source.slice(start, end)}; extractFacebookGroupPosts()`, { document, window, URL, URLSearchParams });
}

function article({ profileName, header, looseLink, time, permalinkLabel, seeMore }) {
  const permalink = el({ href: 'https://www.facebook.com/groups/testgroup/posts/123/?__cft__=x', 'aria-label': permalinkLabel }, '2h');
  permalink.href = permalink.attrs.href;
  const node = {
    innerText: 'Somchai ให้เช่าคอนโด 12,000 บาท',
    querySelectorAll: (sel) => {
      if (sel === 'a[href]') return [permalink];
      if (sel === '[role="button"], span, div') return seeMore ? [el({}, seeMore)] : [];
      return [];
    },
    querySelector: (sel) => {
      if (sel === 'time, abbr[title], [data-utime]') return time || null;
      if (sel === '[data-ad-rendering-role="profile_name"] a') return profileName ? el({}, profileName) : null;
      if (sel === 'h2 a, h3 a') return header ? el({}, header) : null;
      if (sel === '[data-ad-rendering-role="profile_name"]') return null;
      if (sel.includes('a[role="link"]')) return looseLink ? el({}, looseLink) : null;
      return null;
    },
  };
  return { node };
}

test('poster prefers profile_name, then the header, never a loose link', () => {
  assert.equal(runExtractor(article({ profileName: 'Somchai', header: 'Other' })).posts[0].author_name, 'Somchai');
  assert.equal(runExtractor(article({ header: 'Header Name' })).posts[0].author_name, 'Header Name');
  assert.equal(runExtractor(article({ looseLink: 'A Commenter' })).posts[0].author_name, '');
});

test('posted time falls back to the permalink aria-label, then its text', () => {
  const withTime = runExtractor(article({ time: el({ datetime: '2026-10-18T09:12:00+07:00' }) }));
  assert.equal(withTime.posts[0].posted_at, '2026-10-18T09:12:00+07:00');
  assert.equal(runExtractor(article({ permalinkLabel: '18 October at 09:12' })).posts[0].posted_at, '18 October at 09:12');
  assert.equal(runExtractor(article({})).posts[0].posted_at, '2h');
});

test('permalink drops per-load __cft__/__tn__ tokens', () => {
  const post = runExtractor(article({})).posts[0];
  assert.equal(post.post_url, 'https://facebook.com/groups/testgroup/posts/123');
});

test('text_complete follows a visible See more control, not the word in the text', () => {
  assert.equal(runExtractor(article({})).posts[0].text_complete, true);
  assert.equal(runExtractor(article({ seeMore: 'ดูเพิ่มเติม' })).posts[0].text_complete, false);
  assert.equal(runExtractor(article({ seeMore: 'See more' })).posts[0].text_complete, false);
  assert.equal(runExtractor(article({ seeMore: 'อ่านเพิ่มเติม' })).posts[0].text_complete, false);
  assert.equal(runExtractor(article({ seeMore: 'แสดงเพิ่มเติม' })).posts[0].text_complete, false);
});
