// Offline tests for chrome-extension/cloud.js.  Run: node --test tests/js
// Uses fake chrome.* and fetch objects; nothing reaches the network.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const cloudApi = require(path.join(__dirname, '..', '..', 'chrome-extension', 'cloud.js'));

const REDIRECT = 'https://abcdefghijklmnopabcdefghijklmnop.chromiumapp.org/';

function memoryArea(initial) {
  const data = { ...(initial || {}) };
  return {
    data,
    async get(keys) {
      const out = {};
      keys.forEach((key) => { if (data[key] !== undefined) out[key] = JSON.parse(JSON.stringify(data[key])); });
      return out;
    },
    async set(values) { Object.assign(data, JSON.parse(JSON.stringify(values))); },
  };
}

// authReply(url, interactive) returns the redirect URL the provider would send.
function fakeChrome(settings, authReply) {
  const calls = [];
  return {
    calls,
    storage: { local: memoryArea({ cloudSettings: settings }), session: memoryArea() },
    identity: {
      getRedirectURL: () => REDIRECT,
      async launchWebAuthFlow({ url, interactive }) {
        calls.push({ url, interactive });
        return authReply(new URL(url), interactive);
      },
    },
  };
}

function implicitReply(token) {
  return (url) => `${REDIRECT}#access_token=${token}&expires_in=3600&state=${url.searchParams.get('state')}`;
}

function response(status, body, headers) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => (headers || {})[name] || null },
    async json() { return body; },
    async text() { return JSON.stringify(body); },
  };
}

function enabled(id, extra) {
  const settings = cloudApi.normaliseSettings({ autoUpload: true, folder: 'Quick Saver', ...(extra || {}) });
  settings.providers[id] = { enabled: true, clientId: `${id}-client` };
  return settings;
}

test('disabled by default: no auth, no request', async () => {
  const chrome = fakeChrome(undefined, () => { throw new Error('should not auth'); });
  const cloud = cloudApi.createCloud({ chrome, fetch: () => { throw new Error('should not fetch'); } });
  assert.deepEqual(await cloud.uploadExport('a.csv', 'x\n1'), []);
});

test('settings are normalised: folder traversal stripped, unknown flags dropped', () => {
  const settings = cloudApi.normaliseSettings({ autoUpload: 'yes', folder: '../a/./b:c/..', providers: { gdrive: { enabled: true, clientId: ' id ' } } });
  assert.equal(settings.autoUpload, false);
  assert.equal(settings.folder, 'a/bc');
  assert.deepEqual(settings.providers.gdrive, { enabled: true, clientId: 'id' });
  assert.equal(settings.providers.dropbox.enabled, false);
  assert.equal(cloudApi.normaliseFolder('..'), 'Quick Saver');
});

test('redirect state mismatch and provider errors are rejected', () => {
  assert.throws(() => cloudApi.parseRedirect(`${REDIRECT}#access_token=t&state=evil`, 'good'), /auth_state_mismatch/);
  assert.throws(() => cloudApi.parseRedirect(`${REDIRECT}?error=access_denied&state=good`, 'good'), /auth_error:access_denied/);
  assert.equal(cloudApi.parseRedirect(`${REDIRECT}?code=c1&state=good`, 'good').get('code'), 'c1');
});

test('Dropbox-API-Arg escapes non-ASCII so Thai folder names survive the header', () => {
  const header = cloudApi.headerSafeJson({ path: '/ทดสอบ/a.csv' });
  assert.match(header, /^[\x20-\x7e]+$/);
  assert.deepEqual(JSON.parse(header), { path: '/ทดสอบ/a.csv' });
});

test('Google Drive: drive.file scope, folder created, resumable upload into it', async () => {
  const chrome = fakeChrome(enabled('gdrive'), implicitReply('g-token'));
  const requests = [];
  const fetch = async (url, options) => {
    requests.push({ url, options: options || {} });
    if (url.startsWith('https://www.googleapis.com/drive/v3/files?q=')) return response(200, { files: [] });
    if (url.startsWith('https://www.googleapis.com/drive/v3/files?fields=id')) return response(200, { id: 'folder-1' });
    if (url.includes('uploadType=resumable')) return response(200, {}, { Location: 'https://www.googleapis.com/upload/session-1' });
    if (url === 'https://www.googleapis.com/upload/session-1') return response(200, { id: 'file-1', webViewLink: 'https://drive.google.com/file/d/file-1' });
    throw new Error(`unexpected ${url}`);
  };
  const cloud = cloudApi.createCloud({ chrome, fetch, now: () => Date.parse('2026-10-18T10:00:00Z') });
  const [result] = await cloud.uploadExport('facebook_group_posts_export.csv', 'h\nrow');

  assert.equal(result.ok, true, result.error);
  assert.equal(result.link, 'https://drive.google.com/file/d/file-1');
  assert.equal(result.name, 'facebook_group_posts_export_2026-10-18T10-00-00Z.csv');
  const auth = new URL(chrome.calls[0].url);
  assert.equal(auth.searchParams.get('scope'), 'https://www.googleapis.com/auth/drive.file');
  assert.equal(auth.searchParams.get('redirect_uri'), REDIRECT);
  assert.equal(chrome.calls[0].interactive, false, 'silent auth is tried first');
  const start = requests.find((r) => r.url.includes('uploadType=resumable'));
  assert.deepEqual(JSON.parse(start.options.body).parents, ['folder-1']);
  assert.equal(start.options.headers.Authorization, 'Bearer g-token');
  const put = requests.at(-1);
  assert.equal(put.options.method, 'PUT');
  assert.equal(await put.options.body.text(), 'h\nrow');
});

