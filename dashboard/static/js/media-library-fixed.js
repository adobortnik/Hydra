// Media Library functionality - Fixed version for Windows

// Global variables
let allMedia = [];
let allTags = [];
let allFolders = [];
let currentFolderId = null;

// Initialize when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing fixed media library');
    
    // Set up event listeners for UI interactions
    const refreshMediaBtn = document.getElementById('refreshMedia');
    if (refreshMediaBtn) {
        refreshMediaBtn.addEventListener('click', loadMediaLibraryData);
    }
    
    const mediaSearchInput = document.getElementById('mediaSearch');
    if (mediaSearchInput) {
        mediaSearchInput.addEventListener('input', filterMedia);
    }
    
    const typeFilterSelect = document.getElementById('typeFilter');
    if (typeFilterSelect) {
        typeFilterSelect.addEventListener('change', filterMedia);
    }
    
    const tagFilterSelect = document.getElementById('tagFilter');
    if (tagFilterSelect) {
        tagFilterSelect.addEventListener('change', filterMedia);
    }
    
    const uploadMediaBtn = document.getElementById('uploadMediaBtn');
    if (uploadMediaBtn) {
        uploadMediaBtn.addEventListener('click', function() {
            const modal = document.getElementById('uploadMediaModal');
            if (modal) {
                const bsModal = new bootstrap.Modal(modal);
                bsModal.show();
            }
        });
    }
    
    const createFolderBtn = document.getElementById('createFolderBtn');
    if (createFolderBtn) {
        createFolderBtn.addEventListener('click', showCreateFolderModal);
    }
    
    // Load initial data
    loadMediaLibraryData();
    
    // Setup upload functionality
    setupUploadFunctionality();
});

// Load all media library data
async function loadMediaLibraryData() {
    console.log('Loading all media library data');
    try {
        // Show loading indicator
        const mediaGrid = document.getElementById('mediaGrid');
        if (mediaGrid) {
            mediaGrid.innerHTML = '<div class="col-12 text-center py-5"><div class="spinner-border text-primary" role="status"></div><p class="mt-3">Loading media library...</p></div>';
        }
        
        // Load folders first
        await loadFolders();
        console.log('Folders loaded');
        
        // Then load tags
        await loadTags();
        console.log('Tags loaded');
        
        // Finally load media - this will filter and render automatically
        await loadMedia();
        console.log('Media loaded and rendered');
        
        // Everything loaded successfully
        showToast('Media library refreshed', 'success');
    } catch (error) {
        console.error('Error loading media library data:', error);
        const mediaGrid = document.getElementById('mediaGrid');
        if (mediaGrid) {
            mediaGrid.innerHTML = '<div class="col-12 text-center py-5"><div class="alert alert-danger">Failed to load media library. <button class="btn btn-sm btn-danger" onclick="loadMediaLibraryData()">Try Again</button></div></div>';
        }
    }
}

// Load folders from API
async function loadFolders() {
    console.log('Starting to load folders');
    try {
        // Show loading state in folder tree
        const folderTree = document.getElementById('folderTree');
        if (folderTree) {
            folderTree.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm text-primary" role="status"></div><p class="small mt-2 mb-0">Loading folders...</p></div>';
        }
        
        console.log('Fetching from /api/folders');
        const response = await fetch('/api/folders');
        
        if (!response.ok) {
            console.error('Failed to load folders, status:', response.status);
            throw new Error('Failed to load folders');
        }
        
        allFolders = await response.json();
        console.log('Successfully loaded', allFolders.length, 'folders');
        
        // Render the folder tree
        renderFolderTree();
        
        return allFolders;
    } catch (error) {
        console.error('Error loading folders:', error);
        const folderTree = document.getElementById('folderTree');
        if (folderTree) {
            folderTree.innerHTML = '<div class="text-center py-3"><div class="alert alert-danger p-2 small">Failed to load folders</div></div>';
        }
        throw error; // Re-throw for the calling function to handle
    }
}

