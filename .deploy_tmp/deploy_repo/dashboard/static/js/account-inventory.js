document.addEventListener('DOMContentLoaded', function() {
    // Initialize toasts
    const successToast = new bootstrap.Toast(document.getElementById('successToast'));
    const errorToast = new bootstrap.Toast(document.getElementById('errorToast'));
    
    // Load accounts and devices
    loadInventoryAccounts();
    loadDevices();
    
    // Event listeners
    document.getElementById('importAccountsBtn').addEventListener('click', function(e) {
        e.preventDefault();
        importAccounts();
    });
    
    document.getElementById('searchBtn').addEventListener('click', filterAccounts);
    document.getElementById('statusFilter').addEventListener('change', filterAccounts);
    document.getElementById('searchInventory').addEventListener('keyup', function(e) {
        if (e.key === 'Enter') {
            filterAccounts();
        }
    });
    document.getElementById('saveAccountBtn').addEventListener('click', saveAccountDetails);
    document.getElementById('deleteAccountBtn').addEventListener('click', deleteAccount);
    document.getElementById('confirmAssignBtn').addEventListener('click', assignAccountToDevice);
    
    // Password toggle buttons
    document.querySelectorAll('.toggle-password').forEach(button => {
        button.addEventListener('click', function() {
            const input = this.previousElementSibling;
            const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
            input.setAttribute('type', type);
            this.querySelector('i').classList.toggle('fa-eye');
            this.querySelector('i').classList.toggle('fa-eye-slash');
        });
    });
});

// Load all accounts from inventory
function loadInventoryAccounts() {
    fetch('/api/inventory/accounts')
        .then(response => response.json())
        .then(accounts => {
            displayAccounts(accounts);
        })
        .catch(error => {
            showError('Failed to load accounts: ' + error.message);
        });
}

// Load all devices for the assign modal
function loadDevices() {
    fetch('/api/devices')
        .then(response => response.json())
        .then(devices => {
            const deviceSelect = document.getElementById('deviceSelect');
            deviceSelect.innerHTML = '';
            
            if (devices.length === 0) {
                deviceSelect.innerHTML = '<option value="">No devices found</option>';
                return;
            }
            
            devices.forEach(device => {
                const option = document.createElement('option');
                option.value = device.deviceid;
                option.textContent = `${device.devicename} (${device.deviceid})`;
                deviceSelect.appendChild(option);
            });
        })
        .catch(error => {
            showError('Failed to load devices: ' + error.message);
        });
}

// Display accounts in the table
function displayAccounts(accounts) {
    const tableBody = document.getElementById('accountInventoryTable');
    const noAccountsMessage = document.getElementById('noAccountsMessage');
    
    console.log('Displaying accounts:', accounts);
    tableBody.innerHTML = '';
    
    if (!accounts || accounts.length === 0) {
        noAccountsMessage.classList.remove('d-none');
        return;
    }
    
    noAccountsMessage.classList.add('d-none');
    
    accounts.forEach(account => {
        const row = document.createElement('tr');
        
        // Format dates
        const dateAdded = account.date_added ? new Date(account.date_added).toLocaleString() : '-';
        const dateUsed = account.date_used ? new Date(account.date_used).toLocaleString() : '-';
        
        // Create status badge
        const statusBadge = document.createElement('span');
        statusBadge.classList.add('badge');
        if (account.status === 'available') {
            statusBadge.classList.add('bg-success');
            statusBadge.textContent = 'Available';
        } else {
            statusBadge.classList.add('bg-secondary');
            statusBadge.textContent = 'Used';
        }
        
        // Mask password and 2FA
        const maskedPassword = account.password ? '••••••••' : '-';
        const masked2FA = account.two_factor_auth ? '••••••••' : '-';
        
        row.innerHTML = `
            <td>${account.username || '-'}</td>
            <td>${maskedPassword}</td>
            <td>${masked2FA}</td>
            <td></td>
            <td>${account.device_assigned || '-'}</td>
            <td>${dateAdded}</td>
            <td>${dateUsed}</td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-sm btn-outline-primary edit-account" data-id="${account.id}">
                        <i class="fas fa-edit"></i>
                    </button>
                    ${account.status === 'available' ? `
                    <button class="btn btn-sm btn-outline-success assign-account" data-id="${account.id}" data-username="${account.username}">
                        <i class="fas fa-user-plus"></i>
                    </button>` : ''}
                </div>
            </td>
        `;
        
        // Add status badge to the status cell
        row.querySelector('td:nth-child(4)').appendChild(statusBadge);
        
        // Add event listeners for buttons
        row.querySelector('.edit-account').addEventListener('click', () => openAccountDetails(account.id));
        
        const assignBtn = row.querySelector('.assign-account');
        if (assignBtn) {
            assignBtn.addEventListener('click', () => openAssignModal(account.id, account.username));
        }
        
        tableBody.appendChild(row);
    });
}

