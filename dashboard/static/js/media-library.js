// Media Library functionality for The Live House

// Global variables
let allMedia = [];
let allTags = [];
let allFolders = [];
let currentFolderId = null;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Load initial data
    loadMediaLibraryData();
    
    // Set up event listeners
    document.getElementById('refreshMedia').addEventListener('click', loadMediaLibraryData);
    document.getElementById('mediaSearch').addEventListener('input', filterMedia);
    document.getElementById('typeFilter').addEventListener('change', filterMedia);
    document.getElementById('tagFilter').addEventListener('change', filterMedia);
    document.getElementById('uploadMediaBtn').addEventListener('click', showUploadModal);
    document.getElementById('saveUploadMedia').addEventListener('click', uploadMedia);
    document.getElementById('saveMediaDetails').addEventListener('click', saveMediaDetails);
    document.getElementById('processMedia').addEventListener('click', processMedia);
    document.getElementById('deleteMedia').addEventListener('click', deleteMedia);
    document.getElementById('batchProcessBtn').addEventListener('click', showBatchProcessModal);
    document.getElementById('selectAllImages').addEventListener('change', toggleSelectAllImages);
    document.getElementById('viewOriginal').addEventListener('click', viewOriginal);
    document.getElementById('viewProcessed').addEventListener('click', viewProcessed);
    
    // Folder management event listeners
    document.getElementById('createFolderBtn').addEventListener('click', showCreateFolderModal);
    document.getElementById('saveFolder').addEventListener('click', createFolder);
    document.getElementById('updateFolder').addEventListener('click', updateFolder);
    document.getElementById('deleteFolder').addEventListener('click', confirmDeleteFolder);
    document.getElementById('batchScheduleBtn').addEventListener('click', showBatchScheduleModal);
    document.getElementById('saveBatchSchedule').addEventListener('click', batchSchedulePosts);
    
    // Set up drag and drop functionality
    setupDragAndDrop();
    
    // Initialize context menu for folders
    initFolderContextMenu();
});

// Load all media library data
async function loadMediaLibraryData() {
    try {
        // Show loading state
        document.getElementById('mediaGrid').innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div><p class="mt-2 text-white">Loading media...</p></div>';
        
        // Load folders first
        await loadFolders();
        
        // Load tags
        await loadTags();
        
        // Then load media
        await loadMedia();
        
        // Initial filtering
        filterMedia();
    } catch (error) {
        handleApiError(error);
        document.getElementById('mediaGrid').innerHTML = '<div class="text-center py-5 text-danger"><i class="fas fa-exclamation-circle fa-3x mb-3"></i><p>Error loading media. Please try again.</p></div>';
    }
}

// Load folders from API
async function loadFolders() {
    try {
        const response = await fetch('/api/folders');
        if (!response.ok) throw new Error('Failed to load folders');
        
        allFolders = await response.json();
        renderFolderTree();
        
        // Also populate folder dropdowns
        populateFolderDropdowns();
    } catch (error) {
        console.error('Error loading folders:', error);
        showToast('Error loading folders', 'danger');
    }
}

// Render folder tree
function renderFolderTree() {
    const folderTree = document.getElementById('folderTree');
    if (!folderTree) return;
    
    // Show loading state
    folderTree.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm text-primary" role="status"></div><p class="small mt-2 mb-0">Loading folders...</p></div>';
    
    // Get folders
    fetch('/api/folders')
        .then(response => response.json())
        .then(folders => {
            // Build folder tree HTML
            let html = '';
            
            // Add root folder item
            const isRootActive = !currentFolderId;
            html += `
            <div class="folder-item root-folder ${isRootActive ? 'active' : ''}" data-folder-id="">
                <div class="d-flex align-items-center">
                    <i class="fas fa-home me-2"></i>
                    <span class="folder-name">All Media</span>
                    <span class="ms-auto badge bg-secondary rounded-pill"></span>
                </div>
            </div>`;
            
            // Build tree for root-level folders
            const rootFolders = folders.filter(folder => !folder.parent_id);
            rootFolders.forEach(folder => {
                const childFolders = folders.filter(f => f.parent_id === folder.id);
                html += generateFolderItem(folder, childFolders, folders);
            });
            
            // Update folder tree
            folderTree.innerHTML = html;
            
            // Add click event listeners
            document.querySelectorAll('.folder-item').forEach(item => {
                item.addEventListener('click', function(e) {
                    // Prevent clicks on child elements from triggering folder selection
                    if (e.target.closest('.folder-toggle')) return;
                    
                    const folderId = this.getAttribute('data-folder-id');
                    console.log(`DEBUG: Folder item clicked with ID: ${folderId || 'root'}`);
                    
                    // If this is the root folder (All Media), ensure we load all media
                    if (this.classList.contains('root-folder') || folderId === '') {
                        console.log('DEBUG: Root folder clicked, loading all media');
                        // Reset current folder ID
                        currentFolderId = null;
                        
                        // Update active state in UI
                        document.querySelectorAll('.folder-item').forEach(item => {
                            item.classList.remove('active');
                        });
                        this.classList.add('active');
                        
                        // Load all media and render it - this is the exact sequence used on page load
                        loadMedia().then(() => {
                            filterMedia(); // This will render the media grid with all media
                            console.log('DEBUG: All media loaded and rendered');
                        }).catch(error => {
                            console.error('Error loading all media:', error);
                        });
                    } else {
                        selectFolder(folderId);
                    }
                });
            });
            
            // Add toggle event listeners
            document.querySelectorAll('.folder-toggle').forEach(toggle => {
                toggle.addEventListener('click', function() {
                    const folderId = this.closest('.folder-item').getAttribute('data-folder-id');
                    const subfolders = document.querySelector(`.subfolders[data-parent="${folderId}"]`);
                    
                    if (subfolders) {
                        subfolders.classList.toggle('d-none');
                        this.querySelector('i').classList.toggle('fa-caret-right');
                        this.querySelector('i').classList.toggle('fa-caret-down');
                    }
                });
            });
        })
        .catch(error => {
            console.error('Error loading folders:', error);
            folderTree.innerHTML = '<div class="text-center py-3 text-danger"><i class="fas fa-exclamation-circle"></i><p class="small mt-2 mb-0">Error loading folders</p></div>';
        });
}

// Generate HTML for a folder item and its subfolders
function generateFolderItem(folder, childFolders, allFolders) {
    const hasChildren = childFolders.length > 0;
    const isActive = currentFolderId === folder.id;
    
    let html = `
    <div class="folder-item ${isActive ? 'active' : ''}" data-folder-id="${folder.id}">
        <div class="d-flex align-items-center">
            <i class="fas ${hasChildren ? 'fa-folder-open' : 'fa-folder'} me-2"></i>
            <span class="folder-name">${folder.name}</span>
            <span class="ms-auto badge bg-secondary rounded-pill">${folder.media_count}</span>
        </div>
    `;
    
    // Add toggle button if folder has children
    if (hasChildren) {
        html += `
        <button class="folder-toggle btn btn-link p-0 text-decoration-none text-reset" type="button">
            <i class="fas fa-caret-right"></i>
        </button>
        `;
    }
    
    html += '</div>';
    
    // Add subfolders if any
    if (hasChildren) {
        html += `
        <div class="subfolders d-none" data-parent="${folder.id}">
            ${childFolders.map(childFolder => generateFolderItem(childFolder, allFolders.filter(f => f.parent_id === childFolder.id), allFolders)).join('')}
        </div>
        `;
    }
    
    return html;
}

