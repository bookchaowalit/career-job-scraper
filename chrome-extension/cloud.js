// Quick Saver — optional cloud upload of exported CSV files.
//
// Off by default.  When the operator enables a provider in the options page,
// every CSV the extension exports is also uploaded to that operator's own
// storage account.  Only the exported CSV leaves the browser: no cookies, no
// page HTML, no Facebook request.  Access tokens live in chrome.storage.session
// (memory only, cleared when Chrome closes); client IDs are public OAuth
// identifiers, not secrets, and are the only cloud values kept on disk.
//
// Loaded by background.js (importScripts) and options.js (<script>); the tests
// load it with require() and inject fake chrome/fetch objects.

(function (root) {
  const SETTINGS_KEY = 'cloudSettings';
  const TOKENS_KEY = 'cloudTokens';
  const LAST_UPLOAD_KEY = 'lastCloudUpload';
  const TOKEN_SKEW_MS = 60 * 1000;
  const ONEDRIVE_SIMPLE_LIMIT = 4 * 1024 * 1024;
  const ONEDRIVE_SESSION_LIMIT = 60 * 1024 * 1024;
  const REQUEST_TIMEOUT_MS = 120 * 1000;
  const KEEPALIVE_INTERVAL_MS = 20 * 1000;

  const DEFAULT_SETTINGS = {
    autoUpload: false,
    folder: 'Quick Saver',
    providers: {
      gdrive: { enabled: false, clientId: '' },
      dropbox: { enabled: false, clientId: '' },
      onedrive: { enabled: false, clientId: '' },
    },
  };

  function cloneDefaults() {
    return JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
  }

  function normaliseFolder(value) {
    const cleaned = String(value || '')
      .split('/')
      .map((part) => part.replace(/[\\:*?"<>|\u0000-\u001f]/g, '').trim())
      .filter((part) => part && part !== '.' && part !== '..')
      .join('/')
      .slice(0, 120);
    return cleaned || DEFAULT_SETTINGS.folder;
  }

  function normaliseSettings(raw) {
    const settings = cloneDefaults();
    const input = raw && typeof raw === 'object' ? raw : {};
    settings.autoUpload = input.autoUpload === true;
    settings.folder = normaliseFolder(input.folder);
    Object.keys(settings.providers).forEach((id) => {
      const provider = (input.providers && input.providers[id]) || {};
      settings.providers[id] = {
        enabled: provider.enabled === true,
        clientId: String(provider.clientId || '').trim().slice(0, 200),
      };
    });
    return settings;
  }

  function timestampedFilename(filename, now) {
    const stamp = (now || new Date()).toISOString().replace(/\.\d+Z$/, 'Z').replace(/:/g, '-');
    const dot = filename.lastIndexOf('.');
    return dot > 0 ? `${filename.slice(0, dot)}_${stamp}${filename.slice(dot)}` : `${filename}_${stamp}`;
  }

  function base64Url(bytes) {
    let binary = '';
    bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function randomToken(byteLength) {
    const bytes = new Uint8Array(byteLength);
    crypto.getRandomValues(bytes);
    return base64Url(bytes);
  }

  async function pkceChallenge(verifier) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
    return base64Url(new Uint8Array(digest));
  }

  // Dropbox-API-Arg is an HTTP header, so non-ASCII path characters (Thai
  // folder names) must be sent as JSON \uXXXX escapes.
  function headerSafeJson(value) {
    return JSON.stringify(value).replace(/[\u007f-￿]/g, (ch) => `\\u${ch.charCodeAt(0).toString(16).padStart(4, '0')}`);
  }

  function encodePath(path) {
    return path.split('/').map(encodeURIComponent).join('/');
  }

  function parseRedirect(redirectUrl, expectedState) {
    const parsed = new URL(redirectUrl);
    // Code flows answer in the query, implicit flows in the fragment.
    const params = new URLSearchParams(parsed.search.slice(1));
    new URLSearchParams(parsed.hash.slice(1)).forEach((value, key) => params.set(key, value));
    if (params.get('error')) {
      throw new Error(`auth_error:${params.get('error')}`);
    }
    if (params.get('state') !== expectedState) {
      throw new Error('auth_state_mismatch');
    }
    return params;
  }

  // Bound every request, including reading its body, so a stalled provider
  // fails cleanly instead of holding the export (and the remaining
  // providers) forever.  read: 'json' returns the parsed body, 'none' returns
  // the Response after checking its status.
  async function checkedFetch(fetchImpl, url, options, label, read) {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS) : null;
    try {
      const response = await fetchImpl(url, controller ? { ...options, signal: controller.signal } : options);
      if (!response.ok) {
        let detail = '';
        try { detail = (await response.text()).slice(0, 200); } catch (error) { detail = ''; }
        const err = new Error(`${label}_http_${response.status}${detail ? `: ${detail}` : ''}`);
        err.status = response.status;
        throw err;
      }
      return read === 'none' ? response : await response.json();
    } catch (error) {
      if (error && error.name === 'AbortError') throw new Error(`${label}_timeout`);
      throw error;
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  const PROVIDERS = {
    gdrive: {
      label: 'Google Drive',
      flow: 'implicit',
      authUrl(clientId, redirectUri, state) {
        const url = new URL('https://accounts.google.com/o/oauth2/v2/auth');
        url.search = new URLSearchParams({
          client_id: clientId,
          response_type: 'token',
          redirect_uri: redirectUri,
          scope: 'https://www.googleapis.com/auth/drive.file',
          include_granted_scopes: 'true',
          state,
        }).toString();
        return url.toString();
      },
      async ensureFolder(ctx, token) {
        // drive.file only sees files this app created, so the folder lookup is
        // scoped to Quick Saver's own folder by construction.
        const folderPath = ctx.settings.folder.split('/');
        let parent = 'root';
        for (const name of folderPath) {
          const escaped = name.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
          const query = `name='${escaped}' and mimeType='application/vnd.google-apps.folder' and '${parent}' in parents and trashed=false`;
          const listUrl = `https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(query)}&fields=files(id)&spaces=drive`;
          const listed = await checkedFetch(ctx.fetch, listUrl, { headers: { Authorization: `Bearer ${token}` } }, 'gdrive_list', 'json');
          if (listed.files && listed.files.length) {
            parent = listed.files[0].id;
            continue;
          }
          const created = await checkedFetch(ctx.fetch, 'https://www.googleapis.com/drive/v3/files?fields=id', {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json; charset=UTF-8' },
            body: JSON.stringify({ name, mimeType: 'application/vnd.google-apps.folder', parents: [parent] }),
          }, 'gdrive_folder', 'json');
          parent = created.id;
        }
        return parent;
      },
      async upload(ctx, token, file) {
        const folderId = await this.ensureFolder(ctx, token);
        // Resumable upload handles any size; multipart is capped at 5 MB.
        const start = await checkedFetch(ctx.fetch, 'https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,webViewLink', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json; charset=UTF-8',
            'X-Upload-Content-Type': file.mimeType,
          },
          body: JSON.stringify({ name: file.name, parents: [folderId], mimeType: file.mimeType }),
        }, 'gdrive_start', 'none');
        const sessionUrl = start.headers.get('Location');
        if (!sessionUrl) throw new Error('gdrive_no_upload_session');
        const done = await checkedFetch(ctx.fetch, sessionUrl, {
          method: 'PUT',
          headers: { 'Content-Type': file.mimeType },
          body: file.blob,
        }, 'gdrive_upload', 'json');
        return { link: done.webViewLink || '' };
      },
    },

    dropbox: {
      label: 'Dropbox',
      flow: 'pkce',
      authUrl(clientId, redirectUri, state, challenge) {
        const url = new URL('https://www.dropbox.com/oauth2/authorize');
        url.search = new URLSearchParams({
          client_id: clientId,
          response_type: 'code',
          redirect_uri: redirectUri,
          code_challenge: challenge,
          code_challenge_method: 'S256',
          token_access_type: 'online',
          state,
        }).toString();
        return url.toString();
      },
      tokenUrl: 'https://api.dropboxapi.com/oauth2/token',
      async upload(ctx, token, file) {
        const path = `/${ctx.settings.folder}/${file.name}`;
        const result = await checkedFetch(ctx.fetch, 'https://content.dropboxapi.com/2/files/upload', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/octet-stream',
            'Dropbox-API-Arg': headerSafeJson({ path, mode: 'add', autorename: true, mute: true }),
          },
          body: file.blob,
        }, 'dropbox_upload', 'json');
        return { link: '', path: result.path_display || path };
      },
    },

    onedrive: {
      label: 'OneDrive',
      flow: 'implicit',
      authUrl(clientId, redirectUri, state) {
        const url = new URL('https://login.microsoftonline.com/common/oauth2/v2.0/authorize');
        url.search = new URLSearchParams({
          client_id: clientId,
          response_type: 'token',
          redirect_uri: redirectUri,
          response_mode: 'fragment',
          scope: 'Files.ReadWrite.AppFolder',
          state,
        }).toString();
        return url.toString();
      },
      async ensureFolder(ctx, token) {
        // Path-based uploads do not create missing parents, so create each
        // folder level under approot first; 409 means it already exists.
        let parentPath = '';
        for (const name of ctx.settings.folder.split('/')) {
          const parent = parentPath
            ? `https://graph.microsoft.com/v1.0/me/drive/special/approot:/${encodePath(parentPath)}:/children`
            : 'https://graph.microsoft.com/v1.0/me/drive/special/approot/children';
          try {
            await checkedFetch(ctx.fetch, parent, {
              method: 'POST',
              headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
              body: JSON.stringify({ name, folder: {}, '@microsoft.graph.conflictBehavior': 'fail' }),
            }, 'onedrive_folder', 'none');
          } catch (error) {
            if (error.status !== 409) throw error;
          }
          parentPath = parentPath ? `${parentPath}/${name}` : name;
        }
      },
      async upload(ctx, token, file) {
        await this.ensureFolder(ctx, token);
        // approot = Apps/<app name>/ in the operator's OneDrive.
        const itemPath = encodePath(`${ctx.settings.folder}/${file.name}`);
        const base = `https://graph.microsoft.com/v1.0/me/drive/special/approot:/${itemPath}:`;
        if (file.blob.size <= ONEDRIVE_SIMPLE_LIMIT) {
          const item = await checkedFetch(ctx.fetch, `${base}/content?@microsoft.graph.conflictBehavior=rename`, {
            method: 'PUT',
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': file.mimeType },
            body: file.blob,
          }, 'onedrive_upload', 'json');
          return { link: item.webUrl || '' };
        }
        if (file.blob.size > ONEDRIVE_SESSION_LIMIT) throw new Error('onedrive_file_too_large');
        const session = await checkedFetch(ctx.fetch, `${base}/createUploadSession`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ item: { '@microsoft.graph.conflictBehavior': 'rename' } }),
        }, 'onedrive_session', 'json');
        // A single final chunk may be up to 60 MiB.  The session URL is
        // pre-authorised; Graph rejects an Authorization header on it.
        const size = file.blob.size;
        const item = await checkedFetch(ctx.fetch, session.uploadUrl, {
          method: 'PUT',
          headers: { 'Content-Range': `bytes 0-${size - 1}/${size}` },
          body: file.blob,
        }, 'onedrive_upload', 'json');
        return { link: item.webUrl || '' };
      },
    },
  };

  function createCloud(deps) {
    const chromeApi = deps.chrome;
    const fetchImpl = deps.fetch;
    const now = deps.now || (() => Date.now());

    async function loadSettings() {
      const stored = await chromeApi.storage.local.get([SETTINGS_KEY]);
      return normaliseSettings(stored[SETTINGS_KEY]);
    }

    async function saveSettings(settings) {
      const clean = normaliseSettings(settings);
      await chromeApi.storage.local.set({ [SETTINGS_KEY]: clean });
      return clean;
    }

    async function readTokens() {
      const store = chromeApi.storage.session || chromeApi.storage.local;
      const stored = await store.get([TOKENS_KEY]);
      return { store, tokens: stored[TOKENS_KEY] || {} };
    }

    async function cacheToken(providerId, token) {
      const { store, tokens } = await readTokens();
      tokens[providerId] = token;
      await store.set({ [TOKENS_KEY]: tokens });
    }

    async function forgetToken(providerId) {
      const { store, tokens } = await readTokens();
      delete tokens[providerId];
      await store.set({ [TOKENS_KEY]: tokens });
    }

    async function authorise(providerId, clientId, interactive) {
      const provider = PROVIDERS[providerId];
      const redirectUri = chromeApi.identity.getRedirectURL();
      const state = randomToken(16);
      let verifier = '';
      let challenge = '';
      if (provider.flow === 'pkce') {
        verifier = randomToken(48);
        challenge = await pkceChallenge(verifier);
      }
      const redirect = await chromeApi.identity.launchWebAuthFlow({
        url: provider.authUrl(clientId, redirectUri, state, challenge),
        interactive,
      });
      if (!redirect) throw new Error('auth_cancelled');
      const params = parseRedirect(redirect, state);
      let accessToken = params.get('access_token');
      let expiresIn = Number(params.get('expires_in') || 3600);
      if (provider.flow === 'pkce') {
        const code = params.get('code');
        if (!code) throw new Error('auth_no_code');
        const tokenResponse = await checkedFetch(fetchImpl, provider.tokenUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            code,
            grant_type: 'authorization_code',
            client_id: clientId,
            redirect_uri: redirectUri,
            code_verifier: verifier,
          }).toString(),
        }, `${providerId}_token`, 'json');
        accessToken = tokenResponse.access_token;
        expiresIn = Number(tokenResponse.expires_in || 3600);
      }
      if (!accessToken) throw new Error('auth_no_token');
      const token = { access_token: accessToken, client_id: clientId, expires_at: now() + expiresIn * 1000 };
      await cacheToken(providerId, token);
      return token.access_token;
    }

    async function getToken(providerId, clientId, options) {
      const opts = options || {};
      if (!opts.forceRefresh) {
        const { tokens } = await readTokens();
        const cached = tokens[providerId];
        // A token minted for a different client ID belongs to another app
        // (and app folder), so it is never reused after the ID changes.
        if (cached && cached.access_token && cached.client_id === clientId
          && cached.expires_at - TOKEN_SKEW_MS > now()) return cached.access_token;
      }
      try {
        return await authorise(providerId, clientId, false);
      } catch (silentError) {
        if (!opts.interactive) throw silentError;
        return authorise(providerId, clientId, true);
      }
    }

    async function connect(providerId) {
      const settings = await loadSettings();
      const provider = PROVIDERS[providerId];
      const clientId = settings.providers[providerId] && settings.providers[providerId].clientId;
      if (!provider) throw new Error('unknown_provider');
      if (!clientId) throw new Error('missing_client_id');
      await forgetToken(providerId);
      return authorise(providerId, clientId, true);
    }

    async function uploadToProvider(providerId, settings, file, interactive) {
      const provider = PROVIDERS[providerId];
      const clientId = settings.providers[providerId].clientId;
      if (!clientId) throw new Error('missing_client_id');
      const ctx = { settings, fetch: fetchImpl };
      let token = await getToken(providerId, clientId, { interactive });
      try {
        return await provider.upload(ctx, token, file);
      } catch (error) {
        if (error.status !== 401) throw error;
        // Token revoked or expired early: re-authorise once and retry.
        await forgetToken(providerId);
        token = await getToken(providerId, clientId, { interactive, forceRefresh: true });
        return provider.upload(ctx, token, file);
      }
    }

    // Upload one exported CSV to every enabled provider.  Never throws: each
    // provider reports its own ok/error so a Drive failure cannot hide a
    // successful Dropbox upload or break the local download.
    async function uploadExport(filename, csv, options) {
      const opts = options || {};
      const settings = await loadSettings();
      const enabled = Object.keys(PROVIDERS).filter((id) => settings.providers[id].enabled);
      if (!opts.force && (!settings.autoUpload || !enabled.length)) return [];
      const file = {
        name: timestampedFilename(filename, new Date(now())),
        mimeType: 'text/csv',
        blob: new Blob([csv], { type: 'text/csv;charset=utf-8' }),
      };
      const results = [];
      // Chrome stops an idle service worker after 30 s; a long upload is not
      // extension activity, so ping an extension API while it runs.
      const keepAlive = chromeApi.runtime && chromeApi.runtime.getPlatformInfo
        ? setInterval(() => chromeApi.runtime.getPlatformInfo(() => {}), KEEPALIVE_INTERVAL_MS)
        : null;
      try {
        for (const id of enabled) {
          try {
            const outcome = await uploadToProvider(id, settings, file, opts.interactive !== false);
            results.push({ provider: id, label: PROVIDERS[id].label, ok: true, name: file.name, link: outcome.link || '', path: outcome.path || '' });
          } catch (error) {
            results.push({ provider: id, label: PROVIDERS[id].label, ok: false, name: file.name, error: String(error && error.message || error).slice(0, 300) });
          }
        }
      } finally {
        if (keepAlive) clearInterval(keepAlive);
      }
      try {
        await chromeApi.storage.local.set({
          [LAST_UPLOAD_KEY]: { at: new Date(now()).toISOString(), filename: file.name, results },
        });
      } catch (error) {
        // Status history is best effort; it must not turn a finished export
        // and upload into a reported failure.
        console.warn('Cloud upload status could not be saved', error);
      }
      return results;
    }

    return { loadSettings, saveSettings, connect, getToken, uploadExport, forgetToken };
  }

  const api = {
    PROVIDERS,
    DEFAULT_SETTINGS,
    SETTINGS_KEY,
    LAST_UPLOAD_KEY,
    createCloud,
    normaliseSettings,
    normaliseFolder,
    timestampedFilename,
    headerSafeJson,
    parseRedirect,
    pkceChallenge,
    encodePath,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.QuickSaverCloud = api;
}(typeof self !== 'undefined' ? self : globalThis));
