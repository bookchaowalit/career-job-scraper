// Quick Job Saver — Popup Script
document.addEventListener('DOMContentLoaded', async () => {
  const saveBtn = document.getElementById('saveBtn');
  const saveApplyBtn = document.getElementById('saveApplyBtn');
  const successMsg = document.getElementById('successMsg');
  const jobStatus = document.getElementById('jobStatus');
  const propertyModeBtn = document.getElementById('propertyModeBtn');
  const propertyArea = document.getElementById('propertyArea');
  const propertyStatus = document.getElementById('propertyStatus');
  const propertySuccess = document.getElementById('propertySuccess');
  const facebookGroupModeBtn = document.getElementById('facebookGroupModeBtn');
  const facebookGroupArea = document.getElementById('facebookGroupArea');
  const facebookGroupStatus = document.getElementById('facebookGroupStatus');
  const facebookGroupVisibility = document.getElementById('facebookGroupVisibility');
  const facebookGroupPostsArea = document.getElementById('facebookGroupPosts');
  const captureNextFacebookGroupPageBtn = document.getElementById('captureNextFacebookGroupPageBtn');
  const saveFacebookGroupPostsBtn = document.getElementById('saveFacebookGroupPostsBtn');
  const exportFacebookGroupCaptureBtn = document.getElementById('exportFacebookGroupCaptureBtn');
  const exportFacebookGroupPostsBtn = document.getElementById('exportFacebookGroupPostsBtn');
  const clearFacebookGroupCaptureBtn = document.getElementById('clearFacebookGroupCaptureBtn');
  const facebookGroupSuccess = document.getElementById('facebookGroupSuccess');
  let facebookGroupCapture = { group_url: '', group_name: '', captured_at: '', posts: [] };
  let facebookGroupCaptureRounds = 0;
  const FACEBOOK_GROUP_DRAFT_LIMIT = 500;
  const FACEBOOK_GROUP_DRAFT_TTL_MS = 24 * 60 * 60 * 1000;

  // Load saved counts
  const data = await chrome.storage.local.get(['savedJobs', 'stats', 'facebookGroupCaptureDraft']);
  const stats = data.stats || { saved: 0, applied: 0, todaySaved: 0, lastDate: '' };
  const draft = data.facebookGroupCaptureDraft;
  const draftTimestamp = draft && Date.parse(String(draft.last_updated_at || draft.captured_at || ''));
  const draftIsFresh = Number.isFinite(draftTimestamp) && Math.abs(Date.now() - draftTimestamp) <= FACEBOOK_GROUP_DRAFT_TTL_MS;
  if (draftIsFresh && typeof draft === 'object' && String(draft.group_url || '').trim() && Array.isArray(draft.posts)) {
    facebookGroupCapture = {
      group_url: String(draft.group_url).trim(),
      group_name: String(draft.group_name || '').trim(),
      captured_at: String(draft.captured_at || ''),
      posts: mergeFacebookGroupPosts([], draft.posts).slice(-FACEBOOK_GROUP_DRAFT_LIMIT),
    };
    facebookGroupCaptureRounds = Math.max(0, Number(draft.capture_rounds) || 0);
    if (['public', 'private', 'unknown'].includes(String(draft.visibility || '').toLowerCase())) {
      facebookGroupVisibility.value = String(draft.visibility).toLowerCase();
    }
  } else if (draft) {
    // Drafts are convenience state, so stale capture data must not silently rejoin a later session.
    chrome.storage.local.remove(['facebookGroupCaptureDraft']);
  }

  // Reset daily counter
  const today = new Date().toDateString();
  if (stats.lastDate !== today) {
    stats.todaySaved = 0;
    stats.lastDate = today;
  }

  document.getElementById('savedCount').textContent = stats.todaySaved || 0;
  document.getElementById('totalCount').textContent = stats.saved || 0;
  document.getElementById('appliedCount').textContent = stats.applied || 0;

  // Get current tab info and detect job data
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // Try to extract job info from the page
  chrome.tabs.sendMessage(tab.id, { action: 'extractJob' }, (response) => {
    if (chrome.runtime.lastError) {
      // Content script not loaded — try to extract from URL
      extractFromUrl(tab.url);
      return;
    }
    if (response && response.job) {
      populateForm(response.job);
      jobStatus.classList.add('detected');
      jobStatus.innerHTML = `
        <p>✅ Job detected:</p>
        <div class="job-title">${response.job.title || 'Unknown'}</div>
        <div class="company">${response.job.company || 'Unknown'}</div>
      `;
    } else {
      extractFromUrl(tab.url);
    }
  });

  function extractFromUrl(url) {
    const urlObj = new URL(url);
    jobStatus.innerHTML = `<p>📋 Manual entry — fill in details below</p>`;

    // Try to extract from URL patterns
    const patterns = {
      'linkedin.com': /\/jobs\/view\/\d+/,
      'indeed.com': /\/viewjob\?jk=/,
      'glassdoor.com': /\/job-listing\//,
      'remotive.com': /\/jobs\//,
      'weworkremotely.com': /\/jobs\//,
      'wellfound.com': /\/jobs\//,
      'otta.com': /\/jobs\//,
    };

    for (const [domain, pattern] of Object.entries(patterns)) {
      if (url.includes(domain)) {
        jobStatus.innerHTML += `<p style="margin-top:4px;font-size:12px;color:#60a5fa">Detected: ${domain}</p>`;
        document.getElementById('location').value = 'Remote';
        break;
      }
    }
  }

  function populateForm(job) {
    if (job.title) document.getElementById('jobTitle').value = job.title;
    if (job.company) document.getElementById('company').value = job.company;
    if (job.location) document.getElementById('location').value = job.location;
    if (job.salary) document.getElementById('salary').value = job.salary;
  }

  async function saveJob(markApplied = false) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    const jobData = {
      title: document.getElementById('jobTitle').value || 'Unknown Position',
      company: document.getElementById('company').value || 'Unknown',
      url: tab.url,
      location: document.getElementById('location').value || '',
      salary: document.getElementById('salary').value || '',
      notes: document.getElementById('notes').value || '',
      board: new URL(tab.url).hostname.replace('www.', ''),
      saved_at: new Date().toISOString(),
      status: markApplied ? 'applied' : 'saved',
    };

    // Save to chrome storage
    const { savedJobs = [] } = await chrome.storage.local.get(['savedJobs']);
    savedJobs.push(jobData);
    await chrome.storage.local.set({ savedJobs });

    // Update stats
    stats.saved = (stats.saved || 0) + 1;
    stats.todaySaved = (stats.todaySaved || 0) + 1;
    stats.lastDate = today;
    if (markApplied) stats.applied = (stats.applied || 0) + 1;
    await chrome.storage.local.set({ stats });

    // Update UI
    document.getElementById('savedCount').textContent = stats.todaySaved;
    document.getElementById('totalCount').textContent = stats.saved;
    document.getElementById('appliedCount').textContent = stats.applied;

    // Show success
    successMsg.style.display = 'block';
    successMsg.textContent = markApplied ? '✅ Saved & marked as applied!' : '✅ Job saved to pipeline!';

    // Send to background for CSV export
    chrome.runtime.sendMessage({ action: 'saveJob', job: jobData });

    // Reset form after delay
    setTimeout(() => {
      successMsg.style.display = 'none';
    }, 3000);
  }

  saveBtn.addEventListener('click', () => saveJob(false));
  saveApplyBtn.addEventListener('click', () => saveJob(true));

  propertyModeBtn.addEventListener('click', () => {
    const opening = propertyArea.style.display !== 'block';
    propertyArea.style.display = opening ? 'block' : 'none';
    if (opening) extractProperty();
  });

  async function extractProperty() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    propertyStatus.innerHTML = '<p>กำลังอ่านข้อความที่มองเห็นบนแท็บปัจจุบัน...</p>';
    chrome.tabs.sendMessage(tab.id, { action: 'extractProperty' }, (response) => {
      if (chrome.runtime.lastError || !response || !response.property) {
        propertyStatus.innerHTML = '<p>กรอกข้อมูลเองได้ ระบบไม่สามารถอ่านแท็บนี้ได้</p>';
        document.getElementById('propertyTitle').value = tab.title || '';
        return;
      }
      populateProperty(response.property);
      propertyStatus.innerHTML = '<p>✅ ดึงข้อมูลที่เห็นบนหน้าแล้ว โปรดตรวจข้อความ owner/co-agent ก่อนบันทึก</p>';
    });
  }

  function populateProperty(property) {
    if (property.title) document.getElementById('propertyTitle').value = property.title;
    if (property.location) document.getElementById('propertyLocation').value = property.location;
    if (property.price_raw) document.getElementById('propertyPrice').value = property.price_raw;
    if (property.bedrooms) document.getElementById('propertyBedrooms').value = property.bedrooms;
    if (property.bathrooms) document.getElementById('propertyBathrooms').value = property.bathrooms;
    if (property.area_sqm) document.getElementById('propertyAreaSqm').value = property.area_sqm;
    if (property.listing_type) document.getElementById('propertyType').value = property.listing_type;
    if (property.description) document.getElementById('propertyDescription').value = property.description;
  }

  async function saveProperty() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const property = {
      title: document.getElementById('propertyTitle').value.trim(),
      url: tab.url || '',
      location: document.getElementById('propertyLocation').value.trim(),
      price_raw: document.getElementById('propertyPrice').value.trim(),
      bedrooms: document.getElementById('propertyBedrooms').value.trim(),
      bathrooms: document.getElementById('propertyBathrooms').value.trim(),
      area_sqm: document.getElementById('propertyAreaSqm').value.trim(),
      listing_type: document.getElementById('propertyType').value.trim(),
      description: document.getElementById('propertyDescription').value.trim(),
      captured_at: new Date().toISOString(),
      source: 'solo_empire_chrome_extension',
    };
    if (!property.title || !property.url) {
      propertyStatus.innerHTML = '<p>กรุณาใส่ชื่อประกาศและเปิดหน้าที่มี URL ก่อน</p>';
      return;
    }
    chrome.runtime.sendMessage({ action: 'saveProperty', property }, (response) => {
      if (chrome.runtime.lastError || !response || !response.ok) {
        propertyStatus.innerHTML = '<p>บันทึกไม่สำเร็จ โปรดลองโหลด extension ใหม่</p>';
        return;
      }
      propertySuccess.style.display = 'block';
      propertySuccess.textContent = `✅ บันทึกแถว property ในเครื่องแล้ว (${response.count} แถว)`;
      setTimeout(() => { propertySuccess.style.display = 'none'; }, 3000);
    });
  }

  // One line per enabled cloud provider, appended to the export status.
  function describeUploads(uploads) {
    if (!Array.isArray(uploads) || !uploads.length) return '';
    return uploads.map((upload) => (upload.ok
      ? ` · ☁️ ${upload.label}: อัปโหลดแล้ว`
      : ` · ⚠️ ${upload.label}: อัปโหลดไม่สำเร็จ (${upload.error})`)).join('');
  }

  function exportProperties() {
    chrome.runtime.sendMessage({ action: 'exportProperties' }, (response) => {
      if (chrome.runtime.lastError || !response || !response.ok) {
        propertyStatus.innerHTML = '<p>ยังไม่มีแถว property ให้ export</p>';
        return;
      }
      const message = document.createElement('p');
      message.textContent = `⬇️ ดาวน์โหลด CSV แล้ว ${response.count} แถว — นำเข้าโดย scripts/import_property_leads.py${describeUploads(response.uploads)}`;
      propertyStatus.replaceChildren(message);
    });
  }

  facebookGroupModeBtn.addEventListener('click', () => {
    const opening = facebookGroupArea.style.display !== 'block';
    facebookGroupArea.style.display = opening ? 'block' : 'none';
    if (opening) extractFacebookGroupPosts();
  });

  facebookGroupVisibility.addEventListener('change', () => {
    renderFacebookGroupPosts();
    persistFacebookGroupCaptureDraft();
  });

  captureNextFacebookGroupPageBtn.addEventListener('click', () => extractFacebookGroupPosts());

  function facebookGroupTextComplete(value) {
    if (typeof value === 'boolean') return value;
    return ['1', 'true', 'yes', 'y', 'complete'].includes(String(value || '').trim().toLowerCase());
  }

  function facebookGroupPostScore(post) {
    const textLength = String(post && post.text || '').trim().length;
    return [facebookGroupTextComplete(post && post.text_complete), textLength, Boolean(post && post.author_name), Boolean(post && post.posted_at)]
      .map((value) => Number(value));
  }

  function isHigherQualityFacebookGroupPost(candidate, current) {
    const candidateScore = facebookGroupPostScore(candidate);
    const currentScore = facebookGroupPostScore(current);
    for (let index = 0; index < candidateScore.length; index += 1) {
      if (candidateScore[index] !== currentScore[index]) return candidateScore[index] > currentScore[index];
    }
    return false;
  }

  function canonicalFacebookGroupPostUrl(value) {
    try {
      const parsed = new URL(String(value || '').trim());
      const host = parsed.hostname.toLowerCase().replace(/^www\./, '');
      if (parsed.protocol !== 'https:' || (host !== 'facebook.com' && !host.endsWith('.facebook.com')) || parsed.username || parsed.password || parsed.port) return '';
      const params = new URLSearchParams(parsed.search);
      [...params.keys()].forEach((key) => {
        if (/^(utm_|fbclid$|gclid$|dclid$|ref$|referrer$|source$|src$)/i.test(key)) params.delete(key);
      });
      params.sort();
      parsed.hostname = 'facebook.com';
      parsed.search = params.toString();
      parsed.hash = '';
      parsed.pathname = parsed.pathname.replace(/\/+$/, '') || '/';
      return parsed.toString();
    } catch (error) {
      return '';
    }
  }

  function mergeFacebookGroupPosts(existing, incoming) {
    const merged = new Map();
    [...(Array.isArray(existing) ? existing : []), ...(Array.isArray(incoming) ? incoming : [])]
      .forEach((post) => {
        const postUrl = canonicalFacebookGroupPostUrl(post && post.post_url);
        if (!postUrl) return;
        const normalisedPost = { ...post, post_url: postUrl };
        const current = merged.get(postUrl);
        if (!current || isHigherQualityFacebookGroupPost(normalisedPost, current)) merged.set(postUrl, normalisedPost);
      });
    return Array.from(merged.values());
  }

  async function persistFacebookGroupCaptureDraft() {
    try {
      if (!facebookGroupCapture.posts.length) {
        await chrome.storage.local.remove(['facebookGroupCaptureDraft']);
        return;
      }
      await chrome.storage.local.set({
        facebookGroupCaptureDraft: {
          group_url: facebookGroupCapture.group_url,
          group_name: facebookGroupCapture.group_name,
          captured_at: facebookGroupCapture.captured_at,
          capture_rounds: facebookGroupCaptureRounds,
          visibility: facebookGroupVisibility.value,
          last_updated_at: new Date().toISOString(),
          posts: facebookGroupCapture.posts.slice(-FACEBOOK_GROUP_DRAFT_LIMIT),
        },
      });
    } catch (error) {
      // A draft is a convenience only; the Save action remains the durable local copy.
      console.warn('Facebook Group capture draft could not be persisted', error);
    }
  }

  async function extractFacebookGroupPosts() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    facebookGroupStatus.textContent = 'กำลังอ่านข้อความโพสต์ที่มองเห็นบนแท็บปัจจุบัน...';
    captureNextFacebookGroupPageBtn.disabled = true;
    chrome.tabs.sendMessage(tab.id, { action: 'extractFacebookGroupPosts' }, (response) => {
      captureNextFacebookGroupPageBtn.disabled = false;
      if (chrome.runtime.lastError || !response || !response.group) {
        facebookGroupStatus.textContent = 'อ่านแท็บนี้ไม่ได้ ให้เปิดหน้า Facebook Group แล้วลองใหม่';
        renderFacebookGroupPosts();
        return;
      }
      const incomingGroupUrl = String(response.group.group_url || '').trim();
      if (!incomingGroupUrl) {
        facebookGroupStatus.textContent = 'ต้องเปิดหน้า Facebook Group ก่อน ระบบจะไม่รวมข้อมูลจากแท็บอื่น';
        renderFacebookGroupPosts();
        return;
      }
      const previousGroupUrl = String(facebookGroupCapture.group_url || '').trim();
      const groupChanged = Boolean(previousGroupUrl && incomingGroupUrl !== previousGroupUrl);
      const existingPosts = groupChanged ? [] : facebookGroupCapture.posts;
      const incomingPosts = Array.isArray(response.group.posts) ? response.group.posts : [];
      const mergedPosts = mergeFacebookGroupPosts(existingPosts, incomingPosts);
      const addedCount = Math.max(0, mergedPosts.length - existingPosts.length);
      facebookGroupCapture = {
        group_url: incomingGroupUrl,
        group_name: String(response.group.group_name || facebookGroupCapture.group_name || ''),
        captured_at: String(response.group.captured_at || new Date().toISOString()),
        posts: mergedPosts,
      };
      if (!facebookGroupCaptureRounds || groupChanged) {
        if (response.group.visibility === 'public' || response.group.visibility === 'private') {
          facebookGroupVisibility.value = response.group.visibility;
        } else {
          facebookGroupVisibility.value = 'unknown';
        }
      }
      facebookGroupCaptureRounds = groupChanged ? 1 : facebookGroupCaptureRounds + 1;
      persistFacebookGroupCaptureDraft();
      facebookGroupStatus.textContent = `รอบนี้เห็น ${incomingPosts.length} โพสต์ เพิ่มใหม่ ${addedCount} รายการ รวม ${facebookGroupCapture.posts.length} รายการ — เลื่อนหน้าเองแล้วกด Capture next ได้`;
      renderFacebookGroupPosts();
    });
  }

  function renderFacebookGroupPosts() {
    facebookGroupPostsArea.replaceChildren();
    const posts = Array.isArray(facebookGroupCapture.posts) ? facebookGroupCapture.posts : [];
    if (!posts.length) {
      const empty = document.createElement('div');
      empty.className = 'group-post-empty';
      empty.textContent = 'ยังไม่พบโพสต์ที่มี permalink ในส่วนที่แสดงอยู่';
      facebookGroupPostsArea.appendChild(empty);
      saveFacebookGroupPostsBtn.disabled = true;
      return;
    }
    let selectable = 0;
    posts.forEach((post, index) => {
      const wrapper = document.createElement('div');
      wrapper.className = 'group-post';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.dataset.index = String(index);
      checkbox.checked = Boolean(post.post_url);
      checkbox.disabled = !post.post_url;
      checkbox.addEventListener('change', updateFacebookGroupSelectionState);
      if (post.post_url) selectable += 1;

      const body = document.createElement('div');
      const meta = document.createElement('div');
      meta.className = 'group-post-meta';
      meta.textContent = [post.author_name, post.posted_at, post.text_complete ? 'ข้อความครบ' : 'ข้อความอาจไม่ครบ']
        .filter(Boolean).join(' · ') || 'โพสต์ไม่มี metadata';
      const text = document.createElement('div');
      text.className = 'group-post-text';
      text.textContent = String(post.text || '').slice(0, 320);
      body.append(meta, text);
      wrapper.append(checkbox, body);
      facebookGroupPostsArea.appendChild(wrapper);
    });
    saveFacebookGroupPostsBtn.disabled = selectable === 0;
  }

  function updateFacebookGroupSelectionState() {
    saveFacebookGroupPostsBtn.disabled = !Array.from(
      facebookGroupPostsArea.querySelectorAll('input[type="checkbox"]:checked:not(:disabled)')
    ).length;
  }

  async function saveFacebookGroupPosts() {
    const visibility = facebookGroupVisibility.value;
    if (visibility === 'unknown') {
      facebookGroupStatus.textContent = 'กรุณาตรวจและเลือก Public หรือ Private ก่อนบันทึก — unknown จะถูกกักไว้';
      return;
    }
    const selected = Array.from(
      facebookGroupPostsArea.querySelectorAll('input[type="checkbox"]:checked:not(:disabled)')
    ).map((checkbox) => facebookGroupCapture.posts[Number(checkbox.dataset.index)]).filter(Boolean);
    if (!selected.length) {
      facebookGroupStatus.textContent = 'เลือกอย่างน้อยหนึ่งโพสต์ที่มี permalink';
      return;
    }
    const posts = buildFacebookGroupPostPayload(selected);
    chrome.runtime.sendMessage({ action: 'saveFacebookGroupPosts', posts }, (response) => {
      if (chrome.runtime.lastError || !response || !response.ok) {
        facebookGroupStatus.textContent = 'บันทึกไม่สำเร็จ โปรดลองโหลด extension ใหม่';
        return;
      }
      facebookGroupSuccess.style.display = 'block';
      facebookGroupSuccess.textContent = `✅ บันทึกโพสต์ในเครื่องแล้ว (${response.count} แถว)`;
      facebookGroupStatus.textContent = 'ตรวจ CSV ที่ export แล้วนำเข้า scripts/import_facebook_group_posts.py';
      setTimeout(() => { facebookGroupSuccess.style.display = 'none'; }, 3000);
    });
  }

  function buildFacebookGroupPostPayload(posts) {
    const visibility = facebookGroupVisibility.value;
    return (Array.isArray(posts) ? posts : []).map((post) => ({
      group_url: facebookGroupCapture.group_url || post.group_url || '',
      group_name: facebookGroupCapture.group_name || post.group_name || '',
      post_url: post.post_url || '',
      post_id: post.post_id || '',
      author_name: post.author_name || '',
      posted_at: post.posted_at || '',
      text: post.text || '',
      visibility,
      text_complete: facebookGroupTextComplete(post.text_complete),
      capture_method: post.capture_method || 'chrome_extension_visible_tab',
      source_channel: 'facebook_group',
      source_platform: 'facebook',
      captured_at: post.captured_at || facebookGroupCapture.captured_at || new Date().toISOString(),
    }));
  }

  function exportFacebookGroupCapture() {
    const visibility = facebookGroupVisibility.value;
    if (visibility === 'unknown') {
      facebookGroupStatus.textContent = 'กรุณาตรวจและเลือก Public หรือ Private ก่อน export — unknown จะถูกกักไว้';
      return;
    }
    const posts = buildFacebookGroupPostPayload(facebookGroupCapture.posts);
    if (!posts.length) {
      facebookGroupStatus.textContent = 'ยังไม่มีโพสต์ใน capture draft ให้ export';
      return;
    }
    chrome.runtime.sendMessage({ action: 'exportFacebookGroupCapture', posts }, (response) => {
      if (chrome.runtime.lastError || !response || !response.ok) {
        facebookGroupStatus.textContent = 'export capture ไม่สำเร็จ โปรดลองโหลด extension ใหม่';
        return;
      }
      facebookGroupStatus.textContent = `⬇️ ดาวน์โหลด capture ปัจจุบันแล้ว ${response.count} แถว — ยังไม่ล้าง draft${describeUploads(response.uploads)}`;
    });
  }

  function exportFacebookGroupPosts() {
    chrome.runtime.sendMessage({ action: 'exportFacebookGroupPosts' }, (response) => {
      if (chrome.runtime.lastError || !response || !response.ok) {
        facebookGroupStatus.textContent = 'ยังไม่มีโพสต์ที่บันทึกไว้ ให้เลือกและ Save ก่อน export';
        return;
      }
      facebookGroupStatus.textContent = `⬇️ ดาวน์โหลด CSV แล้ว ${response.count} แถว — นำเข้าโดย scripts/import_facebook_group_posts.py${describeUploads(response.uploads)}`;
    });
  }

  async function clearFacebookGroupCapture() {
    facebookGroupCapture = { group_url: '', group_name: '', captured_at: '', posts: [] };
    facebookGroupCaptureRounds = 0;
    facebookGroupVisibility.value = 'unknown';
    await persistFacebookGroupCaptureDraft();
    facebookGroupStatus.textContent = 'ล้าง draft ในเครื่องแล้ว เริ่ม capture กลุ่มใหม่ได้';
    renderFacebookGroupPosts();
  }

  document.getElementById('cloudSettingsBtn').addEventListener('click', () => chrome.runtime.openOptionsPage());
  document.getElementById('savePropertyBtn').addEventListener('click', saveProperty);
  document.getElementById('exportPropertiesBtn').addEventListener('click', exportProperties);
  saveFacebookGroupPostsBtn.addEventListener('click', saveFacebookGroupPosts);
  exportFacebookGroupCaptureBtn.addEventListener('click', exportFacebookGroupCapture);
  exportFacebookGroupPostsBtn.addEventListener('click', exportFacebookGroupPosts);
  clearFacebookGroupCaptureBtn.addEventListener('click', clearFacebookGroupCapture);
});
