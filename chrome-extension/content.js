// Quick Job Saver — Content Script
// Detects job information from the current page

(function() {
  // Injected on demand by the popup (and declared for job sites), so it can
  // run twice in one page; register listeners and the button only once.
  if (window.__quickSaverContentLoaded) return;
  window.__quickSaverContentLoaded = true;

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'extractJob') {
      const job = extractJobFromPage();
      sendResponse({ job });
    } else if (request.action === 'extractProperty') {
      const property = extractPropertyFromPage();
      sendResponse({ property });
    } else if (request.action === 'extractFacebookGroupPosts') {
      const group = extractFacebookGroupPosts();
      sendResponse({ group });
    }
    return true; // async response
  });

  function extractJobFromPage() {
    const job = {
      title: '',
      company: '',
      location: '',
      salary: '',
      description: '',
    };

    const url = window.location.href;
    const hostname = window.location.hostname;

    // Generic extraction strategies
    job.title = extractTitle();
    job.company = extractCompany();
    job.location = extractLocation();
    job.salary = extractSalary();

    return job;
  }

  function extractTitle() {
    // Try common selectors
    const selectors = [
      '[class*="job-title"]', '[class*="jobTitle"]', '[class*="position-title"]',
      'h1[class*="title"]', 'h1', '[data-test="job-title"]',
      '.job-header h1', '.posting-title h1', '[class*="role-title"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent.trim().length > 3 && el.textContent.trim().length < 150) {
        return el.textContent.trim();
      }
    }

    // Try meta tags
    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) return ogTitle.content;

    return document.title.split(' - ')[0].split(' | ')[0].trim();
  }

  function extractCompany() {
    const selectors = [
      '[class*="company-name"]', '[class*="companyName"]', '[class*="employer"]',
      '[data-test="company-name"]', '.company h2', '[class*="org-name"]',
      'a[class*="company"]', '[class*="hiring-org"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent.trim().length > 1 && el.textContent.trim().length < 80) {
        return el.textContent.trim();
      }
    }

    // Try meta tags
    const ogSite = document.querySelector('meta[property="og:site_name"]');
    if (ogSite) return ogSite.content;

    return '';
  }

  function extractLocation() {
    const selectors = [
      '[class*="location"]', '[class*="job-location"]', '[class*="jobLocation"]',
      '[data-test="location"]', '[class*="city"]', '[class*="place"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent.trim().length > 1 && el.textContent.trim().length < 100) {
        const text = el.textContent.trim();
        // Filter out noise
        if (text.match(/remote|hybrid|onsite|bangkok|thailand|singapore|tokyo|london|new york|san francisco|berlin/i)) {
          return text;
        }
      }
    }

    // Check page text for location patterns
    const bodyText = document.body.innerText.substring(0, 5000);
    const locationMatch = bodyText.match(/(remote|hybrid|onsite)[\s—–-]*(bangkok|thailand|singapore|tokyo|london|new york|san francisco|berlin|worldwide|global)?/i);
    if (locationMatch) return locationMatch[0];

    return '';
  }

  function extractSalary() {
    const selectors = [
      '[class*="salary"]', '[class*="compensation"]', '[class*="pay-range"]',
      '[data-test="salary"]', '[class*="comp"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        const text = el.textContent.trim();
        if (text.match(/\$|฿|€|£|\d+[kK]|\d{3,}/)) {
          return text;
        }
      }
    }

    // Search page text for salary patterns
    const bodyText = document.body.innerText.substring(0, 10000);
    const salaryMatch = bodyText.match(/(\$[\d,]+[kK]?\s*[-–—to]+\s*\$[\d,]+[kK]?)/);
    if (salaryMatch) return salaryMatch[0];

    return '';
  }

  // Property capture is deliberately generic.  It reads rendered text from
  // the tab the operator opened and leaves owner/co-agent classification to
  // the offline Python importer, where the evidence and review defaults are
  // versioned with property.v1.  It never requests another URL or reads
  // cookies/private API payloads.
  function extractPropertyFromPage() {
    const titleSelectors = [
      '[data-testid*="title"]', '[class*="property-title"]',
      '[class*="listing-title"]', 'h1', 'meta[property="og:title"]',
    ];
    let title = '';
    for (const selector of titleSelectors) {
      const el = document.querySelector(selector);
      const value = selector.startsWith('meta[') ? el && el.content : el && el.textContent;
      if (value && value.trim().length > 2) {
        title = value.trim().slice(0, 240);
        break;
      }
    }
    if (!title) title = (document.title || '').split(' | ')[0].split(' - ')[0].trim().slice(0, 240);

    const bodyText = (document.body && document.body.innerText || '').replace(/\s+/g, ' ').trim();
    const priceMatch = bodyText.match(/(?:฿|THB|บาท)\s*[\d,]+(?:\.\d+)?(?:\s*(?:ล้าน|\/\s*(?:เดือน|month)))?|[\d,]+(?:\.\d+)?\s*(?:ล้าน|บาท|\/\s*(?:เดือน|month))/i);
    const bedroomMatch = bodyText.match(/(\d+(?:\.\d+)?)\s*(?:bedrooms?|beds?|ห้องนอน)/i);
    const bathroomMatch = bodyText.match(/(\d+(?:\.\d+)?)\s*(?:bathrooms?|baths?|ห้องน้ำ)/i);
    const areaMatch = bodyText.match(/(\d+(?:\.\d+)?)\s*(?:sq\.?\s*m\.?|sqm|m²|ตร\.?ม)/i);
    const locationSelectors = [
      '[class*="location"]', '[class*="address"]', '[class*="district"]',
      '[data-testid*="location"]', '[data-testid*="address"]',
    ];
    let location = '';
    for (const selector of locationSelectors) {
      const el = document.querySelector(selector);
      if (el && el.textContent.trim().length > 1) {
        location = el.textContent.trim().slice(0, 240);
        break;
      }
    }

    return {
      title,
      url: window.location.href,
      location,
      price_raw: priceMatch ? priceMatch[0].trim() : '',
      bedrooms: bedroomMatch ? bedroomMatch[1] : '',
      bathrooms: bathroomMatch ? bathroomMatch[1] : '',
      area_sqm: areaMatch ? areaMatch[1] : '',
      listing_type: '',
      description: bodyText.slice(0, 5000),
      captured_at: new Date().toISOString(),
    };
  }

  // Facebook Group capture intentionally stays inside the rendered tab.  It
  // reads only visible article text and links; it does not scroll, call an
  // API, follow a post, inspect cookies, or make an outbound request.
  function extractFacebookGroupPosts() {
    const currentUrl = new URL(window.location.href);
    const host = currentUrl.hostname.toLowerCase().replace(/^www\./, '');
    const groupMatch = currentUrl.pathname.match(/^\/groups\/([^/]+)/i);
    const result = {
      group_url: '',
      group_name: '',
      visibility: 'unknown',
      captured_at: new Date().toISOString(),
      posts: [],
    };
    if (host !== 'facebook.com' && !host.endsWith('.facebook.com')) return result;
    if (!groupMatch) return result;

    result.group_url = `https://facebook.com/groups/${groupMatch[1]}`;
    const heading = document.querySelector('h1, [role="heading"]');
    const ogTitle = document.querySelector('meta[property="og:title"]');
    result.group_name = ((heading && heading.textContent) || (ogTitle && ogTitle.content) || document.title || '')
      .replace(/\s+/g, ' ').trim().slice(0, 240);

    const pageText = ((document.body && document.body.innerText) || '').slice(0, 4000);
    if (/\bpublic\s+group\b|กลุ่มสาธารณะ|สาธารณะ/iu.test(pageText)) {
      result.visibility = 'public';
    } else if (/\bprivate\s+group\b|กลุ่มส่วนตัว|สมาชิกเท่านั้น|ส่วนตัว/iu.test(pageText)) {
      result.visibility = 'private';
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

    // Text is truncated while Facebook still shows a "See more" control in the
    // post.  Matching the word in the text misfired on posts that merely say
    // "เพิ่มเติม" ("more").
    const hasVisibleSeeMore = (article) => Array.from(article.querySelectorAll('[role="button"], span, div'))
      .some((node) => /^\s*(see more|ดูเพิ่มเติม|อ่านเพิ่มเติม|แสดงเพิ่มเติม)\s*$/i.test(node.textContent || '')
        && (!node.getClientRects || node.getClientRects().length > 0));

    const postId = (postUrl) => {
      try {
        const parsed = new URL(postUrl);
        const pathMatch = parsed.pathname.match(/\/groups\/[^/]+\/(?:posts|permalink)\/([^/]+)/i) || parsed.pathname.match(/\/(?:posts|permalink)\/([^/]+)/i);
        if (pathMatch) return pathMatch[1].slice(0, 100);
        const id = parsed.searchParams.get('story_fbid') || parsed.searchParams.get('fbid') || parsed.searchParams.get('post_id') || parsed.searchParams.get('id');
        return id ? id.slice(0, 100) : '';
      } catch (error) {
        return '';
      }
    };

    const articles = Array.from(document.querySelectorAll('[role="article"]'));
    const seen = new Set();
    articles.forEach((article) => {
      const anchors = Array.from(article.querySelectorAll('a[href]'));
      const permalinkAnchor = anchors.find((anchor) => canonicalFacebookPostUrl(anchor.href));
      const link = permalinkAnchor ? canonicalFacebookPostUrl(permalinkAnchor.href) : '';
      if (!link || seen.has(link)) return;
      seen.add(link);

      const articleText = ((article.innerText || article.textContent || '') || '').replace(/\s+/g, ' ').trim().slice(0, 10000);
      if (!articleText) return;
      const time = article.querySelector('time, abbr[title], [data-utime]');
      // Poster: Facebook's profile-name slot first, then the post header.  A
      // generic a[role="link"] is not used: it often matched a commenter, a
      // reaction list, or the group itself.
      const authorCandidate = article.querySelector('[data-ad-rendering-role="profile_name"] a')
        || article.querySelector('h2 a, h3 a')
        || article.querySelector('[data-ad-rendering-role="profile_name"]');
      const author = ((authorCandidate && authorCandidate.textContent) || '').replace(/\s+/g, ' ').trim().slice(0, 160);
      // Without <time>, the permalink anchor is the timestamp: its aria-label
      // or tooltip holds the date ("18 October at 09:12"), its text a relative
      // time ("2h").
      const timeSource = time || permalinkAnchor;
      const postedAt = timeSource
        ? (timeSource.getAttribute('datetime') || timeSource.getAttribute('aria-label') || timeSource.getAttribute('title') || timeSource.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80)
        : '';
      result.posts.push({
        group_url: result.group_url,
        group_name: result.group_name,
        post_url: link,
        post_id: postId(link),
        author_name: author === result.group_name ? '' : author,
        posted_at: postedAt,
        text: articleText,
        text_complete: !hasVisibleSeeMore(article),
        capture_method: 'chrome_extension_visible_tab',
        source_channel: 'facebook_group',
        source_platform: 'facebook',
        visibility: result.visibility,
        captured_at: result.captured_at,
      });
    });
    return result;
  }

  // Add floating save button to job pages
  function addFloatingButton() {
    const hostname = window.location.hostname;
    const jobPatterns = [
      /linkedin\.com\/jobs/,
      /indeed\.com\/viewjob/,
      /glassdoor\.com.*job-listing/,
      /remotive\.com\/jobs/,
      /weworkremotely\.com\/jobs/,
      /wellfound\.com\/jobs/,
      /otta\.com\/jobs/,
      /dice\.com\/jobs/,
      /jobthai\.com/,
    ];

    const isJobPage = jobPatterns.some(p => p.test(window.location.href));
    if (!isJobPage) return;

    const btn = document.createElement('button');
    btn.id = 'qjs-float-btn';
    btn.innerHTML = '💾 Save Job';
    btn.title = 'Save to Solo Empire Pipeline';
    document.body.appendChild(btn);

    btn.addEventListener('click', () => {
      const job = extractJobFromPage();
      chrome.runtime.sendMessage({
        action: 'quickSave',
        job: { ...job, url: window.location.href, board: hostname }
      });

      btn.innerHTML = '✅ Saved!';
      btn.style.background = '#22c55e';
      setTimeout(() => {
        btn.innerHTML = '💾 Save Job';
        btn.style.background = '#3b82f6';
      }, 2000);
    });
  }

  // Add button after page loads
  if (document.readyState === 'complete') {
    addFloatingButton();
  } else {
    window.addEventListener('load', addFloatingButton);
  }
})();
