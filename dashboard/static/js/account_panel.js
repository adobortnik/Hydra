// ============================================================================
//  account_panel.js  —  SHARED Account Detail panel component
//  Single source of truth used by: accounts.html, device_manager_detail.html,
//  mother_detail.html. Provides the offcanvas settings panel + content/insights
//  /sources/business/mother logic. Entry point: openAccountSettings(serial, user).
//  Extracted from device_manager_detail.html (2026-06) — edit HERE, applies
//  everywhere the partial _account_panel.html is included.
// ============================================================================

// Self-contained HTML helpers (pages may also define their own copies).
function escHtml(str) {
    if (str === null || str === undefined) return '';
    const d = document.createElement('div'); d.textContent = String(str); return d.innerHTML;
}
function escAttr(str) { return escHtml(str).replace(/"/g, '&quot;'); }

// ═══════════════════════════════════════════════════════════
//  Settings Panel Logic
// ═══════════════════════════════════════════════════════════

let spCurrentDevice = '';
let spCurrentAccount = '';
let spOffcanvas = null;

// ── Tab Switching ──
document.querySelectorAll('.sp-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.sp-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        document.querySelectorAll('.sp-pane').forEach(p => p.classList.remove('active'));
        const pane = document.querySelector(`.sp-pane[data-pane="${tab}"]`);
        if (pane) pane.classList.add('active');
        if (tab === 'content') { spInitDropZone(); loadAccountContent(); }
    });
});

// ── Content tab: drag-drop quick add (multi-file) ──
// Each item: { id, file, previewUrl, isVideo, type, caption, uploaded }
let _spComposerItems = [];
let _spComposerNextId = 1;

function spInitDropZone() {
    const dz = document.getElementById('spDropZone');
    const input = document.getElementById('spDropInput');
    if (!dz || dz.dataset.bound) return;
    dz.dataset.bound = '1';

    dz.addEventListener('click', () => input.click());
    input.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length) spAddFiles(e.target.files);
        input.value = '';
    });
    ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, (e) => {
        e.preventDefault(); e.stopPropagation();
        dz.classList.add('dragover');
    }));
    ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, (e) => {
        e.preventDefault(); e.stopPropagation();
        dz.classList.remove('dragover');
    }));
    dz.addEventListener('drop', (e) => {
        const files = e.dataTransfer && e.dataTransfer.files;
        if (files && files.length) spAddFiles(files);
    });

    // Schedule/Now toggle reveals time picker, recomputes per-item times
    document.getElementById('spComposerWhen').addEventListener('change', (e) => {
        const t = document.getElementById('spComposerTime');
        if (e.target.value === 'schedule') {
            t.style.display = '';
            if (!t.value) {
                const d = new Date(Date.now() + 60 * 60 * 1000);  // +1h default
                d.setSeconds(0, 0);
                t.value = spLocalDateTimeStr(d);
            }
        } else {
            t.style.display = 'none';
        }
        spRenderComposer();
    });
    document.getElementById('spComposerTime').addEventListener('input', spRenderComposer);
    document.getElementById('spComposerInterval').addEventListener('input', spRenderComposer);
}

function spLocalDateTimeStr(d) {
    // YYYY-MM-DDTHH:MM in local time (for datetime-local input value)
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}` +
           `T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function spComposerAddMore() {
    document.getElementById('spDropInput').click();
}

function spAddFiles(filesIterable) {
    const files = Array.from(filesIterable);
    for (const f of files) {
        const isVideo = f.type.startsWith('video/');
        _spComposerItems.push({
            id: _spComposerNextId++,
            file: f,
            previewUrl: URL.createObjectURL(f),
            isVideo,
            type: isVideo ? 'reel' : 'post',
            caption: '',
            uploaded: null,
        });
    }
    document.getElementById('spComposer').style.display = 'block';
    document.getElementById('spComposerStatus').textContent = '';
    spRenderComposer();
}

function spRemoveComposerItem(id) {
    const it = _spComposerItems.find(x => x.id === id);
    if (it && it.previewUrl) { try { URL.revokeObjectURL(it.previewUrl); } catch(e){} }
    _spComposerItems = _spComposerItems.filter(x => x.id !== id);
    if (_spComposerItems.length === 0) { spComposerCancel(); return; }
    spRenderComposer();
}

function spComputeScheduledTimes() {
    // Returns array of Date objects, one per composer item.
    const when = document.getElementById('spComposerWhen').value;
    const startVal = document.getElementById('spComposerTime').value;
    const interval = Math.max(1, parseInt(
        document.getElementById('spComposerInterval').value || '60', 10));
    let start;
    if (when === 'schedule' && startVal) {
        start = new Date(startVal);  // datetime-local parsed as local
    } else {
        start = new Date();
    }
    return _spComposerItems.map((_, i) =>
        new Date(start.getTime() + i * interval * 60 * 1000));
}

