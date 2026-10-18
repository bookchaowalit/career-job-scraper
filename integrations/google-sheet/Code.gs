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
    const existing = new Set(last > 1 ? sh.getRange(2, 4, last - 1, 1).getValues().flat().map(String) : []);
    const rows = [];
    incoming.forEach(function (r) {
      const link = r && String(r.permalink || '');
      if (!/^https:\/\/facebook\.com\//.test(link) || existing.has(link)) return;
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
