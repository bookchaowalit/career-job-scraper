// Quick Job Saver — Background Service Worker

importScripts('cloud.js', 'sheet.js');
const cloud = self.QuickSaverCloud.createCloud({ chrome, fetch: (...args) => fetch(...args) });
const sheet = self.QuickSaverSheet.createSheet({
  chrome,
  fetch: (...args) => fetch(...args),
  // Queued rows from before 1.4 carry __cft__ URLs; compare canonical forms.
  canonical: (url) => canonicalFacebookPostUrl(url),
});

// Create context menu on install
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'saveJob',
    title: '💼 Save job to Pipeline',
    contexts: ['page', 'link'],
  });

  chrome.contextMenus.create({
    id: 'saveAndApply',
    title: '📤 Save & mark as Applied',
    contexts: ['page', 'link'],
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'saveJob' || info.menuItemId === 'saveAndApply') {
    const url = info.linkUrl || tab.url;
    const jobData = {
      title: tab.title || 'Unknown Position',
      company: '',
      url: url,
      location: '',
      salary: '',
      notes: '',
      board: new URL(url).hostname.replace('www.', ''),
      saved_at: new Date().toISOString(),
      status: info.menuItemId === 'saveAndApply' ? 'applied' : 'saved',
    };

    // Save to storage
    const { savedJobs = [] } = await chrome.storage.local.get(['savedJobs']);
    savedJobs.push(jobData);
    await chrome.storage.local.set({ savedJobs });

    // Update stats
    const { stats = {} } = await chrome.storage.local.get(['stats']);
    stats.saved = (stats.saved || 0) + 1;
    stats.todaySaved = (stats.todaySaved || 0) + 1;
    stats.lastDate = new Date().toDateString();
    if (jobData.status === 'applied') stats.applied = (stats.applied || 0) + 1;
    await chrome.storage.local.set({ stats });

    // Notify user
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: 'Job Saved!',
      message: `${jobData.title} saved to pipeline.`,
    });
  }
});

// Handle messages from popup and content script.  Keep this listener itself
// synchronous: Chrome's message channel is held open explicitly while the
// storage/download promise runs, so the popup always receives a response.
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'saveJob' || request.action === 'quickSave') {
    (async () => {
      const { savedJobs = [] } = await chrome.storage.local.get(['savedJobs']);
      if (savedJobs.length >= 10) await exportToCSV(savedJobs);
    })();
    return false;
  }

  if (request.action === 'saveProperty') {
    savePropertyLocally(request.property || {}, sendResponse);
    return true;
  }

  if (request.action === 'exportProperties') {
    exportProperties(request, sendResponse);
    return true;
  }

  if (request.action === 'saveFacebookGroupPosts') {
    saveFacebookGroupPostsLocally(request.posts || [], sendResponse);
    return true;
  }

  if (request.action === 'exportFacebookGroupPosts') {
    exportFacebookGroupPosts(request, sendResponse);
    return true;
  }

  if (request.action === 'exportFacebookGroupCapture') {
    exportFacebookGroupPosts(request, sendResponse);
    return true;
  }

  if (request.action === 'writeCaptureDraft') {
    recordAutoCapture(request, sender).then(() => sendResponse({ ok: true }), () => sendResponse({ ok: false }));
    return true;
  }

  if (request.action === 'autoCaptureBatch' || request.action === 'autoCaptureDone') {
    recordAutoCapture(request, sender).then(() => sendResponse({ ok: true }), () => sendResponse({ ok: false }));
    return true;
  }

  return false;
});

async function savePropertyLocally(property, sendResponse) {
  try {
    const { savedProperties = [] } = await chrome.storage.local.get(['savedProperties']);
    savedProperties.push({
      title: String(property.title || '').slice(0, 240),
      url: String(property.url || ''),
      location: String(property.location || '').slice(0, 240),
      price_raw: String(property.price_raw || '').slice(0, 160),
      bedrooms: String(property.bedrooms || '').slice(0, 20),
      bathrooms: String(property.bathrooms || '').slice(0, 20),
      area_sqm: String(property.area_sqm || '').slice(0, 20),
      listing_type: String(property.listing_type || '').slice(0, 100),
      description: String(property.description || '').slice(0, 5000),
      captured_at: property.captured_at || new Date().toISOString(),
      source: 'solo_empire_chrome_extension',
    });
    await chrome.storage.local.set({ savedProperties });
    sendResponse({ ok: true, count: savedProperties.length });
  } catch (error) {
    console.warn('Property capture could not be saved locally', error);
    sendResponse({ ok: false, count: 0 });
  }
}

