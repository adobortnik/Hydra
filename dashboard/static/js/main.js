// Common utility functions for the application

// Format numbers with commas
function formatNumber(num) {
    return num ? num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",") : "0";
}

// Format date strings
function formatDate(dateStr) {
    if (!dateStr) return "N/A";
    const date = new Date(dateStr);
    return date.toLocaleDateString();
}

// Show toast notifications
function showToast(message, type = 'info') {
    // Create toast container if it doesn't exist
    if (!document.getElementById('toast-container')) {
        const toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }
    
    // Create toast element
    const toastId = 'toast-' + Date.now();
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.id = toastId;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    // Toast content
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    // Add to container
    document.getElementById('toast-container').appendChild(toast);
    
    // Initialize and show toast
    const bsToast = new bootstrap.Toast(toast, { delay: 5000 });
    bsToast.show();
    
    // Remove after hiding
    toast.addEventListener('hidden.bs.toast', function () {
        toast.remove();
    });
}

// Handle API errors
function handleApiError(error) {
    console.error('API Error:', error);
    showToast('Error: ' + (error.message || 'An unknown error occurred'), 'danger');
}

// Load accounts for bulk settings modal
async function loadAccountsForBulkSettings() {
    try {
        const response = await fetch('/api/accounts');
        if (!response.ok) throw new Error('Failed to load accounts');
        
        const accounts = await response.json();
        const bulkAccounts = document.getElementById('bulkAccounts');
        
        // Clear existing options
        bulkAccounts.innerHTML = '';
        
        // Add account options
        accounts.forEach(account => {
            const option = document.createElement('option');
            option.value = JSON.stringify({deviceid: account.deviceid, account: account.account});
            option.textContent = `${account.account} (${account.devicename})`;
            bulkAccounts.appendChild(option);
        });
    } catch (error) {
        handleApiError(error);
    }
}

// Save bulk account settings
async function saveBulkSettings() {
    try {
        // Get selected accounts
        const bulkAccountsSelect = document.getElementById('bulkAccounts');
        const selectedAccounts = Array.from(bulkAccountsSelect.selectedOptions).map(option => JSON.parse(option.value));
        
        if (selectedAccounts.length === 0) {
            showToast('Please select at least one account', 'danger');
            return;
        }
        
        // Get settings values
        const settings = {
            follow: document.getElementById('bulkFollow').checked ? 'True' : 'False',
            unfollow: document.getElementById('bulkUnfollow').checked ? 'True' : 'False',
            like: document.getElementById('bulkLike').checked ? 'True' : 'False',
            comment: document.getElementById('bulkComment').checked ? 'True' : 'False',
            story: document.getElementById('bulkStory').checked ? 'True' : 'False'
        };
        
        const followLimit = document.getElementById('bulkFollowLimit').value;
        if (followLimit) {
            settings.followlimit = followLimit;
        }
        
        // Send request
        const response = await fetch('/api/bulk_update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                accounts: selectedAccounts,
                settings: settings
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to update accounts');
        }
        
        const result = await response.json();
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('bulkSettingsModal'));
        modal.hide();
        
        // Show success message
        showToast(result.message || 'Settings updated successfully', 'success');
        
        // Reload page if we're on the accounts page
        if (window.location.pathname === '/accounts') {
            setTimeout(() => {
                window.location.reload();
            }, 1000);
        }
    } catch (error) {
        handleApiError(error);
    }
}

// Format runtime from starttime and endtime
function formatRuntime(starttime, endtime) {
    if (!starttime || !endtime) return 'Not set';
    
    // Handle case where both are 0
    if (starttime === '0' && endtime === '0') return 'Not active';
    
    // Format as a range
    return `${starttime} - ${endtime}`;
}

// Create status indicator
function createStatusIndicator(isActive) {
    return `<span class="status-indicator ${isActive ? 'status-active' : 'status-inactive'}"></span>`;
}

// Toggle value display for sensitive information
function toggleSensitiveInfo(element) {
    const hiddenValue = element.getAttribute('data-value');
    const currentText = element.textContent;
    
    if (currentText === '••••••••') {
        element.textContent = hiddenValue;
        element.nextElementSibling.innerHTML = '<i class="fas fa-eye-slash"></i>';
    } else {
        element.textContent = '••••••••';
        element.nextElementSibling.innerHTML = '<i class="fas fa-eye"></i>';
    }
}

// Add animation effects
document.addEventListener('DOMContentLoaded', function() {
    // Add fade-in animation to cards
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
        
        setTimeout(() => {
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 100 * index);
    });
    
    // Add pulse animation to refresh button
    const refreshBtn = document.getElementById('refreshData');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            this.classList.add('btn-pulse');
            setTimeout(() => {
                this.classList.remove('btn-pulse');
            }, 1000);
        });
    }
    
    // Initialize bulk settings modal
    const bulkSettingsModal = document.getElementById('bulkSettingsModal');
    if (bulkSettingsModal) {
        bulkSettingsModal.addEventListener('show.bs.modal', function() {
            loadAccountsForBulkSettings();
        });
        
        const saveBulkSettingsBtn = document.getElementById('saveBulkSettings');
        if (saveBulkSettingsBtn) {
            saveBulkSettingsBtn.addEventListener('click', saveBulkSettings);
        }
    }
});

// Add custom styles for animations
const animationStyle = document.createElement('style');
animationStyle.textContent = `
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
    
    .btn-pulse {
        animation: pulse 0.5s;
    }
    
    .table-hover tbody tr {
        transition: background-color 0.3s ease;
    }
    
    .btn {
        transition: all 0.3s ease;
    }
    
    .btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
`;
document.head.appendChild(animationStyle);
