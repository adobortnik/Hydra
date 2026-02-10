// Standalone script to update inventory statistics on the dashboard

// Load when the DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on the dashboard page
    if (document.getElementById('inventoryAccounts')) {
        console.log('Dashboard detected, loading inventory stats...');
        loadInventoryStats();
        
        // Also refresh when the refresh button is clicked
        const refreshButton = document.getElementById('refreshDashboard');
        if (refreshButton) {
            refreshButton.addEventListener('click', function() {
                console.log('Refresh button clicked, reloading inventory stats...');
                loadInventoryStats();
            });
        }
    }
});

// Load inventory statistics from API
async function loadInventoryStats() {
    try {
        // Show loading state
        if (document.getElementById('inventoryAccounts')) {
            document.getElementById('inventoryAccounts').innerHTML = '<div class="spinner-border spinner-border-sm text-light" role="status"></div>';
        }
        
        // Fetch inventory data
        console.log('Fetching inventory stats from API...');
        const response = await fetch('/api/inventory/stats');
        if (!response.ok) {
            throw new Error(`Failed to load inventory data: ${response.status} ${response.statusText}`);
        }
        
        const stats = await response.json();
        console.log('Inventory stats loaded:', stats);
        
        // Update the dashboard
        updateInventoryStats(stats);
    } catch (error) {
        console.error('Error loading inventory stats:', error);
        
        // Show error state
        if (document.getElementById('inventoryAccounts')) {
            document.getElementById('inventoryAccounts').textContent = '?';
        }
    }
}

// Update inventory statistics on the dashboard
function updateInventoryStats(stats) {
    console.log('Updating inventory stats on dashboard...');
    
    // Main inventory accounts card
    const inventoryElement = document.getElementById('inventoryAccounts');
    if (inventoryElement) {
        console.log(`Setting inventoryAccounts to ${stats.total}`);
        inventoryElement.textContent = stats.total || 0;
    } else {
        console.warn('inventoryAccounts element not found');
    }
    
    // Detailed stats
    updateElement('availableAccounts', stats.available || 0);
    updateElement('usedAccounts', stats.used || 0);
    updateElement('recentlyAddedAccounts', stats.recently_added || 0);
    updateElement('recentlyUsedAccounts', stats.recently_used || 0);
}

// Helper function to update an element if it exists
function updateElement(id, value) {
    const element = document.getElementById(id);
    if (element) {
        console.log(`Setting ${id} to ${value}`);
        element.textContent = value;
    } else {
        console.warn(`${id} element not found`);
    }
}
