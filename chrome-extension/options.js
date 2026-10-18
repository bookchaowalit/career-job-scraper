// Quick Saver — cloud storage options page.

document.addEventListener('DOMContentLoaded', async () => {
  const { createCloud, PROVIDERS, LAST_UPLOAD_KEY } = self.QuickSaverCloud;
  const cloud = createCloud({ chrome, fetch: (...args) => fetch(...args) });

  const autoUpload = document.getElementById('autoUpload');
  const folder = document.getElementById('folder');
  const saveStatus = document.getElementById('saveStatus');
  const cards = Array.from(document.querySelectorAll('[data-provider]'));

  document.getElementById('redirectUri').textContent = chrome.identity.getRedirectURL();

  function setStatus(element, text, kind) {
    element.textContent = text;
    element.className = `status ${kind || ''}`.trim();
  }

  function readForm() {
    const providers = {};
    cards.forEach((card) => {
      providers[card.dataset.provider] = {
        enabled: card.querySelector('.enabled').checked,
        clientId: card.querySelector('.client-id').value,
      };
    });
    return { autoUpload: autoUpload.checked, folder: folder.value, providers };
  }

  function fillForm(settings) {
    autoUpload.checked = settings.autoUpload;
    folder.value = settings.folder;
    cards.forEach((card) => {
      const provider = settings.providers[card.dataset.provider];
      card.querySelector('.enabled').checked = provider.enabled;
      card.querySelector('.client-id').value = provider.clientId;
    });
  }

  async function renderLastUpload() {
    const target = document.getElementById('lastUpload');
    const stored = await chrome.storage.local.get([LAST_UPLOAD_KEY]);
    const last = stored[LAST_UPLOAD_KEY];
    if (!last || !Array.isArray(last.results) || !last.results.length) return;
    const lines = [document.createElement('p')];
    lines[0].textContent = `${last.filename} — ${new Date(last.at).toLocaleString()}`;
    last.results.forEach((result) => {
      const line = document.createElement('p');
      line.className = result.ok ? 'ok' : 'err';
      line.textContent = result.ok ? `✓ ${result.label}` : `✗ ${result.label}: ${result.error}`;
      if (result.ok && /^https:\/\//.test(result.link || '')) {
        const link = document.createElement('a');
        link.href = result.link;
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = ' เปิดไฟล์';
        link.style.color = '#93c5fd';
        line.append(link);
      }
      lines.push(line);
    });
    target.replaceChildren(...lines);
  }

  fillForm(await cloud.loadSettings());
  renderLastUpload();

  document.getElementById('save').addEventListener('click', async () => {
    const saved = await cloud.saveSettings(readForm());
    fillForm(saved);
    const missing = Object.keys(saved.providers)
      .filter((id) => saved.providers[id].enabled && !saved.providers[id].clientId)
      .map((id) => PROVIDERS[id].label);
    if (missing.length) {
      setStatus(saveStatus, `บันทึกแล้ว แต่ยังไม่มี Client ID: ${missing.join(', ')}`, 'err');
    } else {
      setStatus(saveStatus, 'บันทึกแล้ว', 'ok');
    }
  });

  cards.forEach((card) => {
    const providerId = card.dataset.provider;
    const status = card.querySelector('.status');
    card.querySelector('.connect').addEventListener('click', async () => {
      // Save first so the connection test uses what is on screen.
      fillForm(await cloud.saveSettings(readForm()));
      setStatus(status, 'กำลังเชื่อมต่อ…');
      try {
        await cloud.connect(providerId);
        setStatus(status, 'เชื่อมต่อแล้ว', 'ok');
      } catch (error) {
        const message = String(error && error.message || error);
        setStatus(status, message === 'missing_client_id' ? 'ใส่ Client ID ก่อน' : `เชื่อมต่อไม่สำเร็จ: ${message}`, 'err');
      }
    });
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes[LAST_UPLOAD_KEY]) renderLastUpload();
  });
});