async function exportProperties(request, sendResponse) {
  try {
    const { savedProperties = [] } = await chrome.storage.local.get(['savedProperties']);
    if (!savedProperties.length) {
      sendResponse({ ok: false, count: 0 });
      return;
    }
    const { count, csv } = await exportPropertiesToCSV(savedProperties);
    const uploads = await cloud.uploadExport('property_owner_coagent_export.csv', csv);
    sendResponse({ ok: true, count, uploads });
  } catch (error) {
    console.warn('Property capture could not be exported', error);
    sendResponse({ ok: false, count: 0 });
  }
}

const FACEBOOK_GROUP_STORAGE_LIMIT = 500;
const FACEBOOK_CAPTURE_METHODS = ['chrome_extension_visible_tab', 'chrome_extension_auto_scroll', 'manual_browser_export', 'playwright_visible_tab'];
const AUTO_CAPTURE_STATUS_KEY = 'autoCaptureStatus';

// Auto-scroll batches land in the same capture draft the popup keeps, so the
// operator reviews them, confirms visibility, and saves as with a manual
// capture.  Writes are serialised because batches can arrive back to back.
let autoCaptureWrite = Promise.resolve();
function recordAutoCapture(request, sender) {
  const run = autoCaptureWrite.then(() => applyAutoCapture(request, sender));
  // Keep the queue alive after a failure, but report it to the caller so a
  // batch that was not stored is retried or ends the run.
  autoCaptureWrite = run.catch((error) => {
    console.warn('Auto-capture batch could not be stored', error);
  });
  return run;
}

function mergeDraftPosts(existing, incoming, groupUrl) {
  const byUrl = new Map();
  [...(existing || []), ...(incoming || [])].forEach((post) => {
    const key = canonicalFacebookPostUrl(post && post.post_url);
    if (!key) return;
    const candidate = { ...post, post_url: key, group_url: groupUrl };
    const current = byUrl.get(key);
    if (!current || isBetterFacebookGroupPost(candidate, current)) byUrl.set(key, candidate);
  });
  return Array.from(byUrl.values()).slice(-FACEBOOK_GROUP_STORAGE_LIMIT);
}

// The popup's own draft writes go through the same queue, merging with any
// posts auto-capture added meanwhile instead of overwriting them.
async function writePopupDraft(request) {
  const draft = request.draft || {};
  if (!Array.isArray(draft.posts) || !draft.posts.length) {
    await chrome.storage.local.remove(['facebookGroupCaptureDraft']);
    return;
  }
  const groupUrl = normaliseFacebookGroupUrl(draft.group_url);
  if (!groupUrl) return;
  const { facebookGroupCaptureDraft: stored } = await chrome.storage.local.get(['facebookGroupCaptureDraft']);
  const sameGroup = stored && stored.group_url === groupUrl && Array.isArray(stored.posts);
  await chrome.storage.local.set({
    facebookGroupCaptureDraft: {
      ...draft,
      group_url: groupUrl,
      posts: mergeDraftPosts(sameGroup ? stored.posts : [], draft.posts, groupUrl),
    },
  });
}

