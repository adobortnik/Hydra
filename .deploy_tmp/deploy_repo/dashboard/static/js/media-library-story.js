// Media Library - Batch Schedule Story functionality

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing batch schedule story functionality');
    
    // Set up event listener for the batch schedule story button
    const batchScheduleStoryBtn = document.getElementById('batchScheduleStoryBtn');
    if (batchScheduleStoryBtn) {
        batchScheduleStoryBtn.addEventListener('click', showBatchScheduleStoryModal);
    }
});

// Show batch schedule story modal
function showBatchScheduleStoryModal() {
    // Reset form
    document.getElementById('batchScheduleStoryForm').reset();
    
    // Populate folders dropdown
    populateStoryFoldersDropdown();
    
    // Populate device dropdown
    populateStoryDeviceDropdown();
    
    // Set default start time to tomorrow at 9 AM
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(9, 0, 0, 0);
    document.getElementById('startTimeStory').value = tomorrow.toISOString().slice(0, 16);
    
    // Add event listener for the 'All accounts' checkbox
    document.getElementById('useAllAccountsStory').addEventListener('change', function() {
        const accountSelect = document.getElementById('scheduleStoryAccount');
        accountSelect.disabled = this.checked;
        if (this.checked) {
            accountSelect.value = '';
        }
    });
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('batchScheduleStoryModal'));
    modal.show();
}

// Populate folders dropdown for story modal
function populateStoryFoldersDropdown() {
    try {
        fetch('/api/folders')
            .then(response => {
                if (!response.ok) throw new Error('Failed to load folders');
                return response.json();
            })
            .then(folders => {
                const folderSelect = document.getElementById('scheduleStoryFolder');
                
                // Clear existing options except the first one
                while (folderSelect.options.length > 1) {
                    folderSelect.remove(1);
                }
                
                // Add folder options
                folders.forEach(folder => {
                    const option = document.createElement('option');
                    option.value = folder.id;
                    option.textContent = folder.name;
                    folderSelect.appendChild(option);
                });
            })
            .catch(error => {
                console.error('Error loading folders:', error);
                showToast('Error loading folders', 'danger');
            });
    } catch (error) {
        console.error('Error in populateStoryFoldersDropdown:', error);
    }
}

// Populate device dropdown for story modal
function populateStoryDeviceDropdown() {
    try {
        fetch('/api/devices')
            .then(response => {
                if (!response.ok) throw new Error('Failed to load devices');
                return response.json();
            })
            .then(devices => {
                const deviceSelect = document.getElementById('scheduleStoryDevice');
                
                // Clear existing options except the first one
                while (deviceSelect.options.length > 1) {
                    deviceSelect.remove(1);
                }
                
                // Add device options
                devices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.deviceid;
                    option.textContent = device.devicename || device.deviceid;
                    deviceSelect.appendChild(option);
                });
                
                // Add change event listener
                deviceSelect.onchange = function() {
                    if (this.value) {
                        populateStoryAccountDropdown(this.value);
                    }
                };
            })
            .catch(error => {
                console.error('Error loading devices:', error);
                showToast('Error loading devices', 'danger');
            });
    } catch (error) {
        console.error('Error in populateStoryDeviceDropdown:', error);
    }
}

// Populate account dropdown for story modal
function populateStoryAccountDropdown(deviceId) {
    try {
        fetch(`/api/accounts?deviceid=${deviceId}`)
            .then(response => {
                if (!response.ok) throw new Error('Failed to load accounts');
                return response.json();
            })
            .then(accounts => {
                const accountSelect = document.getElementById('scheduleStoryAccount');
                
                // Clear existing options except the first one
                while (accountSelect.options.length > 1) {
                    accountSelect.remove(1);
                }
                
                // Add account options
                accounts.forEach(account => {
                    const option = document.createElement('option');
                    option.value = account.account;
                    option.textContent = account.account;
                    accountSelect.appendChild(option);
                });
            })
            .catch(error => {
                console.error('Error loading accounts:', error);
                showToast('Error loading accounts', 'danger');
            });
    } catch (error) {
        console.error('Error in populateStoryAccountDropdown:', error);
    }
}

// Handle save button click for batch schedule story
document.addEventListener('DOMContentLoaded', function() {
    const saveBatchScheduleStory = document.getElementById('saveBatchScheduleStory');
    if (saveBatchScheduleStory) {
        saveBatchScheduleStory.addEventListener('click', batchScheduleStories);
    }
});

// Batch schedule stories
async function batchScheduleStories() {
    try {
        const folderId = document.getElementById('scheduleStoryFolder').value;
        const deviceId = document.getElementById('scheduleStoryDevice').value;
        const useAllAccounts = document.getElementById('useAllAccountsStory').checked;
        const account = useAllAccounts ? 'all_accounts' : document.getElementById('scheduleStoryAccount').value;
        const mentionUsername = document.getElementById('storyMentionUsername').value;
        const startTime = document.getElementById('startTimeStory').value;
        const intervalHours = document.getElementById('intervalHoursStory').value;
        const repurpose = document.getElementById('repurposeMediaStory').checked;
        
        if (!folderId || !deviceId || (!useAllAccounts && !account) || !startTime) {
            showToast('Please fill in all required fields', 'warning');
            return;
        }
        
        // Show loading state
        const saveButton = document.getElementById('saveBatchScheduleStory');
        const originalText = saveButton.innerHTML;
        saveButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Scheduling...';
        saveButton.disabled = true;
        
        // Prepare data
        const scheduleData = {
            folder_id: folderId,
            device_id: deviceId,
            account: account,
            use_all_accounts: useAllAccounts,
            mention_username: mentionUsername,
            start_time: startTime,
            interval_hours: parseInt(intervalHours),
            repurpose: repurpose,
            post_type: 'story'  // This is the key difference from regular batch scheduling
        };
        
        // Send API request
        const response = await fetch('/api/batch/schedule', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(scheduleData)
        });
        
        // Reset button state
        saveButton.innerHTML = originalText;
        saveButton.disabled = false;
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to schedule stories');
        }
        
        const result = await response.json();
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('batchScheduleStoryModal'));
        modal.hide();
        
        // Show success message
        showToast(`Successfully scheduled ${result.count || 'multiple'} stories`, 'success');
        
    } catch (error) {
        console.error('Error scheduling stories:', error);
        showToast(`Error: ${error.message || 'Failed to schedule stories'}`, 'danger');
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) return;
    
    const toastId = 'toast-' + Date.now();
    const bgClass = type === 'danger' ? 'bg-danger' : 
                   type === 'success' ? 'bg-success' : 
                   type === 'warning' ? 'bg-warning' : 'bg-info';
    
    const iconClass = type === 'danger' ? 'fa-exclamation-circle' : 
                     type === 'success' ? 'fa-check-circle' : 
                     type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle';
    
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.id = toastId;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="toast-header ${bgClass} text-white">
            <i class="fas ${iconClass} me-2"></i>
            <strong class="me-auto">${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
        <div class="toast-body bg-dark text-white">
            ${message}
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    const bsToast = new bootstrap.Toast(toast, {
        autohide: true,
        delay: 5000
    });
    
    bsToast.show();
    
    // Remove toast after it's hidden
    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });
}
