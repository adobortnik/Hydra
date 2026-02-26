// Dashboard Charts JavaScript for The Live House

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Load dashboard data
    loadDashboardData();
    
    // Set up event listeners
    document.getElementById('refreshDashboard').addEventListener('click', loadDashboardData);
});

// Load dashboard data from API
async function loadDashboardData() {
    try {
        // Show loading state
        document.getElementById('totalDevices').innerHTML = '<div class="spinner-border spinner-border-sm text-primary" role="status"></div>';
        document.getElementById('totalAccounts').innerHTML = '<div class="spinner-border spinner-border-sm text-primary" role="status"></div>';
        document.getElementById('activeAccounts').innerHTML = '<div class="spinner-border spinner-border-sm text-primary" role="status"></div>';
        
        if (document.getElementById('inventoryAccounts')) {
            document.getElementById('inventoryAccounts').innerHTML = '<div class="spinner-border spinner-border-sm text-primary" role="status"></div>';
        }
        
        // Fetch dashboard stats
        const response = await fetch('/api/dashboard/stats');
        if (!response.ok) throw new Error('Failed to load dashboard data');
        
        const stats = await response.json();
        
        // Update stats cards
        updateStatsCards(stats);
        
        // Create charts
        createDeviceChart(stats);
        createSettingsChart(stats);
        
        // Load recent activity
        loadRecentActivity();
        
        // Also load inventory stats separately
        await loadInventoryStats();
    } catch (error) {
        handleApiError(error);
    }
}

// Update stats cards with data
function updateStatsCards(stats) {
    document.getElementById('totalDevices').textContent = stats.total_devices || 0;
    document.getElementById('totalAccounts').textContent = stats.total_accounts || 0;
    document.getElementById('activeAccounts').textContent = stats.active_accounts || 0;
}

// Create device distribution chart
function createDeviceChart(stats) {
    const ctx = document.getElementById('deviceChart').getContext('2d');
    
    // Extract data for chart
    const deviceData = stats.accounts_by_device;
    const labels = [];
    const data = [];
    const backgroundColors = [];
    
    // Generate colors based on number of devices
    const colorPalette = [
        'rgba(137, 100, 255, 0.8)',
        'rgba(100, 181, 246, 0.8)',
        'rgba(255, 145, 0, 0.8)',
        'rgba(76, 175, 80, 0.8)',
        'rgba(244, 67, 54, 0.8)',
        'rgba(156, 39, 176, 0.8)',
        'rgba(255, 193, 7, 0.8)',
        'rgba(0, 188, 212, 0.8)'
    ];
    
    let i = 0;
    for (const deviceId in deviceData) {
        labels.push(deviceData[deviceId].name || deviceId);
        data.push(deviceData[deviceId].count);
        backgroundColors.push(colorPalette[i % colorPalette.length]);
        i++;
    }
    
    // Destroy existing chart if it exists
    if (window.deviceChart instanceof Chart) {
        window.deviceChart.destroy();
    }
    
    // Create new chart
    window.deviceChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: backgroundColors,
                borderColor: 'rgba(30, 30, 30, 1)',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: 'rgba(255, 255, 255, 0.87)',
                        font: {
                            family: "'Inter', sans-serif",
                            size: 12
                        },
                        padding: 20
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(30, 30, 30, 0.9)',
                    titleColor: 'rgba(255, 255, 255, 0.87)',
                    bodyColor: 'rgba(255, 255, 255, 0.87)',
                    bodyFont: {
                        family: "'Inter', sans-serif"
                    },
                    titleFont: {
                        family: "'Inter', sans-serif",
                        weight: 'bold'
                    },
                    padding: 15,
                    boxPadding: 10,
                    cornerRadius: 8,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.raw || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${label}: ${value} accounts (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Create settings distribution chart
function createSettingsChart(stats) {
    const ctx = document.getElementById('settingsChart').getContext('2d');
    
    // Extract data for chart
    const labels = ['Follow Enabled', 'Unfollow Enabled'];
    const data = [stats.follow_enabled, stats.unfollow_enabled];
    const backgroundColors = [
        'rgba(76, 175, 80, 0.8)',
        'rgba(244, 67, 54, 0.8)'
    ];
    
    // Destroy existing chart if it exists
    if (window.settingsChart instanceof Chart) {
        window.settingsChart.destroy();
    }
    
    // Create new chart
    window.settingsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Number of Accounts',
                data: data,
                backgroundColor: backgroundColors,
                borderColor: 'rgba(30, 30, 30, 1)',
                borderWidth: 2,
                borderRadius: 8,
                borderSkipped: false,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.6)',
                        font: {
                            family: "'Inter', sans-serif"
                        }
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.6)',
                        font: {
                            family: "'Inter', sans-serif"
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(30, 30, 30, 0.9)',
                    titleColor: 'rgba(255, 255, 255, 0.87)',
                    bodyColor: 'rgba(255, 255, 255, 0.87)',
                    bodyFont: {
                        family: "'Inter', sans-serif"
                    },
                    titleFont: {
                        family: "'Inter', sans-serif",
                        weight: 'bold'
                    },
                    padding: 15,
                    boxPadding: 10,
                    cornerRadius: 8
                }
            }
        }
    });
}

