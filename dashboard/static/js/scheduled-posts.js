// Scheduled Posts functionality for The Live House

// Global variables
let allScheduledPosts = [];
let allAccounts = [];
let currentSortColumn = 0;
let currentSortDirection = 'asc';

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Load initial data
    loadScheduledPostsData();
    
    // Set up event listeners
    document.getElementById('refreshScheduledPosts').addEventListener('click', loadScheduledPostsData);
    document.getElementById('postSearch').addEventListener('input', filterScheduledPosts);
    document.getElementById('statusFilter').addEventListener('change', filterScheduledPosts);
    document.getElementById('accountFilter').addEventListener('change', filterScheduledPosts);
    document.getElementById('addScheduledPost').addEventListener('click', showAddPostModal);
    document.getElementById('saveScheduledPost').addEventListener('click', saveScheduledPost);
    document.getElementById('saveBulkSettings').addEventListener('click', saveBulkSettings);
    
    // Add event listeners for select all and delete selected functionality
    document.getElementById('selectAllPosts').addEventListener('click', toggleSelectAllPosts);
    document.getElementById('selectAllCheckbox').addEventListener('change', toggleSelectAllCheckboxes);
    document.getElementById('deleteSelectedPosts').addEventListener('click', deleteSelectedPosts);
    
    // Set today's date as default for new posts
    const today = new Date();
    const formattedDate = today.toISOString().split('T')[0];
    document.getElementById('postDate').value = formattedDate;
    
    // Set a reasonable default time (1 hour from now)
    const nextHour = new Date(today.getTime() + 60 * 60 * 1000);
    const hours = String(nextHour.getHours()).padStart(2, '0');
    const minutes = String(nextHour.getMinutes()).padStart(2, '0');
    document.getElementById('postTime').value = `${hours}:${minutes}`;
});

// Load all scheduled posts data
async function loadScheduledPostsData() {
    try {
        // Show loading state
        document.getElementById('scheduledPostsTableBody').innerHTML = '<tr><td colspan="7" class="text-center"><div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>Loading scheduled posts...</td></tr>';
        
        // Load accounts first (needed for filters and dropdowns)
        await loadAccounts();
        
        // Then load scheduled posts
        await loadScheduledPosts();
        
        // Initial filtering and sorting
        filterScheduledPosts();
    } catch (error) {
        handleApiError(error);
        document.getElementById('scheduledPostsTableBody').innerHTML = '<tr><td colspan="7" class="text-center text-danger">Error loading data. Please try again.</td></tr>';
    }
}

// Load accounts from API
async function loadAccounts() {
    try {
        const response = await fetch('/api/accounts');
        if (!response.ok) throw new Error('Failed to load accounts');
        
        allAccounts = await response.json();
        
        // Populate account filter dropdown
        const accountFilter = document.getElementById('accountFilter');
        const postAccounts = document.getElementById('postAccounts');
        const bulkAccounts = document.getElementById('bulkAccounts');
        
        // Clear existing options except the first one in the filter
        while (accountFilter.options.length > 1) {
            accountFilter.remove(1);
        }
        
        // Clear all options in the post modal and bulk settings modal
        postAccounts.innerHTML = '';
        bulkAccounts.innerHTML = '';
        
        // Add account options
        allAccounts.forEach(account => {
            // For the filter dropdown
            const filterOption = document.createElement('option');
            filterOption.value = account.account;
            filterOption.textContent = `${account.account} (${account.devicename})`;
            accountFilter.appendChild(filterOption);
            
            // For the post modal dropdown
            const postOption = document.createElement('option');
            postOption.value = JSON.stringify({deviceid: account.deviceid, account: account.account});
            postOption.textContent = `${account.account} (${account.devicename})`;
            postAccounts.appendChild(postOption);
            
            // For the bulk settings modal dropdown
            const bulkOption = document.createElement('option');
            bulkOption.value = JSON.stringify({deviceid: account.deviceid, account: account.account});
            bulkOption.textContent = `${account.account} (${account.devicename})`;
            bulkAccounts.appendChild(bulkOption);
        });
    } catch (error) {
        handleApiError(error);
        throw error; // Re-throw to handle in the calling function
    }
}

// Load scheduled posts from API
async function loadScheduledPosts() {
    try {
        const response = await fetch('/api/scheduled_posts');
        if (!response.ok) throw new Error('Failed to load scheduled posts');
        
        allScheduledPosts = await response.json();
    } catch (error) {
        handleApiError(error);
        throw error; // Re-throw to handle in the calling function
    }
}