function spRenderComposer() {
    const wrap = document.getElementById('spComposerRows');
    const count = _spComposerItems.length;
    document.getElementById('spComposerCount').textContent =
        count + (count === 1 ? ' item' : ' items');
    document.getElementById('spComposerIntervalWrap').style.display =
        count > 1 ? 'flex' : 'none';

    const times = spComputeScheduledTimes();
    const submitBtn = document.getElementById('spComposerSubmit');
    const when = document.getElementById('spComposerWhen').value;
    if (count > 1) {
        submitBtn.innerHTML = `<i class="fas fa-clock me-1"></i> Schedule ${count}`;
    } else if (when === 'now') {
        submitBtn.innerHTML = '<i class="fas fa-paper-plane me-1"></i> Post now';
    } else {
        submitBtn.innerHTML = '<i class="fas fa-clock me-1"></i> Schedule';
    }

    wrap.innerHTML = _spComposerItems.map((it, i) => {
        const thumb = it.isVideo
            ? `<video src="${it.previewUrl}" muted autoplay loop playsinline></video>`
            : `<img src="${it.previewUrl}">`;
        const tStr = times[i].toLocaleString([], {
            month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
        return `
        <div class="sp-composer-row" data-id="${it.id}">
            <div class="sp-composer-thumb">${thumb}</div>
            <div class="flex-grow-1">
                <div class="d-flex gap-2 mb-1 align-items-center flex-wrap">
                    <select class="form-select form-select-sm sp-row-type" style="max-width:110px;"
                            onchange="_spSetItemField(${it.id},'type',this.value)">
                        <option value="post"  ${it.type==='post'?'selected':''}>Post</option>
                        <option value="reel"  ${it.type==='reel'?'selected':''}>Reel</option>
                        <option value="story" ${it.type==='story'?'selected':''}>Story</option>
                    </select>
                    <span class="small sp-row-time" title="Scheduled time">
                        <i class="fas fa-clock me-1"></i>${escHtml(tStr)}
                    </span>
                    <button class="sp-row-remove ms-auto" title="Remove"
                            onclick="spRemoveComposerItem(${it.id})">&times;</button>
                </div>
                <textarea class="form-control form-control-sm sp-row-caption" rows="2"
                          placeholder="Caption (optional) — include #hashtags here"
                          oninput="_spSetItemField(${it.id},'caption',this.value)">${escHtml(it.caption)}</textarea>
            </div>
        </div>`;
    }).join('');
}

function _spSetItemField(id, field, value) {
    const it = _spComposerItems.find(x => x.id === id);
    if (it) it[field] = value;
}

function spComposerCancel() {
    for (const it of _spComposerItems) {
        if (it.previewUrl) { try { URL.revokeObjectURL(it.previewUrl); } catch(e){} }
    }
    _spComposerItems = [];
    document.getElementById('spComposer').style.display = 'none';
    const rows = document.getElementById('spComposerRows');
    if (rows) rows.innerHTML = '';
    const stat = document.getElementById('spComposerStatus');
    if (stat) stat.textContent = '';
}

async function spComposerSubmit() {
    if (!_spCurrentAccountId) {
        showSpToast('Account not loaded yet', 'error'); return;
    }
    if (_spComposerItems.length === 0) {
        showSpToast('No files', 'error'); return;
    }
    const btn = document.getElementById('spComposerSubmit');
    const stat = document.getElementById('spComposerStatus');
    const originalBtnHtml = btn.innerHTML;
    btn.disabled = true;
    stat.style.color = '#9ca3af';

    const total = _spComposerItems.length;
    const times = spComputeScheduledTimes();
    const spoofOn = (document.getElementById('spComposerSpoof') || {}).checked !== false;
    let okCount = 0;
    const errors = [];

    try {
        for (let i = 0; i < _spComposerItems.length; i++) {
            const it = _spComposerItems[i];
            const tag = `[${i+1}/${total}]`;

            // Upload if not already
            if (!it.uploaded) {
                stat.textContent = `${tag} Uploading ${it.file.name}…`;
                btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>${tag} Uploading`;
                const fd = new FormData();
                fd.append('file', it.file);
                const ur = await fetch('/api/content-schedule/upload', { method: 'POST', body: fd });
                const ud = await ur.json();
                const first = (ud.files || [])[0];
                if (!ur.ok || !first || !first.success) {
                    errors.push(`${it.file.name}: ${(first && first.error) || ud.error || 'upload failed'}`);
                    continue;
                }
                it.uploaded = first;
            }

            // Schedule. First "Start now" item goes to /post-now which
            // also signals the device bot engine to skip its cooldown.
            const whenMode = document.getElementById('spComposerWhen').value;
            const useNow = (whenMode === 'now' && i === 0);
            stat.textContent = useNow ? `${tag} Posting NOW…` : `${tag} Scheduling…`;
            btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>${tag} ${useNow ? 'Posting' : 'Scheduling'}`;
            const endpoint = useNow
                ? '/api/content-schedule/post-now'
                : '/api/content-schedule';
            const cr = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    account_id: _spCurrentAccountId,
                    device_serial: spCurrentDevice,
                    username: spCurrentAccount,
                    content_type: it.type,
                    media_path: it.uploaded.full_path,
                    caption: (it.caption || '').trim(),
                    scheduled_time: times[i].toISOString(),
                    spoof_enabled: spoofOn,
                    spoof_preset: 'medium',
                    spoof_allow_mirror: true,
                }),
            });
            const cd = await cr.json();
            if (!cr.ok) {
                errors.push(`${it.file.name}: ${cd.error || 'schedule failed'}`);
                continue;
            }
            okCount++;
        }

        if (okCount === total) {
            showSpToast(total === 1
                ? 'Scheduled'
                : `${total} items scheduled`, 'success');
            spComposerCancel();
            loadAccountContent();
        } else if (okCount > 0) {
            showSpToast(`${okCount}/${total} scheduled — ${errors.length} error(s)`, 'warning');
            stat.style.color = '#f59e0b';
            stat.textContent = errors.slice(0, 3).join(' · ');
            loadAccountContent();
        } else {
            stat.style.color = '#f87171';
            stat.textContent = errors[0] || 'All items failed';
        }
    } catch (e) {
        stat.style.color = '#f87171';
        stat.textContent = 'Error: ' + e.message;
    } finally {
        btn.innerHTML = originalBtnHtml;
        btn.disabled = false;
    }
}

// ── Content tab: list posts scheduled/posted via Hydra ──
function loadAccountContent() {
    const grid = document.getElementById('spContentGrid');
    const loading = document.getElementById('spContentLoading');
    const empty = document.getElementById('spContentEmpty');
    const summary = document.getElementById('spContentSummary');
    grid.innerHTML = '';
    empty.style.display = 'none';
    summary.textContent = '';
    loading.style.display = 'block';

    if (!_spCurrentAccountId) {
        loading.style.display = 'none';
        empty.style.display = 'block';
        return;
    }
    fetch(`/api/content-schedule/account/${_spCurrentAccountId}`)
        .then(r => r.json())
        .then(data => {
            loading.style.display = 'none';
            if (!data.success || !(data.items || []).length) {
                empty.style.display = 'block';
                return;
            }
            const c = data.counts || {};
            summary.textContent =
                `${c.posted || 0} posted · ${c.pending || 0} pending · ${c.failed || 0} failed`;
            grid.innerHTML = data.items.map(renderContentCard).join('');
        })
        .catch(() => {
            loading.style.display = 'none';
            empty.style.display = 'block';
        });
}

function renderContentCard(it) {
    const statusMap = {
        completed: ['Posted',  '#065f46', '#34d399'],
        pending:   ['Pending', '#78350f', '#fbbf24'],
        posting:   ['Posting', '#1e3a5f', '#60a5fa'],
        failed:    ['Failed',  '#7f1d1d', '#f87171'],
    };
    const st = (it.status || '').toLowerCase();
    const sm = statusMap[st] || [it.status || '?', '#374151', '#9ca3af'];

    // For videos the thumb_url serves the video file itself — an <img> can't
    // render it (black square). Use a <video> element seeked to ~0.5s so the
    // browser paints the first frame as a still preview (no ffmpeg needed).
    const thumb = it.thumb_url
        ? (it.is_video
            ? `<video src="${it.thumb_url}#t=0.5" muted preload="metadata" playsinline
                      style="width:100%;height:100%;object-fit:cover;background:#000;"></video>`
            : `<img src="${it.thumb_url}" loading="lazy" style="width:100%;height:100%;object-fit:cover;">`)
        : `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#4b5563;">
             <i class="fas fa-${it.is_video ? 'film' : 'image'} fa-2x"></i></div>`;
    const playIcon = it.is_video
        ? `<div style="position:absolute;top:6px;right:6px;color:#fff;font-size:1rem;text-shadow:0 1px 4px #000;">
             <i class="fas fa-play-circle"></i></div>`
        : '';
    const date = it.posted_at || it.scheduled_time || it.created_at || '';
    const dateShort = date ? String(date).replace('T', ' ').slice(0, 16) : '';
    const cap = (it.caption || '').trim();
    const capShort = cap.length > 64 ? cap.slice(0, 64) + '…' : cap;
    const capHtml = capShort
        ? escHtml(capShort)
        : '<span style="color:#4b5563;">No caption</span>';
    const errTitle = (st === 'failed' && it.error_message)
        ? ' — ERROR: ' + it.error_message : '';

    return `
    <div class="sp-content-card" title="${escAttr(cap + errTitle)}">
        <div class="sp-content-thumb">
            ${thumb}
            ${playIcon}
            <span class="sp-content-type">${escHtml(it.content_type || '')}</span>
            <span class="sp-content-badge" style="background:${sm[1]};color:${sm[2]};">${sm[0]}</span>
        </div>
        <div class="sp-content-meta">
            <div class="sp-content-cap">${capHtml}</div>
            <div class="sp-content-date">${dateShort}</div>
        </div>
    </div>`;
}