test('Dropbox: PKCE code exchange without a secret, then upload to the folder', async () => {
  const chrome = fakeChrome(enabled('dropbox', { folder: 'ลีด' }), (url) => {
    assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
    return `${REDIRECT}?code=dbx-code&state=${url.searchParams.get('state')}`;
  });
  const requests = [];
  const fetch = async (url, options) => {
    requests.push({ url, options });
    if (url === 'https://api.dropboxapi.com/oauth2/token') return response(200, { access_token: 'd-token', expires_in: 14400 });
    if (url === 'https://content.dropboxapi.com/2/files/upload') return response(200, { path_display: '/ลีด/a.csv' });
    throw new Error(`unexpected ${url}`);
  };
  const cloud = cloudApi.createCloud({ chrome, fetch });
  const [result] = await cloud.uploadExport('a.csv', 'x');

  assert.equal(result.ok, true, result.error);
  const tokenBody = new URLSearchParams(requests[0].options.body);
  assert.equal(tokenBody.get('code'), 'dbx-code');
  assert.equal(tokenBody.get('client_id'), 'dropbox-client');
  assert.ok(tokenBody.get('code_verifier').length >= 43);
  assert.equal(tokenBody.has('client_secret'), false);
  const challenge = new URL(chrome.calls[0].url).searchParams.get('code_challenge');
  assert.equal(challenge, await cloudApi.pkceChallenge(tokenBody.get('code_verifier')));
  const arg = JSON.parse(requests[1].options.headers['Dropbox-API-Arg']);
  assert.match(arg.path, /^\/ลีด\/a_.*\.csv$/);
  assert.equal(arg.autorename, true);
});

test('OneDrive: small file uses one PUT under the app folder', async () => {
  const chrome = fakeChrome(enabled('onedrive', { folder: 'Quick Saver/FB' }), implicitReply('o-token'));
  const requests = [];
  const fetch = async (url, options) => {
    requests.push({ url, options });
    return response(201, { webUrl: 'https://onedrive.live.com/x' });
  };
  const cloud = cloudApi.createCloud({ chrome, fetch });
  const [result] = await cloud.uploadExport('a.csv', 'x');

  assert.equal(result.ok, true, result.error);
  assert.equal(new URL(chrome.calls[0].url).searchParams.get('scope'), 'Files.ReadWrite.AppFolder');
  // Folders are created level by level before the upload.
  assert.equal(requests[0].url, 'https://graph.microsoft.com/v1.0/me/drive/special/approot/children');
  assert.equal(JSON.parse(requests[0].options.body).name, 'Quick Saver');
  assert.equal(requests[1].url, 'https://graph.microsoft.com/v1.0/me/drive/special/approot:/Quick%20Saver:/children');
  assert.equal(JSON.parse(requests[1].options.body).name, 'FB');
  assert.match(requests[2].url, /^https:\/\/graph\.microsoft\.com\/v1\.0\/me\/drive\/special\/approot:\/Quick%20Saver\/FB\/a_[^/]+\.csv:\/content\?/);
  assert.equal(requests[2].options.method, 'PUT');
});

test('OneDrive: files over 4 MB go through an upload session without the bearer token', async () => {
  const chrome = fakeChrome(enabled('onedrive'), implicitReply('o-token'));
  const requests = [];
  const fetch = async (url, options) => {
    requests.push({ url, options });
    if (url.endsWith(':/createUploadSession')) return response(200, { uploadUrl: 'https://upload.example/session' });
    return response(201, { webUrl: 'https://onedrive.live.com/big' });
  };
  const cloud = cloudApi.createCloud({ chrome, fetch });
  const big = 'x'.repeat(5 * 1024 * 1024);
  const [result] = await cloud.uploadExport('big.csv', big);

  assert.equal(result.ok, true, result.error);
  const put = requests.find((r) => r.url === 'https://upload.example/session');
  assert.equal(put.options.headers['Content-Range'], `bytes 0-${big.length - 1}/${big.length}`);
  assert.equal(put.options.headers.Authorization, undefined);
});