// Load recent activity data
async function loadRecentActivity() {
    try {
        console.log('Loading recent activity...');
        // Fetch accounts data
        const response = await fetch('/api/accounts');
        if (!response.ok) throw new Error('Failed to load accounts data');
        
        const accounts = await response.json();
        console.log('Accounts loaded:', accounts.length);
        
        // Sort by starttime (most recent first)
        accounts.sort((a, b) => {
            const aTime = parseInt(a.starttime || '0');
            const bTime = parseInt(b.starttime || '0');
            return bTime - aTime;
        });
        
        // Take only the top 5 most recent accounts
        const recentAccounts = accounts.slice(0, 5);
        console.log('Recent accounts:', recentAccounts);
        
        // Render recent activity table
        renderRecentActivity(recentAccounts);
    } catch (error) {
        console.error('Error loading recent activity:', error);
        handleApiError(error);
        document.getElementById('recentActivityTable').innerHTML = `
            <tr>
                <td colspan="5" class="text-center text-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error loading activity data
                </td>
            </tr>
        `;
    }
}

// Render recent activity table
function renderRecentActivity(accounts) {
    console.log('Rendering recent activity table with accounts:', accounts);
    const tableBody = document.getElementById('recentActivityTable');
    
    // Clear existing rows
    tableBody.innerHTML = '';
    
    // If no accounts, show message
    if (!accounts || accounts.length === 0) {
        console.log('No accounts to display');
        tableBody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center text-white-50">
                    No recent activity found
                </td>
            </tr>
        `;
        return;
    }
    
    // Add rows for each account
    accounts.forEach(account => {
        console.log('Rendering account:', account.account);
        const row = document.createElement('tr');
        
        // Account column
        const accountCell = document.createElement('td');
        accountCell.innerHTML = `
            <div class="d-flex align-items-center">
                <div class="avatar-sm me-2 bg-primary rounded-circle d-flex align-items-center justify-content-center">
                    <span>${account.account ? account.account.charAt(0).toUpperCase() : 'U'}</span>
                </div>
                <span class="text-white">${account.account || 'Unknown'}</span>
            </div>
        `;
        row.appendChild(accountCell);
        
        // Device column
        const deviceCell = document.createElement('td');
        deviceCell.innerHTML = `<span class="badge bg-info text-white">${account.devicename || account.deviceid || 'Unknown'}</span>`;
        row.appendChild(deviceCell);
        
        // Status column
        const statusCell = document.createElement('td');
        const isActive = account.starttime && account.starttime !== '0' || account.endtime && account.endtime !== '0';
        statusCell.innerHTML = isActive ? 
            '<span class="badge bg-success text-white"><i class="fas fa-check-circle me-1"></i>Active</span>' : 
            '<span class="badge bg-secondary text-white"><i class="fas fa-times-circle me-1"></i>Inactive</span>';
        row.appendChild(statusCell);
        
        // Last active column
        const lastActiveCell = document.createElement('td');
        const hasStats = account.stats && Object.keys(account.stats).length > 0;
        if (hasStats && account.stats.date) {
            lastActiveCell.textContent = account.stats.date;
        } else {
            lastActiveCell.textContent = 'Never';
        }
        row.appendChild(lastActiveCell);
        
        // Actions column
        const actionsCell = document.createElement('td');
        actionsCell.innerHTML = `
            <div class="btn-group">
                <button class="btn btn-sm btn-outline-primary view-account-btn" data-device="${account.deviceid}" data-account="${account.account}">
                    <i class="fas fa-eye"></i>
                </button>
            </div>
        `;
        row.appendChild(actionsCell);
        
        // Add the row to the table
        tableBody.appendChild(row);
    });
    
    // Add event listeners to view buttons
    document.querySelectorAll('.view-account-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const deviceId = this.getAttribute('data-device');
            const accountName = this.getAttribute('data-account');
            showAccountDetails(deviceId, accountName);
        });
    });
}

// Load inventory stats
async function loadInventoryStats() {
    try {
        console.log('Loading inventory stats...');
        // Fetch inventory data
        const response = await fetch('/api/inventory/stats');
        if (!response.ok) throw new Error('Failed to load inventory data');
        
        const stats = await response.json();
        console.log('Inventory stats loaded:', stats);
        
        // Update inventory stats cards
        updateInventoryStatsCards(stats);
    } catch (error) {
        console.error('Error loading inventory stats:', error);
        handleApiError(error);
    }
}

// Update inventory stats cards with data
function updateInventoryStatsCards(stats) {
    console.log('Updating inventory stats cards...');
    
    // Update main inventory card
    const inventoryAccountsElement = document.getElementById('inventoryAccounts');
    console.log('inventoryAccounts element:', inventoryAccountsElement);
    if (inventoryAccountsElement) {
        console.log('Setting inventoryAccounts to:', stats.total || 0);
        inventoryAccountsElement.textContent = stats.total || 0;
    }
    
    // Update detailed inventory stats
    const availableAccountsElement = document.getElementById('availableAccounts');
    console.log('availableAccounts element:', availableAccountsElement);
    if (availableAccountsElement) {
        console.log('Setting availableAccounts to:', stats.available || 0);
        availableAccountsElement.textContent = stats.available || 0;
    }
    
    const usedAccountsElement = document.getElementById('usedAccounts');
    console.log('usedAccounts element:', usedAccountsElement);
    if (usedAccountsElement) {
        console.log('Setting usedAccounts to:', stats.used || 0);
        usedAccountsElement.textContent = stats.used || 0;
    }
    
    const recentlyAddedAccountsElement = document.getElementById('recentlyAddedAccounts');
    console.log('recentlyAddedAccounts element:', recentlyAddedAccountsElement);
    if (recentlyAddedAccountsElement) {
        console.log('Setting recentlyAddedAccounts to:', stats.recently_added || 0);
        recentlyAddedAccountsElement.textContent = stats.recently_added || 0;
    }
    
    const recentlyUsedAccountsElement = document.getElementById('recentlyUsedAccounts');
    console.log('recentlyUsedAccounts element:', recentlyUsedAccountsElement);
    if (recentlyUsedAccountsElement) {
        console.log('Setting recentlyUsedAccounts to:', stats.recently_used || 0);
        recentlyUsedAccountsElement.textContent = stats.recently_used || 0;
    }
}

// Format a number with commas
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Format runtime from start and end times
function formatRuntime(startTime, endTime) {
    if (!startTime || startTime === '0') {
        return 'Not started';
    }
    
    const start = parseInt(startTime);
    const end = parseInt(endTime) || Math.floor(Date.now() / 1000);
    const duration = end - start;
    
    if (duration < 0) {
        return 'Invalid time';
    }
    
    const hours = Math.floor(duration / 3600);
    const minutes = Math.floor((duration % 3600) / 60);
    
    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else {
        return `${minutes}m`;
    }
}

// Handle API errors
function handleApiError(error) {
    console.error('API Error:', error);
    // Show error toast
    const toastContainer = document.getElementById('toastContainer');
    if (toastContainer) {
        const toast = document.createElement('div');
        toast.className = 'toast align-items-center text-white bg-danger border-0';
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
        toast.setAttribute('aria-atomic', 'true');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    ${error.message || 'An error occurred'}
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
}
