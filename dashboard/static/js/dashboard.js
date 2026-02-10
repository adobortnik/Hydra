// Dashboard functionality for The Live House

// Global variables
let allAccounts = [];
let allDevices = [];
let currentSortColumn = 0;
let currentSortDirection = 'asc';

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Load initial data
    loadDashboardData();
    
    // Set up event listeners
    document.getElementById('refreshData').addEventListener('click', loadDashboardData);
    document.getElementById('accountSearch').addEventListener('input', filterAccounts);
    document.getElementById('deviceFilter').addEventListener('change', filterAccounts);
});

// Load all dashboard data
async function loadDashboardData() {
    try {
        // Show loading state
        document.getElementById('accountsTableBody').innerHTML = '<tr><td colspan="8" class="text-center"><div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>Loading accounts data...</td></tr>';
        
        // Load devices first
        await loadDevices();
        
        // Then load accounts
        await loadAccounts();
        
        // Initial filtering and sorting
        filterAccounts();
    } catch (error) {
        handleApiError(error);
        document.getElementById('accountsTableBody').innerHTML = '<tr><td colspan="8" class="text-center text-danger">Error loading data. Please try again.</td></tr>';
    }
}

// Load devices from API
async function loadDevices() {
    try {
        const response = await fetch('/api/devices');
        if (!response.ok) throw new Error('Failed to load devices');
        
        allDevices = await response.json();
        
        // Populate device filter dropdown
        const deviceFilter = document.getElementById('deviceFilter');
        
        // Clear existing options except the first one
        while (deviceFilter.options.length > 1) {
            deviceFilter.remove(1);
        }
        
        // Add device options
        allDevices.forEach(device => {
            const option = document.createElement('option');
            option.value = device.deviceid;
            option.textContent = `${device.devicename} (${device.deviceid})`;
            deviceFilter.appendChild(option);
        });
    } catch (error) {
        handleApiError(error);
        throw error; // Re-throw to handle in the calling function
    }
}

// Load accounts from API
async function loadAccounts() {
    try {
        const response = await fetch('/api/accounts');
        if (!response.ok) throw new Error('Failed to load accounts');
        
        allAccounts = await response.json();
    } catch (error) {
        handleApiError(error);
        throw error; // Re-throw to handle in the calling function
    }
}

// Filter accounts based on search and device filter
function filterAccounts() {
    const searchTerm = document.getElementById('accountSearch').value.toLowerCase();
    const deviceId = document.getElementById('deviceFilter').value;
    
    // Filter accounts based on search term and device
    const filteredAccounts = allAccounts.filter(account => {
        const matchesSearch = account.account.toLowerCase().includes(searchTerm);
        const matchesDevice = deviceId === '' || account.deviceid === deviceId;
        return matchesSearch && matchesDevice;
    });
    
    // Sort the filtered accounts
    sortAccounts(filteredAccounts);
    
    // Render the filtered and sorted accounts
    renderAccounts(filteredAccounts);
}

// Sort accounts by the specified column
function sortTable(columnIndex) {
    // If clicking the same column, toggle direction
    if (currentSortColumn === columnIndex) {
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortColumn = columnIndex;
        currentSortDirection = 'asc';
    }
    
    // Update sort indicators in the table header
    updateSortIndicators();
    
    // Re-filter (which will also sort and render)
    filterAccounts();
}

// Update sort indicator icons in the table header
function updateSortIndicators() {
    const headers = document.querySelectorAll('#accountsTable th');
    
    headers.forEach((header, index) => {
        const icon = header.querySelector('i');
        
        // Reset all icons
        icon.className = 'fas fa-sort ms-1';
        header.classList.remove('active-sort');
        
        // Set active sort icon
        if (index === currentSortColumn) {
            header.classList.add('active-sort');
            icon.className = currentSortDirection === 'asc' ? 
                'fas fa-sort-up ms-1' : 'fas fa-sort-down ms-1';
        }
    });
}

