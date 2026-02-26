// Profile Automation JavaScript
let currentTag = null;
let allDevices = [];
let allAccounts = [];
let selectedAccounts = new Set(); // Track selected accounts for campaigns
let campaignSelectedAccounts = new Set(); // Track accounts selected in campaign modal
let campaignTagAccounts = []; // All accounts for the selected tag in campaign modal

// Load initial data
document.addEventListener('DOMContentLoaded', function() {
    loadStats();
    loadTags();
    loadLibrary();
    loadDevicesAndAccounts();
});

// Load stats
async function loadStats() {
    try {
        // Get tags
        const tagsResp = await fetch('/api/profile_automation/tags');
        const tagsData = await tagsResp.json();
        document.getElementById('totalTags').textContent = tagsData.tags.length;

        // Count tagged accounts
        let totalTagged = tagsData.tags.reduce((sum, tag) => sum + tag.account_count, 0);
        document.getElementById('taggedAccounts').textContent = totalTagged;

        // Get pending tasks
        const tasksResp = await fetch('/api/profile_automation/tasks');
        const tasksData = await tasksResp.json();
        document.getElementById('pendingTasks').textContent = tasksData.tasks.length;

        // Get profile pictures
        const picsResp = await fetch('/api/profile_automation/profile_pictures');
        const picsData = await picsResp.json();
        document.getElementById('profilePictures').textContent = picsData.pictures.length;

    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Load tags
async function loadTags() {
    try {
        const response = await fetch('/api/profile_automation/tags');
        const data = await response.json();

        const tagsList = document.getElementById('tagsList');
        const campaignTagSelect = document.getElementById('campaignTag');

        tagsList.innerHTML = '';
        campaignTagSelect.innerHTML = '<option value="">-- Select Tag --</option>';

        data.tags.forEach(tag => {
            // Badge for tags list
            const badge = document.createElement('span');
            badge.className = 'badge bg-primary tag-badge';
            badge.textContent = `${tag.name} (${tag.account_count})`;
            badge.onclick = () => selectTag(tag.name);
            tagsList.appendChild(badge);

            // Option for campaign select
            const option = document.createElement('option');
            option.value = tag.name;
            option.textContent = `${tag.name} (${tag.account_count} accounts)`;
            campaignTagSelect.appendChild(option);
        });

    } catch (error) {
        console.error('Error loading tags:', error);
        showAlert('Error loading tags', 'danger');
    }
}

// Create tag
async function createTag() {
    const tagName = document.getElementById('newTagName').value.trim();

    if (!tagName) {
        showAlert('Please enter a tag name', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/profile_automation/tags', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: tagName})
        });

        const data = await response.json();

        if (data.status === 'success') {
            showAlert(`Tag "${tagName}" created!`, 'success');
            document.getElementById('newTagName').value = '';
            loadTags();
            loadStats();
        } else {
            showAlert(data.message, 'danger');
        }

    } catch (error) {
        console.error('Error creating tag:', error);
        showAlert('Error creating tag', 'danger');
    }
}

// Select tag
async function selectTag(tagName) {
    currentTag = tagName;
    selectedAccounts.clear(); // Reset selections
    document.getElementById('selectedTagName').textContent = tagName;
    document.getElementById('bulkTagBtn').style.display = 'inline-block';
    document.getElementById('bulkTagName').textContent = tagName;

    try {
        const response = await fetch(`/api/profile_automation/accounts/${tagName}`);
        const data = await response.json();

        const accountsList = document.getElementById('taggedAccountsList');

        if (data.accounts.length === 0) {
            accountsList.innerHTML = `
                <div class="alert alert-warning">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    No accounts tagged with "${tagName}". Use "Bulk Tag Devices" to tag accounts.
                </div>
            `;
            return;
        }

        // Add select all / deselect all buttons
        accountsList.innerHTML = `
            <div class="mb-3">
                <button class="btn btn-sm btn-primary me-2" onclick="selectAllAccounts()">
                    <i class="fas fa-check-square me-1"></i>Select All
                </button>
                <button class="btn btn-sm btn-secondary me-2" onclick="deselectAllAccounts()">
                    <i class="fas fa-square me-1"></i>Deselect All
                </button>
                <button class="btn btn-sm btn-success" onclick="campaignWithSelected()">
                    <i class="fas fa-rocket me-1"></i>Campaign with Selected (<span id="selectedCount">0</span>)
                </button>
            </div>
            <div id="accountsContainer"></div>
        `;

        const container = document.getElementById('accountsContainer');

        data.accounts.forEach(account => {
            const accountKey = `${account.device_serial}|||${account.username}`;
            const card = document.createElement('div');
            card.className = 'card account-card mb-2';
            card.innerHTML = `
                <div class="card-body py-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="form-check">
                            <input class="form-check-input account-checkbox" type="checkbox"
                                   id="acc_${account.device_serial}_${account.username}"
                                   data-device="${account.device_serial}"
                                   data-username="${account.username}"
                                   onchange="updateSelectedCount()">
                            <label class="form-check-label text-white" for="acc_${account.device_serial}_${account.username}">
                                <strong>${account.username}</strong>
                                <br>
                                <small class="text-white-50">${account.device_serial}</small>
                            </label>
                        </div>
                        <button class="btn btn-sm btn-danger" onclick="untagAccount('${account.device_serial}', '${account.username}', '${tagName}')">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });

    } catch (error) {
        console.error('Error loading tagged accounts:', error);
        showAlert('Error loading tagged accounts', 'danger');
    }
}

// Select all accounts
function selectAllAccounts() {
    document.querySelectorAll('.account-checkbox').forEach(checkbox => {
        checkbox.checked = true;
    });
    updateSelectedCount();
}

// Deselect all accounts
function deselectAllAccounts() {
    document.querySelectorAll('.account-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });
    updateSelectedCount();
}

// Update selected count
function updateSelectedCount() {
    selectedAccounts.clear();
    document.querySelectorAll('.account-checkbox:checked').forEach(checkbox => {
        const device = checkbox.getAttribute('data-device');
        const username = checkbox.getAttribute('data-username');
        selectedAccounts.add(`${device}|||${username}`);
    });
    document.getElementById('selectedCount').textContent = selectedAccounts.size;
}

// Campaign with selected accounts
function campaignWithSelected() {
    if (selectedAccounts.size === 0) {
        showAlert('Please select at least one account', 'warning');
        return;
    }

    // Open quick campaign modal with selected accounts
    const modal = new bootstrap.Modal(document.getElementById('quickCampaignModal'));

    // Pre-fill the tag
    document.getElementById('campaignTag').value = currentTag;

    // Update modal to show selected accounts
    updateCampaignModalForSelected();

    modal.show();
}

// Update campaign modal to show selected accounts
function updateCampaignModalForSelected() {
    const selectedList = Array.from(selectedAccounts).map(key => {
        const [device, username] = key.split('|||');
        return `<li>${username} <small class="text-white-50">(${device})</small></li>`;
    }).join('');

    const existingWarning = document.querySelector('#quickCampaignModal .alert-warning');
    if (existingWarning) {
        existingWarning.innerHTML = `
            <i class="fas fa-info-circle me-2"></i>
            Campaign will be created for <strong>${selectedAccounts.size} selected accounts</strong>:
            <ul class="mt-2 mb-0" style="max-height: 150px; overflow-y: auto;">
                ${selectedList}
            </ul>
        `;
    }
}

// Untag account
async function untagAccount(deviceSerial, username, tag) {
    if (!confirm(`Remove tag "${tag}" from ${username}?`)) return;

    try {
        const response = await fetch('/api/profile_automation/accounts/untag', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                device_serial: deviceSerial,
                username: username,
                tag: tag
            })
        });

        const data = await response.json();

        if (data.status === 'success') {
            showAlert('Tag removed', 'success');
            selectTag(tag);
            loadStats();
        }

    } catch (error) {
        console.error('Error untagging account:', error);
        showAlert('Error removing tag', 'danger');
    }
}

// Load devices and accounts (same method as /accounts page)
async function loadDevicesAndAccounts() {
    try {
        // Load devices first
        const devicesResp = await fetch('/api/devices');
        const devicesData = await devicesResp.json();
        allDevices = devicesData;

        // Load accounts
        const accountsResp = await fetch('/api/accounts');
        allAccounts = await accountsResp.json();

        // Populate device select in modal
        const deviceSelect = document.getElementById('deviceSelect');
        deviceSelect.innerHTML = '';
        allDevices.forEach(device => {
            const option = document.createElement('option');
            option.value = device.deviceid;
            option.textContent = `${device.devicename || device.deviceid} (${device.deviceid})`;
            deviceSelect.appendChild(option);
        });

        console.log(`Loaded ${allDevices.length} devices and ${allAccounts.length} accounts`);

    } catch (error) {
        console.error('Error loading devices and accounts:', error);
        showAlert('Error loading devices and accounts', 'danger');
    }
}

// Bulk tag devices
function bulkTagDevices() {
    if (!currentTag) {
        showAlert('Please select a tag first', 'warning');
        return;
    }

    // Populate device select - you'll need to integrate with your existing device list
    const modal = new bootstrap.Modal(document.getElementById('bulkTagModal'));
    modal.show();
}

// Execute bulk tag
async function executeBulkTag() {
    const deviceSelect = document.getElementById('deviceSelect');
    const selectedDevices = Array.from(deviceSelect.selectedOptions).map(opt => opt.value);

    if (selectedDevices.length === 0) {
        showAlert('Please select at least one device', 'warning');
        return;
    }

    // Show loading state
    const executeBtn = document.querySelector('#bulkTagModal .btn-primary');
    const originalText = executeBtn.innerHTML;
    executeBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Tagging...';
    executeBtn.disabled = true;

    try {
        const response = await fetch('/api/profile_automation/accounts/tag/bulk', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                tag: currentTag,
                device_serials: selectedDevices
            })
        });

        const data = await response.json();

        if (data.status === 'success') {
            showAlert(`Tagged ${data.tagged_count} accounts!`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('bulkTagModal')).hide();
            selectTag(currentTag);
            loadStats();
            loadTags(); // Refresh tag counts
        } else {
            showAlert(data.message || 'Error bulk tagging accounts', 'danger');
        }

    } catch (error) {
        console.error('Error bulk tagging:', error);
        showAlert('Error bulk tagging accounts', 'danger');
    } finally {
        executeBtn.innerHTML = originalText;
        executeBtn.disabled = false;
    }
}

// Execute quick campaign
async function executeQuickCampaign() {
    const tag = document.getElementById('campaignTag').value;
    const motherAccount = document.getElementById('motherAccount').value.trim();
    const motherBio = document.getElementById('motherBio').value.trim();
    const nameShortcuts = document.getElementById('nameShortcuts').value.trim();
    const useAI = document.getElementById('useAI').checked;

    // Get action checkboxes
    const changePicture = document.getElementById('changePicture').checked;
    const changeBio = document.getElementById('changeBio').checked;
    const changeUsername = document.getElementById('changeUsername').checked;

    if (!tag) {
        showAlert('Please select a tag', 'warning');
        return;
    }

    if (!motherAccount) {
        showAlert('Please enter a mother account', 'warning');
        return;
    }

    // Note: API key will be loaded from global settings by the backend

    // Check if at least one action is selected
    if (!changePicture && !changeBio && !changeUsername) {
        showAlert('Please select at least one action to perform', 'warning');
        return;
    }

    const resultDiv = document.getElementById('campaignResult');
    resultDiv.innerHTML = '<div class="text-center"><div class="spinner-border text-primary"></div><p class="mt-2">Creating campaign...</p></div>';

    // Prepare selected accounts from campaign modal (priority) or from tags tab
    let selectedAccountsList = null;
    if (campaignSelectedAccounts.size > 0) {
        selectedAccountsList = Array.from(campaignSelectedAccounts).map(key => {
            const [device_serial, username] = key.split('|||');
            return { device_serial, username };
        });
    } else if (selectedAccounts.size > 0) {
        selectedAccountsList = Array.from(selectedAccounts).map(key => {
            const [device_serial, username] = key.split('|||');
            return { device_serial, username };
        });
    }

    // Parse name shortcuts
    const shortcuts = nameShortcuts ? nameShortcuts.split(',').map(s => s.trim()).filter(s => s) : [];

    try {
        const response = await fetch('/api/profile_automation/quick_campaign', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                tag: tag,
                mother_account: motherAccount,
                mother_bio: motherBio || '',
                name_shortcuts: shortcuts,
                use_ai: useAI,
                // API key will be loaded from global settings by the backend
                selected_accounts: selectedAccountsList,  // Include selected accounts
                actions: {
                    change_picture: changePicture,
                    change_bio: changeBio,
                    change_username: changeUsername
                }
            })
        });

        const data = await response.json();

        if (data.status === 'success') {
            resultDiv.innerHTML = `
                <div class="alert alert-success">
                    <h6><i class="fas fa-check-circle me-2"></i>Campaign Created!</h6>
                    <p class="mb-2">${data.message}</p>
                    <p class="mb-0"><strong>${data.tasks_created}</strong> profile update tasks created.</p>
                    <hr>
                    <p class="mb-0 small">
                        <i class="fas fa-terminal me-2"></i>
                        Next step: Run <code>python automated_profile_manager.py</code> in the uiAutomator folder to execute the tasks.
                    </p>
                </div>
            `;
            loadStats();

            // Clear selections after successful campaign
            selectedAccounts.clear();
            campaignSelectedAccounts.clear();
        } else {
            resultDiv.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    ${data.message}
                </div>
            `;
        }

    } catch (error) {
        console.error('Error executing campaign:', error);
        resultDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>
                Error executing campaign: ${error.message}
            </div>
        `;
    }
}

// Load library (pictures and bio templates)
async function loadLibrary() {
    try {
        // Load profile pictures
        const picsResp = await fetch('/api/profile_automation/profile_pictures');
        const picsData = await picsResp.json();

        const picturesList = document.getElementById('picturesList');
        picturesList.innerHTML = '';

        if (picsData.pictures.length === 0) {
            picturesList.innerHTML = `
                <div class="col-12">
                    <p class="text-white-50">No profile pictures in library. Add pictures using profile_task_manager.py</p>
                </div>
            `;
        } else {
            picsData.pictures.slice(0, 12).forEach(pic => {
                const col = document.createElement('div');
                col.className = 'col-md-4 mb-3';
                col.innerHTML = `
                    <div class="card">
                        <div class="card-body">
                            <h6 class="text-white">${pic.filename}</h6>
                            <small class="text-white-50">Gender: ${pic.gender || 'N/A'}<br>Used: ${pic.times_used} times</small>
                        </div>
                    </div>
                `;
                picturesList.appendChild(col);
            });
        }

        // Load bio templates
        const biosResp = await fetch('/api/profile_automation/bio_templates');
        const biosData = await biosResp.json();

        const biosList = document.getElementById('bioTemplatesList');
        biosList.innerHTML = '';

        if (biosData.templates.length === 0) {
            biosList.innerHTML = '<p class="text-white-50">No bio templates. Add templates using profile_task_manager.py</p>';
        } else {
            biosData.templates.forEach(template => {
                const card = document.createElement('div');
                card.className = 'card mb-2';
                card.innerHTML = `
                    <div class="card-body py-2">
                        <strong class="text-white">${template.name}</strong>
                        <p class="text-white-50 mb-0 small">${template.bio_text}</p>
                        <small class="text-white-50">Used ${template.times_used} times</small>
                    </div>
                `;
                biosList.appendChild(card);
            });
        }

    } catch (error) {
        console.error('Error loading library:', error);
    }
}

// Show alert
function showAlert(message, type = 'info') {
    // You can integrate this with your existing alert system
    alert(message);
}

// Load tag accounts for campaign modal
async function loadTagAccountsForCampaign() {
    const tag = document.getElementById('campaignTag').value;

    if (!tag) {
        document.getElementById('tagAccountCount').style.display = 'none';
        document.getElementById('accountSelectionSection').style.display = 'none';
        return;
    }

    try {
        const response = await fetch(`/api/profile_automation/accounts/${tag}`);
        const data = await response.json();

        campaignTagAccounts = data.accounts;
        campaignSelectedAccounts.clear(); // Reset selections

        // Show account count
        document.getElementById('totalAccountCount').textContent = data.accounts.length;
        document.getElementById('tagAccountCount').style.display = 'block';

        // Update warning message
        updateCampaignWarning(data.accounts.length, 0);

    } catch (error) {
        console.error('Error loading tag accounts:', error);
        showAlert('Error loading accounts for tag', 'danger');
    }
}

// Toggle account selection section
function toggleAccountSelection() {
    const section = document.getElementById('accountSelectionSection');

    if (section.style.display === 'none') {
        section.style.display = 'block';
        renderCampaignAccounts();
    } else {
        section.style.display = 'none';
    }
}

// Render campaign accounts list
function renderCampaignAccounts() {
    const container = document.getElementById('campaignAccountsList');

    if (campaignTagAccounts.length === 0) {
        container.innerHTML = '<p class="text-white-50 text-center">No accounts in this tag</p>';
        return;
    }

    container.innerHTML = '';

    campaignTagAccounts.forEach(account => {
        const accountKey = `${account.device_serial}|||${account.username}`;
        const isSelected = campaignSelectedAccounts.has(accountKey);

        const accountDiv = document.createElement('div');
        accountDiv.className = `campaign-account-item p-2 mb-1 rounded ${isSelected ? 'selected' : ''}`;
        accountDiv.setAttribute('data-device', account.device_serial);
        accountDiv.setAttribute('data-username', account.username);
        accountDiv.style.cursor = 'pointer'; // Make it look clickable
        accountDiv.innerHTML = `
            <div class="form-check">
                <input class="form-check-input campaign-account-checkbox" type="checkbox"
                       id="campaign_acc_${account.device_serial}_${account.username}"
                       data-account-key="${accountKey}"
                       ${isSelected ? 'checked' : ''}
                       onchange="updateCampaignSelectedCount()">
                <label class="form-check-label text-white w-100" for="campaign_acc_${account.device_serial}_${account.username}">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${account.username}</strong>
                            <br>
                            <small class="text-white-50">${account.device_serial}</small>
                        </div>
                    </div>
                </label>
            </div>
        `;

        // Make entire div clickable (toggle checkbox)
        accountDiv.addEventListener('click', function(e) {
            // Don't toggle if clicking directly on the checkbox (it handles itself)
            if (e.target.type === 'checkbox') {
                return;
            }

            // Find the checkbox and toggle it programmatically
            const checkbox = accountDiv.querySelector('.campaign-account-checkbox');
            checkbox.checked = !checkbox.checked;

            // Trigger the change event so the visual updates happen
            const event = new Event('change', { bubbles: true });
            checkbox.dispatchEvent(event);
        });

        container.appendChild(accountDiv);
    });

    updateCampaignSelectedCount();
}

// Select all campaign accounts
function selectAllCampaignAccounts() {
    document.querySelectorAll('.campaign-account-checkbox').forEach(checkbox => {
        checkbox.checked = true;
    });
    updateCampaignSelectedCount();
}

// Deselect all campaign accounts
function deselectAllCampaignAccounts() {
    document.querySelectorAll('.campaign-account-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });
    updateCampaignSelectedCount();
}

// Update campaign selected count
function updateCampaignSelectedCount() {
    campaignSelectedAccounts.clear();

    document.querySelectorAll('.campaign-account-checkbox:checked').forEach(checkbox => {
        const accountKey = checkbox.getAttribute('data-account-key');
        campaignSelectedAccounts.add(accountKey);

        // Update visual styling
        const parent = checkbox.closest('.campaign-account-item');
        parent.classList.add('selected');
        const icon = parent.querySelector('.fa-check-circle');
        if (icon) icon.style.display = 'block';
    });

    document.querySelectorAll('.campaign-account-checkbox:not(:checked)').forEach(checkbox => {
        const parent = checkbox.closest('.campaign-account-item');
        parent.classList.remove('selected');
        const icon = parent.querySelector('.fa-check-circle');
        if (icon) icon.style.display = 'none';
    });

    const selectedCount = campaignSelectedAccounts.size;
    const totalCount = campaignTagAccounts.length;

    document.getElementById('campaignSelectedCount').textContent = `${selectedCount} selected`;

    // Update warning message
    updateCampaignWarning(totalCount, selectedCount);
}

// Update campaign warning message
function updateCampaignWarning(totalCount, selectedCount) {
    const warning = document.getElementById('campaignWarning');

    if (selectedCount === 0) {
        warning.className = 'alert alert-warning';
        warning.innerHTML = `
            <i class="fas fa-exclamation-triangle me-2"></i>
            This will create tasks for <strong>ALL ${totalCount} accounts</strong> with the selected tag.
        `;
    } else if (selectedCount === totalCount) {
        warning.className = 'alert alert-info';
        warning.innerHTML = `
            <i class="fas fa-info-circle me-2"></i>
            Campaign will run on <strong>all ${totalCount} accounts</strong> in this tag.
        `;
    } else {
        warning.className = 'alert alert-info';
        warning.innerHTML = `
            <i class="fas fa-info-circle me-2"></i>
            Campaign will run on <strong>${selectedCount} of ${totalCount} accounts</strong>.
            <span class="text-white-50">(${totalCount - selectedCount} will be skipped)</span>
        `;
    }
}

// Filter campaign accounts by search
function filterCampaignAccounts() {
    const searchTerm = document.getElementById('accountSearchInput').value.toLowerCase();

    document.querySelectorAll('.campaign-account-item').forEach(item => {
        const device = item.getAttribute('data-device').toLowerCase();
        const username = item.getAttribute('data-username').toLowerCase();

        if (device.includes(searchTerm) || username.includes(searchTerm)) {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}

// Grant storage permissions on all devices
async function grantPermissions() {
    const btn = document.getElementById('grantPermissionsBtn');
    const originalHtml = btn.innerHTML;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Granting...';

    try {
        const response = await fetch('/api/profile_automation/grant_permissions', {
            method: 'POST'
        });

        const data = await response.json();

        if (data.status === 'success') {
            showAlert(`✓ ${data.message}\n\nGranted permissions to ${data.granted} Instagram apps across ${data.devices} device(s)`, 'success');
        } else {
            showAlert(`Error: ${data.message}`, 'danger');
        }

    } catch (error) {
        console.error('Error granting permissions:', error);
        showAlert('Error granting permissions: ' + error.message, 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
    }
}

// Run batch processor
async function runBatchProcessor() {
    const btn = document.getElementById('runProcessorBtn');
    const originalHtml = btn.innerHTML;

    // Get current pending tasks count
    const pendingTasks = parseInt(document.getElementById('pendingTasks').textContent);

    if (pendingTasks === 0) {
        showAlert('No pending tasks to process. Create a campaign first!', 'warning');
        return;
    }

    if (!confirm(`Start batch processor for ${pendingTasks} pending task(s)?\n\nThis will connect to devices and execute all profile changes.`)) {
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Starting...';

    try {
        const response = await fetch('/api/profile_automation/run_processor', {
            method: 'POST'
        });

        const data = await response.json();

        if (data.status === 'success') {
            showAlert(`✓ ${data.message}\n\nCheck the console/terminal for progress.`, 'success');

            // Start polling for status updates
            pollProcessorStatus();
        } else {
            showAlert(`Error: ${data.message}`, 'danger');
        }

    } catch (error) {
        console.error('Error starting processor:', error);
        showAlert('Error starting processor: ' + error.message, 'danger');
    } finally {
        setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }, 3000);
    }
}

// Poll processor status
function pollProcessorStatus() {
    const intervalId = setInterval(async () => {
        try {
            const response = await fetch('/api/profile_automation/processor_status');
            const data = await response.json();

            if (data.status === 'success') {
                // Update pending tasks count
                document.getElementById('pendingTasks').textContent = data.total_pending;

                // Update badge on button
                const badge = document.getElementById('processorTaskBadge');
                if (data.total_pending > 0) {
                    badge.textContent = data.total_pending;
                    badge.style.display = 'inline';
                } else {
                    badge.style.display = 'none';
                    // Stop polling when no more tasks
                    clearInterval(intervalId);
                }
            }
        } catch (error) {
            console.error('Error polling status:', error);
        }
    }, 5000); // Poll every 5 seconds
}

// ============================================================================
// TASK QUEUE FUNCTIONS (Similar to Login Automation)
// ============================================================================

let tasks = [];

// Load all tasks
async function loadTasks() {
    try {
        const response = await fetch('/api/profile_automation/tasks');
        const data = await response.json();

        if (data.status === 'success') {
            tasks = data.tasks || [];
            renderTasks(tasks);

            // Update badge
            const pendingCount = tasks.filter(t => t.status === 'pending').length;
            document.getElementById('taskQueueBadge').textContent = pendingCount;
            document.getElementById('processorTaskBadge').textContent = pendingCount;
        }
    } catch (error) {
        console.error('Error loading tasks:', error);
    }
}

// Render tasks list
function renderTasks(taskList) {
    const container = document.getElementById('tasksList');

    if (taskList.length === 0) {
        container.innerHTML = `
            <div class="text-center text-white-50 py-5">
                <i class="fas fa-clipboard-list fa-3x mb-3"></i>
                <p>No tasks yet. Create tasks via campaigns or tags.</p>
            </div>
        `;
        return;
    }

    // Group by status
    const grouped = {
        pending: taskList.filter(t => t.status === 'pending'),
        processing: taskList.filter(t => t.status === 'processing'),
        completed: taskList.filter(t => t.status === 'completed'),
        failed: taskList.filter(t => t.status === 'failed')
    };

    let html = '';

    // Pending tasks
    if (grouped.pending.length > 0) {
        html += `<div class="mb-4">
            <h6 class="text-warning mb-3"><i class="fas fa-clock me-2"></i>Pending (${grouped.pending.length})</h6>`;
        grouped.pending.forEach(task => {
            html += renderTaskCard(task);
        });
        html += '</div>';
    }

    // Processing tasks
    if (grouped.processing.length > 0) {
        html += `<div class="mb-4">
            <h6 class="text-info mb-3"><i class="fas fa-spinner me-2"></i>Processing (${grouped.processing.length})</h6>`;
        grouped.processing.forEach(task => {
            html += renderTaskCard(task);
        });
        html += '</div>';
    }

    // Failed tasks
    if (grouped.failed.length > 0) {
        html += `<div class="mb-4">
            <h6 class="text-danger mb-3"><i class="fas fa-times-circle me-2"></i>Failed (${grouped.failed.length})</h6>`;
        grouped.failed.forEach(task => {
            html += renderTaskCard(task);
        });
        html += '</div>';
    }

    // Completed tasks
    if (grouped.completed.length > 0) {
        html += `<div class="mb-4">
            <h6 class="text-success mb-3"><i class="fas fa-check-circle me-2"></i>Completed (${grouped.completed.length})</h6>`;
        grouped.completed.forEach(task => {
            html += renderTaskCard(task);
        });
        html += '</div>';
    }

    container.innerHTML = html;
}

// Render individual task card
function renderTaskCard(task) {
    const statusColors = {
        pending: 'warning',
        processing: 'info',
        completed: 'success',
        failed: 'danger'
    };

    const statusIcons = {
        pending: 'clock',
        processing: 'spinner fa-spin',
        completed: 'check-circle',
        failed: 'times-circle'
    };

    const color = statusColors[task.status] || 'secondary';
    const icon = statusIcons[task.status] || 'question';

    const actions = task.username || '';
    const actionsArray = [];
    if (task.new_username) actionsArray.push('Username');
    if (task.new_bio) actionsArray.push('Bio');
    if (task.profile_picture_id) actionsArray.push('Picture');
    const actionsText = actionsArray.join(', ') || 'Profile update';

    return `
        <div class="p-3 mb-2 rounded" style="border: 1px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.2);">
            <div class="d-flex justify-content-between align-items-start">
                <div class="flex-grow-1">
                    <div class="d-flex align-items-center mb-2">
                        <span class="badge bg-${color} me-2">
                            <i class="fas fa-${icon} me-1"></i>${task.status}
                        </span>
                        <strong class="text-white">Task #${task.id}</strong>
                        <span class="text-white-50 ms-2">${task.device_serial}</span>
                    </div>
                    <div class="text-white-50 small">
                        ${actionsText}
                        ${task.error_message ? `<br><span class="text-danger">${task.error_message}</span>` : ''}
                    </div>
                </div>
                <div>
                    ${(task.status === 'processing' || task.status === 'failed' || task.status === 'pending') ? `
                        <button class="btn btn-sm btn-outline-warning me-1" onclick="restartTask(${task.id})" title="Restart">
                            <i class="fas fa-redo"></i>
                        </button>
                    ` : ''}
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteTask(${task.id})" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        </div>
    `;
}

// Delete task
async function deleteTask(taskId) {
    if (!confirm('Delete this task?')) return;

    try {
        const response = await fetch(`/api/profile_automation/tasks/${taskId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.status === 'success') {
            showAlert('Task deleted', 'success');
            loadTasks();
            refreshStatistics();
        } else {
            showAlert('Error: ' + data.message, 'danger');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error: ' + error.message, 'danger');
    }
}

// Restart task
async function restartTask(taskId) {
    if (!confirm('Restart this task? It will be set back to pending status.')) return;

    try {
        const response = await fetch(`/api/profile_automation/tasks/${taskId}/restart`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });

        const data = await response.json();

        if (data.status === 'success') {
            showAlert('Task restarted', 'success');
            loadTasks();
            refreshStatistics();
        } else {
            showAlert('Error: ' + data.message, 'danger');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error: ' + error.message, 'danger');
    }
}

// Run parallel processor
async function runParallelProcessor() {
    const pendingCount = tasks.filter(t => t.status === 'pending').length;

    if (pendingCount === 0) {
        showAlert('No pending tasks to process', 'warning');
        return;
    }

    // Count tasks by device
    const tasksByDevice = {};
    tasks.filter(t => t.status === 'pending').forEach(task => {
        if (!tasksByDevice[task.device_serial]) {
            tasksByDevice[task.device_serial] = 0;
        }
        tasksByDevice[task.device_serial]++;
    });

    const deviceCount = Object.keys(tasksByDevice).length;
    const deviceList = Object.entries(tasksByDevice)
        .map(([device, count]) => `  • ${device}: ${count} task(s)`)
        .join('\n');

    const message = `Process ${pendingCount} pending task(s) across ${deviceCount} device(s) in parallel?\n\n${deviceList}\n\nDevices will run simultaneously for faster processing!`;

    if (!confirm(message)) return;

    const btn = document.getElementById('runProcessorBtn');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Processing...';

    try {
        const response = await fetch('/api/profile_automation/tasks/process-parallel', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({})
        });

        const data = await response.json();

        if (data.status === 'success') {
            const stats = data.stats;
            const duration = data.duration;

            let message = `Parallel Processing Complete!\n\n`;
            message += `✅ Successful: ${stats.successful}\n`;
            message += `❌ Failed: ${stats.failed}\n`;
            message += `📊 Total: ${stats.total}\n`;
            message += `⏱️ Duration: ${duration} seconds (${Math.floor(duration / 60)}m ${duration % 60}s)`;

            showAlert(message, 'success');
            loadTasks();
            refreshStatistics();
            loadHistory();
        } else {
            showAlert('Error: ' + data.message, 'danger');
            if (data.traceback) {
                console.error('Traceback:', data.traceback);
            }
        }
    } catch (error) {
        console.error('Error running parallel processor:', error);
        showAlert('Error running parallel processor: ' + error.message, 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

// Clear completed tasks
async function clearCompletedTasks() {
    if (!confirm('Clear all completed tasks from the queue?')) return;

    try {
        const response = await fetch('/api/profile_automation/tasks/clear', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({days_old: 7})
        });

        const data = await response.json();

        if (data.status === 'success') {
            showAlert(`Cleared ${data.deleted_count} completed tasks`, 'success');
            loadTasks();
            refreshStatistics();
        } else {
            showAlert('Error: ' + data.message, 'danger');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Error: ' + error.message, 'danger');
    }
}

// Load history
async function loadHistory() {
    try {
        const response = await fetch('/api/profile_automation/history?limit=50');
        const data = await response.json();

        if (data.status === 'success') {
            renderHistory(data.history || []);
        }
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

// Render history
function renderHistory(history) {
    const container = document.getElementById('historyList');

    if (history.length === 0) {
        container.innerHTML = '<div class="text-center text-white-50 py-3"><p>No history yet</p></div>';
        return;
    }

    container.innerHTML = history.map(item => {
        const icon = item.success ? '<i class="fas fa-check-circle text-success"></i>' : '<i class="fas fa-times-circle text-danger"></i>';
        const time = new Date(item.updated_at || item.created_at).toLocaleString();

        return `
            <div class="p-2 mb-2 rounded" style="border: 1px solid rgba(255,255,255,0.1);">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        ${icon} <strong>${item.device_serial}</strong>
                        <br>
                        <small class="text-white-50">
                            ${time}<br>
                            Task #${item.id || 'N/A'}
                        </small>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Refresh statistics
async function refreshStatistics() {
    try {
        const response = await fetch('/api/profile_automation/statistics');
        const data = await response.json();

        if (data.status === 'success') {
            const stats = data.statistics;
            document.getElementById('pendingTasks').textContent = stats.pending || 0;
            document.getElementById('processorTaskBadge').textContent = stats.pending || 0;
            document.getElementById('taskQueueBadge').textContent = stats.pending || 0;
        }
    } catch (error) {
        console.error('Error refreshing statistics:', error);
    }
}

// Start polling on page load
document.addEventListener('DOMContentLoaded', function() {
    pollProcessorStatus();
    loadTasks();
    loadHistory();
    refreshStatistics();

    // Auto-refresh every 30 seconds
    setInterval(() => {
        loadTasks();
        refreshStatistics();
    }, 30000);
});