// ── Open Settings Panel ──
function openAccountSettings(deviceSerial, username) {
    spCurrentDevice = deviceSerial;
    spCurrentAccount = username;

    // Clear any composer state from a previous account
    try { spComposerCancel(); } catch (e) {}

    // Header
    document.getElementById('spUsername').textContent = '@' + username;
    document.getElementById('spDevice').textContent = deviceSerial;

    // Reset to overview tab
    document.querySelectorAll('.sp-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.sp-tab-btn[data-tab="overview"]').classList.add('active');
    document.querySelectorAll('.sp-pane').forEach(p => p.classList.remove('active'));
    document.querySelector('.sp-pane[data-pane="overview"]').classList.add('active');

    // Show loading, hide content
    document.getElementById('spLoading').style.display = 'flex';
    document.getElementById('spContent').style.display = 'none';

    // Show offcanvas
    var panelEl = document.getElementById('settingsPanel');
    if (!spOffcanvas) {
        spOffcanvas = new bootstrap.Offcanvas(panelEl);
        // Strip Bootstrap's scrollbar padding compensation after panel is fully shown
        panelEl.addEventListener('shown.bs.offcanvas', function() {
            document.body.style.removeProperty('padding-right');
            document.querySelectorAll('.navbar, .fixed-top, .navbar-expand-lg').forEach(function(el) {
                el.style.removeProperty('padding-right');
            });
        });
    }
    spOffcanvas.show();

    // Load settings from API
    fetch(`/api/bot-settings/${encodeURIComponent(deviceSerial)}/${encodeURIComponent(username)}`)
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                showSpToast(data.error || 'Failed to load settings', 'error');
                return;
            }
            populateSettings(data.settings || {}, data.account_data || {});
            populateBusinessFields(data.account_data || {});
            populateMotherFields(data.account_data || {});

            // Load insights data in background
            loadInsights(deviceSerial, username);

            // Load sources in background
            loadSources('sources', 'sp_follow_sources');
            loadSources('like_sources', 'sp_like_sources');
            loadSources('watch_reels_sources', 'sp_reels_sources');
            loadSources('share_sources', 'sp_share_sources');
            loadSources('comment_sources', 'sp_comment_sources');

            // Load follower growth chart
            loadFollowerGrowth(deviceSerial, username);

            document.getElementById('spLoading').style.display = 'none';
            document.getElementById('spContent').style.display = 'block';
        })
        .catch(err => {
            showSpToast('Error loading settings: ' + err, 'error');
        });
}

// ── Toggle Advanced sections ──
function toggleAdvanced(toggleEl) {
    toggleEl.classList.toggle('open');
    const body = toggleEl.nextElementSibling;
    if (body) body.classList.toggle('open');
}

function toggleDmSpecificUsers() {
    var method = document.getElementById('sp_directmessage_method').value;
    var section = document.getElementById('dmSpecificUsersSection');
    if (section) {
        section.style.display = (method === 'dm-specific-users') ? 'block' : 'none';
    }
}

// ── Populate Settings into Form ──
function populateSettings(settings, accountData) {
    // Overview - readonly account info
    document.getElementById('sp_username').value = accountData.username || '';
    document.getElementById('sp_password').value = accountData.password || '';
    // 2FA TOTP secret stored in accounts.two_fa_token (read-only display)
    document.getElementById('sp_2fa').value = accountData.two_fa_token || '';
    document.getElementById('sp_status').value = accountData.status || '';
    document.getElementById('sp_instagram_package').value = accountData.instagram_package || '';
    document.getElementById('sp_followers').value = accountData.followers || '0';
    document.getElementById('sp_tag').value = accountData.tag || '';

    // Active Hours - from account data (now in Overview tab)
    document.getElementById('sp_start_time').value = accountData.start_time || '';
    document.getElementById('sp_end_time').value = accountData.end_time || '';

    // All sp-setting fields (settings_json + toggles merged)
    document.querySelectorAll('.sp-setting').forEach(el => {
        const key = el.dataset.key;
        if (!key) return;
        const val = settings[key];

        if (el.type === 'checkbox') {
            el.checked = toBool(val);
        } else if (el.tagName === 'SELECT') {
            if (val !== undefined && val !== null) {
                // Try to set the option; if not found, just set value
                el.value = val;
            }
        } else {
            el.value = (val !== undefined && val !== null) ? val : '';
        }
    });

    // Show/hide conditional sections
    toggleDmSpecificUsers();

    // Update conditional field visibility based on loaded settings
    updateConditionalFields();

    // Update tab status dots
    updateTabDots();

    // Load browse profiles sources from account_sources
    loadBrowseProfilesSources();
}

// ── Conditional Fields (show/hide based on checkbox) ──
function updateConditionalFields() {
    document.querySelectorAll('.sp-conditional').forEach(div => {
        const dependsId = div.getAttribute('data-depends');
        const checkbox = document.getElementById(dependsId);
        if (checkbox) {
            div.style.display = checkbox.checked ? 'block' : 'none';
        }
    });
}

// Wire up conditional field toggles
document.querySelectorAll('.sp-conditional').forEach(div => {
    const dependsId = div.getAttribute('data-depends');
    const checkbox = document.getElementById(dependsId);
    if (checkbox) {
        checkbox.addEventListener('change', () => {
            div.style.display = checkbox.checked ? 'block' : 'none';
        });
    }
});

