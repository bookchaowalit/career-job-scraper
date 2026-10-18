// Quick Saver — optional Google Sheet sink for Facebook Group posts.
//
// Off by default.  When enabled in the options page, posts the operator saves
// or exports are appended to a Google Sheet through the operator's own Apps
// Script web app (integrations/google-sheet/Code.gs).  Only rows the operator
// labelled `public` are sent; private and unknown rows stay local, matching
// the importer's quarantine rule.  Rows that cannot be delivered are kept in
// a bounded local queue and retried on the next send.
//
// Loaded by background.js (importScripts) and options.js (<script>); the tests
// load it with require() and inject fake chrome/fetch objects.

(function (root) {
  const SETTINGS_KEY = 'sheetSettings';
  const PENDING_KEY = 'sheetPendingRows';
  const LAST_SEND_KEY = 'lastSheetSend';
  const PENDING_LIMIT = 2000;
  const PENDING_BYTE_LIMIT = 4 * 1024 * 1024;
  const REQUEST_TIMEOUT_MS = 60 * 1000;
  const BANGKOK_OFFSET_MS = 7 * 60 * 60 * 1000;
  const WEB_APP_URL = /^https:\/\/script\.google\.com\/macros\/s\/[A-Za-z0-9_-]+\/exec$/;

  function normaliseSettings(raw) {
    const input = raw && typeof raw === 'object' ? raw : {};
    const url = String(input.url || '').trim();
    return {
      enabled: input.enabled === true,
      url: WEB_APP_URL.test(url) ? url : '',
      secret: String(input.secret || '').trim().slice(0, 200),
    };
  }

  // ISO 8601 in Asia/Bangkok (UTC+7, no daylight saving).
  function bangkokIso(value) {
    const parsed = new Date(value || Date.now());
    const time = Number.isNaN(parsed.getTime()) ? Date.now() : parsed.getTime();
    return new Date(time + BANGKOK_OFFSET_MS).toISOString().replace(/\.\d{3}Z$/, '+07:00');
  }

  function toRow(post) {
    return {
      collected_at: bangkokIso(post.captured_at),
      group_name: String(post.group_name || '').slice(0, 240),
      group_url: String(post.group_url || ''),
      permalink: String(post.post_url || ''),
      poster: String(post.author_name || '').slice(0, 160),
      posted: String(post.posted_at || '').slice(0, 80),
      text: String(post.text || '').slice(0, 10000),
      text_complete: post.text_complete === true,
    };
  }

  // Same preference as background.js isBetterFacebookGroupPost: complete text
  // first, then longer text, then poster/time present.
  function rowScore(row) {
    return (row.text_complete ? 1e9 : 0) + String(row.text || '').length * 10
      + (row.poster ? 2 : 0) + (row.posted ? 1 : 0);
  }

  function createSheet(deps) {
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

    async function post(settings, rows) {
      const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
      const timer = controller ? setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS) : null;
      try {
        // text/plain keeps this a "simple" request (no CORS preflight, which
        // Apps Script does not answer).  The 302 to googleusercontent.com is
        // followed by fetch.
        const response = await fetchImpl(settings.url, {
          method: 'POST',
          headers: { 'Content-Type': 'text/plain;charset=utf-8' },
          body: JSON.stringify({ secret: settings.secret, rows }),
          redirect: 'follow',
          signal: controller ? controller.signal : undefined,
        });
        const text = await response.text();
        if (!response.ok) throw new Error(`sheet_http_${response.status}`);
        let body;
        try { body = JSON.parse(text); } catch (error) { body = null; }
        // Accept our Code.gs ({ok:true, added}) and the minimal variant that
        // returns only {added}; anything else (e.g. "forbidden") is a reject.
        if (!body || (body.ok !== true && typeof body.added !== 'number')) {
          const err = new Error(`sheet_rejected:${(body && body.error) || text.slice(0, 80)}`);
          err.permanent = true;
          throw err;
        }
        return body;
      } catch (error) {
        if (error && error.name === 'AbortError') throw new Error('sheet_timeout');
        throw error;
      } finally {
        if (timer) clearTimeout(timer);
      }
    }

    // Sends are serialised: each one reads and rewrites the shared queue.
    let chain = Promise.resolve();
    function serialise(task) {
      const run = chain.then(task, task);
      chain = run.catch(() => {});
      return run;
    }

    // Keep the newest rows whose JSON fits the byte budget (storage.local is
    // capped at 10 MB without unlimitedStorage).
    function boundQueue(rows) {
      const kept = [];
      let bytes = 2;
      for (let i = rows.length - 1; i >= 0 && kept.length < PENDING_LIMIT; i -= 1) {
        const size = JSON.stringify(rows[i]).length * 3 + 1;
        if (bytes + size > PENDING_BYTE_LIMIT) break;
        bytes += size;
        kept.unshift(rows[i]);
      }
      return kept;
    }

    async function readQueue() {
      const stored = await chromeApi.storage.local.get([PENDING_KEY]);
      return Array.isArray(stored[PENDING_KEY]) ? stored[PENDING_KEY] : [];
    }

    // Send posts (plus anything still queued).  Never throws: the result says
    // what happened so a Sheet outage cannot break a local save or export.
    function sendPosts(posts, options) {
      return serialise(() => sendPostsNow(posts, options));
    }

    async function sendPostsNow(posts, options) {
      const opts = options || {};
      const list = (Array.isArray(posts) ? posts : []).filter((p) => p && p.post_url);
      const publicPosts = list.filter((p) => p.visibility === 'public');
      // The latest label wins: a post now marked private/unknown is withdrawn
      // from the retry queue, even while the sink is switched off.
      const withdrawn = new Set(list.filter((p) => p.visibility !== 'public').map((p) => p.post_url));
      const skipped = list.length - publicPosts.length;
      const queued = await readQueue();
      if (withdrawn.size && queued.some((row) => row && withdrawn.has(row.permalink))) {
        await chromeApi.storage.local.set({ [PENDING_KEY]: queued.filter((row) => row && !withdrawn.has(row.permalink)) });
      }

      const settings = await loadSettings();
      if (!settings.enabled && !opts.force) return null;
      if (!settings.url || !settings.secret) {
        return { ok: false, error: 'sheet_not_configured', sent: 0, added: 0, skipped, pending: 0 };
      }

      const byLink = new Map();
      queued.forEach((row) => {
        if (row && row.permalink && !withdrawn.has(row.permalink)) byLink.set(row.permalink, row);
      });
      // Never replace a fuller queued copy with a truncated recapture.
      publicPosts.map(toRow).forEach((row) => {
        const current = byLink.get(row.permalink);
        if (!current || rowScore(row) >= rowScore(current)) byLink.set(row.permalink, row);
      });
      const rows = boundQueue(Array.from(byLink.values()));

      // Persist before the request so a closed browser or reloaded extension
      // cannot lose rows that were never confirmed.
      try {
        await chromeApi.storage.local.set({ [PENDING_KEY]: rows });
      } catch (error) {
        console.warn('Sheet queue could not be saved', error);
        return { ok: false, error: 'sheet_queue_not_saved', sent: 0, added: 0, skipped, pending: 0 };
      }

      let result;
      // Keep the service worker alive while the request runs (Chrome stops an
      // idle worker after 30 s and a pending fetch does not count).
      const keepAlive = chromeApi.runtime && chromeApi.runtime.getPlatformInfo
        ? setInterval(() => chromeApi.runtime.getPlatformInfo(() => {}), 20 * 1000)
        : null;
      try {
        if (!rows.length && !opts.force) {
          result = { ok: true, sent: 0, added: 0, skipped, pending: 0 };
        } else {
          let lastError = null;
          for (let attempt = 0; attempt < 2; attempt += 1) {
            try {
              const body = await post(settings, rows);
              lastError = null;
              result = { ok: true, sent: rows.length, added: Number(body.added || 0), skipped, pending: 0 };
              break;
            } catch (error) {
              lastError = error;
              if (error.permanent) break;
            }
          }
          if (lastError) {
            result = { ok: false, error: String(lastError.message || lastError).slice(0, 200), sent: 0, added: 0, skipped, pending: rows.length };
          }
        }
      } finally {
        if (keepAlive) clearInterval(keepAlive);
      }
      try {
        if (result.ok) {
          // Remove only what this request delivered.
          const delivered = new Set(rows.map((row) => row.permalink));
          await chromeApi.storage.local.set({ [PENDING_KEY]: (await readQueue()).filter((row) => !delivered.has(row.permalink)) });
        }
        await chromeApi.storage.local.set({ [LAST_SEND_KEY]: { at: new Date(now()).toISOString(), ...result } });
      } catch (error) {
        console.warn('Sheet send status could not be saved', error);
      }
      return result;
    }

    // Connection test: an empty batch checks the URL and secret without
    // writing a row.
    async function testConnection() {
      const settings = await loadSettings();
      if (!settings.url || !settings.secret) return { ok: false, error: 'sheet_not_configured' };
      try {
        await post(settings, []);
        return { ok: true };
      } catch (error) {
        return { ok: false, error: String(error.message || error).slice(0, 200) };
      }
    }

    return { loadSettings, saveSettings, sendPosts, testConnection };
  }

  const api = { createSheet, normaliseSettings, bangkokIso, toRow, SETTINGS_KEY, PENDING_KEY, LAST_SEND_KEY, WEB_APP_URL };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.QuickSaverSheet = api;
}(typeof self !== 'undefined' ? self : globalThis));