// Import accounts from text
function importAccounts() {
    const accountsText = document.getElementById('accountsText').value.trim();
    
    if (!accountsText) {
        showError('Please enter accounts to import');
        return;
    }
    
    console.log('Importing accounts:', accountsText);
    
    // Disable the import button while processing
    const importBtn = document.getElementById('importAccountsBtn');
    const originalText = importBtn.innerHTML;
    importBtn.disabled = true;
    importBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Importing...';
    
    fetch('/api/inventory/accounts/import', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ accounts_text: accountsText })
    })
    .then(response => {
        console.log('Response status:', response.status);
        return response.json();
    })
    .then(data => {
        console.log('Response data:', data);
        
        // Re-enable the import button
        importBtn.disabled = false;
        importBtn.innerHTML = originalText;
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        showSuccess(data.message);
        document.getElementById('accountsText').value = '';
        loadInventoryAccounts();
    })
    .catch(error => {
        console.error('Import error:', error);
        
        // Re-enable the import button
        importBtn.disabled = false;
        importBtn.innerHTML = originalText;
        
        showError('Failed to import accounts: ' + error.message);
    });
}

// Filter accounts by status and search term
function filterAccounts() {
    const status = document.getElementById('statusFilter').value;
    const search = document.getElementById('searchInventory').value.trim();
    
    let url = '/api/inventory/accounts/filter';
    const params = [];
    
    if (status) {
        params.push(`status=${encodeURIComponent(status)}`);
    }
    
    if (search) {
        params.push(`search=${encodeURIComponent(search)}`);
    }
    
    if (params.length > 0) {
        url += '?' + params.join('&');
    }
    
    fetch(url)
        .then(response => response.json())
        .then(accounts => {
            displayAccounts(accounts);
        })
        .catch(error => {
            showError('Failed to filter accounts: ' + error.message);
        });
}

// Open account details modal
function openAccountDetails(accountId) {
    fetch(`/api/inventory/accounts/${accountId}`)
        .then(response => response.json())
        .then(account => {
            if (account.error) {
                showError(account.error);
                return;
            }
            
            // Populate form fields
            document.getElementById('accountId').value = account.id;
            document.getElementById('username').value = account.username;
            document.getElementById('password').value = account.password;
            document.getElementById('twoFactorAuth').value = account.two_factor_auth || '';
            document.getElementById('status').value = account.status;
            document.getElementById('notes').value = account.notes || '';
            document.getElementById('tags').value = account.tags || '';
            
            // Show modal
            const modal = new bootstrap.Modal(document.getElementById('accountDetailsModal'));
            modal.show();
        })
        .catch(error => {
            showError('Failed to load account details: ' + error.message);
        });
}

// Save account details
function saveAccountDetails() {
    const accountId = document.getElementById('accountId').value;
    
    const accountData = {
        password: document.getElementById('password').value,
        two_factor_auth: document.getElementById('twoFactorAuth').value,
        status: document.getElementById('status').value,
        notes: document.getElementById('notes').value,
        tags: document.getElementById('tags').value
    };
    
    fetch(`/api/inventory/accounts/${accountId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(accountData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showError(data.error);
            return;
        }
        
        showSuccess('Account updated successfully');
        bootstrap.Modal.getInstance(document.getElementById('accountDetailsModal')).hide();
        loadInventoryAccounts();
    })
    .catch(error => {
        showError('Failed to update account: ' + error.message);
    });
}

// Delete account
function deleteAccount() {
    if (!confirm('Are you sure you want to delete this account?')) {
        return;
    }
    
    const accountId = document.getElementById('accountId').value;
    
    fetch(`/api/inventory/accounts/${accountId}`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showError(data.error);
            return;
        }
        
        showSuccess('Account deleted successfully');
        bootstrap.Modal.getInstance(document.getElementById('accountDetailsModal')).hide();
        loadInventoryAccounts();
    })
    .catch(error => {
        showError('Failed to delete account: ' + error.message);
    });
}

// Open assign to device modal
function openAssignModal(accountId, username) {
    document.getElementById('assignAccountId').value = accountId;
    document.getElementById('assignAccountUsername').textContent = username;
    
    const modal = new bootstrap.Modal(document.getElementById('assignDeviceModal'));
    modal.show();
}

// Assign account to device
function assignAccountToDevice() {
    const accountId = document.getElementById('assignAccountId').value;
    const deviceId = document.getElementById('deviceSelect').value;
    
    if (!deviceId) {
        showError('Please select a device');
        return;
    }
    
    fetch(`/api/inventory/accounts/${accountId}/assign`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ device_id: deviceId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showError(data.error);
            return;
        }
        
        showSuccess(data.message);
        bootstrap.Modal.getInstance(document.getElementById('assignDeviceModal')).hide();
        loadInventoryAccounts();
    })
    .catch(error => {
        showError('Failed to assign account: ' + error.message);
    });
}

// Show success toast
function showSuccess(message) {
    document.getElementById('successToastMessage').textContent = message;
    const toast = new bootstrap.Toast(document.getElementById('successToast'));
    toast.show();
}

// Show error toast
function showError(message) {
    document.getElementById('errorToastMessage').textContent = message;
    const toast = new bootstrap.Toast(document.getElementById('errorToast'));
    toast.show();
}