// Select a folder and load its media
function selectFolder(folderId) {
    console.log(`DEBUG: Selecting folder ID: ${folderId ? folderId : 'All Media (Root)'}`);
    
    // Update active state in UI
    document.querySelectorAll('.folder-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // If folderId is null or empty, we're selecting the root "All Media" option
    const selectedItem = folderId 
        ? document.querySelector(`.folder-item[data-folder-id="${folderId}"]`)
        : document.querySelector(`.folder-item[data-folder-id=""]:not([data-parent-id]), .folder-item.root-folder`);
        
    if (selectedItem) {
        selectedItem.classList.add('active');
        console.log('DEBUG: Found and activated folder item in UI');
    } else {
        console.warn(`DEBUG: Could not find folder item in UI for folder ID: ${folderId || 'Root'}`);
    }
    
    // Update current folder ID
    currentFolderId = folderId;
    
    // Load media for this folder or all media if no folder is selected
    if (folderId) {
        console.log(`DEBUG: Loading media for folder ID: ${folderId}`);
        loadFolderMedia(folderId);
    } else {
        console.log('DEBUG: Loading all media (no folder selected)');
        loadMedia();
    }
}

// Load media for a specific folder
async function loadFolderMedia(folderId) {
    try {
        console.log(`DEBUG: Loading media for folder ID: ${folderId}`);
        // Show loading state
        document.getElementById('mediaGrid').innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div><p class="mt-2 text-white">Loading media...</p></div>';
        
        // Get media for this folder
        console.log(`DEBUG: Fetching from URL: /api/folders/${folderId}/media`);
        const response = await fetch(`/api/folders/${folderId}/media`);
        if (!response.ok) {
            console.error(`DEBUG: Response not OK. Status: ${response.status}`);
            throw new Error('Failed to load folder media');
        }
        
        const folderMedia = await response.json();
        console.log(`DEBUG: Received ${folderMedia.length} media items from API`);
        console.log('DEBUG: Media items:', folderMedia);
        
        // Update allMedia with folder media
        allMedia = folderMedia;
        
        // Render media grid
        renderMediaGrid(folderMedia);
    } catch (error) {
        console.error('Error loading folder media:', error);
        document.getElementById('mediaGrid').innerHTML = '<div class="text-center py-5 text-danger"><i class="fas fa-exclamation-circle fa-3x mb-3"></i><p>Error loading folder media. Please try again.</p></div>';
    }
}

// Populate folder dropdowns in modals
function populateFolderDropdowns() {
    // Get all folder select elements
    const folderSelects = [
        document.getElementById('parentFolder'),
        document.getElementById('editParentFolder'),
        document.getElementById('scheduleFolder')
    ];
    
    folderSelects.forEach(select => {
        if (!select) return;
        
        // Clear existing options except the first one
        while (select.options.length > 1) {
            select.remove(1);
        }
        
        // Add folder options
        allFolders.forEach(folder => {
            const option = document.createElement('option');
            option.value = folder.id;
            option.textContent = folder.name;
            select.appendChild(option);
        });
    });
}

// Show create folder modal
function showCreateFolderModal() {
    // Reset form
    document.getElementById('createFolderForm').reset();
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('createFolderModal'));
    modal.show();
}

// Create a new folder
async function createFolder() {
    try {
        const folderName = document.getElementById('folderName').value.trim();
        const folderDescription = document.getElementById('folderDescription').value.trim();
        const parentId = document.getElementById('parentFolder').value || null;
        
        if (!folderName) {
            showToast('Folder name is required', 'warning');
            return;
        }
        
        // Create folder data
        const folderData = {
            name: folderName,
            description: folderDescription,
            parent_id: parentId
        };
        
        // Send API request
        const response = await fetch('/api/folders', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(folderData)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to create folder');
        }
        
        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('createFolderModal')).hide();
        
        // Reload folders
        await loadFolders();
        
        // Show success message
        showToast('Folder created successfully', 'success');
    } catch (error) {
        console.error('Error creating folder:', error);
        showToast(error.message || 'Error creating folder', 'danger');
    }
}

// Show edit folder modal
function showEditFolderModal(folderId) {
    // Find folder
    const folder = allFolders.find(f => f.id === folderId);
    if (!folder) {
        showToast('Folder not found', 'danger');
        return;
    }
    
    // Populate form
    document.getElementById('editFolderId').value = folder.id;
    document.getElementById('editFolderName').value = folder.name;
    document.getElementById('editFolderDescription').value = folder.description || '';
    
    // Set parent folder
    const parentSelect = document.getElementById('editParentFolder');
    parentSelect.value = folder.parent_id || '';
    
    // Disable parent options that would create circular references
    Array.from(parentSelect.options).forEach(option => {
        // Disable self
        if (option.value === folder.id) {
            option.disabled = true;
        } else {
            option.disabled = false;
        }
        
        // TODO: Disable descendants (would require recursive function)
    });
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('editFolderModal'));
    modal.show();
}

// Update folder
async function updateFolder() {
    try {
        const folderId = document.getElementById('editFolderId').value;
        const folderName = document.getElementById('editFolderName').value.trim();
        const folderDescription = document.getElementById('editFolderDescription').value.trim();
        const parentId = document.getElementById('editParentFolder').value || null;
        
        if (!folderName) {
            showToast('Folder name is required', 'warning');
            return;
        }
        
        // Update folder data
        const folderData = {
            name: folderName,
            description: folderDescription,
            parent_id: parentId
        };
        
        // Send API request
        const response = await fetch(`/api/folders/${folderId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(folderData)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to update folder');
        }
        
        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('editFolderModal')).hide();
        
        // Reload folders
        await loadFolders();
        
        // Show success message
        showToast('Folder updated successfully', 'success');
    } catch (error) {
        console.error('Error updating folder:', error);
        showToast(error.message || 'Error updating folder', 'danger');
    }
}

// Confirm delete folder
function confirmDeleteFolder() {
    const folderId = document.getElementById('editFolderId').value;
    const folderName = document.getElementById('editFolderName').value;
    
    if (confirm(`Are you sure you want to delete the folder "${folderName}"? This will remove all media associations but not delete the media files.`)) {
        deleteFolder(folderId);
    }
}

// Delete folder
async function deleteFolder(folderId) {
    try {
        // Send API request
        const response = await fetch(`/api/folders/${folderId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to delete folder');
        }
        
        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('editFolderModal')).hide();
        
        // Reset current folder if it was deleted
        if (currentFolderId === folderId) {
            currentFolderId = null;
            await loadMedia(); // Load all media
        }
        
        // Reload folders
        await loadFolders();
        
        // Show success message
        showToast('Folder deleted successfully', 'success');
    } catch (error) {
        console.error('Error deleting folder:', error);
        showToast(error.message || 'Error deleting folder', 'danger');
    }
}

