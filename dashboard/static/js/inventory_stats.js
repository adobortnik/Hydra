// Account Inventory Statistics for Dashboard

// Load inventory statistics when the page loads
document.addEventListener('DOMContentLoaded', function() {
    loadInventoryStats();
    
    // Refresh stats when dashboard is refreshed
    const refreshButton = document.getElementById('refreshDashboard');
    if (refreshButton) {
        refreshButton.addEventListener('click', loadInventoryStats);
    }
});

// Load inventory statistics from API
async function loadInventoryStats() {
    try {
        const response = await fetch('/api/inventory/stats');
        if (!response.ok) throw new Error('Failed to load inventory statistics');
        
        const stats = await response.json();
        
        // Update the dashboard stats
        updateInventoryStats(stats);
    } catch (error) {
        console.error('Error loading inventory statistics:', error);
    }
}

// Update inventory statistics on the dashboard
function updateInventoryStats(stats) {
    // Update main stats card
    const inventoryAccountsElement = document.getElementById('inventoryAccounts');
    if (inventoryAccountsElement) {
        inventoryAccountsElement.textContent = stats.total || 0;
    }
    
    // Update detailed stats
    const availableAccountsElement = document.getElementById('availableAccounts');
    if (availableAccountsElement) {
        availableAccountsElement.textContent = stats.available || 0;
    }
    
    const usedAccountsElement = document.getElementById('usedAccounts');
    if (usedAccountsElement) {
        usedAccountsElement.textContent = stats.used || 0;
    }
    
    const recentlyAddedAccountsElement = document.getElementById('recentlyAddedAccounts');
    if (recentlyAddedAccountsElement) {
        recentlyAddedAccountsElement.textContent = stats.recently_added || 0;
    }
    
    const recentlyUsedAccountsElement = document.getElementById('recentlyUsedAccounts');
    if (recentlyUsedAccountsElement) {
        recentlyUsedAccountsElement.textContent = stats.recently_used || 0;
    }
}