// Sort the accounts array based on current sort settings
function sortAccounts(accounts) {
    accounts.sort((a, b) => {
        let valueA, valueB;
        
        // Extract values based on column index
        switch (currentSortColumn) {
            case 0: // Username
                valueA = a.account;
                valueB = b.account;
                break;
            case 1: // Device
                valueA = a.devicename || '';
                valueB = b.devicename || '';
                break;
            case 2: // Runtime
                valueA = parseInt(a.starttime || '0');
                valueB = parseInt(b.starttime || '0');
                break;
            case 3: // Followers
                valueA = parseInt(a.stats?.followers || '0');
                valueB = parseInt(b.stats?.followers || '0');
                break;
            case 4: // Following
                valueA = parseInt(a.stats?.following || '0');
                valueB = parseInt(b.stats?.following || '0');
                break;
            case 5: // Follow
                valueA = a.follow === 'True' ? 1 : 0;
                valueB = b.follow === 'True' ? 1 : 0;
                break;
            case 6: // Unfollow
                valueA = a.unfollow === 'True' ? 1 : 0;
                valueB = b.unfollow === 'True' ? 1 : 0;
                break;
            default:
                valueA = a.account;
                valueB = b.account;
        }
        
        // Compare the values
        if (valueA < valueB) {
            return currentSortDirection === 'asc' ? -1 : 1;
        }
        if (valueA > valueB) {
            return currentSortDirection === 'asc' ? 1 : -1;
        }
        return 0;
    });
}