async function applyAutoCapture(request, sender) {
  if (request.action === 'writeCaptureDraft') {
    await writePopupDraft(request);
    return;
  }
  const group = request.group || {};
  const groupUrl = normaliseFacebookGroupUrl(group.group_url);
  const now = new Date().toISOString();
  const stored = await chrome.storage.local.get(['facebookGroupCaptureDraft', AUTO_CAPTURE_STATUS_KEY]);
  const status = stored[AUTO_CAPTURE_STATUS_KEY] || {};
  // Only the run the popup started last may write; a leftover run (an older
  // tab, or one superseded by a new start) is ignored.
  if (status.run_id && request.runId !== status.run_id) return;

  if (request.action === 'autoCaptureDone') {
    await chrome.storage.local.set({
      [AUTO_CAPTURE_STATUS_KEY]: {
        ...status,
        running: false,
        finished_at: now,
        reason: String(request.reason || ''),
        error: String(request.error || '').slice(0, 200),
        found: Number(request.found || 0),
      },
    });
    return;
  }

  if (!groupUrl) return;
  let draft = stored.facebookGroupCaptureDraft;
  const draftTime = Date.parse(String(draft && draft.last_updated_at || ''));
  const runStart = Date.parse(String(status.started_at || ''));
  // A draft of another group made after this run started is the operator's
  // newer capture: keep it and drop this batch.
  if (draft && draft.group_url !== groupUrl && Number.isFinite(draftTime) && Number.isFinite(runStart) && draftTime > runStart) return;
  // An older draft from another group is replaced; the operator chose to
  // start a capture on this group.
  if (!draft || draft.group_url !== groupUrl || !Array.isArray(draft.posts)) {
    draft = { group_url: groupUrl, group_name: '', captured_at: now, capture_rounds: 0, visibility: 'unknown', posts: [] };
  }
  const posts = mergeDraftPosts(draft.posts, Array.isArray(request.posts) ? request.posts : [], groupUrl);
  await chrome.storage.local.set({
    facebookGroupCaptureDraft: {
      ...draft,
      group_name: String(group.group_name || draft.group_name || '').slice(0, 240),
      capture_rounds: (Number(draft.capture_rounds) || 0) + 1,
      last_updated_at: now,
      posts,
    },
    [AUTO_CAPTURE_STATUS_KEY]: {
      ...status,
      running: true,
      group_url: groupUrl,
      tab_id: sender && sender.tab ? sender.tab.id : status.tab_id,
      found: posts.length,
      updated_at: now,
    },
  });
}

// One canonical form per post, shared with the Python importer and Code.gs:
// https://facebook.com/groups/<g>/posts/<id> with no query (Facebook adds
// per-load __cft__/__tn__ tokens), and permalink.php/story.php reduced to
// story_fbid + id.  Without this the same post dedupes as a new row on every
// page load.
function canonicalFacebookPostUrl(value) {
  let parsed;
  try {
    parsed = new URL(String(value || '').trim());
  } catch (error) {
    return '';
  }
  const host = parsed.hostname.toLowerCase().replace(/^(www|m|web)\./, '');
  if (parsed.protocol !== 'https:' || (host !== 'facebook.com' && !host.endsWith('.facebook.com')) || parsed.username || parsed.password || parsed.port) return '';
  const path = parsed.pathname.replace(/\/+$/, '');
  const group = path.match(/^\/groups\/([^/]+)\/(?:posts|permalink)\/([^/]+)$/i);
  if (group) return `https://facebook.com/groups/${group[1]}/posts/${group[2]}`;
  if (/^\/(?:permalink|story)\.php$/i.test(path)) {
    const keep = new URLSearchParams();
    ['id', 'story_fbid'].forEach((key) => {
      const found = parsed.searchParams.get(key);
      if (found) keep.set(key, found);
    });
    if (!keep.get('story_fbid')) return '';
    return `https://facebook.com${path.toLowerCase()}?${keep.toString()}`;
  }
  if (/^\/(?:posts|permalink|story)\/[^/]+$/i.test(path)) return `https://facebook.com${path}`;
  return '';
}

function normaliseFacebookGroupUrl(value) {
  try {
    const parsed = new URL(String(value || '').trim());
    const host = parsed.hostname.toLowerCase().replace(/^www\./, '');
    if (parsed.protocol !== 'https:' || (host !== 'facebook.com' && !host.endsWith('.facebook.com')) || parsed.username || parsed.password || parsed.port) return '';
    parsed.hostname = 'facebook.com';
    parsed.hash = '';
    const params = new URLSearchParams(parsed.search);
    [...params.keys()].forEach((key) => {
      if (/^(utm_|fbclid$|gclid$|dclid$|ref$|referrer$|source$|src$)/i.test(key)) params.delete(key);
    });
    params.sort();
    parsed.search = params.toString();
    parsed.pathname = parsed.pathname.replace(/\/+$/, '') || '/';
    return parsed.toString();
  } catch (error) {
    return '';
  }
}

function normaliseBoolean(value) {
  if (typeof value === 'boolean') return value;
  return ['1', 'true', 'yes', 'y', 'complete'].includes(String(value || '').trim().toLowerCase());
}

function facebookGroupPostScore(post) {
  return [
    normaliseBoolean(post && post.text_complete),
    String(post && post.text || '').trim().length,
    Boolean(post && post.author_name),
    Boolean(post && post.posted_at),
  ].map((value) => Number(value));
}

function isBetterFacebookGroupPost(candidate, current) {
  const candidateScore = facebookGroupPostScore(candidate);
  const currentScore = facebookGroupPostScore(current);
  for (let index = 0; index < candidateScore.length; index += 1) {
    if (candidateScore[index] !== currentScore[index]) return candidateScore[index] > currentScore[index];
  }
  return false;
}