// Render folder tree
function renderFolderTree() {
    console.log('Starting to render folder tree');
    const folderTree = document.getElementById('folderTree');
    if (!folderTree) {
        console.error('folderTree element not found');
        return;
    }
    
    // Safety check - if allFolders is undefined or not an array, initialize it
    if (!allFolders || !Array.isArray(allFolders)) {
        console.error('allFolders is not valid, resetting to empty array');
        allFolders = [];
        folderTree.innerHTML = '<div class="text-center py-3"><div class="alert alert-warning p-2 small">No folders available</div></div>';
        return;
    }
    
    try {
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
        
        console.log('Building tree with', allFolders.length, 'folders');
        
        // Build tree for root-level folders
        const rootFolders = allFolders.filter(folder => !folder.parent_id);
        rootFolders.forEach(folder => {
            try {
                html += `
                <div class="folder-item ${folder.id === currentFolderId ? 'active' : ''}" data-folder-id="${folder.id}">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-folder me-2"></i>
                        <span class="folder-name">${folder.name}</span>
                        <button class="btn btn-sm btn-link ms-auto" onclick="showEditFolderModal(${folder.id})"><i class="fas fa-edit"></i></button>
                        <button class="btn btn-sm btn-link text-danger ms-1" onclick="confirmDeleteFolder(${folder.id})"><i class="fas fa-trash"></i></button>
                    </div>
                </div>`;
            } catch (itemError) {
                console.error('Error generating folder item for:', folder.id, itemError);
                // Continue with other folders
            }
        });
        
        // Set HTML
        folderTree.innerHTML = html;
        
        // Add event listeners to folder items
        const folderItems = folderTree.querySelectorAll('.folder-item');
        folderItems.forEach(item => {
            item.addEventListener('click', function(e) {
                // Only trigger if clicked on the folder item itself or the folder name
                if (e.target === item || e.target.classList.contains('folder-name') || e.target.tagName === 'I') {
                    e.stopPropagation();
                    const folderId = this.dataset.folderId;
                    selectFolder(folderId);
                }
            });
        });
        
        console.log('Folder tree rendered successfully');
    } catch (error) {
        console.error('Error rendering folder tree:', error);
        folderTree.innerHTML = '<div class="text-center py-3"><div class="alert alert-danger p-2 small">Error loading folders</div></div>';
    }
}

// Select a folder
function selectFolder(folderId) {
    currentFolderId = folderId || null;
    
    // Update active state in UI
    const folderItems = document.querySelectorAll('.folder-item');
    folderItems.forEach(item => {
        item.classList.toggle('active', item.dataset.folderId === folderId);
    });
    
    // Load media for the selected folder
    if (folderId) {
        loadFolderMedia(folderId);
    } else {
        loadMedia();
    }
}

// Load media for a specific folder
async function loadFolderMedia(folderId) {
    if (!folderId) {
        return loadMedia(); // Load all media if no folder ID
    }
    
    try {
        // Show loading state
        const mediaGrid = document.getElementById('mediaGrid');
        if (mediaGrid) {
            mediaGrid.innerHTML = '<div class="col-12 text-center py-5"><div class="spinner-border text-primary" role="status"></div><p class="mt-3">Loading media...</p></div>';
        }
        
        const response = await fetch(`/api/folders/${folderId}/media`);
        if (!response.ok) {
            throw new Error('Failed to load folder media');
        }
        
        allMedia = await response.json();
        console.log(`Loaded ${allMedia.length} media items for folder ${folderId}`);
        
        // Filter and render media
        filterMedia();
    } catch (error) {
        console.error('Error loading folder media:', error);
        const mediaGrid = document.getElementById('mediaGrid');
        if (mediaGrid) {
            mediaGrid.innerHTML = '<div class="col-12 text-center py-5"><div class="alert alert-danger">Failed to load folder media</div></div>';
        }
    }
}

// Load tags from API
async function loadTags() {
    try {
        const response = await fetch('/api/tags');
        if (!response.ok) {
            throw new Error('Failed to load tags');
        }
        
        allTags = await response.json();
        console.log(`Loaded ${allTags.length} tags`);
        
        // Populate tag filter dropdown
        const tagFilter = document.getElementById('tagFilter');
        if (tagFilter) {
            let html = '<option value="">All Tags</option>';
            
            allTags.forEach(tag => {
                html += `<option value="${tag.name}">${tag.name}</option>`;
            });
            
            tagFilter.innerHTML = html;
        }
    } catch (error) {
        console.error('Error loading tags:', error);
    }
}