// Filter scheduled posts based on search and filters
function filterScheduledPosts() {
    const searchTerm = document.getElementById('postSearch').value.toLowerCase();
    const statusFilter = document.getElementById('statusFilter').value;
    const accountFilter = document.getElementById('accountFilter').value;
    
    // Filter posts based on criteria
    const filteredPosts = allScheduledPosts.filter(post => {
        const matchesSearch = post.caption.toLowerCase().includes(searchTerm);
        const matchesStatus = statusFilter === '' || post.status === statusFilter;
        const matchesAccount = accountFilter === '' || post.account === accountFilter;
        return matchesSearch && matchesStatus && matchesAccount;
    });
    
    // Sort the filtered posts
    sortScheduledPosts(filteredPosts);
    
    // Render the filtered and sorted posts
    renderScheduledPosts(filteredPosts);
}

// Sort scheduled posts by the specified column
function sortPostsTable(columnIndex) {
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
    filterScheduledPosts();
}

// Update sort indicator icons in the table header
function updateSortIndicators() {
    const headers = document.querySelectorAll('#scheduledPostsTable th');
    
    headers.forEach((header, index) => {
        const icon = header.querySelector('i');
        if (!icon) return;
        
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

// Sort the scheduled posts array based on current sort settings
function sortScheduledPosts(posts) {
    posts.sort((a, b) => {
        let valueA, valueB;
        
        // Extract values based on column index
        switch (currentSortColumn) {
            case 0: // Date/Time
                valueA = new Date(a.scheduled_time);
                valueB = new Date(b.scheduled_time);
                break;
            case 1: // Account
                valueA = a.account;
                valueB = b.account;
                break;
            case 3: // Type
                valueA = a.post_type;
                valueB = b.post_type;
                break;
            case 4: // Status
                valueA = a.status;
                valueB = b.status;
                break;
            default:
                valueA = new Date(a.scheduled_time);
                valueB = new Date(b.scheduled_time);
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

// Render scheduled posts to the table
function renderScheduledPosts(posts) {
    const tableBody = document.getElementById('scheduledPostsTableBody');
    
    // Clear existing rows
    tableBody.innerHTML = '';
    
    // If no posts, show message
    if (posts.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="7" class="text-center">No scheduled posts found matching your criteria</td></tr>';
        return;
    }
    
    // Add each post to the table
    posts.forEach(post => {
        const row = document.createElement('tr');
        
        // Format date and time
        const postDate = new Date(post.scheduled_time);
        const formattedDate = postDate.toLocaleDateString();
        const formattedTime = postDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        
        // Create media preview if available
        let mediaPreview = '';
        if (post.media_path) {
            // Fix the media URL path to handle both central and account-specific media
            let mediaUrl;
            if (post.media_path.startsWith('/api/accounts/')) {
                // This is an account-specific media path, use it directly
                mediaUrl = post.media_path;
                console.log('Using account-specific media path:', mediaUrl);
            } else {
                // This is a central media path, use the scheduled_posts media endpoint
                // Extract just the filename without any path
                const filename = post.media_path.split('/').pop();
                mediaUrl = `/api/scheduled_posts/${filename}`;
                console.log('Using central media path:', mediaUrl);
            }
            
            const isImage = post.media_path.match(/\.(jpg|jpeg|png|gif)$/i);
            const isVideo = post.media_path.match(/\.(mp4|mov|avi)$/i);
            
            if (isImage) {
                mediaPreview = `
                <div class="media-preview mb-2">
                    <img src="${mediaUrl}" alt="Post media" class="img-thumbnail" style="max-width: 100px; max-height: 100px;">
                </div>`;
            } else if (isVideo) {
                mediaPreview = `
                <div class="media-preview mb-2">
                    <video src="${mediaUrl}" class="img-thumbnail" style="max-width: 100px; max-height: 100px;"></video>
                </div>`;
            }
        }
        
        // Create cells
        row.innerHTML = `
            <td class="text-center">
                <div class="form-check">
                    <input class="form-check-input post-checkbox" type="checkbox" value="${post.id}" data-post-id="${post.id}">
                </div>
            </td>
            <td>
                <div class="d-flex align-items-center">
                    <div class="icon-square bg-primary text-white me-3">
                        <i class="fas fa-calendar-alt"></i>
                    </div>
                    <div>
                        <div>${formattedDate}</div>
                        <small class="text-white-50">${formattedTime}</small>
                    </div>
                </div>
            </td>
            <td>
                <div class="d-flex align-items-center">
                    <div class="avatar-sm me-3">
                        <img src="https://ui-avatars.com/api/?name=${post.account}&background=random&color=fff" alt="${post.account}" class="rounded-circle">
                    </div>
                    <span>${post.account}</span>
                </div>
            </td>
            <td>
                ${mediaPreview}
                <div class="caption-preview">${post.caption.substring(0, 50)}${post.caption.length > 50 ? '...' : ''}</div>
            </td>
            <td>
                <span class="badge bg-${getPostTypeBadgeColor(post.post_type)}">${post.post_type}</span>
            </td>
            <td>
                <span class="badge bg-${getStatusBadgeColor(post.status)}">${post.status}</span>
            </td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-sm btn-outline-primary" onclick="editScheduledPost('${post.id}')" data-bs-toggle="tooltip" title="Edit Post">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteScheduledPost('${post.id}')" data-bs-toggle="tooltip" title="Delete Post">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        `;
        
        tableBody.appendChild(row);
    });
    
    // Add event listeners to checkboxes
    addCheckboxEventListeners();
    
    // Initialize tooltips
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(tooltip => new bootstrap.Tooltip(tooltip));
}

// Get badge color for post type
function getPostTypeBadgeColor(type) {
    switch (type.toLowerCase()) {
        case 'post': return 'primary';
        case 'story': return 'info';
        case 'reel': return 'purple';
        default: return 'secondary';
    }
}

// Get badge color for status
function getStatusBadgeColor(status) {
    switch (status.toLowerCase()) {
        case 'scheduled': return 'warning';
        case 'published': return 'success';
        case 'failed': return 'danger';
        default: return 'secondary';
    }
}

// Show modal for adding a new post
function showAddPostModal() {
    // Reset form
    document.getElementById('scheduledPostForm').reset();
    document.getElementById('postId').value = '';
    document.getElementById('scheduledPostModalTitle').textContent = 'Add Scheduled Post';
    
    // Set today's date as default
    const today = new Date();
    const formattedDate = today.toISOString().split('T')[0];
    document.getElementById('postDate').value = formattedDate;
    
    // Set a reasonable default time (1 hour from now)
    const nextHour = new Date(today.getTime() + 60 * 60 * 1000);
    const hours = String(nextHour.getHours()).padStart(2, '0');
    const minutes = String(nextHour.getMinutes()).padStart(2, '0');
    document.getElementById('postTime').value = `${hours}:${minutes}`;
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('scheduledPostModal'));
    modal.show();
}

// Edit an existing scheduled post
async function editScheduledPost(postId) {
    try {
        // Get post details
        const response = await fetch(`/api/scheduled_posts/${postId}`);
        if (!response.ok) throw new Error('Failed to load post details');
        
        const post = await response.json();
        
        // Set form values
        document.getElementById('postId').value = post.id;
        document.getElementById('scheduledPostModalTitle').textContent = 'Edit Scheduled Post';
        
        // Set selected account
        const postAccounts = document.getElementById('postAccounts');
        for (let i = 0; i < postAccounts.options.length; i++) {
            const option = postAccounts.options[i];
            const accountData = JSON.parse(option.value);
            if (accountData.account === post.account && accountData.deviceid === post.deviceid) {
                option.selected = true;
                break;
            }
        }
        
        // Set other form fields
        document.getElementById('postType').value = post.post_type;
        document.getElementById('postCaption').value = post.caption;
        document.getElementById('postLocation').value = post.location || '';
        
        // Set date and time
        const postDate = new Date(post.scheduled_time);
        document.getElementById('postDate').value = postDate.toISOString().split('T')[0];
        
        const hours = String(postDate.getHours()).padStart(2, '0');
        const minutes = String(postDate.getMinutes()).padStart(2, '0');
        document.getElementById('postTime').value = `${hours}:${minutes}`;
        
        // Show media preview if available
        const mediaPreviewContainer = document.getElementById('mediaPreviewContainer');
        if (mediaPreviewContainer) {
            if (post.media_path) {
                // Fix the media URL path to handle both central and account-specific media
                let mediaUrl;
                if (post.media_path.startsWith('/api/accounts/')) {
                    // This is an account-specific media path, use it directly
                    mediaUrl = post.media_path;
                    console.log('Using account-specific media path:', mediaUrl);
                } else {
                    // This is a central media path, use the scheduled_posts media endpoint
                    // Extract just the filename without any path
                    const filename = post.media_path.split('/').pop();
                    mediaUrl = `/api/scheduled_posts/${filename}`;
                    console.log('Using central media path:', mediaUrl);
                }
                
                const isImage = post.media_path.match(/\.(jpg|jpeg|png|gif)$/i);
                const isVideo = post.media_path.match(/\.(mp4|mov|avi)$/i);
                
                let previewHtml = '';
                if (isImage) {
                    previewHtml = `
                    <div class="mb-3">
                        <label class="form-label">Current Media</label>
                        <div class="d-block">
                            <img src="${mediaUrl}" alt="Post media" class="img-thumbnail mb-3" style="max-width: 200px; max-height: 200px;">
                        </div>
                        <div class="form-text text-white-50">Upload a new file below to replace this media</div>
                    </div>
                    `;
                } else if (isVideo) {
                    previewHtml = `
                    <div class="mb-3">
                        <label class="form-label">Current Media</label>
                        <div class="d-block">
                            <video src="${mediaUrl}" controls class="img-thumbnail mb-3" style="max-width: 200px; max-height: 200px;"></video>
                        </div>
                        <div class="form-text text-white-50">Upload a new file below to replace this media</div>
                    </div>
                    `;
                }
                
                mediaPreviewContainer.innerHTML = previewHtml;
                mediaPreviewContainer.classList.remove('d-none');
            } else {
                mediaPreviewContainer.innerHTML = '';
                mediaPreviewContainer.classList.add('d-none');
            }
        }
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('scheduledPostModal'));
        modal.show();
    } catch (error) {
        handleApiError(error);
    }
}

// Save scheduled post
async function saveScheduledPost() {
    try {
        // Get form values
        const postId = document.getElementById('postId').value;
        const postAccountsSelect = document.getElementById('postAccounts');
        const selectedAccounts = Array.from(postAccountsSelect.selectedOptions).map(option => JSON.parse(option.value));
        
        if (selectedAccounts.length === 0) {
            showToast('Please select at least one account', 'danger');
            return;
        }
        
        const postType = document.getElementById('postType').value;
        const caption = document.getElementById('postCaption').value;
        const location = document.getElementById('postLocation').value;
        const date = document.getElementById('postDate').value;
        const time = document.getElementById('postTime').value;
        
        if (!date || !time) {
            showToast('Please select date and time', 'danger');
            return;
        }
        
        // Combine date and time
        const scheduledTime = new Date(`${date}T${time}`);
        
        // Get media file
        const mediaInput = document.getElementById('postMedia');
        const mediaFile = mediaInput.files[0];
        
        // Create FormData for file upload
        const formData = new FormData();
        
        if (postId) {
            formData.append('id', postId);
        }
        
        // Add accounts data
        formData.append('accounts', JSON.stringify(selectedAccounts));
        formData.append('post_type', postType);
        formData.append('caption', caption);
        formData.append('location', location);
        formData.append('scheduled_time', scheduledTime.toISOString());
        
        if (mediaFile) {
            formData.append('media', mediaFile);
        }
        
        // Send request
        const url = postId ? `/api/scheduled_posts/${postId}` : '/api/scheduled_posts';
        const method = postId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message || 'Failed to save scheduled post');
        }
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('scheduledPostModal'));
        modal.hide();
        
        // Reload data
        loadScheduledPostsData();
        
        // Show success message
        showToast(postId ? 'Post updated successfully' : 'Post scheduled successfully', 'success');
    } catch (error) {
        handleApiError(error);
    }
}

// Delete a scheduled post
async function deleteScheduledPost(postId) {
    if (!confirm('Are you sure you want to delete this scheduled post?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/scheduled_posts/${postId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message || 'Failed to delete scheduled post');
        }
        
        // Reload data
        loadScheduledPostsData();
        
        // Show success message
        showToast('Post deleted successfully', 'success');
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
        
        // Send request for each account
        const updatePromises = selectedAccounts.map(account => {
            return fetch(`/api/accounts/${account.deviceid}/${account.account}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });
        });
        
        // Wait for all updates to complete
        const results = await Promise.all(updatePromises);
        
        // Check if any failed
        const failedCount = results.filter(response => !response.ok).length;
        
        if (failedCount > 0) {
            showToast(`Failed to update ${failedCount} accounts`, 'warning');
        } else {
            showToast(`Successfully updated ${selectedAccounts.length} accounts`, 'success');
        }
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('bulkSettingsModal'));
        modal.hide();
        
        // Reload accounts data
        loadScheduledPostsData();
    } catch (error) {
        handleApiError(error);
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    
    const toastElement = document.createElement('div');
    toastElement.className = `toast align-items-center text-white bg-${type} border-0`;
    toastElement.setAttribute('role', 'alert');
    toastElement.setAttribute('aria-live', 'assertive');
    toastElement.setAttribute('aria-atomic', 'true');
    
    toastElement.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    toastContainer.appendChild(toastElement);
    
    const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
    toast.show();
    
    // Remove toast from DOM after it's hidden
    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}

// Handle API errors
function handleApiError(error) {
    console.error('API Error:', error);
    showToast(error.message || 'An error occurred', 'danger');
}

// Add event listeners to checkboxes
function addCheckboxEventListeners() {
    const checkboxes = document.querySelectorAll('.post-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const postId = this.getAttribute('data-post-id');
            const isChecked = this.checked;
            
            // Toggle select all checkbox
            const selectAllCheckbox = document.getElementById('selectAllCheckbox');
            if (isChecked) {
                selectAllCheckbox.indeterminate = true;
            } else {
                selectAllCheckbox.indeterminate = false;
            }
            
            // Update delete selected button
            const deleteSelectedButton = document.getElementById('deleteSelectedPosts');
            const selectedPosts = Array.from(checkboxes).filter(checkbox => checkbox.checked).map(checkbox => checkbox.getAttribute('data-post-id'));
            if (selectedPosts.length > 0) {
                deleteSelectedButton.disabled = false;
                deleteSelectedButton.textContent = `Delete Selected (${selectedPosts.length})`;
            } else {
                deleteSelectedButton.disabled = true;
                deleteSelectedButton.textContent = 'Delete Selected';
            }
        });
    });
}

// Toggle select all checkboxes
function toggleSelectAllCheckboxes() {
    const checkboxes = document.querySelectorAll('.post-checkbox');
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const isChecked = selectAllCheckbox.checked;
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = isChecked;
    });
    
    // Update delete selected button
    const deleteSelectedButton = document.getElementById('deleteSelectedPosts');
    const selectedPosts = Array.from(checkboxes).filter(checkbox => checkbox.checked).map(checkbox => checkbox.getAttribute('data-post-id'));
    if (selectedPosts.length > 0) {
        deleteSelectedButton.disabled = false;
        deleteSelectedButton.textContent = `Delete Selected (${selectedPosts.length})`;
    } else {
        deleteSelectedButton.disabled = true;
        deleteSelectedButton.textContent = 'Delete Selected';
    }
}

// Toggle select all posts
function toggleSelectAllPosts() {
    const checkboxes = document.querySelectorAll('.post-checkbox');
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const isChecked = selectAllCheckbox.checked;
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = isChecked;
    });
    
    // Update delete selected button
    const deleteSelectedButton = document.getElementById('deleteSelectedPosts');
    const selectedPosts = Array.from(checkboxes).filter(checkbox => checkbox.checked).map(checkbox => checkbox.getAttribute('data-post-id'));
    if (selectedPosts.length > 0) {
        deleteSelectedButton.disabled = false;
        deleteSelectedButton.textContent = `Delete Selected (${selectedPosts.length})`;
    } else {
        deleteSelectedButton.disabled = true;
        deleteSelectedButton.textContent = 'Delete Selected';
    }
}

// Delete selected posts
async function deleteSelectedPosts() {
    const checkboxes = document.querySelectorAll('.post-checkbox');
    const selectedPosts = Array.from(checkboxes).filter(checkbox => checkbox.checked).map(checkbox => checkbox.getAttribute('data-post-id'));
    
    if (selectedPosts.length === 0) {
        showToast('No posts selected for deletion', 'warning');
        return;
    }
    
    if (!confirm(`Are you sure you want to delete ${selectedPosts.length} scheduled posts?`)) {
        return;
    }
    
    // Show loading state
    const deleteButton = document.getElementById('deleteSelectedPosts');
    const originalButtonText = deleteButton.innerHTML;
    deleteButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Deleting...';
    deleteButton.disabled = true;
    
    try {
        // Process deletions one by one to avoid overwhelming the server
        let successCount = 0;
        let failedCount = 0;
        
        for (const postId of selectedPosts) {
            try {
                const response = await fetch(`/api/scheduled_posts/${postId}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    successCount++;
                } else {
                    failedCount++;
                    console.error(`Failed to delete post ${postId}:`, await response.text());
                }
            } catch (error) {
                failedCount++;
                console.error(`Error deleting post ${postId}:`, error);
            }
            
            // Update progress in the button text
            const progress = Math.round(((successCount + failedCount) / selectedPosts.length) * 100);
            deleteButton.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status"></span>Deleting... ${progress}%`;
        }
        
        // Show results
        if (failedCount > 0) {
            showToast(`Deleted ${successCount} posts, but failed to delete ${failedCount} posts`, 'warning');
        } else {
            showToast(`Successfully deleted ${successCount} posts`, 'success');
        }
        
        // Reload data
        loadScheduledPostsData();
    } catch (error) {
        handleApiError(error);
    } finally {
        // Restore button state
        deleteButton.innerHTML = originalButtonText;
        deleteButton.disabled = false;
    }
}