function sanitiseFacebookGroupPost(post) {
  const groupUrl = normaliseFacebookGroupUrl(post.group_url);
  // canonicalFacebookPostUrl is the single path rule (shared with content.js).
  const postUrl = canonicalFacebookPostUrl(post.post_url);
  if (!groupUrl || !postUrl || !/^\/groups\/[^/]+$/i.test(new URL(groupUrl).pathname)) return null;
  const visibility = ['public', 'private', 'unknown'].includes(String(post.visibility || '').toLowerCase())
    ? String(post.visibility).toLowerCase() : 'unknown';
  return {
    group_url: groupUrl,
    post_url: postUrl,
    post_id: String(post.post_id || '').slice(0, 100),
    group_name: String(post.group_name || '').slice(0, 240),
    author_name: String(post.author_name || '').slice(0, 160),
    posted_at: String(post.posted_at || '').slice(0, 80),
    text: String(post.text || '').replace(/\s+/g, ' ').trim().slice(0, 10000),
    visibility,
    text_complete: normaliseBoolean(post.text_complete),
    capture_method: FACEBOOK_CAPTURE_METHODS.includes(post.capture_method)
      ? post.capture_method : 'chrome_extension_visible_tab',
    source_channel: 'facebook_group',
    source_platform: 'facebook',
    captured_at: post.captured_at || new Date().toISOString(),
  };
}

async function saveFacebookGroupPostsLocally(posts, sendResponse) {
  try {
    const { savedFacebookGroupPosts = [] } = await chrome.storage.local.get(['savedFacebookGroupPosts']);
    // Re-sanitise stored posts so pre-1.4 rows (with __cft__ URLs) merge with
    // their canonical recaptures instead of duplicating.
    const byUrl = new Map();
    savedFacebookGroupPosts.forEach((post) => {
      const clean = sanitiseFacebookGroupPost(post || {});
      if (clean && (!byUrl.has(clean.post_url) || isBetterFacebookGroupPost(clean, byUrl.get(clean.post_url)))) {
        byUrl.set(clean.post_url, clean);
      }
    });
    const cleaned = [];
    (Array.isArray(posts) ? posts : []).forEach((post) => {
      const clean = sanitiseFacebookGroupPost(post || {});
      if (clean) cleaned.push(clean);
      if (clean && clean.post_url && (!byUrl.has(clean.post_url) || isBetterFacebookGroupPost(clean, byUrl.get(clean.post_url)))) {
        byUrl.set(clean.post_url, clean);
      }
    });
    const next = Array.from(byUrl.values()).slice(-FACEBOOK_GROUP_STORAGE_LIMIT);
    await chrome.storage.local.set({ savedFacebookGroupPosts: next });
    // Optional Google Sheet sink (off unless enabled; public rows only).
    const sheetResult = await sheet.sendPosts(cleaned);
    sendResponse({ ok: true, count: next.length, sheet: sheetResult });
  } catch (error) {
    console.warn('Facebook Group capture could not be saved locally', error);
    sendResponse({ ok: false, count: 0 });
  }
}