// Add media to folder
async function addMediaToFolder(mediaId, folderId) {
    try {
        // Send API request
        const response = await fetch(`/api/media/${mediaId}/folders`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ folder_id: folderId })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to add media to folder');
        }
        
        // Reload folders to update counts
        await loadFolders();
        
        // Show success message
        showToast('Media added to folder successfully', 'success');
        
        return true;
    } catch (error) {
        console.error('Error adding media to folder:', error);
        showToast(error.message || 'Error adding media to folder', 'danger');
        return false;
    }
}

// Remove media from folder
async function removeMediaFromFolder(mediaId, folderId) {
    try {
        // Send API request
        const response = await fetch(`/api/media/${mediaId}/folders/${folderId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to remove media from folder');
        }
        
        // Reload folders to update counts
        await loadFolders();
        
        // If we're viewing a folder, refresh its contents
        if (currentFolderId === folderId) {
            await loadFolderMedia(folderId);
        }
        
        // Show success message
        showToast('Media removed from folder successfully', 'success');
        
        return true;
    } catch (error) {
        console.error('Error removing media from folder:', error);
        showToast(error.message || 'Error removing media from folder', 'danger');
        return false;
    }
}

// Show batch schedule modal
function showBatchScheduleModal() {
    // Reset form
    document.getElementById('batchScheduleForm').reset();
    
    // Populate device dropdown
    populateDeviceDropdown();
    
    // Set default start time to tomorrow at 9 AM
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(9, 0, 0, 0);
    document.getElementById('startTime').value = tomorrow.toISOString().slice(0, 16);
    
    // Add event listener for the startTime input
    document.getElementById('startTime').addEventListener('input', function() {
        console.log('Start time changed:', this.value);
    });
    
    // Add event listener for the 'All accounts' checkbox
    document.getElementById('useAllAccounts').addEventListener('change', function() {
        const accountSelect = document.getElementById('scheduleAccount');
        accountSelect.disabled = this.checked;
        if (this.checked) {
            accountSelect.value = '';
        }
    });
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('batchScheduleModal'));
    modal.show();
}

// Populate device dropdown
async function populateDeviceDropdown() {
    try {
        const response = await fetch('/api/devices');
        if (!response.ok) throw new Error('Failed to load devices');
        
        const devices = await response.json();
        const deviceSelect = document.getElementById('scheduleDevice');
        
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
        deviceSelect.addEventListener('change', async function() {
            if (this.value) {
                await populateAccountDropdown(this.value);
            }
        });
    } catch (error) {
        console.error('Error loading devices:', error);
        showToast('Error loading devices', 'danger');
    }
}

// Populate account dropdown for selected device
async function populateAccountDropdown(deviceId) {
    try {
        const response = await fetch(`/api/accounts?deviceid=${deviceId}`);
        if (!response.ok) throw new Error('Failed to load accounts');
        
        const accounts = await response.json();
        const accountSelect = document.getElementById('scheduleAccount');
        
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
    } catch (error) {
        console.error('Error loading accounts:', error);
        showToast('Error loading accounts', 'danger');
    }
}

// Batch schedule posts
async function batchSchedulePosts() {
    try {
        const folderId = document.getElementById('scheduleFolder').value;
        const deviceId = document.getElementById('scheduleDevice').value;
        const useAllAccounts = document.getElementById('useAllAccounts').checked;
        const account = useAllAccounts ? 'all_accounts' : document.getElementById('scheduleAccount').value;
        const captionTemplateId = document.getElementById('captionTemplateId').value;
        const captionTemplate = document.getElementById('captionTemplate').value;
        const hashtags = document.getElementById('scheduleHashtags').value;
        const startTime = document.getElementById('startTime').value;
        const intervalHours = document.getElementById('intervalHours').value;
        const repurpose = document.getElementById('repurposeMedia').checked;
        
        if (!folderId || !deviceId || (!useAllAccounts && !account) || !startTime) {
            showToast('Please fill in all required fields', 'warning');
            return;
        }
        
        // Show loading state
        const saveButton = document.getElementById('saveBatchSchedule');
        const originalText = saveButton.innerHTML;
        saveButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Scheduling...';
        saveButton.disabled = true;
        
        // Prepare data
        const scheduleData = {
            folder_id: folderId,
            device_id: deviceId,
            account: account,
            use_all_accounts: useAllAccounts,
            caption_template_id: captionTemplateId,
            caption_template: captionTemplate,
            hashtags: hashtags,
            start_time: startTime,
            interval_hours: parseInt(intervalHours),
            repurpose: repurpose
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
            throw new Error(error.error || 'Failed to schedule posts');
        }
        
        const result = await response.json();
        
        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('batchScheduleModal')).hide();
        
        // Show success message
        showToast(result.message || 'Posts scheduled successfully', 'success');
    } catch (error) {
        console.error('Error scheduling posts:', error);
        showToast(error.message || 'Error scheduling posts', 'danger');
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    
    const toast = document.createElement('div');
    toast.className = `toast bg-${type} text-white`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="toast-header bg-${type} text-white">
            <strong class="me-auto">Media Library</strong>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
        <div class="toast-body">
            ${message}
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    const bsToast = new bootstrap.Toast(toast, { autohide: true, delay: 5000 });
    bsToast.show();
    
    // Remove toast from DOM after it's hidden
    toast.addEventListener('hidden.bs.toast', function() {
        this.remove();
    });
}

// Handle API errors
function handleApiError(error) {
    console.error('API Error:', error);
    showToast(error.message || 'An error occurred', 'danger');
}

// Load tags from API
async function loadTags() {
    try {
        const response = await fetch('/api/tags');
        if (!response.ok) throw new Error('Failed to load tags');
        
        allTags = await response.json();
        
        // Populate tag filter dropdown
        const tagFilter = document.getElementById('tagFilter');
        
        // Clear existing options except the first one
        while (tagFilter.options.length > 1) {
            tagFilter.remove(1);
        }
        
        // Add tag options
        allTags.forEach(tag => {
            const option = document.createElement('option');
            option.value = tag;
            option.textContent = tag;
            tagFilter.appendChild(option);
        });
    } catch (error) {
        handleApiError(error);
        throw error; // Re-throw to handle in the calling function
    }
}

// Load media from API
async function loadMedia() {
    try {
        console.log('DEBUG: Loading all media from API');
        const response = await fetch('/api/media');
        if (!response.ok) throw new Error('Failed to load media');
        
        allMedia = await response.json();
        console.log(`DEBUG: Loaded ${allMedia.length} media items:`, allMedia);
        return allMedia;
    } catch (error) {
        handleApiError(error);
        throw error; // Re-throw to handle in the calling function
    }
}

// Filter media based on search and filters
function filterMedia() {
    console.log('DEBUG: Filtering media, current allMedia length:', allMedia.length);
    const searchTerm = document.getElementById('mediaSearch').value.toLowerCase();
    const typeFilter = document.getElementById('typeFilter').value;
    const tagFilter = document.getElementById('tagFilter').value;
    
    // Filter media based on criteria
    const filteredMedia = allMedia.filter(media => {
        const matchesSearch = media.filename.toLowerCase().includes(searchTerm) || 
                            (media.description && media.description.toLowerCase().includes(searchTerm));
        const matchesType = typeFilter === '' || media.media_type === typeFilter;
        const matchesTag = tagFilter === '' || (media.tags_list && media.tags_list.includes(tagFilter));
        return matchesSearch && matchesType && matchesTag;
    });
    
    console.log(`DEBUG: Filtered to ${filteredMedia.length} media items`);
    
    // Render the filtered media
    renderMediaGrid(filteredMedia);
}

// Render media grid
function renderMediaGrid(mediaItems) {
    const mediaGrid = document.getElementById('mediaGrid');
    
    // Clear existing items
    mediaGrid.innerHTML = '';
    
    // If no media, show message
    if (mediaItems.length === 0) {
        mediaGrid.innerHTML = '<div class="text-center py-5 text-white-50"><i class="fas fa-photo-video fa-3x mb-3"></i><p>No media found matching your criteria</p></div>';
        return;
    }
    
    // Add each media item to the grid
    mediaItems.forEach(media => {
        const mediaItem = document.createElement('div');
        mediaItem.className = 'media-item';
        mediaItem.dataset.id = media.id;
        mediaItem.addEventListener('click', () => showMediaDetails(media.id));
        
        // Determine thumbnail source
        let thumbnailSrc;
        if (media.processed_path) {
            // Get just the filename without any path
            let filename;
            if (media.processed_path.includes('\\')) {
                // Windows path
                filename = media.processed_path.split('\\').pop();
            } else {
                // Unix path
                filename = media.processed_path.split('/').pop();
            }
            // Use direct file endpoint to avoid path issues
            thumbnailSrc = `/api/media/processed/${filename}`;
        } else {
            // Get just the filename without any path
            let filename;
            if (media.original_path.includes('\\')) {
                // Windows path
                filename = media.original_path.split('\\').pop();
            } else {
                // Unix path
                filename = media.original_path.split('/').pop();
            }
            thumbnailSrc = `/api/media/original/${filename}`;
        }
        
        // Create processed badge if applicable
        const processedBadge = media.processed_path ? 
            '<div class="processed-badge"><i class="fas fa-check-circle me-1"></i>Processed</div>' : '';
        
        // Create tag elements
        let tagsHtml = '';
        if (media.tags_list && media.tags_list.length > 0) {
            tagsHtml = '<div class="media-tags">';
            media.tags_list.slice(0, 3).forEach(tag => {
                tagsHtml += `<span class="media-tag">${tag}</span>`;
            });
            if (media.tags_list.length > 3) {
                tagsHtml += `<span class="media-tag">+${media.tags_list.length - 3}</span>`;
            }
            tagsHtml += '</div>';
        }
        
        // Set HTML content based on media type
        if (media.media_type === 'video') {
            // For video files, handle differently based on file extension
            let videoFilename;
            if (media.original_path.includes('\\')) {
                // Windows path
                videoFilename = media.original_path.split('\\').pop();
            } else {
                // Unix path
                videoFilename = media.original_path.split('/').pop();
            }
            
            const fileExtension = videoFilename.split('.').pop().toLowerCase();
            
            if (fileExtension === 'mp4' || fileExtension === 'mov') {
                // Try to play both MP4 and MOV videos directly
                let mimeType = fileExtension === 'mov' ? 'video/quicktime' : 'video/mp4';
                console.log(`DEBUG: Setting video preview with path: ${thumbnailSrc} and type: ${mimeType}`);
                mediaItem.innerHTML = `
                    ${processedBadge}
                    <div class="position-relative">
                        <video controls class="media-thumbnail" preload="metadata" style="max-height: 500px;">
                            <source src="${thumbnailSrc}" type="${mimeType}">
                            Your browser does not support the video tag.
                        </video>
                        <div class="mt-2 text-center">
                            <a href="${thumbnailSrc}" target="_blank" class="btn btn-primary">Download Video</a>
                        </div>
                    </div>
                    <div class="media-info">
                        <div class="media-title">${media.filename}</div>
                        ${tagsHtml}
                    </div>
                `;
            } else {
                // For other video formats, use placeholder with download button
                console.log(`DEBUG: Setting non-MP4/MOV video preview with path: ${thumbnailSrc}`);
                mediaItem.innerHTML = `
                    ${processedBadge}
                    <div class="video-container position-relative">
                        <div class="text-center mb-2">
                            <img src="/static/img/placeholder.jpg" class="img-fluid rounded" alt="Video: ${media.filename}" style="max-height: 300px; width: auto;">
                            <div class="position-absolute top-50 start-50 translate-middle">
                                <i class="fas fa-film fa-3x text-white"></i>
                            </div>
                        </div>
                        <div class="mt-2 text-center">
                            <a href="${thumbnailSrc}" target="_blank" class="btn btn-primary">Download Video</a>
                        </div>
                    </div>
                    <div class="media-info">
                        <div class="media-title">${media.filename}</div>
                        ${tagsHtml}
                    </div>
                `;
            }
        } else {
            // For image files, show the actual image
            mediaItem.innerHTML = `
                ${processedBadge}
                <img src="${thumbnailSrc}" alt="${media.filename}" class="media-thumbnail" onerror="this.src='/static/img/placeholder.jpg'">
                <div class="media-info">
                    <div class="media-title">${media.filename}</div>
                    ${tagsHtml}
                </div>
            `;
        }
        
        mediaGrid.appendChild(mediaItem);
    });
}

// Show media details modal
async function showMediaDetails(mediaId) {
    try {
        console.log(`DEBUG: Showing details for media ID: ${mediaId}`);
        const response = await fetch(`/api/media/${mediaId}`);
        if (!response.ok) throw new Error('Failed to load media details');
        
        const media = await response.json();
        console.log('DEBUG: Media details:', media);
        
        // Populate modal fields with null checks
        const setElementValue = (id, value) => {
            const element = document.getElementById(id);
            if (element) {
                element.value = value;
            } else {
                console.warn(`Element with ID '${id}' not found`);
            }
        };
        
        setElementValue('mediaId', media.id);
        setElementValue('mediaFilename', media.filename);
        setElementValue('mediaType', media.media_type);
        setElementValue('mediaDescription', media.description || '');
        setElementValue('mediaTags', media.tags_list ? media.tags_list.join(', ') : '');
        setElementValue('mediaUploadDate', formatDate(media.upload_date));
        setElementValue('mediaUsageCount', media.times_used || 0);
        setElementValue('mediaLastUsed', media.last_used ? formatDate(media.last_used) : 'Never');
        
        // Load media folders
        await loadMediaFolders(mediaId);
        
        // Set preview based on media type
        const previewContainer = document.getElementById('mediaPreview');
        if (previewContainer) {
            if (media.media_type === 'video') {
                // Extract filename from path
                let videoFilename;
                if (media.original_path.includes('\\')) {
                    // Windows path
                    videoFilename = media.original_path.split('\\').pop();
                } else {
                    // Unix path
                    videoFilename = media.original_path.split('/').pop();
                }
                
                const fileExtension = videoFilename.split('.').pop().toLowerCase();
                
                if (fileExtension === 'mp4' || fileExtension === 'mov') {
                    // Try to play both MP4 and MOV videos directly
                    let mimeType = fileExtension === 'mov' ? 'video/quicktime' : 'video/mp4';
                    console.log(`DEBUG: Setting video preview with path: ${thumbnailSrc} and type: ${mimeType}`);
                    previewContainer.innerHTML = `
                        <video controls class="img-fluid rounded" preload="metadata">
                            <source src="${thumbnailSrc}" type="${mimeType}">
                            Your browser does not support the video tag.
                        </video>
                        <div class="mt-2 text-center">
                            <a href="${thumbnailSrc}" target="_blank" class="btn btn-primary">Download Video</a>
                        </div>
                    `;
                } else {
                    // For other video formats, use placeholder with download button
                    console.log(`DEBUG: Setting non-MP4/MOV video preview with path: ${thumbnailSrc}`);
                    previewContainer.innerHTML = `
                        <div class="video-container position-relative">
                            <div class="text-center mb-2">
                                <img src="/static/img/placeholder.jpg" class="img-fluid rounded" alt="Video: ${media.filename}" style="max-height: 300px; width: auto;">
                                <div class="position-absolute top-50 start-50 translate-middle">
                                    <i class="fas fa-film fa-3x text-white"></i>
                                </div>
                            </div>
                            <div class="mt-2 text-center">
                                <a href="${thumbnailSrc}" target="_blank" class="btn btn-primary">Download Video</a>
                            </div>
                        </div>
                    `;
                }
            } else if (media.media_type === 'image') {
                // Get just the filename without any path
                let filename;
                if (media.processed_path) {
                    // Get just the filename without any path
                    let filename;
                    if (media.processed_path.includes('\\')) {
                        // Windows path
                        filename = media.processed_path.split('\\').pop();
                    } else {
                        // Unix path
                        filename = media.processed_path.split('/').pop();
                    }
                    // Use direct file endpoint to avoid path issues
                    thumbnailSrc = `/api/media/processed/${filename}`;
                } else {
                    // Get just the filename without any path
                    let filename;
                    if (media.original_path.includes('\\')) {
                        // Windows path
                        filename = media.original_path.split('\\').pop();
                    } else {
                        // Unix path
                        filename = media.original_path.split('/').pop();
                    }
                    thumbnailSrc = `/api/media/original/${filename}`;
                }
                console.log(`DEBUG: Setting image preview with path: ${thumbnailSrc}`);
                previewContainer.innerHTML = `<img src="${thumbnailSrc}" class="img-fluid rounded" alt="${media.filename}">`;
            }
        }
        
        // Show modal
        const modalElement = document.getElementById('mediaDetailsModal');

        // Add event listener for when the modal is hidden
        modalElement.addEventListener('hidden.bs.modal', function() {
            console.log('DEBUG: Media details modal closed, reloading media');
            // Reload the current view (either folder or all media)
            if (currentFolderId) {
                loadFolderMedia(currentFolderId);
            } else {
                loadMedia();
            }
        }, { once: true }); // Use once: true to ensure the event listener is removed after it's triggered

        const modal = new bootstrap.Modal(modalElement);
        modal.show();
    } catch (error) {
        console.error('Error showing media details:', error);
        showToast('Error', 'Failed to load media details: ' + error.message, 'error');
    }
}

// Load media folders
async function loadMediaFolders(mediaId) {
    try {
        // Get all folders
        const foldersResponse = await fetch('/api/folders');
        if (!foldersResponse.ok) throw new Error('Failed to load folders');
        
        const allFolders = await foldersResponse.json();
        
        // Get media folders
        const mediaFoldersResponse = await fetch(`/api/media/${mediaId}/folders`);
        if (!mediaFoldersResponse.ok) throw new Error('Failed to load media folders');
        
        const mediaFolders = await mediaFoldersResponse.json();
        
        // Populate folders select
        const foldersSelect = document.getElementById('mediaFolders');
        foldersSelect.innerHTML = '';
        
        if (mediaFolders.length === 0) {
            const option = document.createElement('option');
            option.disabled = true;
            option.textContent = 'Not in any folders';
            foldersSelect.appendChild(option);
        } else {
            mediaFolders.forEach(folder => {
                const option = document.createElement('option');
                option.value = folder.id;
                option.textContent = folder.name;
                foldersSelect.appendChild(option);
            });
        }
        
        // Update remove button state
        document.getElementById('removeFromFolderBtn').disabled = mediaFolders.length === 0;
        
        return mediaFolders;
    } catch (error) {
        console.error('Error loading media folders:', error);
        showToast('Error loading folders', 'danger');
        return [];
    }
}

// Show add to folder modal
function showAddToFolderModal(mediaId) {
    // Create a modal on the fly
    const modalId = 'addToFolderModal';
    let modal = document.getElementById(modalId);
    
    // Remove existing modal if it exists
    if (modal) {
        modal.remove();
    }
    
    // Create new modal
    modal = document.createElement('div');
    modal.id = modalId;
    modal.className = 'modal fade';
    modal.setAttribute('tabindex', '-1');
    modal.setAttribute('aria-labelledby', `${modalId}Title`);
    modal.setAttribute('aria-hidden', 'true');
    
    modal.innerHTML = `
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content bg-dark text-white">
                <div class="modal-header border-secondary">
                    <h5 class="modal-title" id="${modalId}Title">Add to Folder</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label for="selectFolder" class="form-label">Select Folder</label>
                        <select id="selectFolder" class="form-select bg-dark text-white border-secondary">
                            <option value="" selected disabled>Select a folder</option>
                            <!-- Folders will be populated by JavaScript -->
                        </select>
                    </div>
                </div>
                <div class="modal-footer border-secondary">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                        <i class="fas fa-times me-2"></i>Cancel
                    </button>
                    <button type="button" class="btn btn-primary" id="confirmAddToFolder">
                        <i class="fas fa-folder-plus me-2"></i>Add to Folder
                    </button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Initialize the modal
    const bsModal = new bootstrap.Modal(modal);
    
    // Populate folders dropdown
    const selectFolder = document.getElementById('selectFolder');
    allFolders.forEach(folder => {
        const option = document.createElement('option');
        option.value = folder.id;
        option.textContent = folder.name;
        selectFolder.appendChild(option);
    });
    
    // Add event listener to confirm button
    document.getElementById('confirmAddToFolder').addEventListener('click', async () => {
        const folderId = selectFolder.value;
        if (!folderId) {
            showToast('Please select a folder', 'warning');
            return;
        }
        
        const success = await addMediaToFolder(mediaId, folderId);
        if (success) {
            // Reload media folders
            await loadMediaFolders(mediaId);
            bsModal.hide();
        }
    });
    
    // Show the modal
    bsModal.show();
}

// Remove media from selected folder
async function removeFromSelectedFolder(mediaId) {
    const foldersSelect = document.getElementById('mediaFolders');
    const selectedOptions = foldersSelect.selectedOptions;
    
    if (selectedOptions.length === 0) {
        showToast('Please select a folder to remove from', 'warning');
        return;
    }
    
    const folderId = selectedOptions[0].value;
    const folderName = selectedOptions[0].textContent;
    
    if (confirm(`Are you sure you want to remove this media from the folder "${folderName}"?`)) {
        const success = await removeMediaFromFolder(mediaId, folderId);
        if (success) {
            // Reload media folders
            await loadMediaFolders(mediaId);
        }
    }
}

// Save media details
async function saveMediaDetails() {
    try {
        const mediaId = document.getElementById('mediaId').value;
        const description = document.getElementById('mediaDescription').value;
        const tags = document.getElementById('mediaTags').value;
        
        const response = await fetch(`/api/media/${mediaId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                description: description,
                tags: tags
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to update media');
        }
        
        // Reload data
        await loadMediaLibraryData();
        
        // Show success message
        showToast('Media details updated successfully', 'success');
    } catch (error) {
        handleApiError(error);
    }
}

// Process media for anti-detection
async function processMedia() {
    try {
        const mediaId = document.getElementById('mediaId').value;
        
        // Show processing message
        const processBtn = document.getElementById('processMedia');
        const originalBtnText = processBtn.innerHTML;
        processBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Processing...';
        processBtn.disabled = true;
        
        const response = await fetch(`/api/media/${mediaId}/process`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to process media');
        }
        
        // Reload data
        await loadMediaLibraryData();
        
        // Show success message
        showToast('Media processed successfully', 'success');
        
        // Close modal and reopen with updated details
        const modal = bootstrap.Modal.getInstance(document.getElementById('mediaDetailsModal'));
        modal.hide();
        
        // Wait for modal to close before reopening
        setTimeout(() => {
            showMediaDetails(mediaId);
        }, 500);
    } catch (error) {
        handleApiError(error);
        
        // Reset button
        const processBtn = document.getElementById('processMedia');
        processBtn.innerHTML = '<i class="fas fa-magic me-1"></i>Process for Anti-Detection';
        processBtn.disabled = false;
    }
}

// Delete media
async function deleteMedia() {
    try {
        const mediaId = document.getElementById('mediaId').value;
        
        if (!confirm('Are you sure you want to delete this media? This action cannot be undone.')) {
            return;
        }
        
        const response = await fetch(`/api/media/${mediaId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to delete media');
        }
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('mediaDetailsModal'));
        modal.hide();
        
        // Reload data
        await loadMediaLibraryData();
        
        // Show success message
        showToast('Media deleted successfully', 'success');
    } catch (error) {
        handleApiError(error);
    }
}

// Show upload modal
function showUploadModal() {
    // Reset form
    document.getElementById('uploadMediaForm').reset();
    document.getElementById('uploadProgress').classList.add('d-none');
    
    // Populate folder dropdown
    populateUploadFolderDropdown();
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('uploadMediaModal'));
    modal.show();
}

// Populate upload folder dropdown
function populateUploadFolderDropdown() {
    const folderSelect = document.getElementById('uploadFolder');
    
    // Clear existing options except the first one
    while (folderSelect.options.length > 1) {
        folderSelect.remove(1);
    }
    
    // Add folder options
    allFolders.forEach(folder => {
        const option = document.createElement('option');
        option.value = folder.id;
        option.textContent = folder.name;
        folderSelect.appendChild(option);
    });
    
    // If we're in a folder view, preselect that folder
    if (currentFolderId) {
        folderSelect.value = currentFolderId;
    }
}

// Upload media
async function uploadMedia() {
    try {
        const fileInput = document.getElementById('uploadFiles');
        const description = document.getElementById('uploadDescription').value;
        const tags = document.getElementById('uploadTags').value;
        const processImmediately = document.getElementById('processImmediately').checked;
        const folderId = document.getElementById('uploadFolder').value;
        
        if (fileInput.files.length === 0) {
            showToast('Please select at least one file', 'warning');
            return;
        }
        
        // Show progress bar
        const progressBar = document.getElementById('uploadProgress').querySelector('.progress-bar');
        document.getElementById('uploadProgress').classList.remove('d-none');
        progressBar.style.width = '0%';
        
        // Disable save button
        const saveButton = document.getElementById('saveUploadMedia');
        const originalText = saveButton.innerHTML;
        saveButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Uploading...';
        saveButton.disabled = true;
        
        // Upload each file
        const totalFiles = fileInput.files.length;
        let uploadedFiles = 0;
        const uploadedMediaIds = [];
        
        for (const file of fileInput.files) {
            // Create form data
            const formData = new FormData();
            formData.append('file', file);
            formData.append('description', description);
            formData.append('tags', tags);
            
            // Add folder ID if selected
            if (folderId) {
                console.log(`DEBUG: Adding file to folder ${folderId} during upload`);
                formData.append('folder_id', folderId);
            }
            
            // Upload file
            const response = await fetch('/api/media', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to upload media');
            }
            
            const result = await response.json();
            const mediaId = result.id || result.media_id;
            uploadedMediaIds.push(mediaId);
            
            // Update progress
            uploadedFiles++;
            const progress = Math.round((uploadedFiles / totalFiles) * 100);
            progressBar.style.width = `${progress}%`;
            
            // Process immediately if requested
            if (processImmediately && (result.media_type === 'image' || (result.filename && result.filename.match(/\.(jpg|jpeg|png|gif)$/i)))) {
                await fetch(`/api/media/${mediaId}/process`, { method: 'POST' });
            }
            
            // We no longer need to add to folder here since it's done during upload
            // if (folderId) {
            //     await addMediaToFolder(result.id, folderId);
            // }
        }
        
        // Reset button state
        saveButton.innerHTML = originalText;
        saveButton.disabled = false;
        
        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('uploadMediaModal')).hide();
        
        // Reload media
        if (currentFolderId) {
            // If we're in a folder view, reload that folder's media
            await loadFolderMedia(currentFolderId);
        } else {
            // Otherwise reload all media
            await loadMedia();
        }
        
        // Show success message
        showToast(`Successfully uploaded ${uploadedFiles} file(s)`, 'success');
    } catch (error) {
        console.error('Error uploading media:', error);
        showToast(error.message || 'Error uploading media', 'danger');
        
        // Reset button state
        const saveButton = document.getElementById('saveUploadMedia');
        saveButton.innerHTML = '<i class="fas fa-upload me-2"></i>Upload';
        saveButton.disabled = false;
    }
}