// ── Tab Status Dots ──
const tabDotMap = {
    'follow': 'sp_follow_enabled_master',
    'unfollow': 'sp_unfollow_enabled_master',
    'like': 'sp_like_enabled_master',
    'reels': 'sp_enable_watch_reels',
    'share': 'sp_enable_share_post_to_story',
    'story': 'sp_story_enabled_master',
    'comment': 'sp_comment_enabled_master',
    'dm': 'sp_enable_dm_master',
    'hbe': 'sp_hbe_enabled_master',
};

function updateTabDots() {
    for (const [tab, checkboxId] of Object.entries(tabDotMap)) {
        const dot = document.getElementById(`dot-${tab}`);
        const cb = document.getElementById(checkboxId);
        if (dot && cb) {
            dot.classList.toggle('active', cb.checked);
        }
    }
}

// Update dots when any master toggle changes
for (const checkboxId of Object.values(tabDotMap)) {
    const cb = document.getElementById(checkboxId);
    if (cb) {
        cb.addEventListener('change', updateTabDots);
    }
}

// ── Collect Settings from Form ──
function collectSettings() {
    const settings = {};

    document.querySelectorAll('.sp-setting').forEach(el => {
        const key = el.dataset.key;
        if (!key) return;

        if (el.type === 'checkbox') {
            settings[key] = el.checked;
        } else if (el.type === 'number') {
            const v = el.value.trim();
            settings[key] = v !== '' ? parseInt(v) : null;
        } else {
            settings[key] = el.value;
        }
    });

    return settings;
}

// ── Collect account-level fields (start_time, end_time) ──
function collectAccountSettings() {
    const acctSettings = {};
    document.querySelectorAll('.sp-acct-setting').forEach(el => {
        const key = el.dataset.acctKey;
        if (!key) return;
        const v = el.value.trim();
        acctSettings[key] = v !== '' ? v : null;
    });
    return acctSettings;
}

// ── Detect App ID (foreground app on device) ──
function detectAppId() {
    if (!spCurrentDevice) { showSpToast('No device selected', 'error'); return; }
    const btn = event.currentTarget;
    const origHtml = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Detecting...';
    btn.disabled = true;

    fetch(`/api/device-manager/${encodeURIComponent(spCurrentDevice)}/detect-foreground-app`)
        .then(r => r.json())
        .then(data => {
            if (data.success && data.package) {
                document.getElementById('sp_instagram_package').value = data.package;
                showSpToast(`Detected: ${data.package}`, 'success');
            } else {
                showSpToast(data.error || 'Could not detect app', 'error');
            }
        })
        .catch(err => showSpToast('Detection failed: ' + err, 'error'))
        .finally(() => { btn.innerHTML = origHtml; btn.disabled = false; });
}

// ── Save All Settings ──
function saveAllSettings() {
    const statusEl = document.getElementById('spSaveStatus');
    statusEl.textContent = 'Saving...';
    statusEl.style.color = '#ffc107';

    const settings = collectSettings();
    const acctSettings = collectAccountSettings();

    // Include App ID (instagram_package) — editable field
    const appIdVal = document.getElementById('sp_instagram_package').value.trim();
    if (appIdVal) acctSettings.instagram_package = appIdVal;

    // Merge account-level settings for the POST (they'll go into settings_json too)
    // But also update accounts table for start_time / end_time
    Object.assign(settings, acctSettings);

    fetch(`/api/bot-settings/${encodeURIComponent(spCurrentDevice)}/${encodeURIComponent(spCurrentAccount)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showSpToast('Settings saved!', 'success');
            statusEl.textContent = 'Saved ✓';
            statusEl.style.color = '#28a745';
            setTimeout(() => { statusEl.textContent = ''; }, 3000);
            // Refresh the main table to reflect toggle changes
            if (typeof refreshDetail === "function") refreshDetail();
        } else {
            showSpToast(data.error || 'Save failed', 'error');
            statusEl.textContent = 'Error';
            statusEl.style.color = '#dc3545';
        }
    })
    .catch(err => {
        showSpToast('Save error: ' + err, 'error');
        statusEl.textContent = 'Error';
        statusEl.style.color = '#dc3545';
    });
}

// ── Browse Profiles Sources (account_sources table) ──
function loadBrowseProfilesSources() {
    if (!spCurrentDevice || !spCurrentAccount) return;
    fetch(`/api/sources/info?device_id=${encodeURIComponent(spCurrentDevice)}&account_name=${encodeURIComponent(spCurrentAccount)}&action_type=browse_profiles`)
        .then(r => r.json())
        .then(data => {
            const ta = document.getElementById('sp_browse_profiles_sources');
            if (ta && data.content !== undefined) {
                ta.value = data.content || '';
            }
        })
        .catch(err => console.warn('Failed to load browse profiles sources:', err));
}

function saveBrowseProfilesSources() {
    if (!spCurrentDevice || !spCurrentAccount) return;
    const ta = document.getElementById('sp_browse_profiles_sources');
    const usernames = ta.value.trim();
    const accountId = spCurrentDevice + '/' + spCurrentAccount;

    fetch('/api/sources/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            account_ids: [accountId],
            usernames: usernames,
            source_type: 'browse_profiles'
        })
    })
    .then(r => r.json())
    .then(data => {
        const msg = document.getElementById('sp_browse_profiles_saved_msg');
        if (data.success) {
            msg.classList.remove('d-none');
            setTimeout(() => msg.classList.add('d-none'), 2000);
        } else {
            showSpToast(data.message || 'Save failed', 'error');
        }
    })
    .catch(err => showSpToast('Save error: ' + err, 'error'));
}

// ── Sources (load/save) ──
function loadSources(listType, textareaId) {
    fetch(`/api/bot-settings/${encodeURIComponent(spCurrentDevice)}/${encodeURIComponent(spCurrentAccount)}/lists/${listType}`)
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                document.getElementById(textareaId).value = (data.items || []).join('\n');
            }
        })
        .catch(() => {}); // Silently fail for sources
}

function saveSources(listType, textareaId) {
    const text = document.getElementById(textareaId).value;
    const items = text.split('\n').map(s => s.trim()).filter(s => s.length > 0);

    fetch(`/api/bot-settings/${encodeURIComponent(spCurrentDevice)}/${encodeURIComponent(spCurrentAccount)}/lists/${listType}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showSpToast(`Sources saved (${items.length} items)`, 'success');
        } else {
            showSpToast(data.error || 'Failed to save sources', 'error');
        }
    })
    .catch(err => showSpToast('Error: ' + err, 'error'));
}

// ── Helpers ──
function toBool(val) {
    if (val === true || val === 'True' || val === 'true' || val === 'On' || val === 'on' || val === '1' || val === 1) return true;
    return false;
}

function togglePasswordVis() {
    const inp = document.getElementById('sp_password');
    inp.type = inp.type === 'password' ? 'text' : 'password';
}

function toggle2faVis() {
    const inp = document.getElementById('sp_2fa');
    inp.type = inp.type === 'password' ? 'text' : 'password';
}

