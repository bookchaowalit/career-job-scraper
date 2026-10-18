// Quick Job Saver — Background Service Worker

importScripts('cloud.js', 'sheet.js');
const cloud = self.QuickSaverCloud.createCloud({ chrome, fetch: (...args) => fetch(...args) });
const sheet = self.QuickSaverSheet.createSheet({ chrome, fetch: (...args) => fetch(...args) });

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
  const postUrl = normaliseFacebookGroupUrl(post.post_url);
  if (!groupUrl || !postUrl || !/^\/groups\/[^/]+$/i.test(new URL(groupUrl).pathname)) return null;
  const postPath = new URL(postUrl).pathname;
  if (!(/\/groups\/[^/]+\/(?:posts|permalink)\/[^/]+/i.test(postPath) || /\/(?:permalink|story)\.php$/i.test(postPath) || /\/(?:posts|permalink)\/[^/]+/i.test(postPath))) return null;
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
    capture_method: ['chrome_extension_visible_tab', 'manual_browser_export', 'playwright_visible_tab'].includes(post.capture_method)
      ? post.capture_method : 'chrome_extension_visible_tab',
    source_channel: 'facebook_group',
    source_platform: 'facebook',
    captured_at: post.captured_at || new Date().toISOString(),
  };
}

async function saveFacebookGroupPostsLocally(posts, sendResponse) {
  try {
    const { savedFacebookGroupPosts = [] } = await chrome.storage.local.get(['savedFacebookGroupPosts']);
    const byUrl = new Map(savedFacebookGroupPosts.map((post) => [post.post_url, post]));
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
