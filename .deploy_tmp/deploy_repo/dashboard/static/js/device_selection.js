/**
 * Device Selection Feature
 * This script adds device selection functionality to all tabs in the Manage Sources page
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize device selection for all tabs
    initDeviceSelection('follow');
    initDeviceSelection('share');
    initDeviceSelection('settings');
    
    // Initialize tab switching to refresh device dropdowns
    document.querySelectorAll('#sourcesTabs button[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', function(e) {
            const targetId = e.target.getAttribute('id');
            if (targetId === 'follow-tab') {
                populateDeviceDropdown('followDeviceSelect', window.followAccounts || []);
            } else if (targetId === 'share-tab') {
                populateDeviceDropdown('shareDeviceSelect', window.shareAccounts || []);
            } else if (targetId === 'settings-tab') {
                populateDeviceDropdown('settingsDeviceSelect', window.settingsAccounts || []);
            }
        });
    });
});

/**
 * Initialize device selection for a specific tab
 * @param {string} tabPrefix - The prefix for the tab (follow, share, settings)
 */
function initDeviceSelection(tabPrefix) {
    const deviceSelectId = `${tabPrefix}DeviceSelect`;
    const deviceSelect = document.getElementById(deviceSelectId);
    
    if (!deviceSelect) return;
    
    deviceSelect.addEventListener('change', function() {
        const selectedDevice = this.value;
        
        // Get the accounts and selectedAccounts from the window object
        const accounts = window[`${tabPrefix}Accounts`] || [];
        const selectedAccountsSet = new Set();
        
        if (selectedDevice) {
            // Filter accounts by selected device
            const filteredAccounts = accounts.filter(account => account.device_id === selectedDevice);
            
            // Select all accounts from this device
            filteredAccounts.forEach(account => {
                const accountId = `${account.device_id}/${account.account_name}`;
                selectedAccountsSet.add(accountId);
            });
            
            // Update the UI to show the selected accounts
            updateAccountSelection(tabPrefix, selectedAccountsSet, accounts);
            
            // Add option to automatically update settings
            if (selectedAccountsSet.size > 0) {
                // Show auto-update prompt
                const autoUpdatePrompt = document.createElement('div');
                autoUpdatePrompt.className = 'alert alert-info mt-3';
                autoUpdatePrompt.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <i class="fas fa-info-circle me-2"></i>
                            <strong>${selectedAccountsSet.size}</strong> accounts selected from device <strong>${selectedDevice}</strong>
                        </div>
                        <button class="btn btn-primary btn-sm auto-update-btn">Auto Update</button>
                    </div>
                `;
                
                // Insert the prompt after the device dropdown
                const deviceFilterContainer = deviceSelect.closest('.device-filter');
                if (deviceFilterContainer) {
                    // Remove any existing prompt
                    const existingPrompt = deviceFilterContainer.nextElementSibling;
                    if (existingPrompt && existingPrompt.classList.contains('alert')) {
                        existingPrompt.remove();
                    }
                    
                    // Insert new prompt
                    deviceFilterContainer.after(autoUpdatePrompt);
                    
                    // Add click handler to auto-update button
                    const autoUpdateBtn = autoUpdatePrompt.querySelector('.auto-update-btn');
                    if (autoUpdateBtn) {
                        autoUpdateBtn.addEventListener('click', function() {
                            // Trigger the appropriate update action based on the tab
                            if (tabPrefix === 'follow') {
                                document.getElementById('followUpdateSourcesBtn').click();
                            } else if (tabPrefix === 'share') {
                                document.getElementById('shareUpdateSourcesBtn').click();
                            } else if (tabPrefix === 'settings') {
                                document.getElementById('updateSettingsBtn').click();
                            }
                        });
                    }
                }
            }
        } else {
            // Show all accounts but don't select them
            updateAccountSelection(tabPrefix, new Set(), accounts);
            
            // Remove any auto-update prompt
            const deviceFilterContainer = deviceSelect.closest('.device-filter');
            if (deviceFilterContainer) {
                const existingPrompt = deviceFilterContainer.nextElementSibling;
                if (existingPrompt && existingPrompt.classList.contains('alert')) {
                    existingPrompt.remove();
                }
            }
        }
    });
}

/**
 * Update the account selection in the UI
 * @param {string} tabPrefix - The prefix for the tab (follow, share, settings)
 * @param {Set} selectedAccounts - Set of selected account IDs
 * @param {Array} accounts - Array of all accounts
 */
function updateAccountSelection(tabPrefix, selectedAccounts, accounts) {
    // Get all account checkboxes in this tab
    const accountCheckboxes = document.querySelectorAll(`#${tabPrefix}AccountsList .account-checkbox`);
    const accountCards = document.querySelectorAll(`#${tabPrefix}AccountsList .account-card`);
    
    // Update the checkboxes and card selection
    accountCheckboxes.forEach((checkbox, index) => {
        const card = accountCards[index];
        if (!card) return;
        
        const accountId = card.dataset.accountId;
        const isSelected = selectedAccounts.has(accountId);
        
        checkbox.checked = isSelected;
        if (isSelected) {
            card.classList.add('selected');
        } else {
            card.classList.remove('selected');
        }
    });
    
    // Update the internal selection state in the page's JavaScript
    if (window[`${tabPrefix}SelectedAccounts`]) {
        // Clear the existing selection
        window[`${tabPrefix}SelectedAccounts`].clear();
        
        // Add all the new selections
        selectedAccounts.forEach(accountId => {
            window[`${tabPrefix}SelectedAccounts`].add(accountId);
        });
    } else {
        // If the selection set doesn't exist yet, create it
        window[`${tabPrefix}SelectedAccounts`] = selectedAccounts;
    }
    
    // Update the selected count badge
    const selectedCountBadge = document.getElementById(`${tabPrefix}SelectedCount`);
    if (selectedCountBadge) {
        selectedCountBadge.textContent = selectedAccounts.size;
    }
}

/**
 * Populate the device dropdown with unique device IDs
 * @param {string} dropdownId - The ID of the dropdown element
 * @param {Array} accounts - Array of accounts
 */
function populateDeviceDropdown(dropdownId, accounts) {
    const dropdown = document.getElementById(dropdownId);
    if (!dropdown || !accounts || accounts.length === 0) return;
    
    // Get unique device IDs
    const deviceIds = [...new Set(accounts.map(account => account.device_id))];
    
    // Clear existing options except the first one (All Devices)
    while (dropdown.options.length > 1) {
        dropdown.remove(1);
    }
    
    // Add device options
    deviceIds.forEach(deviceId => {
        const option = document.createElement('option');
        option.value = deviceId;
        option.textContent = deviceId;
        dropdown.appendChild(option);
    });
}