// Load media from API
async function loadMedia() {
    try {
        console.log('Loading media from API');
        const response = await fetch('/api/media');
        
        if (!response.ok) {
            console.error('Failed to load media:', response.status, response.statusText);
            showToast('Error loading media', 'danger');
            throw new Error('Failed to load media');
        }
        
        allMedia = await response.json();
        console.log('Media loaded successfully:', allMedia.length, 'items');
        
        // Filter and render media
        filterMedia();
    } catch (error) {
        console.error('Error loading media:', error);
        showToast('Error loading media', 'danger');
    }
}

// Filter media based on search and filters
function filterMedia() {
    console.log('Starting to filter media, allMedia length:', allMedia ? allMedia.length : 'null');
    
    // Safety check - if allMedia is undefined or not an array, initialize it
    if (!allMedia || !Array.isArray(allMedia)) {
        console.error('allMedia is not valid, resetting to empty array');
        allMedia = [];
        const mediaGrid = document.getElementById('mediaGrid');
        if (mediaGrid) {
            mediaGrid.innerHTML = '<div class="col-12 text-center py-5"><div class="alert alert-warning">No media data available. <button class="btn btn-sm btn-primary" onclick="loadMedia()">Reload Media</button></div></div>';
        }
        return;
    }
    
    const searchInput = document.getElementById('mediaSearch');
    const typeFilter = document.getElementById('typeFilter');
    const tagFilter = document.getElementById('tagFilter');
    
    const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
    const typeFilterValue = typeFilter ? typeFilter.value : '';
    const tagFilterValue = tagFilter ? tagFilter.value : '';
    
    console.log('Using filters - search:', searchTerm, 'type:', typeFilterValue, 'tag:', tagFilterValue);
    
    // Filter media based on search term, type, and tag
    const filteredMedia = allMedia.filter(media => {
        const matchesSearch = searchTerm === '' || 
            (media.filename && media.filename.toLowerCase().includes(searchTerm)) || 
            (media.description && media.description.toLowerCase().includes(searchTerm));
        
        const matchesType = typeFilterValue === '' || media.media_type === typeFilterValue;
        
        const matchesTag = tagFilterValue === '' || 
            (media.tags_list && media.tags_list.includes(tagFilterValue));
        
        return matchesSearch && matchesType && matchesTag;
    });
    
    console.log(`Filtered to ${filteredMedia.length} media items`);
    
    // Render the filtered media
    try {
        renderMediaGrid(filteredMedia);
    } catch (error) {
        console.error('Error rendering media grid:', error);
        const mediaGrid = document.getElementById('mediaGrid');
        if (mediaGrid) {
            mediaGrid.innerHTML = '<div class="col-12 text-center py-5"><div class="alert alert-danger">Error rendering media. <button class="btn btn-sm btn-danger" onclick="loadMediaLibraryData()">Try Again</button></div></div>';
        }
    }
}