function copy2faSecret() {
    const inp = document.getElementById('sp_2fa');
    const val = (inp.value || '').trim();
    if (!val) { showSpToast('No 2FA secret stored for this account', 'error'); return; }
    navigator.clipboard.writeText(val)
        .then(() => showSpToast('2FA secret copied', 'success'))
        .catch(() => {
            // Fallback for non-secure contexts
            inp.type = 'text'; inp.select();
            try { document.execCommand('copy'); showSpToast('2FA secret copied', 'success'); }
            catch (e) { showSpToast('Copy failed — select manually', 'error'); }
        });
}

function showSpToast(msg, type) {
    const toast = document.getElementById('spToast');
    toast.textContent = msg;
    toast.className = 'sp-toast ' + (type || 'success');
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// ── Follower Growth Chart ──
function formatNum(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
}

function formatDelta(n) {
    if (n > 0) return `<span style="color:#22c55e;font-weight:600;">+${formatNum(n)}</span>`;
    if (n < 0) return `<span style="color:#ef4444;font-weight:600;">${formatNum(n)}</span>`;
    return `<span style="color:#6c757d;">±0</span>`;
}

function loadFollowerGrowth(deviceSerial, username) {
    const chartCanvas = document.getElementById('growthChart');
    const noDataEl = document.getElementById('growthNoData');

    fetch(`/api/device-manager/${encodeURIComponent(deviceSerial)}/follower-history?username=${encodeURIComponent(username)}&days=30`)
        .then(r => r.json())
        .then(data => {
            if (!data.success || !data.history || data.history.length === 0) {
                // No data — show placeholder
                chartCanvas.style.display = 'none';
                noDataEl.style.display = 'block';
                document.getElementById('growth_followers').textContent = '—';
                document.getElementById('growth_following').textContent = '—';
                document.getElementById('growth_posts').textContent = '—';
                document.getElementById('growth_followers_delta').innerHTML = '—';
                return;
            }

            chartCanvas.style.display = 'block';
            noDataEl.style.display = 'none';

            const history = data.history;
            const growth = data.growth || {};
            const latest = history[history.length - 1];

            // Update stat cards
            document.getElementById('growth_followers').textContent = formatNum(latest.followers);
            document.getElementById('growth_following').textContent = formatNum(latest.following);
            document.getElementById('growth_posts').textContent = formatNum(latest.posts);

            // Delta indicators
            let deltaHtml = '';
            if (growth.today !== undefined && growth.today !== 0) {
                deltaHtml += formatDelta(growth.today) + ' today';
            }
            if (growth.week !== undefined && growth.week !== 0) {
                if (deltaHtml) deltaHtml += ' · ';
                deltaHtml += formatDelta(growth.week) + ' /wk';
            }
            if (!deltaHtml) deltaHtml = '<span style="color:#6c757d;">no change</span>';
            document.getElementById('growth_followers_delta').innerHTML = deltaHtml;

            // Render chart
            const labels = history.map(h => {
                const d = new Date(h.date + 'T00:00:00');
                return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            });
            const followerData = history.map(h => h.followers);

            // Destroy previous chart instance
            if (growthChartInstance) {
                growthChartInstance.destroy();
                growthChartInstance = null;
            }

            growthChartInstance = new Chart(chartCanvas, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Followers',
                        data: followerData,
                        borderColor: '#22c55e',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        borderWidth: 2,
                        pointRadius: history.length > 14 ? 0 : 3,
                        pointHoverRadius: 5,
                        pointBackgroundColor: '#22c55e',
                        tension: 0.3,
                        fill: true,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        intersect: false,
                        mode: 'index',
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: '#1a1d21',
                            titleColor: '#e5e7eb',
                            bodyColor: '#a0aec0',
                            borderColor: '#2d3748',
                            borderWidth: 1,
                            padding: 10,
                            callbacks: {
                                label: ctx => `Followers: ${ctx.parsed.y.toLocaleString()}`
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: '#2d3748', drawBorder: false },
                            ticks: {
                                color: '#a0aec0',
                                font: { size: 10 },
                                maxTicksLimit: 8,
                            }
                        },
                        y: {
                            grid: { color: '#2d3748', drawBorder: false },
                            ticks: {
                                color: '#a0aec0',
                                font: { size: 10 },
                                callback: val => formatNum(val),
                            },
                            beginAtZero: false,
                        }
                    }
                }
            });
        })
        .catch(err => {
            console.warn('Failed to load follower growth:', err);
            chartCanvas.style.display = 'none';
            noDataEl.style.display = 'block';
        });
}

// ═══════════════════════════════════════════════════════════
//  Business Profile & Insights
// ═══════════════════════════════════════════════════════════

let demographicsChartInstance = null;
let activeTimesChartInstance = null;

function populateBusinessFields(accountData) {
    // Update business profile fields from account data
    const isBiz = accountData.is_business_profile ? true : false;
    const checkbox = document.getElementById('sp_is_business_profile');
    if (checkbox) checkbox.checked = isBiz;

    const catField = document.getElementById('sp_business_category');
    if (catField) catField.value = accountData.business_category || '';

    const switchedAt = document.getElementById('sp_business_switched_at');
    if (switchedAt) switchedAt.value = accountData.business_switched_at || 'Not yet';

    // Disable switch button if already business
    const switchBtn = document.getElementById('btn-switch-business');
    if (switchBtn) switchBtn.disabled = isBiz;

    // Disable switch-private button if already private
    const isPrivate = accountData.is_private === 1 || accountData.is_private === '1';
    const switchPrivBtn = document.getElementById('btn-switch-private');
    if (switchPrivBtn) switchPrivBtn.disabled = isPrivate;
    if (isPrivate && switchPrivBtn) {
        switchPrivBtn.innerHTML = '🔒 Already Private';
    } else if (switchPrivBtn) {
        switchPrivBtn.innerHTML = '🔒 Switch to Private';
    }
}

// Holds the current account's id for save-mother POST
let _spCurrentAccountId = null;

// ── Rename account (Hydra-DB-only metadata rename) ──
function openRenameAccountModal() {
    if (!_spCurrentAccountId) {
        showSpToast('No account loaded', 'error');
        return;
    }
    document.getElementById('renameAcctOld').value = spCurrentAccount;
    document.getElementById('renameAcctNew').value = '';
    document.getElementById('renameAcctStatus').textContent = '';
    const btn = document.getElementById('renameAcctConfirmBtn');
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-check me-1"></i> Rename';
    new bootstrap.Modal(document.getElementById('renameAcctModal')).show();
    setTimeout(() => document.getElementById('renameAcctNew').focus(), 200);
}

