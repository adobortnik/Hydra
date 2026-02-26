// Caption Templates functionality for Media Library

// Load caption templates for batch scheduling
async function loadCaptionTemplates() {
    try {
        const response = await fetch('/api/caption-templates');
        if (!response.ok) {
            throw new Error('Failed to load caption templates');
        }
        
        const templates = await response.json();
        const templateSelect = document.getElementById('captionTemplateId');
        
        // Clear existing options except the first one
        while (templateSelect.options.length > 1) {
            templateSelect.remove(1);
        }
        
        // Add template options
        templates.forEach(template => {
            const option = document.createElement('option');
            option.value = template.id;
            option.textContent = template.name;
            templateSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading caption templates:', error);
        // Don't show toast for this as it's not critical
    }
}

// Handle caption template selection
function handleCaptionTemplateSelection() {
    const templateId = document.getElementById('captionTemplateId').value;
    const captionTextarea = document.getElementById('captionTemplate');
    
    if (templateId) {
        // If a template is selected, disable the custom caption textarea
        captionTextarea.placeholder = 'Using selected caption template...';
    } else {
        // If no template is selected, enable the custom caption textarea
        captionTextarea.placeholder = 'Enter caption template for all posts';
    }
}

// Initialize caption template functionality
document.addEventListener('DOMContentLoaded', function() {
    // Add event listener for template selection
    const templateSelect = document.getElementById('captionTemplateId');
    if (templateSelect) {
        templateSelect.addEventListener('change', handleCaptionTemplateSelection);
    }
    
    // Load caption templates when batch schedule modal is opened
    const batchScheduleModal = document.getElementById('batchScheduleModal');
    if (batchScheduleModal) {
        batchScheduleModal.addEventListener('show.bs.modal', loadCaptionTemplates);
    }
});