// Render media grid
function renderMediaGrid(mediaItems) {
    const mediaGrid = document.getElementById('mediaGrid');
    if (!mediaGrid) {
        console.error('mediaGrid element not found');
        return;
    }
    
    if (!mediaItems || mediaItems.length === 0) {
        mediaGrid.innerHTML = '<div class="col-12 text-center py-5"><p class="text-muted">No media found matching the current filters.</p></div>';
        return;
    }

    console.log('Rendering media grid with', mediaItems.length, 'items');
    let html = '';
    
    mediaItems.forEach(media => {
        // Create media item HTML
        html += '<div class="col-6 col-md-4 col-lg-3 mb-4" data-media-id="' + media.id + '">';
        html += '<div class="media-item card h-100" data-media-filename="' + media.filename + '">';
        
        // Media preview - handle different media types
        html += '<div class="card-img-container">';
        
        // Determine thumbnail source
        let thumbnailSrc = '';
        let filename = '';
        
        console.log('Media item:', media.id, 'Original path:', media.original_path, 'Processed path:', media.processed_path);
        
        if (media.processed_path) {
            // Extract just the filename from the path, regardless of path separator
            filename = media.processed_path.split(/[\\\\\\\\//]/).pop();
            thumbnailSrc = `/api/media/processed/${filename}`;
            console.log('Using processed path, generated URL:', thumbnailSrc);
        } else if (media.original_path) {
            // Extract just the filename from the path, regardless of path separator
            filename = media.original_path.split(/[\\\\\\\\//]/).pop();
            thumbnailSrc = `/api/media/original/${filename}`;
            console.log('Using original path, generated URL:', thumbnailSrc);
        } else {
            console.error('Media item has no path:', media);
            thumbnailSrc = '/static/img/placeholder.jpg';
        }
        
        if (media.media_type === 'image') {
            html += `<img src="${thumbnailSrc}" class="card-img-top" alt="${media.filename}" 
                onerror="this.onerror=null; this.src='/static/img/placeholder.jpg'; console.error('Failed to load image:', '${thumbnailSrc}');">`;        
        } else if (media.media_type === 'video') {
            html += '<div class="video-preview" style="background-image: url(\'' + thumbnailSrc + '\');"><i class="fas fa-play-circle"></i></div>';
        } else {
            html += '<div class="file-preview"><i class="fas fa-file"></i></div>';
        }
        
        html += '</div>';
        html += '<div class="card-body">';
        html += '<h5 class="card-title">' + media.filename + '</h5>';
        html += '<p class="card-text">' + (media.description || '') + '</p>';
        html += '</div>';
        html += '</div>';
        html += '</div>';
    });
    
    mediaGrid.innerHTML = html;
    
    // Add click event listeners to media items
    const mediaItemElements = document.querySelectorAll('.media-item');
    mediaItemElements.forEach(item => {
        item.addEventListener('click', function() {
            const mediaId = this.closest('[data-media-id]').dataset.mediaId;
            showMediaDetails(mediaId);
        });
    });
}

// Show media details modal
function showMediaDetails(mediaId) {
    // Find the media item
    const media = allMedia.find(item => item.id === mediaId);
    if (!media) {
        console.error('Media not found with ID:', mediaId);
        return;
    }
    
    // Get the modal element
    const modal = document.getElementById('mediaDetailsModal');
    if (!modal) {
        console.error('Media details modal not found');
        return;
    }
    
    // Set media details in the modal
    document.getElementById('mediaId').value = media.id;
    document.getElementById('mediaDetailsModalTitle').textContent = media.filename;
    
    // Set preview
    const previewContainer = document.getElementById('mediaPreview');
    if (previewContainer) {
        let previewHtml = '';
        let previewSrc = '';
        
        if (media.processed_path) {
            const filename = media.processed_path.split(/[\\\\\\\\//]/).pop();
            previewSrc = `/api/media/processed/${filename}`;
        } else {
            const filename = media.original_path.split(/[\\\\\\\\//]/).pop();
            previewSrc = `/api/media/original/${filename}`;
        }
        
        if (media.media_type === 'image') {
            previewHtml = `<img src="${previewSrc}" alt="${media.filename}" class="img-fluid" onerror="this.onerror=null; this.src='/static/img/placeholder.jpg';">`;
        } else if (media.media_type === 'video') {
            previewHtml = `<video src="${previewSrc}" controls class="img-fluid"></video>`;
        } else {
            previewHtml = `<div class="file-preview"><i class="fas fa-file fa-5x"></i><p>${media.filename}</p></div>`;
        }
        
        previewContainer.innerHTML = previewHtml;
    }
    
    // Fill form fields
    const descriptionInput = document.getElementById('mediaDescription');
    if (descriptionInput) {
        descriptionInput.value = media.description || '';
    }
    
    // Show the modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

// Save media details
async function saveMediaDetails() {
    const mediaIdInput = document.getElementById('mediaId');
    const descriptionInput = document.getElementById('mediaDescription');
    const saveMediaDetailsBtn = document.getElementById('saveMediaDetails');
    
    if (!mediaIdInput) {
        showToast('Media ID is missing', 'warning');
        return;
    }
    
    const mediaId = mediaIdInput.value;
    if (!mediaId) {
        showToast('Media ID is missing', 'warning');
        return;
    }
    
    // Disable button and show loading
    if (saveMediaDetailsBtn) {
        saveMediaDetailsBtn.disabled = true;
        saveMediaDetailsBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
    }
    
    try {
        const data = {
            description: descriptionInput ? descriptionInput.value : ''
        };
        
        const response = await fetch(`/api/media/${mediaId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            throw new Error('Failed to update media details');
        }
        
        // Show success message
        showToast('Media details updated successfully', 'success');
        
        // Update the media item in the allMedia array
        const mediaIndex = allMedia.findIndex(m => m.id === mediaId);
        if (mediaIndex !== -1) {
            allMedia[mediaIndex].description = data.description;
        }
        
        // Close modal
        const modal = document.getElementById('mediaDetailsModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
        
        // Refresh media grid
        filterMedia();
    } catch (error) {
        console.error('Error updating media details:', error);
        showToast('Error updating media details', 'danger');
    } finally {
        // Reset button
        if (saveMediaDetailsBtn) {
            saveMediaDetailsBtn.disabled = false;
            saveMediaDetailsBtn.innerHTML = 'Save Changes';
        }
    }
}

// Process media for anti-detection
async function processMedia() {
    const mediaIdInput = document.getElementById('mediaId');
    const processMediaBtn = document.getElementById('processMedia');
    
    if (!mediaIdInput) {
        showToast('Media ID is missing', 'warning');
        return;
    }
    
    const mediaId = mediaIdInput.value;
    if (!mediaId) {
        showToast('Media ID is missing', 'warning');
        return;
    }
    
    // Find the media item
    const media = allMedia.find(item => item.id === mediaId);
    if (!media) {
        showToast('Media not found', 'warning');
        return;
    }
    
    // Check if media is already processed
    if (media.processed_path) {
        if (!confirm('This media has already been processed. Process it again?')) {
            return;
        }
    }
    
    // Disable button and show loading
    if (processMediaBtn) {
        processMediaBtn.disabled = true;
        processMediaBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...';
    }
    
    try {
        const response = await fetch(`/api/media/${mediaId}/process`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error('Failed to process media');
        }
        
        const result = await response.json();
        
        // Show success message
        showToast('Media processed successfully', 'success');
        
        // Update the media item in the allMedia array
        const mediaIndex = allMedia.findIndex(m => m.id === mediaId);
        if (mediaIndex !== -1) {
            allMedia[mediaIndex].processed_path = result.processed_path;
        }
        
        // Close modal
        const modal = document.getElementById('mediaDetailsModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
        
        // Refresh media grid
        filterMedia();
    } catch (error) {
        console.error('Error processing media:', error);
        showToast('Error processing media', 'danger');
    } finally {
        // Reset button
        if (processMediaBtn) {
            processMediaBtn.disabled = false;
            processMediaBtn.innerHTML = 'Process for Anti-Detection';
        }
    }
}

// Delete media
async function deleteMedia() {
    const mediaIdInput = document.getElementById('mediaId');
    const deleteMediaBtn = document.getElementById('deleteMedia');
    
    if (!mediaIdInput) {
        showToast('Media ID is missing', 'warning');
        return;
    }
    
    const mediaId = mediaIdInput.value;
    if (!mediaId) {
        showToast('Media ID is missing', 'warning');
        return;
    }
    
    // Find the media item
    const media = allMedia.find(item => item.id === mediaId);
    if (!media) {
        showToast('Media not found', 'warning');
        return;
    }
    
    // Confirm deletion
    if (!confirm(`Are you sure you want to delete "${media.filename}"? This action cannot be undone.`)) {
        return;
    }
    
    // Disable button and show loading
    if (deleteMediaBtn) {
        deleteMediaBtn.disabled = true;
        deleteMediaBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Deleting...';
    }
    
    try {
        const response = await fetch(`/api/media/${mediaId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            throw new Error('Failed to delete media');
        }
        
        // Show success message
        showToast('Media deleted successfully', 'success');
        
        // Close modal
        const modal = document.getElementById('mediaDetailsModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
        
        // Remove the media item from the allMedia array
        const mediaIndex = allMedia.findIndex(m => m.id === mediaId);
        if (mediaIndex !== -1) {
            allMedia.splice(mediaIndex, 1);
        }
        
        // Refresh media grid
        filterMedia();
    } catch (error) {
        console.error('Error deleting media:', error);
        showToast('Error deleting media', 'danger');
    } finally {
        // Reset button
        if (deleteMediaBtn) {
            deleteMediaBtn.disabled = false;
            deleteMediaBtn.innerHTML = 'Delete Media';
        }
    }
}

// View original media
function viewOriginal() {
    const mediaIdInput = document.getElementById('mediaId');
    if (!mediaIdInput) return;
    
    const mediaId = mediaIdInput.value;
    if (!mediaId) return;
    
    // Find the media item
    const media = allMedia.find(item => item.id === mediaId);
    if (!media || !media.original_path) return;
    
    // Extract filename from path
    const filename = media.original_path.split(/[\\\\\\\\//]/).pop();
    const url = `/api/media/original/${filename}`;
    
    // Open in new tab
    window.open(url, '_blank');
}

// View processed media
function viewProcessed() {
    const mediaIdInput = document.getElementById('mediaId');
    if (!mediaIdInput) return;
    
    const mediaId = mediaIdInput.value;
    if (!mediaId) return;
    
    // Find the media item
    const media = allMedia.find(item => item.id === mediaId);
    if (!media || !media.processed_path) {
        showToast('This media has not been processed yet', 'warning');
        return;
    }
    
    // Extract filename from path
    const filename = media.processed_path.split(/[\\\\\\\\//]/).pop();
    const url = `/api/media/processed/${filename}`;
    
    // Open in new tab
    window.open(url, '_blank');
}

// Show toast notification
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        console.error('Toast container not found');
        return;
    }
    
    const toastId = 'toast-' + Date.now();
    const bgClass = type === 'success' ? 'bg-success' : 
                   type === 'danger' ? 'bg-danger' : 
                   type === 'warning' ? 'bg-warning' : 'bg-info';
    
    const toastHtml = `
    <div id="${toastId}" class="toast ${bgClass} text-white" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="toast-header ${bgClass} text-white">
            <strong class="me-auto">${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
        <div class="toast-body">
            ${message}
        </div>
    </div>`;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
    toast.show();
    
    // Remove toast from DOM after it's hidden
    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}

// Upload media
function setupUploadFunctionality() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const saveUploadBtn = document.getElementById('saveUploadMedia');
    
    if (!dropzone || !fileInput || !saveUploadBtn) return;
    
    // Setup dropzone click to trigger file input
    dropzone.addEventListener('click', () => {
        fileInput.click();
    });
    
    // Setup drag and drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    // Highlight dropzone when dragging over it
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => {
            dropzone.classList.add('highlight');
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, () => {
            dropzone.classList.remove('highlight');
        }, false);
    });
    
    // Handle dropped files
    dropzone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        fileInput.files = files;
        updateFilePreview(files);
    }, false);
    
    // Handle selected files
    fileInput.addEventListener('change', () => {
        updateFilePreview(fileInput.files);
    });
    
    // Update file preview
    function updateFilePreview(files) {
        if (!files || files.length === 0) return;
        
        let previewHtml = '<div class="mt-3"><h5>Selected Files:</h5><div class="row">';
        
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const isImage = file.type.startsWith('image/');
            const isVideo = file.type.startsWith('video/');
            
            previewHtml += `
            <div class="col-md-3 mb-3">
                <div class="card bg-dark">
                    <div class="card-img-top text-center p-2" style="height: 100px; display: flex; align-items: center; justify-content: center;">
                        ${isImage ? `<img src="${URL.createObjectURL(file)}" style="max-height: 100%; max-width: 100%;">` : ''}
                        ${isVideo ? `<i class="fas fa-video fa-3x text-muted"></i>` : ''}
                        ${!isImage && !isVideo ? `<i class="fas fa-file fa-3x text-muted"></i>` : ''}
                    </div>
                    <div class="card-body p-2">
                        <p class="card-text small text-truncate">${file.name}</p>
                    </div>
                </div>
            </div>`;
        }
        
        previewHtml += '</div></div>';
        dropzone.innerHTML = `
            <div class="dropzone-message">
                <h4><i class="fas fa-cloud-upload-alt fa-2x mb-3"></i><br>Drop files here or click to upload</h4>
                <p>Upload images and videos for your Instagram posts</p>
            </div>
            ${previewHtml}`;
    }
    
    // Handle upload button click
    saveUploadBtn.addEventListener('click', uploadMedia);
}

// Upload media to server
async function uploadMedia() {
    const fileInput = document.getElementById('fileInput');
    const description = document.getElementById('uploadDescription')?.value || '';
    const saveUploadBtn = document.getElementById('saveUploadMedia');
    
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        showToast('Please select files to upload', 'warning');
        return;
    }
    
    // Disable button and show loading
    if (saveUploadBtn) {
        saveUploadBtn.disabled = true;
        saveUploadBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Uploading...';
    }
    
    try {
        const files = fileInput.files;
        let successCount = 0;
        let errorCount = 0;
        
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const formData = new FormData();
            formData.append('file', file);
            formData.append('description', description);
            
            try {
                const response = await fetch('/api/media', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    successCount++;
                } else {
                    errorCount++;
                    console.error('Error uploading file:', file.name);
                }
            } catch (fileError) {
                errorCount++;
                console.error('Error uploading file:', file.name, fileError);
            }
        }
        
        // Show results
        if (successCount > 0 && errorCount === 0) {
            showToast(`Successfully uploaded ${successCount} files`, 'success');
            // Close modal and refresh media
            const uploadModal = document.getElementById('uploadMediaModal');
            if (uploadModal) {
                const bsModal = bootstrap.Modal.getInstance(uploadModal);
                if (bsModal) bsModal.hide();
            }
            loadMediaLibraryData();
        } else if (successCount > 0 && errorCount > 0) {
            showToast(`Uploaded ${successCount} files, ${errorCount} failed`, 'warning');
        } else {
            showToast('Failed to upload files', 'danger');
        }
    } catch (error) {
        console.error('Error uploading media:', error);
        showToast('Error uploading media', 'danger');
    } finally {
        // Reset button
        if (saveUploadBtn) {
            saveUploadBtn.disabled = false;
            saveUploadBtn.innerHTML = 'Upload';
        }
        
        // Reset file input
        if (fileInput) {
            fileInput.value = '';
            const dropzone = document.getElementById('dropzone');
            if (dropzone) {
                dropzone.innerHTML = `
                <div class="dropzone-message">
                    <h4><i class="fas fa-cloud-upload-alt fa-2x mb-3"></i><br>Drop files here or click to upload</h4>
                    <p>Upload images and videos for your Instagram posts</p>
                </div>`;
            }
        }
    }
}

// Show create folder modal
function showCreateFolderModal() {
    const modal = document.getElementById('createFolderModal');
    if (!modal) return;
    
    // Reset form
    const form = modal.querySelector('form');
    if (form) form.reset();
    
    // Set parent folder if a folder is selected
    const parentFolderInput = document.getElementById('folderParent');
    if (parentFolderInput && currentFolderId) {
        parentFolderInput.value = currentFolderId;
    }
    
    // Show modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

// Create a new folder
async function createFolder() {
    const folderNameInput = document.getElementById('folderName');
    const parentFolderInput = document.getElementById('folderParent');
    const saveFolderBtn = document.getElementById('saveFolder');
    
    if (!folderNameInput) {
        showToast('Folder name is required', 'warning');
        return;
    }
    
    const folderName = folderNameInput.value.trim();
    if (!folderName) {
        showToast('Folder name is required', 'warning');
        return;
    }
    
    // Disable button and show loading
    if (saveFolderBtn) {
        saveFolderBtn.disabled = true;
        saveFolderBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Creating...';
    }
    
    try {
        const data = {
            name: folderName,
            parent_id: parentFolderInput && parentFolderInput.value ? parentFolderInput.value : null
        };
        
        const response = await fetch('/api/folders', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            throw new Error('Failed to create folder');
        }
        
        const result = await response.json();
        
        // Close modal
        const modal = document.getElementById('createFolderModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
        
        // Show success message
        showToast('Folder created successfully', 'success');
        
        // Reload folders
        await loadFolders();
    } catch (error) {
        console.error('Error creating folder:', error);
        showToast('Error creating folder', 'danger');
    } finally {
        // Reset button
        if (saveFolderBtn) {
            saveFolderBtn.disabled = false;
            saveFolderBtn.innerHTML = 'Create Folder';
        }
    }
}

// Show edit folder modal
function showEditFolderModal(folderId) {
    if (!folderId) return;
    
    const folder = allFolders.find(f => f.id === folderId);
    if (!folder) {
        console.error('Folder not found:', folderId);
        return;
    }
    
    const modal = document.getElementById('editFolderModal');
    if (!modal) return;
    
    // Set folder details
    const folderIdInput = document.getElementById('editFolderId');
    const folderNameInput = document.getElementById('editFolderName');
    const parentFolderInput = document.getElementById('editFolderParent');
    
    if (folderIdInput) folderIdInput.value = folder.id;
    if (folderNameInput) folderNameInput.value = folder.name;
    if (parentFolderInput) {
        // Populate parent folder options
        let html = '<option value="">None (Root Level)</option>';
        
        // Add all folders except the current one and its children
        const childFolderIds = getChildFolderIds(folder.id);
        allFolders.forEach(f => {
            if (f.id !== folder.id && !childFolderIds.includes(f.id)) {
                html += `<option value="${f.id}" ${f.id === folder.parent_id ? 'selected' : ''}>${f.name}</option>`;
            }
        });
        
        parentFolderInput.innerHTML = html;
    }
    
    // Show modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

// Get all child folder IDs (recursive)
function getChildFolderIds(folderId) {
    const childIds = [];
    
    function addChildIds(parentId) {
        const children = allFolders.filter(f => f.parent_id === parentId);
        children.forEach(child => {
            childIds.push(child.id);
            addChildIds(child.id);
        });
    }
    
    addChildIds(folderId);
    return childIds;
}

// Update folder
async function updateFolder() {
    const folderIdInput = document.getElementById('editFolderId');
    const folderNameInput = document.getElementById('editFolderName');
    const parentFolderInput = document.getElementById('editFolderParent');
    const updateFolderBtn = document.getElementById('updateFolder');
    
    if (!folderIdInput || !folderNameInput) {
        showToast('Folder information is incomplete', 'warning');
        return;
    }
    
    const folderId = folderIdInput.value;
    const folderName = folderNameInput.value.trim();
    
    if (!folderId || !folderName) {
        showToast('Folder information is incomplete', 'warning');
        return;
    }
    
    // Disable button and show loading
    if (updateFolderBtn) {
        updateFolderBtn.disabled = true;
        updateFolderBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Updating...';
    }
    
    try {
        const data = {
            name: folderName,
            parent_id: parentFolderInput && parentFolderInput.value ? parentFolderInput.value : null
        };
        
        const response = await fetch(`/api/folders/${folderId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            throw new Error('Failed to update folder');
        }
        
        // Close modal
        const modal = document.getElementById('editFolderModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
        
        // Show success message
        showToast('Folder updated successfully', 'success');
        
        // Reload folders
        await loadFolders();
    } catch (error) {
        console.error('Error updating folder:', error);
        showToast('Error updating folder', 'danger');
    } finally {
        // Reset button
        if (updateFolderBtn) {
            updateFolderBtn.disabled = false;
            updateFolderBtn.innerHTML = 'Update Folder';
        }
    }
}

// Confirm delete folder
function confirmDeleteFolder(folderId) {
    if (!folderId) return;
    
    const folder = allFolders.find(f => f.id === folderId);
    if (!folder) {
        console.error('Folder not found:', folderId);
        return;
    }
    
    // Show confirmation dialog
    if (confirm(`Are you sure you want to delete the folder "${folder.name}"? This will not delete the media inside it.`)) {
        deleteFolder(folderId);
    }
}

// Delete folder
async function deleteFolder(folderId) {
    if (!folderId) return;
    
    try {
        const response = await fetch(`/api/folders/${folderId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            throw new Error('Failed to delete folder');
        }
        
        // Show success message
        showToast('Folder deleted successfully', 'success');
        
        // Reload folders
        await loadFolders();
        
        // If the deleted folder was the current folder, go back to all media
        if (currentFolderId === folderId) {
            selectFolder(null);
        }
    } catch (error) {
        console.error('Error deleting folder:', error);
        showToast('Error deleting folder', 'danger');
    }
}