async function submitRenameAccount() {
    const newName = document.getElementById('renameAcctNew').value.trim();
    const status  = document.getElementById('renameAcctStatus');
    if (!newName) { status.innerHTML = '<span class="text-danger">Enter a new username.</span>'; return; }
    if (newName === spCurrentAccount) {
        status.innerHTML = '<span class="text-warning">Same as current — no change.</span>';
        return;
    }
    const btn = document.getElementById('renameAcctConfirmBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Renaming…';
    status.innerHTML = '<span class="text-muted">Updating DBs…</span>';
    try {
        const r = await fetch(`/api/accounts/${_spCurrentAccountId}/rename`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({new_username: newName})
        });
        const d = await r.json();
        if (!r.ok || !d.success) {
            status.innerHTML = `<span class="text-danger">${d.error || 'Failed'}</span>`;
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-check me-1"></i> Rename';
            return;
        }
        const ff = d.phone_farm_db || {};
        const pa = d.profile_automation_db || {};
        const fmt = (o) => Object.entries(o).map(([k,v])=>`${k}: ${v}`).join(' · ');
        status.innerHTML = `<span class="text-success">
            ✓ Renamed <strong>${d.old_username}</strong> → <strong>${d.new_username}</strong>
        </span><div class="text-muted small mt-1">
            phone_farm.db &mdash; ${fmt(ff)}<br>
            profile_automation.db &mdash; ${fmt(pa)}
        </div>`;
        showSpToast(`Renamed → ${d.new_username}`, 'success');
        // Update visible state immediately so user sees it
        spCurrentAccount = d.new_username;
        document.getElementById('sp_username').value = d.new_username;
        document.getElementById('spUsername').textContent = '@' + d.new_username;
        // Refresh accounts table on the page so the new name appears
        setTimeout(() => { if (typeof refreshDetail === "function") refreshDetail(); }, 400);
    } catch (e) {
        status.innerHTML = `<span class="text-danger">Network error: ${e.message}</span>`;
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-check me-1"></i> Rename';
    }
}

function populateMotherFields(accountData) {
    _spCurrentAccountId = accountData.id || null;
    const cb = document.getElementById('sp_is_mother');
    const isMother = accountData.is_mother === 1 || accountData.is_mother === '1' || accountData.is_mother === true;
    if (cb) cb.checked = !!isMother;

    const warn = document.getElementById('motherWarning');
    if (warn) {
        const isBiz = !!accountData.is_business_profile;
        const hasTag = !!(accountData.tag && String(accountData.tag).trim());
        const issues = [];
        if (isMother && !isBiz) issues.push('Not a business profile — Insights/analytics will be unavailable.');
        if (isMother && !hasTag) issues.push('No tag set — slaves cannot be linked. Add a tag first.');
        if (issues.length) {
            warn.innerHTML = '<i class="fas fa-exclamation-triangle me-1"></i>' + issues.join(' ');
            warn.style.display = 'block';
        } else {
            warn.style.display = 'none';
        }
    }
    const status = document.getElementById('motherSaveStatus');
    if (status) status.textContent = '';
}

async function saveMotherFlag(checked) {
    if (!_spCurrentAccountId) return;
    const status = document.getElementById('motherSaveStatus');
    if (status) status.textContent = 'Saving…';
    try {
        const r = await fetch(`/api/accounts/${_spCurrentAccountId}/mother`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({is_mother: checked ? 1 : 0})
        });
        const data = await r.json();
        if (!r.ok || !data.success) throw new Error(data.error || 'Save failed');
        if (status) {
            status.textContent = checked ? '✅ Marked as mother' : '✅ Unmarked';
            setTimeout(() => { if (status) status.textContent = ''; }, 3000);
        }
        const warn = document.getElementById('motherWarning');
        if (warn && data.warning && checked) {
            warn.innerHTML = '<i class="fas fa-exclamation-triangle me-1"></i>' + data.warning;
            warn.style.display = 'block';
        } else if (warn && !checked) {
            warn.style.display = 'none';
        }
    } catch (e) {
        if (status) status.textContent = '❌ ' + e.message;
        // revert checkbox
        const cb = document.getElementById('sp_is_mother');
        if (cb) cb.checked = !checked;
    }
}

function switchToBusiness() {
    if (!spCurrentDevice || !spCurrentAccount) return;
    const category = document.getElementById('sp_business_category').value.trim() || 'Digital creator';

    const btn = document.getElementById('btn-switch-business');
    const statusEl = document.getElementById('switchBusinessStatus');
    btn.disabled = true;
    statusEl.textContent = 'Creating task...';
    statusEl.style.color = '#ffc107';

    fetch(`/api/device-manager/${encodeURIComponent(spCurrentDevice)}/${encodeURIComponent(spCurrentAccount)}/switch-business`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: category })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showSpToast(data.message, 'success');
            statusEl.textContent = '✓ Task queued — will run on next bot session';
            statusEl.style.color = '#28a745';
        } else {
            showSpToast(data.error || 'Failed', 'error');
            statusEl.textContent = data.error || 'Failed';
            statusEl.style.color = '#dc3545';
            btn.disabled = false;
        }
    })
    .catch(err => {
        showSpToast('Error: ' + err, 'error');
        statusEl.textContent = 'Error';
        statusEl.style.color = '#dc3545';
        btn.disabled = false;
    });
}

function switchToPrivate() {
    if (!spCurrentDevice || !spCurrentAccount) return;

    const btn = document.getElementById('btn-switch-private');
    const statusEl = document.getElementById('switchPrivateStatus');
    btn.disabled = true;
    statusEl.textContent = 'Creating task...';
    statusEl.style.color = '#ffc107';

    fetch(`/api/device-manager/${encodeURIComponent(spCurrentDevice)}/${encodeURIComponent(spCurrentAccount)}/switch-private`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showSpToast(data.message, 'success');
            statusEl.textContent = '✓ Task queued — will run on next bot session';
            statusEl.style.color = '#28a745';
        } else {
            showSpToast(data.error || 'Failed', 'error');
            statusEl.textContent = data.error || 'Failed';
            statusEl.style.color = '#dc3545';
            btn.disabled = false;
        }
    })
    .catch(err => {
        showSpToast('Error: ' + err, 'error');
        statusEl.textContent = 'Error';
        statusEl.style.color = '#dc3545';
        btn.disabled = false;
    });
}

