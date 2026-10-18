/**
 * Quick Saver -> Google Sheet receiver.
 *
 * Paste into the target Sheet via Extensions > Apps Script, then:
 *   1. Project Settings > Script properties > add SECRET = <long random value>
 *      (the same value goes in the extension's options page) and
 *      SPREADSHEET_ID = the id in the Sheet URL (/spreadsheets/d/<id>/edit).
 *   2. Deploy > New deployment > Web app; Execute as: Me; Who has access: Anyone.
 *   3. Copy the /exec URL into the extension's options page.
 *
 * The extension only sends rows the operator labelled public.  Rows are
 * deduplicated by permalink and cells that would run as formulas are stored
 * as text.
 */

const SHEET_NAME = 'raw_posts';
const HEADER = ['collected_at', 'group_name', 'group_url', 'permalink', 'poster', 'posted', 'text', 'text_complete', 'processed'];
const MAX_ROWS_PER_REQUEST = 2000;

// Same rule as canonicalFacebookPostUrl in the extension and the Python
// importer: one URL per post, without Facebook's per-load __cft__/__tn__.
function canonicalPostUrl_(value) {
  const m = String(value || '').trim().match(/^https:\/\/(?:(?:www|m|web)\.)?facebook\.com(\/[^?#]*)(?:\?([^#]*))?/i);
  if (!m) return '';
  const path = m[1].replace(/\/+$/, '');
  const group = path.match(/^\/groups\/([^/]+)\/(?:posts|permalink)\/([^/]+)$/i);
  if (group) return 'https://facebook.com/groups/' + group[1] + '/posts/' + group[2];
  if (/^\/(?:permalink|story)\.php$/i.test(path)) {
    const params = {};
    String(m[2] || '').split('&').forEach(function (pair) {
      const i = pair.indexOf('=');
      if (i > 0) params[pair.slice(0, i)] = pair.slice(i + 1);
    });
    if (!params.story_fbid) return '';
    const kept = ['id', 'story_fbid'].filter(function (k) { return params[k]; }).map(function (k) { return k + '=' + params[k]; });
    return 'https://facebook.com' + path.toLowerCase() + '?' + kept.join('&');
  }
  if (/^\/(?:posts|permalink|story)\/[^/]+$/i.test(path)) return 'https://facebook.com' + path;
  return '';
}

function json_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}

// setValues() treats a string starting with = + - @ as a formula.
function cell_(value) {
  if (typeof value === 'boolean') return value;
  const text = String(value == null ? '' : value).slice(0, 10000);
  return /^[=+\-@]/.test(text) ? "'" + text : text;
}

// Web-app requests have no "active" spreadsheet guarantee, so prefer an
// explicit SPREADSHEET_ID script property and fall back to the bound Sheet.
function spreadsheet_() {
  const id = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
  const ss = id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('Set the SPREADSHEET_ID script property');
  return ss;
}

function doPost(e) {
  const secret = PropertiesService.getScriptProperties().getProperty('SECRET');
  let body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({ ok: false, error: 'bad_json' });
  }
  if (!secret || !body || body.secret !== secret) return json_({ ok: false, error: 'forbidden' });
  const incoming = Array.isArray(body.rows) ? body.rows.slice(0, MAX_ROWS_PER_REQUEST) : [];

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const ss = spreadsheet_();
    const sh = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
    if (sh.getLastRow() === 0) sh.appendRow(HEADER);
    const last = sh.getLastRow();
    // Compare canonical forms so rows written before the fix still dedupe.
    const existing = new Set(last > 1 ? sh.getRange(2, 4, last - 1, 1).getValues().flat().map(canonicalPostUrl_) : []);
    const rows = [];
    incoming.forEach(function (r) {
      const link = canonicalPostUrl_(r && r.permalink);
      if (!link || existing.has(link)) return;
      existing.add(link);
      rows.push([r.collected_at, r.group_name, r.group_url, link, r.poster, r.posted, r.text, r.text_complete === true, ''].map(cell_));
    });
    if (rows.length) sh.getRange(last + 1, 1, rows.length, HEADER.length).setValues(rows);
    // Commit before the lock is released so a concurrent request sees these
    // rows (and the new last row) instead of overwriting them.
    SpreadsheetApp.flush();
    return json_({ ok: true, added: rows.length });
  } finally {
    lock.releaseLock();
  }
}

/**
 * One-off cleanup for rows added before permalinks were canonical: rewrites
 * column D to the canonical URL and deletes later duplicates (keeps the first
 * row for each post).  Run it once from the Apps Script editor (select
 * cleanUpDuplicatePermalinks, then Run).  Takes the same lock as doPost.
 */
function cleanUpDuplicatePermalinks() {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const sh = spreadsheet_().getSheetByName(SHEET_NAME);
    if (!sh || sh.getLastRow() < 2) return 'nothing to clean';
    const range = sh.getRange(2, 4, sh.getLastRow() - 1, 1);
    const links = range.getValues().map(function (row) { return row[0]; });
    const seen = new Set();
    const duplicates = [];
    const rewritten = links.map(function (link, i) {
      const canonical = canonicalPostUrl_(link) || String(link);
      if (seen.has(canonical)) duplicates.push(i + 2);
      seen.add(canonical);
      return [canonical];
    });
    range.setValues(rewritten);
    // Delete from the bottom so row numbers stay valid.
    duplicates.reverse().forEach(function (row) { sh.deleteRow(row); });
    SpreadsheetApp.flush();
    const message = 'removed ' + duplicates.length + ' duplicate rows';
    Logger.log(message);
    return message;
  } finally {
    lock.releaseLock();
  }
}