// Setup drag and drop functionality
function setupDragAndDrop() {
    const dropzone = document.getElementById('mediaDropzone');
    const fileInput = document.getElementById('fileInput');
    
    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    
    // Highlight drop area when item is dragged over it
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, unhighlight, false);
    });
    
    // Handle dropped files
    dropzone.addEventListener('drop', handleDrop, false);
    
    // Handle click to browse
    dropzone.addEventListener('click', () => {
        fileInput.click();
    });
    
    fileInput.addEventListener('change', () => {
        handleFiles(fileInput.files);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight() {
        dropzone.classList.add('highlight');
    }
    
    function unhighlight() {
        dropzone.classList.remove('highlight');
    }
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    }
    
    function handleFiles(files) {
        // Set files to upload modal
        document.getElementById('uploadFiles').files = files;
        
        // Show upload modal
        showUploadModal();
    }
}

// Show batch process modal
async function showBatchProcessModal() {
    try {
        // Get unprocessed images
        const batchProcessList = document.getElementById('batchProcessList');
        batchProcessList.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm text-primary" role="status"></div><span class="ms-2">Loading images...</span></div>';
        
        // Filter for unprocessed images
        const unprocessedImages = allMedia.filter(media => 
            media.media_type === 'image' && !media.processed_path
        );
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('batchProcessModal'));
        modal.show();
        
        // If no unprocessed images, show message
        if (unprocessedImages.length === 0) {
            batchProcessList.innerHTML = '<div class="text-center py-3"><i class="fas fa-check-circle text-success me-2"></i>All images have been processed</div>';
            document.getElementById('selectAllImages').disabled = true;
            document.getElementById('startBatchProcess').disabled = true;
            return;
        }
        
        // Enable controls
        document.getElementById('selectAllImages').disabled = false;
        document.getElementById('startBatchProcess').disabled = false;
        
        // Clear list
        batchProcessList.innerHTML = '';
        
        // Add each unprocessed image to the list
        unprocessedImages.forEach(media => {
            const batchItem = document.createElement('div');
            batchItem.className = 'batch-item';
            
            const thumbnailSrc = `/api/media/original/${media.original_path.split('/').pop()}`;
            
            batchItem.innerHTML = `
                <input type="checkbox" class="form-check-input me-3 batch-select" data-id="${media.id}">
                <img src="${thumbnailSrc}" alt="${media.filename}" class="batch-thumbnail">
                <div class="batch-item-info">
                    <div class="batch-item-title">${media.filename}</div>
                    <div class="batch-item-status">${formatFileSize(media.file_size)}</div>
                </div>
            `;
            
            batchProcessList.appendChild(batchItem);
        });
    } catch (error) {
        handleApiError(error);
    }
}