function loadInsights(deviceSerial, username) {
    const notBizEl = document.getElementById('insights-not-business');
    const bizContent = document.getElementById('insights-business-content');
    const noDataEl = document.getElementById('insights-no-data');

    // Hide all sections initially
    notBizEl.style.display = 'none';
    bizContent.style.display = 'none';
    noDataEl.style.display = 'none';

    fetch(`/api/account/${encodeURIComponent(username)}/insights`)
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                notBizEl.style.display = 'block';
                return;
            }

            if (!data.is_business) {
                notBizEl.style.display = 'block';
                return;
            }

            if (!data.insights) {
                noDataEl.style.display = 'block';
                return;
            }

            // Show business content
            bizContent.style.display = 'block';
            const ins = data.insights;

            // Business category badge
            document.getElementById('insights-biz-category').textContent = data.business_category ? `· ${data.business_category}` : '';

            // Overview cards
            document.getElementById('ins-views').textContent = formatNum(ins.views || 0);
            document.getElementById('ins-interactions').textContent = formatNum(ins.interactions || 0);
            document.getElementById('ins-new-followers').textContent = formatNum(ins.new_followers || 0);
            document.getElementById('ins-content-shared').textContent = formatNum(ins.content_shared || 0);

            // Views breakdown
            document.getElementById('ins-accounts-reached').textContent = formatNum(ins.accounts_reached || 0);
            const reachedChg = ins.accounts_reached_change_pct || 0;
            document.getElementById('ins-reached-change').innerHTML =
                reachedChg > 0 ? `<span style="color:#22c55e">▲ ${reachedChg.toFixed(1)}%</span>` :
                reachedChg < 0 ? `<span style="color:#ef4444">▼ ${Math.abs(reachedChg).toFixed(1)}%</span>` : '';

            // Followers vs Non-followers bar
            const fPct = ins.views_followers_pct || 0;
            const nfPct = ins.views_non_followers_pct || 0;
            document.getElementById('ins-bar-followers').style.width = fPct + '%';
            document.getElementById('ins-bar-nonfollowers').style.width = nfPct + '%';
            document.getElementById('ins-followers-pct-label').textContent = `Followers ${fPct.toFixed(0)}%`;
            document.getElementById('ins-nonfollowers-pct-label').textContent = `Non-followers ${nfPct.toFixed(0)}%`;

            // Profile Activity
            document.getElementById('ins-profile-visits').textContent = formatNum(ins.profile_visits || 0);
            const visitChg = ins.profile_visits_change_pct || 0;
            document.getElementById('ins-visits-change').innerHTML =
                visitChg > 0 ? `<span style="color:#22c55e">▲ ${visitChg.toFixed(1)}%</span>` :
                visitChg < 0 ? `<span style="color:#ef4444">▼ ${Math.abs(visitChg).toFixed(1)}%</span>` : '';
            document.getElementById('ins-link-taps').textContent = formatNum(ins.external_link_taps || 0);

            // Total followers
            document.getElementById('ins-total-followers').textContent = formatNum(ins.total_followers || 0);

            // Comparison period
            document.getElementById('insights-comparison-period').textContent =
                ins.comparison_period ? `vs ${ins.comparison_period}` : (ins.date_range || '');

            // Last scraped
            if (ins.scraped_at) {
                const d = new Date(ins.scraped_at);
                document.getElementById('insights-last-scraped').textContent =
                    'Last scraped: ' + d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
            } else {
                document.getElementById('insights-last-scraped').textContent = 'Last scraped: Never';
            }

            // Demographics & active times (from parsed JSON fields)
            const demo = {
                age_ranges: ins.age_range || {},
                gender: ins.gender || {},
                most_active_hours: (ins.most_active_times || {}).hours || [],
                most_active_days: (ins.most_active_times || {}).days || []
            };
            renderDemographicsChart(demo);
            renderActiveTimesChart(demo);
        })
        .catch(err => {
            console.warn('Failed to load insights v2:', err);
            notBizEl.style.display = 'block';
        });
}

function renderDemographicsChart(demo) {
    const canvas = document.getElementById('demographicsChart');
    const noData = document.getElementById('demographicsNoData');

    const ageRanges = demo.age_ranges || {};
    const labels = Object.keys(ageRanges);

    if (!labels.length) {
        canvas.style.display = 'none';
        noData.style.display = 'block';
        return;
    }

    canvas.style.display = 'block';
    noData.style.display = 'none';

    if (demographicsChartInstance) {
        demographicsChartInstance.destroy();
        demographicsChartInstance = null;
    }

    demographicsChartInstance = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Age Distribution %',
                data: labels.map(l => ageRanges[l] || 0),
                backgroundColor: 'rgba(99, 102, 241, 0.6)',
                borderColor: '#6366f1',
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: '#2d3748' }, ticks: { color: '#a0aec0', font: { size: 10 } } },
                y: { grid: { color: '#2d3748' }, ticks: { color: '#a0aec0', font: { size: 10 }, callback: v => v + '%' }, beginAtZero: true }
            }
        }
    });
}

function renderActiveTimesChart(demo) {
    const canvas = document.getElementById('activeTimesChart');
    const noData = document.getElementById('activeTimesNoData');

    const activeHours = demo.most_active_hours || [];
    const activeDays = demo.most_active_days || [];

    if (!activeHours.length && !activeDays.length) {
        canvas.style.display = 'none';
        noData.style.display = 'block';
        return;
    }

    canvas.style.display = 'block';
    noData.style.display = 'none';

    if (activeTimesChartInstance) {
        activeTimesChartInstance.destroy();
        activeTimesChartInstance = null;
    }

    // Build 24-hour activity data (mark active hours)
    const hourLabels = Array.from({length: 24}, (_, i) => i + ':00');
    const hourData = hourLabels.map((_, i) => activeHours.includes(i) ? 1 : 0.15);

    activeTimesChartInstance = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: hourLabels,
            datasets: [{
                label: 'Activity',
                data: hourData,
                backgroundColor: hourData.map(v => v > 0.5 ? 'rgba(40, 167, 69, 0.7)' : 'rgba(108, 117, 125, 0.2)'),
                borderRadius: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false }, ticks: { color: '#a0aec0', font: { size: 8 }, maxTicksLimit: 12 } },
                y: { display: false }
            }
        }
    });
}

function scrapeInsights() {
    if (!spCurrentDevice || !spCurrentAccount) return;

    const btn = document.getElementById('btn-scrape-insights');
    const statusEl = document.getElementById('insights-last-scraped');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scraping...';

    fetch(`/api/insights/${encodeURIComponent(spCurrentDevice)}/${encodeURIComponent(spCurrentAccount)}/scrape`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period: '7d' })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showSpToast(data.message, 'success');
            statusEl.textContent = '✓ Scrape task queued';
        } else {
            showSpToast(data.error || 'Failed', 'error');
        }
    })
    .catch(err => showSpToast('Error: ' + err, 'error'))
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '🔄 Scrape Latest Insights';
    });
}