// Render accounts to the table
function renderAccounts(accounts) {
    const tableBody = document.getElementById('accountsTableBody');
    
    // Clear existing rows
    tableBody.innerHTML = '';
    
    // If no accounts, show message
    if (accounts.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="8" class="text-center">No accounts found matching your criteria</td></tr>';
        return;
    }
    
    // Add rows for each account
    accounts.forEach(account => {
        const row = document.createElement('tr');
        
        // Username column
        const usernameCell = document.createElement('td');
        usernameCell.innerHTML = `<div class="d-flex align-items-center">
            <div class="avatar-sm me-2 bg-primary rounded-circle d-flex align-items-center justify-content-center">
                <span>${account.account.charAt(0).toUpperCase()}</span>
            </div>
            <strong>${account.account}</strong>
        </div>`;
        row.appendChild(usernameCell);
        
        // Device column
        const deviceCell = document.createElement('td');
        deviceCell.innerHTML = `<span class="badge bg-info text-dark">${account.devicename || account.deviceid}</span>`;
        row.appendChild(deviceCell);
        
        // Runtime column
        const runtimeCell = document.createElement('td');
        const isActive = account.starttime !== '0' || account.endtime !== '0';
        runtimeCell.innerHTML = `${createStatusIndicator(isActive)} ${formatRuntime(account.starttime, account.endtime)}`;
        row.appendChild(runtimeCell);
        
        // Followers column
        const followersCell = document.createElement('td');
        followersCell.innerHTML = `<span class="badge bg-secondary">${formatNumber(account.stats?.followers || 0)}</span>`;
        row.appendChild(followersCell);
        
        // Following column
        const followingCell = document.createElement('td');
        followingCell.innerHTML = `<span class="badge bg-secondary">${formatNumber(account.stats?.following || 0)}</span>`;
        row.appendChild(followingCell);
        
        // Follow column
        const followCell = document.createElement('td');
        followCell.innerHTML = account.follow === 'True' ? 
            '<span class="badge bg-success"><i class="fas fa-check-circle me-1"></i>Enabled</span>' : 
            '<span class="badge bg-secondary"><i class="fas fa-times-circle me-1"></i>Disabled</span>';
        row.appendChild(followCell);
        
        // Unfollow column
        const unfollowCell = document.createElement('td');
        unfollowCell.innerHTML = account.unfollow === 'True' ? 
            '<span class="badge bg-success"><i class="fas fa-check-circle me-1"></i>Enabled</span>' : 
            '<span class="badge bg-secondary"><i class="fas fa-times-circle me-1"></i>Disabled</span>';
        row.appendChild(unfollowCell);
        
        // Actions column
        const actionsCell = document.createElement('td');
        actionsCell.innerHTML = `
            <div class="btn-group" role="group">
                <button type="button" class="btn btn-sm btn-primary view-details" data-deviceid="${account.deviceid}" data-account="${account.account}" data-bs-toggle="tooltip" title="View Details">
                    <i class="fas fa-eye"></i>
                </button>
                <button type="button" class="btn btn-sm btn-danger remove-account" data-deviceid="${account.deviceid}" data-account="${account.account}" data-bs-toggle="tooltip" title="Remove Account">
                    <i class="fas fa-trash"></i>
                </button>
                <button type="button" class="btn btn-sm btn-info buy-followers" data-deviceid="${account.deviceid}" data-account="${account.account}" data-bs-toggle="tooltip" title="Buy Followers">
                    <i class="fas fa-shopping-cart"></i>
                </button>
            </div>
        `;
        row.appendChild(actionsCell);
        
        // Add row to table
        tableBody.appendChild(row);
    });
    
    // Add event listeners to view details buttons
    document.querySelectorAll('.view-details').forEach(button => {
        button.addEventListener('click', function() {
            const deviceId = this.getAttribute('data-deviceid');
            const accountName = this.getAttribute('data-account');
            showAccountDetails(deviceId, accountName);
        });
    });
    
    // Add event listeners to remove account buttons
    document.querySelectorAll('.remove-account').forEach(button => {
        button.addEventListener('click', function() {
            const deviceId = this.getAttribute('data-deviceid');
            const accountName = this.getAttribute('data-account');
            showRemoveAccountModal(deviceId, accountName);
        });
    });
    
    // Add event listeners to buy followers buttons
    document.querySelectorAll('.buy-followers').forEach(button => {
        button.addEventListener('click', function() {
            const deviceId = this.getAttribute('data-deviceid');
            const accountName = this.getAttribute('data-account');
            showBuyFollowersModal(accountName);
        });
    });

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Show account details in modal
async function showAccountDetails(deviceId, accountName) {
    try {
        // Update modal title
        document.getElementById('accountDetailsTitle').textContent = `Account Details: ${accountName}`;
        
        // Show loading state
        document.getElementById('accountDetailsBody').innerHTML = `
            <div class="text-center">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p>Loading account details...</p>
            </div>
        `;
        
        // Show the modal
        const modal = new bootstrap.Modal(document.getElementById('accountDetailsModal'));
        modal.show();
        
        // Fetch account details
        const response = await fetch(`/api/account/${deviceId}/${accountName}`);
        if (!response.ok) throw new Error('Failed to load account details');
        
        const accountDetails = await response.json();
        
        // Render account details
        renderAccountDetails(accountDetails);
    } catch (error) {
        handleApiError(error);
        document.getElementById('accountDetailsBody').innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>
                Error loading account details. Please try again.
            </div>
        `;
    }
}

// Render account details in the modal
function renderAccountDetails(account) {
    const detailsBody = document.getElementById('accountDetailsBody');
    
    // Create content
    let content = `
        <div class="row mb-4">
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-header bg-primary text-white">
                        <h6 class="mb-0"><i class="fas fa-user me-2"></i>Account Information</h6>
                    </div>
                    <div class="card-body">
                        <div class="text-center mb-4">
                            <div class="avatar-lg mx-auto bg-primary rounded-circle d-flex align-items-center justify-content-center mb-3">
                                <span style="font-size: 2rem;">${account.account.charAt(0).toUpperCase()}</span>
                            </div>
                            <h5 class="text-white">${account.account}</h5>
                        </div>
                        <div class="account-detail-row">
                            <div class="account-detail-label">Username</div>
                            <div class="text-white">${account.account}</div>
                        </div>
                        <div class="account-detail-row">
                            <div class="account-detail-label">Password</div>
                            <div class="d-flex align-items-center">
                                <span class="me-2 text-white" id="password-display" data-value="${account.password}">••••••••</span>
                                <button class="btn btn-sm btn-outline-secondary" onclick="toggleSensitiveInfo(document.getElementById('password-display'))">
                                    <i class="fas fa-eye"></i>
                                </button>
                            </div>
                        </div>
                        <div class="account-detail-row">
                            <div class="account-detail-label">Run Time</div>
                            <div class="text-white">${formatRuntime(account.starttime, account.endtime)}</div>
                        </div>
                        <div class="account-detail-row">
                            <div class="account-detail-label">Device</div>
                            <div><span class="badge bg-info text-white">${account.deviceid}</span></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-header bg-info text-white">
                        <h6 class="mb-0"><i class="fas fa-chart-bar me-2"></i>Account Stats</h6>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-6 mb-3">
                                <div class="stat-card bg-dark">
                                    <div class="stat-icon text-primary">
                                        <i class="fas fa-users"></i>
                                    </div>
                                    <div class="stat-value text-white">${formatNumber(account.stats?.followers || 0)}</div>
                                    <div class="stat-label text-white-50">Followers</div>
                                </div>
                            </div>
                            <div class="col-6 mb-3">
                                <div class="stat-card bg-dark">
                                    <div class="stat-icon text-success">
                                        <i class="fas fa-user-friends"></i>
                                    </div>
                                    <div class="stat-value text-white">${formatNumber(account.stats?.following || 0)}</div>
                                    <div class="stat-label text-white-50">Following</div>
                                </div>
                            </div>
                            <div class="col-12">
                                <div class="stat-card bg-dark">
                                    <div class="stat-icon text-warning">
                                        <i class="fas fa-exchange-alt"></i>
                                    </div>
                                    <div class="stat-value text-white">
                                        ${calculateFollowRatio(account.stats?.followers || 0, account.stats?.following || 0)}
                                    </div>
                                    <div class="stat-label text-white-50">Follower/Following Ratio</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-warning text-dark d-flex justify-content-between align-items-center">
                        <h6 class="mb-0"><i class="fas fa-cog me-2"></i>Account Settings</h6>
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="editModeSwitch">
                            <label class="form-check-label text-dark" for="editModeSwitch">Edit Mode</label>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-4 mb-3">
                                <div class="setting-card p-3 rounded border border-secondary">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input editable-setting" type="checkbox" id="followSwitch" 
                                               data-field="follow" data-account="${account.account}" data-deviceid="${account.deviceid}" 
                                               ${account.follow === 'True' ? 'checked' : ''} disabled>
                                        <label class="form-check-label text-white" for="followSwitch">Follow</label>
                                    </div>
                                    <small class="text-white-50 d-block mt-2">Automatically follow users</small>
                                </div>
                            </div>
                            <div class="col-md-4 mb-3">
                                <div class="setting-card p-3 rounded border border-secondary">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input editable-setting" type="checkbox" id="unfollowSwitch" 
                                               data-field="unfollow" data-account="${account.account}" data-deviceid="${account.deviceid}" 
                                               ${account.unfollow === 'True' ? 'checked' : ''} disabled>
                                        <label class="form-check-label text-white" for="unfollowSwitch">Unfollow</label>
                                    </div>
                                    <small class="text-white-50 d-block mt-2">Automatically unfollow users</small>
                                </div>
                            </div>
                            <div class="col-md-4 mb-3">
                                <div class="setting-card p-3 rounded border border-secondary">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input editable-setting" type="checkbox" id="muteSwitch" 
                                               data-field="mute" data-account="${account.account}" data-deviceid="${account.deviceid}" 
                                               ${account.mute === 'True' ? 'checked' : ''} disabled>
                                        <label class="form-check-label text-white" for="muteSwitch">Mute</label>
                                    </div>
                                    <small class="text-white-50 d-block mt-2">Mute followed users</small>
                                </div>
                            </div>
                            <div class="col-md-4 mb-3">
                                <div class="setting-card p-3 rounded border border-secondary">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input editable-setting" type="checkbox" id="likeSwitch" 
                                               data-field="like" data-account="${account.account}" data-deviceid="${account.deviceid}" 
                                               ${account.like === 'True' ? 'checked' : ''} disabled>
                                        <label class="form-check-label text-white" for="likeSwitch">Like</label>
                                    </div>
                                    <small class="text-white-50 d-block mt-2">Automatically like posts</small>
                                </div>
                            </div>
                            <div class="col-md-4 mb-3">
                                <div class="setting-card p-3 rounded border border-secondary">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input editable-setting" type="checkbox" id="randomActionSwitch" 
                                               data-field="randomaction" data-account="${account.account}" data-deviceid="${account.deviceid}" 
                                               ${account.randomaction === 'True' ? 'checked' : ''} disabled>
                                        <label class="form-check-label text-white" for="randomActionSwitch">Random Action</label>
                                    </div>
                                    <small class="text-white-50 d-block mt-2">Perform random actions</small>
                                </div>
                            </div>
                            <div class="col-md-4 mb-3">
                                <div class="setting-card p-3 rounded border border-secondary">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input editable-setting" type="checkbox" id="switchModeSwitch" 
                                               data-field="switchmode" data-account="${account.account}" data-deviceid="${account.deviceid}" 
                                               ${account.switchmode === 'True' ? 'checked' : ''} disabled>
                                        <label class="form-check-label text-white" for="switchModeSwitch">Switch Mode</label>
                                    </div>
                                    <small class="text-white-50 d-block mt-2">Switch between modes</small>
                                </div>
                            </div>
                        </div>
                        <div class="mt-4 text-center" id="saveSettingsContainer" style="display: none;">
                            <button id="saveSettings" class="btn btn-success">
                                <i class="fas fa-save me-2"></i>Save Settings
                            </button>
                            <div class="mt-2 text-white-50 small">Changes will be applied to the account immediately</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    detailsBody.innerHTML = content;
    
    // Add event listener to edit mode switch
    document.getElementById('editModeSwitch').addEventListener('change', function() {
        const editableSettings = document.querySelectorAll('.editable-setting');
        const saveContainer = document.getElementById('saveSettingsContainer');
        
        if (this.checked) {
            // Enable editing
            editableSettings.forEach(input => {
                input.disabled = false;
            });
            saveContainer.style.display = 'block';
        } else {
            // Disable editing
            editableSettings.forEach(input => {
                input.disabled = true;
            });
            saveContainer.style.display = 'none';
        }
    });
    
    // Add event listener to save button
    document.getElementById('saveSettings').addEventListener('click', function() {
        saveAccountSettings(account.deviceid, account.account);
    });
}

// Save account settings
async function saveAccountSettings(deviceId, accountName) {
    try {
        // Collect all settings
        const settings = {};
        document.querySelectorAll('.editable-setting').forEach(input => {
            const field = input.getAttribute('data-field');
            const value = input.type === 'checkbox' ? (input.checked ? 'True' : 'False') : input.value;
            settings[field] = value;
        });
        
        // Show loading state
        const saveButton = document.getElementById('saveSettings');
        const originalText = saveButton.innerHTML;
        saveButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Saving...';
        saveButton.disabled = true;
        
        // Send update request
        const response = await fetch(`/api/account/update/${deviceId}/${accountName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(settings)
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Show success message
            const toast = document.createElement('div');
            toast.className = 'toast align-items-center text-white bg-success border-0';
            toast.setAttribute('role', 'alert');
            toast.setAttribute('aria-live', 'assertive');
            toast.setAttribute('aria-atomic', 'true');
            toast.innerHTML = `
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="fas fa-check-circle me-2"></i>
                        Settings saved successfully
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            `;
            
            document.getElementById('toastContainer').appendChild(toast);
            
            const bsToast = new bootstrap.Toast(toast, {
                autohide: true,
                delay: 3000
            });
            
            bsToast.show();
            
            // Turn off edit mode
            document.getElementById('editModeSwitch').checked = false;
            document.querySelectorAll('.editable-setting').forEach(input => {
                input.disabled = true;
            });
            document.getElementById('saveSettingsContainer').style.display = 'none';
            
            // Refresh data
            loadDashboardData();
        } else {
            throw new Error(result.error || 'Failed to save settings');
        }
    } catch (error) {
        handleApiError(error);
    } finally {
        // Restore button state
        const saveButton = document.getElementById('saveSettings');
        saveButton.innerHTML = '<i class="fas fa-save me-2"></i>Save Settings';
        saveButton.disabled = false;
    }
}

// Calculate follower to following ratio
function calculateFollowRatio(followers, following) {
    if (following === 0) return 'N/A';
    const ratio = (followers / following).toFixed(2);
    return ratio;
}

// Show remove account confirmation modal
function showRemoveAccountModal(deviceId, accountName) {
    // Set modal values
    document.getElementById('removeDeviceId').value = deviceId;
    document.getElementById('removeAccountName').value = accountName;
    document.getElementById('removeAccountTitle').textContent = `Remove ${accountName}`;
    document.getElementById('removeAccountConfirmText').textContent = `Are you sure you want to remove ${accountName} from device ${deviceId}?`;
    
    // Show the modal
    const removeModal = new bootstrap.Modal(document.getElementById('removeAccountModal'));
    removeModal.show();
}

// Remove account from device
function removeAccount() {
    const deviceId = document.getElementById('removeDeviceId').value;
    const accountName = document.getElementById('removeAccountName').value;
    
    // Show loading state
    const removeButton = document.getElementById('confirmRemoveBtn');
    const originalText = removeButton.innerHTML;
    removeButton.disabled = true;
    removeButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Removing...';
    
    // Call API to remove account
    fetch('/remove_account_from_device', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            device_id: deviceId,
            username: accountName
        })
    })
    .then(response => response.json())
    .then(data => {
        // Reset button state
        removeButton.disabled = false;
        removeButton.innerHTML = originalText;
        
        // Close the modal
        bootstrap.Modal.getInstance(document.getElementById('removeAccountModal')).hide();
        
        if (data.success) {
            // Show success message
            showToast('Success', data.message, 'success');
            
            // Reload accounts data
            loadDashboardData();
        } else {
            // Show error message
            showToast('Error', data.message, 'danger');
        }
    })
    .catch(error => {
        // Reset button state
        removeButton.disabled = false;
        removeButton.innerHTML = originalText;
        
        // Show error message
        showToast('Error', 'Failed to remove account: ' + error.message, 'danger');
        console.error('Error removing account:', error);
    });
}

// Show toast notification
function showToast(title, message, type = 'info') {
    const toastId = 'toast-' + Date.now();
    const toastContainer = document.getElementById('toastContainer');
    
    const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header bg-${type} text-white">
                <strong class="me-auto">${title}</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body bg-dark text-white">
                ${message}
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
    toast.show();
    
    // Remove toast from DOM after it's hidden
    toastElement.addEventListener('hidden.bs.toast', function () {
        toastElement.remove();
    });
}

// Add avatar style
const style = document.createElement('style');
style.textContent = `
    .avatar-sm {
        width: 32px;
        height: 32px;
        font-size: 14px;
        color: white;
    }
    .avatar-lg {
        width: 80px;
        height: 80px;
        font-size: 32px;
        color: white;
    }
    .setting-card {
        background-color: var(--dark-surface-2);
        transition: transform 0.3s;
    }
    .setting-card:hover {
        transform: translateY(-3px);
    }
`;
document.head.appendChild(style);

// Show buy followers modal
function showBuyFollowersModal(accountName) {
    // Set modal values
    document.getElementById('buyFollowersAccountName').textContent = accountName;
    
    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('buyFollowersModal'));
    modal.show();
}
