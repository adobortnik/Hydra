// Caption Templates functionality for The Live House

// Global variables
let allCaptionTemplates = [];

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Load initial data
    loadCaptionTemplates();
    
    // Set up event listeners
    document.getElementById('addCaptionTemplate').addEventListener('click', showAddTemplateModal);
    document.getElementById('saveCaptionTemplate').addEventListener('click', saveCaptionTemplate);
    document.getElementById('confirmDeleteTemplate').addEventListener('click', deleteTemplate);
});

// Load all caption templates
async function loadCaptionTemplates() {
    try {
        // Show loading state
        document.getElementById('captionTemplatesTableBody').innerHTML = '<tr><td colspan="5" class="text-center"><div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>Loading caption templates...</td></tr>';
        
        // Fetch templates
        const response = await fetch('/api/caption-templates');
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to load caption templates');
        }
        
        allCaptionTemplates = await response.json();
        
        // Render templates
        renderCaptionTemplates();
    } catch (error) {
        console.error('Error loading caption templates:', error);
        document.getElementById('captionTemplatesTableBody').innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error loading data. Please try again.</td></tr>';
        showToast(error.message || 'Error loading caption templates', 'danger');
    }
}

// Render caption templates to the table
function renderCaptionTemplates() {
    const tableBody = document.getElementById('captionTemplatesTableBody');
    
    // Clear existing rows
    tableBody.innerHTML = '';
    
    // If no templates, show message
    if (allCaptionTemplates.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="5" class="text-center">No caption templates found. Click "New Template" to create one.</td></tr>';
        return;
    }
    
    // Add each template to the table
    allCaptionTemplates.forEach(template => {
        const row = document.createElement('tr');
        
        // Format date
        const createdDate = new Date(template.created_at);
        const formattedDate = createdDate.toLocaleDateString();
        
        // Create cells
        row.innerHTML = `
            <td>
                <div class="d-flex align-items-center">
                    <div class="icon-square bg-primary text-white me-3">
                        <i class="fas fa-comment-alt"></i>
                    </div>
                    <span class="fw-bold">${template.name}</span>
                </div>
            </td>
            <td>${template.description || '-'}</td>
            <td>
                <span class="badge bg-info">${template.caption_count} captions</span>
                <button class="btn btn-sm btn-link text-info" onclick="viewCaptions('${template.id}')">View</button>
            </td>
            <td>${formattedDate}</td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-sm btn-outline-primary" onclick="editTemplate('${template.id}')" data-bs-toggle="tooltip" title="Edit Template">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="showDeleteModal('${template.id}', '${template.name}')" data-bs-toggle="tooltip" title="Delete Template">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        `;
        
        tableBody.appendChild(row);
    });
    
    // Initialize tooltips
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(tooltip => new bootstrap.Tooltip(tooltip));
}

// Show modal for adding a new template
function showAddTemplateModal() {
    // Reset form
    document.getElementById('captionTemplateForm').reset();
    document.getElementById('templateId').value = '';
    document.getElementById('captionTemplateModalTitle').textContent = 'Add Caption Template';
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('captionTemplateModal'));
    modal.show();
}

// Edit an existing template
async function editTemplate(templateId) {
    try {
        // Show loading state
        document.getElementById('captionTemplateModalTitle').textContent = 'Loading...';
        document.getElementById('templateName').disabled = true;
        document.getElementById('templateDescription').disabled = true;
        document.getElementById('templateCaptions').disabled = true;
        document.getElementById('saveCaptionTemplate').disabled = true;
        
        // Fetch template details
        const response = await fetch(`/api/caption-templates/${templateId}`);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to load template details');
        }
        
        const template = await response.json();
        
        // Populate form
        document.getElementById('templateId').value = template.id;
        document.getElementById('templateName').value = template.name;
        document.getElementById('templateDescription').value = template.description || '';
        
        // Combine captions into a single string with each caption on a new line
        const captionsText = template.captions.map(caption => caption.caption).join('\n');
        document.getElementById('templateCaptions').value = captionsText;
        
        // Reset form state
        document.getElementById('templateName').disabled = false;
        document.getElementById('templateDescription').disabled = false;
        document.getElementById('templateCaptions').disabled = false;
        document.getElementById('saveCaptionTemplate').disabled = false;
        
        // Update modal title
        document.getElementById('captionTemplateModalTitle').textContent = 'Edit Caption Template';
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('captionTemplateModal'));
        modal.show();
    } catch (error) {
        console.error('Error loading template details:', error);
        showToast(error.message || 'Error loading template details', 'danger');
    }
}