// ── Profile link (per-account panel action — self-contained: offcanvas input + POST) ──
function setProfileLink() {
    const url = document.getElementById('sp_profile_link').value.trim();
    if (!url) { showSpToast('Enter a URL first', 'error'); return; }

    const btn = document.getElementById('btn-set-link');
    const statusEl = document.getElementById('setLinkStatus');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Setting...';
    statusEl.textContent = 'Running on device...';
    statusEl.style.color = '#f0a040';

    fetch('/api/device-manager/set-profile-link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            device_serial: spCurrentDevice,
            username: spCurrentAccount,
            url: url
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showSpToast('Profile link set successfully!', 'success');
            statusEl.textContent = '✅ Link set';
            statusEl.style.color = '#28a745';
        } else {
            showSpToast(data.error || 'Failed to set link', 'error');
            statusEl.textContent = '❌ ' + (data.error || 'Failed');
            statusEl.style.color = '#dc3545';
        }
    })
    .catch(err => {
        showSpToast('Error: ' + err.message, 'error');
        statusEl.textContent = '❌ Error';
        statusEl.style.color = '#dc3545';
    })
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane me-1"></i>Set on Device';
    });
}

// ── Bulk-op launchers: the REAL implementations + their modals live in
//    device_manager_detail.html. On pages that include this panel but not
//    those modals (accounts, mother), fall back gracefully. The device-manager
//    page's own function declarations override these stubs at load. ──
window.openBulkCopyModal = window.openBulkCopyModal || function(){ if(window.showSpToast) showSpToast('Bulk copy is available on the Device Manager page','error'); };
window.openBulkPrivateModal = window.openBulkPrivateModal || function(){ if(window.showSpToast) showSpToast('Bulk private is available on the Device Manager page','error'); };
window.openBulkLinkModal = window.openBulkLinkModal || function(){ if(window.showSpToast) showSpToast('Bulk link is available on the Device Manager page','error'); };

// ════════════════════════════════════════════════════════════════════
//  Quick Profile Edit — change bio / picture on THIS single account,
//  live on the device. Stops the device bot engine, runs the change,
//  restarts the engine. Backend: /api/profile_automation/single-action
// ════════════════════════════════════════════════════════════════════
(function () {
    var fileInput = document.getElementById('qpePic');
    var drop = document.getElementById('qpeDrop');
    function showPic(file) {
        var prev = document.getElementById('qpePicPreview');
        var btn = document.getElementById('qpePicBtn');
        if (file) {
            if (prev) { prev.src = URL.createObjectURL(file); prev.style.display = 'block'; }
            if (drop) drop.classList.add('has-img');
            if (btn) btn.disabled = false;
        } else {
            if (prev) prev.style.display = 'none';
            if (drop) drop.classList.remove('has-img');
            if (btn) btn.disabled = true;
        }
    }
    if (fileInput) fileInput.addEventListener('change', function () {
        showPic(this.files && this.files[0]);
    });
    if (drop) {
        drop.addEventListener('click', function () { if (fileInput) fileInput.click(); });
        drop.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (fileInput) fileInput.click(); }
        });
        ['dragenter', 'dragover'].forEach(function (ev) {
            drop.addEventListener(ev, function (e) { e.preventDefault(); e.stopPropagation(); drop.classList.add('dragover'); });
        });
        ['dragleave', 'dragend'].forEach(function (ev) {
            drop.addEventListener(ev, function (e) { e.preventDefault(); e.stopPropagation(); drop.classList.remove('dragover'); });
        });
        drop.addEventListener('drop', function (e) {
            e.preventDefault(); e.stopPropagation(); drop.classList.remove('dragover');
            var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
            if (!f || !/^image\//.test(f.type)) return;
            try { var dt = new DataTransfer(); dt.items.add(f); if (fileInput) fileInput.files = dt.files; } catch (err) {}
            showPic(f);
        });
    }
    var panel = document.getElementById('settingsPanel');
    if (panel) panel.addEventListener('shown.bs.offcanvas', function () {
        var d = document.getElementById('qpeDevice'); if (d) d.textContent = (typeof spCurrentDevice !== 'undefined' && spCurrentDevice) || 'device';
        var b = document.getElementById('qpeBio'); if (b) b.value = '';
        var st = document.getElementById('qpeStatus'); if (st) st.innerHTML = '';
        var fi = document.getElementById('qpePic'); if (fi) fi.value = '';
        showPic(null);
    });
})();

function _qpeStatus(html, color) {
    var e = document.getElementById('qpeStatus');
    if (e) { e.innerHTML = html; e.style.color = color || '#9ca3af'; }
}

async function qpeSetBio() {
    var bio = (document.getElementById('qpeBio').value || '').trim();
    if (!bio) { _qpeStatus('Enter a bio first', '#e8637a'); return; }
    if (!spCurrentDevice || !spCurrentAccount) { _qpeStatus('No account loaded', '#e8637a'); return; }
    var btn = document.getElementById('qpeBioBtn'), o = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Working…';
    _qpeStatus('<span class="spinner-border spinner-border-sm me-1"></span>Stopping engine + setting bio on device… (~1 min)', '#e0a23c');
    try {
        var r = await fetch('/api/profile_automation/single-action', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_serial: spCurrentDevice, username: spCurrentAccount, bio: bio })
        });
        var d = await r.json();
        if (d.status === 'success') _qpeStatus('✅ Bio set' + (d.engine_restarted ? ' — engine restarted' : ''), '#2ecc9b');
        else _qpeStatus('❌ ' + (d.message || 'Failed'), '#e8637a');
    } catch (e) { _qpeStatus('❌ ' + e.message, '#e8637a'); }
    finally { btn.disabled = false; btn.innerHTML = o; }
}

async function qpeSetPicture() {
    var fi = document.getElementById('qpePic'), f = fi.files && fi.files[0];
    if (!f) { _qpeStatus('Pick an image first', '#e8637a'); return; }
    if (!spCurrentDevice || !spCurrentAccount) { _qpeStatus('No account loaded', '#e8637a'); return; }
    var btn = document.getElementById('qpePicBtn'), o = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Working…';
    _qpeStatus('<span class="spinner-border spinner-border-sm me-1"></span>Uploading picture…', '#e0a23c');
    try {
        var fd = new FormData(); fd.append('file', f);
        var ur = await fetch('/api/profile_automation/upload-picture', { method: 'POST', body: fd });
        var ud = await ur.json();
        var picId = ud.picture_id;
        if (!ur.ok || !picId) { _qpeStatus('❌ Upload failed: ' + (ud.message || 'no id'), '#e8637a'); return; }
        _qpeStatus('<span class="spinner-border spinner-border-sm me-1"></span>Stopping engine + setting picture on device… (~1 min)', '#e0a23c');
        var r = await fetch('/api/profile_automation/single-action', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_serial: spCurrentDevice, username: spCurrentAccount, uploaded_picture_id: picId })
        });
        var d = await r.json();
        if (d.status === 'success') _qpeStatus('✅ Picture set' + (d.engine_restarted ? ' — engine restarted' : ''), '#2ecc9b');
        else _qpeStatus('❌ ' + (d.message || 'Failed'), '#e8637a');
    } catch (e) { _qpeStatus('❌ ' + e.message, '#e8637a'); }
    finally { btn.disabled = false; btn.innerHTML = o; }
}
