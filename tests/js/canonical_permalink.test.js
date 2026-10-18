// The extension (content.js, background.js) and Code.gs must agree on one
// canonical URL per post; tests/test_chrome_extension_cloud_upload.py checks
// the Python importer against the same cases (tests/js/permalink_cases.json).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..', '..');
const CASES = JSON.parse(fs.readFileSync(path.join(__dirname, 'permalink_cases.json'), 'utf8'));

function extractFunction(file, name) {
  const source = fs.readFileSync(path.join(ROOT, file), 'utf8');
  const start = source.indexOf(`function ${name}(`);
  let depth = 0;
  for (let i = source.indexOf('{', start); i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    if (source[i] === '}') { depth -= 1; if (depth === 0) return source.slice(start, i + 1); }
  }
  throw new Error(`${name} not found in ${file}`);
}

const implementations = {
  'background.js': vm.runInNewContext(`(${extractFunction('chrome-extension/background.js', 'canonicalFacebookPostUrl')})`, { URL, URLSearchParams }),
  'content.js': vm.runInNewContext(`(${extractFunction('chrome-extension/content.js', 'canonicalFacebookPostUrl')})`, { URL, URLSearchParams }),
  'Code.gs': vm.runInNewContext(`(${extractFunction('integrations/google-sheet/Code.gs', 'canonicalPostUrl_')})`),
};

for (const [name, canonical] of Object.entries(implementations)) {
  test(`${name} canonicalises every shared case`, () => {
    CASES.forEach(({ input, expected }) => assert.equal(canonical(input), expected, input));
  });
}

test('background keeps every post the extractor accepts, incl. /story/<id>', () => {
  const source = fs.readFileSync(path.join(ROOT, 'chrome-extension/background.js'), 'utf8');
  const fns = ['canonicalFacebookPostUrl', 'normaliseFacebookGroupUrl', 'normaliseBoolean', 'sanitiseFacebookGroupPost']
    .map((name) => extractFunction('chrome-extension/background.js', name)).join('\n');
  const methods = source.match(/const FACEBOOK_CAPTURE_METHODS = [^;]+;/)[0];
  const sanitise = vm.runInNewContext(`${methods}\n${fns}; sanitiseFacebookGroupPost`, { URL, URLSearchParams });
  ['https://www.facebook.com/story/123', 'https://www.facebook.com/groups/condo/permalink/5/?__tn__=x'].forEach((url) => {
    const clean = sanitise({ group_url: 'https://facebook.com/groups/condo', post_url: url });
    assert.ok(clean, url);
    assert.equal(clean.post_url, implementations['content.js'](url));
  });
  assert.ok(source.includes('sanitiseFacebookGroupPost(post || {})'));
});