// Save caption template
async function saveCaptionTemplate() {
    try {
        // Get form data
        const templateId = document.getElementById('templateId').value;
        const name = document.getElementById('templateName').value;
        const description = document.getElementById('templateDescription').value;
        const captions = document.getElementById('templateCaptions').value;
        
        // Validate form
        if (!name) {
            showToast('Template name is required', 'warning');
            return;
        }
        
        if (!captions) {
            showToast('At least one caption is required', 'warning');
            return;
        }
        
        // Show loading state
        const saveButton = document.getElementById('saveCaptionTemplate');
        const originalText = saveButton.textContent;
        saveButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
        saveButton.disabled = true;
        
        // Prepare data
        const templateData = {
            name: name,
            description: description,
            captions: captions
        };
        
        // Send API request (POST for new, PUT for update)
        const url = templateId ? `/api/caption-templates/${templateId}` : '/api/caption-templates';
        const method = templateId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(templateData)
        });
        
        // Reset button state
        saveButton.textContent = originalText;
        saveButton.disabled = false;
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to save template');
        }
        
        const result = await response.json();
        
        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('captionTemplateModal')).hide();
        
        // Reload data
        loadCaptionTemplates();
        
        // Show success message
        showToast(templateId ? 'Template updated successfully' : 'Template created successfully', 'success');
    } catch (error) {
        console.error('Error saving template:', error);
        showToast(error.message || 'Error saving template', 'danger');
    }
}

// Show delete confirmation modal
function showDeleteModal(templateId, templateName) {
    document.getElementById('deleteTemplateId').value = templateId;
    document.getElementById('deleteTemplateName').textContent = templateName;
    
    const modal = new bootstrap.Modal(document.getElementById('deleteTemplateModal'));
    modal.show();
}

// Delete a template
async function deleteTemplate() {
    try {
        const templateId = document.getElementById('deleteTemplateId').value;
        
        // Show loading state
        const deleteButton = document.getElementById('confirmDeleteTemplate');
        const originalText = deleteButton.textContent;
        deleteButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Deleting...';
        deleteButton.disabled = true;
        
        // Send API request
        const response = await fetch(`/api/caption-templates/${templateId}`, {
            method: 'DELETE'
        });
        
        // Reset button state
        deleteButton.textContent = originalText;
        deleteButton.disabled = false;
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to delete template');
        }
        
        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('deleteTemplateModal')).hide();
        
        // Reload data
        loadCaptionTemplates();
        
        // Show success message
        showToast('Template deleted successfully', 'success');
    } catch (error) {
        console.error('Error deleting template:', error);
        showToast(error.message || 'Error deleting template', 'danger');
    }
}

// View captions in a template
async function viewCaptions(templateId) {
    try {
        // Show loading state
        document.getElementById('captionsList').innerHTML = '<div class="d-flex justify-content-center"><div class="spinner-border text-primary" role="status"></div></div>';
        
        // Fetch template details
        const response = await fetch(`/api/caption-templates/${templateId}`);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to load captions');
        }
        
        const template = await response.json();
        
        // Update modal title
        document.getElementById('viewCaptionsModalTitle').textContent = `Captions for ${template.name}`;
        
        // Populate captions list
        const captionsList = document.getElementById('captionsList');
        captionsList.innerHTML = '';
        
        if (template.captions && template.captions.length > 0) {
            template.captions.forEach((caption, index) => {
                const captionItem = document.createElement('div');
                captionItem.className = 'list-group-item bg-dark text-white border-secondary';
                captionItem.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <span class="badge bg-secondary me-2">${index + 1}</span>
                            ${caption.caption}
                        </div>
                    </div>
                `;
                captionsList.appendChild(captionItem);
            });
        } else {
            captionsList.innerHTML = '<div class="text-center text-muted">No captions found</div>';
        }
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('viewCaptionsModal'));
        modal.show();
    } catch (error) {
        console.error('Error loading captions:', error);
        showToast(error.message || 'Error loading captions', 'danger');
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();
    
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    const bsToast = new bootstrap.Toast(toast, {
        autohide: true,
        delay: 5000
    });
    
    bsToast.show();
    
    // Remove toast from DOM after it's hidden
    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });
}

// Create toast container if it doesn't exist
function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '1050';
    document.body.appendChild(container);
    return container;
}