// Toggle select all images
function toggleSelectAllImages() {
    const selectAll = document.getElementById('selectAllImages').checked;
    const checkboxes = document.querySelectorAll('.batch-select');
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = selectAll;
    });
}

// Start batch processing
async function startBatchProcess() {
    try {
        // Get selected media IDs
        const checkboxes = document.querySelectorAll('.batch-select:checked');
        const mediaIds = Array.from(checkboxes).map(checkbox => checkbox.dataset.id);
        
        if (mediaIds.length === 0) {
            showToast('Please select at least one image to process', 'warning');
            return;
        }
        
        // Show progress bar
        const progressBar = document.getElementById('batchProgress');
        const progressBarInner = progressBar.querySelector('.progress-bar');
        progressBar.classList.remove('d-none');
        progressBarInner.style.width = '0%';
        
        // Disable process button
        const processBtn = document.getElementById('startBatchProcess');
        const originalBtnText = processBtn.innerHTML;
        processBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Processing...';
        processBtn.disabled = true;
        
        // Process each image
        let successCount = 0;
        
        for (let i = 0; i < mediaIds.length; i++) {
            const mediaId = mediaIds[i];
            
            // Update progress
            const progress = Math.round((i / mediaIds.length) * 100);
            progressBarInner.style.width = `${progress}%`;
            
            try {
                // Process image
                const response = await fetch(`/api/media/${mediaId}/process`, {
                    method: 'POST'
                });
                
                if (response.ok) {
                    successCount++;
                }
                
                // Update checkbox to show progress
                const checkbox = document.querySelector(`.batch-select[data-id="${mediaId}"]`);
                if (checkbox) {
                    const batchItem = checkbox.closest('.batch-item');
                    checkbox.disabled = true;
                    checkbox.checked = true;
                    
                    // Add success indicator
                    const statusDiv = batchItem.querySelector('.batch-item-status');
                    statusDiv.innerHTML = '<span class="text-success"><i class="fas fa-check-circle me-1"></i>Processed</span>';
                }
            } catch (error) {
                console.error(`Error processing media ${mediaId}:`, error);
                
                // Update checkbox to show error
                const checkbox = document.querySelector(`.batch-select[data-id="${mediaId}"]`);
                if (checkbox) {
                    const batchItem = checkbox.closest('.batch-item');
                    checkbox.disabled = true;
                    
                    // Add error indicator
                    const statusDiv = batchItem.querySelector('.batch-item-status');
                    statusDiv.innerHTML = '<span class="text-danger"><i class="fas fa-times-circle me-1"></i>Failed</span>';
                }
            }
        }
        
        // Complete progress
        progressBarInner.style.width = '100%';
        progressBarInner.setAttribute('aria-valuenow', 100);
        
        // Reset button
        processBtn.innerHTML = originalBtnText;
        processBtn.disabled = false;
        
        // Show success message
        showToast(`Successfully processed ${successCount} of ${mediaIds.length} images`, 'success');
        
        // Reload data
        await loadMediaLibraryData();
    } catch (error) {
        handleApiError(error);
        
        // Reset button
        const processBtn = document.getElementById('startBatchProcess');
        processBtn.innerHTML = '<i class="fas fa-magic me-2"></i>Process Selected Images';
        processBtn.disabled = false;
    }
}

// Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = date.getMonth() + 1;
    const day = date.getDate();
    const hour = date.getHours();
    const minute = date.getMinutes();
    const second = date.getSeconds();
    
    return `${year}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')} ${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}:${second.toString().padStart(2, '0')}`;
}

// Initialize context menu for folders
function initFolderContextMenu() {
    $.contextMenu({
        selector: '.folder-item',
        callback: function(key, options) {
            const folderId = $(this).data('folder-id');
            const folderName = $(this).find('.folder-name').text();
            
            if (key === 'edit') {
                showEditFolderModal(folderId, folderName);
            } else if (key === 'delete') {
                showDeleteFolderConfirmation(folderId, folderName);
            } else if (key === 'schedule') {
                showScheduleFolderModal(folderId, folderName);
            }
        },
        items: {
            "edit": {name: "Edit Folder", icon: "edit"},
            "delete": {name: "Delete Folder", icon: "delete"},
            "schedule": {name: "Schedule Posts", icon: "fa-calendar"}
        }
    });
}

// Show the schedule folder modal
function showScheduleFolderModal(folderId, folderName) {
    // Set the folder ID in the hidden input
    $('#scheduleFolderId').val(folderId);
    
    // Set the modal title to include the folder name
    $('#scheduleFolderModalLabel').text(`Schedule Posts from Folder: ${folderName}`);
    
    // Get devices and populate the dropdown
    $.ajax({
        url: '/api/devices',
        type: 'GET',
        success: function(response) {
            const deviceSelect = $('#scheduleDevice');
            deviceSelect.empty();
            deviceSelect.append('<option value="">Select Device</option>');
            
            if (response && response.length > 0) {
                response.forEach(device => {
                    deviceSelect.append(`<option value="${device.deviceid}">${device.devicename || device.deviceid}</option>`);
                });
            }
            
            // Set today's date as the default start date
            const today = new Date();
            today.setDate(today.getDate() + 1);
            const formattedDate = today.toISOString().slice(0, 10);
            $('#scheduleStartDate').val(formattedDate);
            
            // Set a default time (e.g., noon)
            $('#scheduleStartTime').val('12:00');
            
            // Show the modal
            $('#scheduleFolderModal').modal('show');
        },
        error: function(xhr, status, error) {
            showToast('Error', 'Failed to load devices. Please try again.', 'error');
            console.error('Error loading devices:', error);
        }
    });
}