async function exportFacebookGroupPosts(request, sendResponse) {
  try {
    const fromCapture = Array.isArray(request && request.posts);
    const stored = fromCapture
      ? request.posts
      : (await chrome.storage.local.get(['savedFacebookGroupPosts'])).savedFacebookGroupPosts || [];
    const byUrl = new Map();
    stored.forEach((post) => {
      const clean = sanitiseFacebookGroupPost(post || {});
      if (clean && clean.post_url && (!byUrl.has(clean.post_url) || isBetterFacebookGroupPost(clean, byUrl.get(clean.post_url)))) {
        byUrl.set(clean.post_url, clean);
      }
    });
    const exportPosts = Array.from(byUrl.values()).slice(-FACEBOOK_GROUP_STORAGE_LIMIT);
    if (!exportPosts.length) {
      sendResponse({ ok: false, count: 0 });
      return;
    }
    const header = 'group_url,post_url,post_id,group_name,author_name,posted_at,text,visibility,text_complete,capture_method,captured_at,source_platform\n';
    const rows = exportPosts.map((post) => [
      post.group_url,
      post.post_url,
      post.post_id,
      post.group_name,
      post.author_name,
      post.posted_at,
      post.text,
      post.visibility,
      post.text_complete ? 'true' : 'false',
      post.capture_method,
      post.captured_at,
      'facebook',
    ].map(escapeCsv).join(',')).join('\n');
    const csv = header + rows;
    await chrome.storage.local.set({
      lastFacebookGroupExport: {
        csv,
        exportedAt: new Date().toISOString(),
        postCount: exportPosts.length,
        export_kind: fromCapture ? 'current_capture' : 'saved_posts',
      },
    });
    const filename = fromCapture ? 'facebook_group_current_capture.csv' : 'facebook_group_posts_export.csv';
    if (chrome.downloads && chrome.downloads.download) {
      await chrome.downloads.download({
        url: 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv),
        filename,
        saveAs: true,
      });
    }
    // Optional: also upload to the operator's own cloud storage (off unless
    // enabled in the options page).  Each provider reports its own result.
    const uploads = await cloud.uploadExport(filename, csv);
    // The current capture may never be saved, so send it to the Sheet here;
    // saved posts were already sent when they were saved.
    const sheetResult = fromCapture ? await sheet.sendPosts(exportPosts) : null;
    sendResponse({ ok: true, count: exportPosts.length, uploads, sheet: sheetResult });
  } catch (error) {
    console.warn('Facebook Group capture could not be exported', error);
    sendResponse({ ok: false, count: 0 });
  }
}

// Export saved jobs to CSV format compatible with pipeline
async function exportToCSV(jobs) {
  const header = 'id,title,company,url,location,salary_min,salary_max,board,source,scraped_at,description\n';
  const rows = jobs.map((job, i) => {
    const id = `chrome_${Date.now()}_${i}`;
    const title = escapeCsv(job.title);
    const company = escapeCsv(job.company);
    const url = escapeCsv(job.url);
    const location = escapeCsv(job.location);
    const board = escapeCsv(job.board);
    const savedAt = job.saved_at || new Date().toISOString();
    return `${id},${title},${company},${url},${location},0,0,${board},chrome_extension,${savedAt},`;
  }).join('\n');

  // Store CSV in chrome storage for later retrieval
  await chrome.storage.local.set({
    lastExport: {
      csv: header + rows,
      exportedAt: new Date().toISOString(),
      jobCount: jobs.length,
    }
  });
}

// Export a deliberately raw, user-selected property capture.  The Python
// importer performs source allowlisting, owner/co-agent extraction,
// deduplication, and property.v1 review defaults.  The only network call is
// the optional cloud upload of this CSV, made by the caller (cloud.js).
async function exportPropertiesToCSV(properties) {
  const header = 'title,url,location,price_raw,bedrooms,bathrooms,area_sqm,listing_type,description,captured_at,source\n';
  const rows = properties.map((property) => [
    property.title,
    property.url,
    property.location,
    property.price_raw,
    property.bedrooms,
    property.bathrooms,
    property.area_sqm,
    property.listing_type,
    property.description,
    property.captured_at,
    property.source,
  ].map(escapeCsv).join(',')).join('\n');
  const csv = header + rows;
  await chrome.storage.local.set({
    lastPropertyExport: {
      csv,
      exportedAt: new Date().toISOString(),
      propertyCount: properties.length,
    },
  });

  if (chrome.downloads && chrome.downloads.download) {
    await chrome.downloads.download({
      url: 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv),
      filename: 'property_owner_coagent_export.csv',
      saveAs: true,
    });
  }
  return { count: properties.length, csv };
}

function escapeCsv(value) {
  if (value === null || value === undefined || value === '') return '';
  let str = String(value);
  // Spreadsheet formula guard: a cell starting with = + - @ (or a tab/CR)
  // would run as a formula when the CSV is opened in Excel or Sheets.  The
  // Python importers strip this single leading quote again.
  if (/^[=+\-@\t\r]/.test(str)) str = `'${str}`;
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

// Keyboard shortcut: Ctrl+Shift+S to save current page as job
chrome.commands && chrome.commands.onCommand && chrome.commands.onCommand.addListener(async (command) => {
  if (command === 'save-job') {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const jobData = {
      title: tab.title || 'Unknown Position',
      url: tab.url,
      board: new URL(tab.url).hostname.replace('www.', ''),
      saved_at: new Date().toISOString(),
      status: 'saved',
    };

    const { savedJobs = [] } = await chrome.storage.local.get(['savedJobs']);
    savedJobs.push(jobData);
    await chrome.storage.local.set({ savedJobs });
  }
});