test('cached token is reused; a 401 forces one re-auth and retry', async () => {
  let issued = 0;
  const chrome = fakeChrome(enabled('onedrive'), (url) => {
    issued += 1;
    return `${REDIRECT}#access_token=t${issued}&expires_in=3600&state=${url.searchParams.get('state')}`;
  });
  const seen = [];
  const fetch = async (url, options) => {
    if (url.endsWith('/children')) return response(409, { error: 'nameAlreadyExists' });
    seen.push(options.headers.Authorization);
    return seen.length === 2 ? response(401, { error: 'expired' }) : response(201, {});
  };
  const cloud = cloudApi.createCloud({ chrome, fetch });
  assert.equal((await cloud.uploadExport('a.csv', 'x'))[0].ok, true);
  const second = await cloud.uploadExport('a.csv', 'x');
  assert.equal(second[0].ok, true, second[0].error);
  assert.deepEqual(seen, ['Bearer t1', 'Bearer t1', 'Bearer t2']);
  assert.equal(chrome.storage.local.data.cloudTokens, undefined, 'tokens never written to disk storage');
});

test('one failing provider does not hide another success', async () => {
  const settings = enabled('gdrive');
  settings.providers.dropbox = { enabled: true, clientId: '' };
  const chrome = fakeChrome(settings, implicitReply('g'));
  const fetch = async (url) => {
    if (url.includes('drive/v3/files?q=')) return response(200, { files: [{ id: 'f' }] });
    if (url.includes('uploadType=resumable')) return response(200, {}, { Location: 'https://www.googleapis.com/upload/s' });
    return response(200, { webViewLink: 'https://drive.google.com/x' });
  };
  const cloud = cloudApi.createCloud({ chrome, fetch });
  const results = await cloud.uploadExport('a.csv', 'x');
  assert.deepEqual(results.map((r) => [r.provider, r.ok]), [['gdrive', true], ['dropbox', false]]);
  assert.equal(results[1].error, 'missing_client_id');
  assert.equal(chrome.storage.local.data.lastCloudUpload.results.length, 2);
});

test('changing the client ID never reuses the old app token', async () => {
  let issued = 0;
  const chrome = fakeChrome(enabled('dropbox'), (url) => {
    issued += 1;
    return `${REDIRECT}?code=c${issued}&state=${url.searchParams.get('state')}`;
  });
  const auths = [];
  const fetch = async (url, options) => {
    if (url.endsWith('/oauth2/token')) {
      const clientId = new URLSearchParams(options.body).get('client_id');
      auths.push(clientId);
      return response(200, { access_token: `tok-${clientId}`, expires_in: 14400 });
    }
    return response(200, { path_display: '/x' });
  };
  const cloud = cloudApi.createCloud({ chrome, fetch });
  await cloud.uploadExport('a.csv', 'x');
  const settings = await cloud.loadSettings();
  settings.providers.dropbox.clientId = 'new-app';
  await cloud.saveSettings(settings);
  await cloud.uploadExport('a.csv', 'x');
  assert.deepEqual(auths, ['dropbox-client', 'new-app']);
});

test('every request carries an abort signal so a stalled provider times out', async () => {
  const chrome = fakeChrome(enabled('onedrive'), implicitReply('o'));
  const signals = [];
  const fetch = async (url, options) => { signals.push(options.signal); return response(201, {}); };
  const cloud = cloudApi.createCloud({ chrome, fetch });
  await cloud.uploadExport('a.csv', 'x');
  assert.ok(signals.length && signals.every((signal) => signal && typeof signal.aborted === 'boolean'));
});

test('a failed status write does not turn a finished upload into an error', async () => {
  const chrome = fakeChrome(enabled('onedrive'), implicitReply('o'));
  const originalSet = chrome.storage.local.set;
  chrome.storage.local.set = async (values) => {
    if ('lastCloudUpload' in values) throw new Error('QUOTA_BYTES quota exceeded');
    return originalSet.call(chrome.storage.local, values);
  };
  const cloud = cloudApi.createCloud({ chrome, fetch: async () => response(201, {}) });
  const originalWarn = console.warn;
  console.warn = () => {};
  try {
    const results = await cloud.uploadExport('a.csv', 'x');
    assert.equal(results[0].ok, true);
  } finally {
    console.warn = originalWarn;
  }
});

test('OneDrive: an existing folder (409) is fine; other folder errors fail the upload', async () => {
  const chrome = fakeChrome(enabled('onedrive'), implicitReply('o'));
  const ok = cloudApi.createCloud({ chrome, fetch: async (url) => (url.endsWith('/children') ? response(409, {}) : response(201, {})) });
  assert.equal((await ok.uploadExport('a.csv', 'x'))[0].ok, true);
  const bad = cloudApi.createCloud({ chrome, fetch: async (url) => (url.endsWith('/children') ? response(403, {}) : response(201, {})) });
  assert.match((await bad.uploadExport('a.csv', 'x'))[0].error, /^onedrive_folder_http_403/);
});

test('a response body that never finishes still hits the timeout path', async () => {
  const chrome = fakeChrome(enabled('dropbox'), (url) => `${REDIRECT}?code=c&state=${url.searchParams.get('state')}`);
  const fetch = async (url, options) => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: () => new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
      // Simulate the deadline firing while the body is still being read.
      setTimeout(() => options.signal.dispatchEvent(new Event('abort')), 5);
    }),
  });
  const cloud = cloudApi.createCloud({ chrome, fetch });
  const [result] = await cloud.uploadExport('a.csv', 'x');
  assert.equal(result.error, 'dropbox_token_timeout');
});