// Handle device selection to load accounts
$('#scheduleDevice').on('change', async function() {
    const deviceId = $(this).val();
    if (!deviceId) {
        $('#scheduleAccount').empty().append('<option value="">Select Account</option>');
        return;
    }
    
    // Get accounts for the selected device
    $.ajax({
        url: `/api/devices/${deviceId}/accounts`,
        type: 'GET',
        success: async function(response) {
            const accountSelect = $('#scheduleAccount');
            accountSelect.empty();
            accountSelect.append('<option value="">Select Account</option>');
            
            if (response && response.length > 0) {
                response.forEach(account => {
                    accountSelect.append(`<option value="${account.account}">${account.account}</option>`);
                });
            }
        },
        error: function(xhr, status, error) {
            showToast('Error', 'Failed to load accounts. Please try again.', 'error');
            console.error('Error loading accounts:', error);
        },
        complete: function() {}
    });
});

// Update schedule summary when form values change
function updateScheduleSummary() {
    const folderId = $('#scheduleFolderId').val();
    const startDate = $('#scheduleStartDate').val();
    const startTime = $('#scheduleStartTime').val();
    const frequency = $('#scheduleFrequency').val();
    
    if (!folderId || !startDate || !startTime || !frequency) {
        $('#scheduleSummary').hide();
        return;
    }
    
    // Get media count in the folder
    $.ajax({
        url: `/api/folders/${folderId}/media`,
        type: 'GET',
        success: function(response) {
            const mediaCount = response.length;
            let summaryText = `You are about to schedule ${mediaCount} posts`;
            
            // Format the frequency text
            let frequencyText = '';
            if (frequency === 'daily') {
                frequencyText = 'daily';
            } else if (frequency === 'every_other_day') {
                frequencyText = 'every other day';
            } else if (frequency === 'weekly') {
                frequencyText = 'weekly';
            }
            
            // Calculate end date based on frequency and media count
            const startDateTime = new Date(`${startDate}T${startTime}`);
            let endDateTime = new Date(startDateTime);
            
            if (frequency === 'daily') {
                endDateTime.setDate(startDateTime.getDate() + mediaCount - 1);
            } else if (frequency === 'every_other_day') {
                endDateTime.setDate(startDateTime.getDate() + (mediaCount - 1) * 2);
            } else if (frequency === 'weekly') {
                endDateTime.setDate(startDateTime.getDate() + (mediaCount - 1) * 7);
            }
            
            const formattedStartDate = startDateTime.toLocaleDateString();
            const formattedEndDate = endDateTime.toLocaleDateString();
            
            summaryText += ` ${frequencyText}, starting on ${formattedStartDate} at ${startTime}`;
            summaryText += ` and ending on ${formattedEndDate}.`;
            
            $('#scheduleSummaryText').text(summaryText);
            $('#scheduleSummary').show();
        },
        error: function(xhr, status, error) {
            console.error('Error getting media count:', error);
            $('#scheduleSummary').hide();
        }
    });
}

// Update summary when form values change
$('#scheduleStartDate, #scheduleStartTime, #scheduleFrequency').on('change', updateScheduleSummary);

// Handle schedule form submission
$('#saveSchedule').on('click', function() {
    // Validate form
    const form = document.getElementById('scheduleFolderForm');
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }
    
    // Get form values
    const folderId = $('#scheduleFolderId').val();
    const deviceId = $('#scheduleDevice').val();
    const account = $('#scheduleAccount').val();
    const startDate = $('#scheduleStartDate').val();
    const startTime = $('#scheduleStartTime').val();
    const frequency = $('#scheduleFrequency').val();
    const postType = $('#schedulePostType').val();
    const captionTemplate = $('#scheduleCaptionTemplate').val();
    const hashtags = $('#scheduleHashtags').val();
    const location = $('#scheduleLocation').val();
    const repurpose = $('#scheduleRepurpose').is(':checked');
    
    // Create schedule data object
    const scheduleData = {
        deviceid: deviceId,
        account: account,
        start_date: startDate,
        start_time: startTime,
        frequency: frequency,
        post_type: postType,
        caption_template: captionTemplate,
        hashtags: hashtags,
        location: location,
        repurpose: repurpose
    };
    
    // Show loading state
    const saveButton = $('#saveSchedule');
    const originalText = saveButton.text();
    saveButton.text('Scheduling...').prop('disabled', true);
    
    // Send schedule request
    $.ajax({
        url: `/api/folders/${folderId}/schedule`,
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(scheduleData),
        success: function(response) {
            if (response.success) {
                showToast('Success', response.message, 'success');
                $('#scheduleFolderModal').modal('hide');
            } else {
                showToast('Error', response.message, 'error');
            }
        },
        error: function(xhr, status, error) {
            let errorMessage = 'Failed to schedule posts. Please try again.';
            if (xhr.responseJSON && xhr.responseJSON.message) {
                errorMessage = xhr.responseJSON.message;
            }
            showToast('Error', errorMessage, 'error');
            console.error('Error scheduling posts:', error);
        },
        complete: function() {
            saveButton.text(originalText).prop('disabled', false);
        }
    });
});

// View original media
async function viewOriginal() {
    try {
        const mediaId = document.getElementById('mediaId').value;
        
        // Fetch the media details to get the correct path
        fetch(`/api/media/${mediaId}`)
            .then(response => response.json())
            .then(media => {
                // Get filename, handling both Windows and Unix paths
                let filename;
                if (media.original_path.includes('\\')) {
                    // Windows path
                    filename = media.original_path.split('\\').pop();
                } else {
                    // Unix path
                    filename = media.original_path.split('/').pop();
                }
                const originalPath = `/api/media/original/${filename}`;
                console.log(`DEBUG: Opening original media at ${originalPath}`);
                window.open(originalPath, '_blank');
            })
            .catch(error => {
                console.error('Error fetching media details:', error);
                showToast('Error', 'Failed to open original media', 'error');
            });
    } catch (error) {
        console.error('Error in viewOriginal:', error);
        showToast('Error', 'Failed to open original media', 'error');
    }
}

// View processed media
async function viewProcessed() {
    try {
        const mediaId = document.getElementById('mediaId').value;
        
        // Fetch the media details to get the correct path
        fetch(`/api/media/${mediaId}`)
            .then(response => response.json())
            .then(media => {
                if (media.processed_path) {
                    // Log the raw processed path for debugging
                    console.log('Raw processed_path:', media.processed_path);
                    
                    // Get filename, handling both Windows and Unix paths
                    let filename;
                    if (media.processed_path.includes('\\')) {
                        // Windows path
                        filename = media.processed_path.split('\\').pop();
                    } else {
                        // Unix path
                        filename = media.processed_path.split('/').pop();
                    }
                    console.log('Extracted filename:', filename);
                    
                    // Use the same path format as in the preview
                    const processedPath = `/api/media/processed/${filename}`;
                    console.log(`DEBUG: Opening processed media at ${processedPath}`);
                    alert(`Opening processed media at: ${processedPath}`);
                    window.open(processedPath, '_blank');
                } else {
                    showToast('Info', 'This media has not been processed yet', 'info');
                }
            })
            .catch(error => {
                console.error('Error fetching media details:', error);
                showToast('Error', 'Failed to open processed media', 'error');
            });
    } catch (error) {
        console.error('Error in viewProcessed:', error);
        showToast('Error', 'Failed to open processed media', 'error');
    }
}
