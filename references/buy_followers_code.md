# Buy Followers Feature — Saved from Account Inventory
## Reuse in Device Manager account list

### API Endpoints Used
- `GET /api/jap/services` — fetch available follower services
- `POST /api/jap/order-followers` — place order (FormData: service_id, quantity, username)

### Button in table row
```html
<button class="btn btn-sm btn-outline-info buy-followers-btn" data-id="${account.id}" data-username="${account.username}">
    <i class="fas fa-cart-plus"></i>
</button>
```

### Modal HTML
```html
<div class="modal fade" id="buyFollowersModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content bg-dark text-light border-secondary">
            <div class="modal-header border-secondary">
                <h5 class="modal-title">Buy Followers</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <div id="buyFollowersError" class="alert alert-danger" style="display: none;"></div>
                <div id="buyFollowersSuccess" class="alert alert-success" style="display: none;"></div>
                <form id="buyFollowersForm">
                    <input type="hidden" id="followerAccountId" name="accountId">
                    <input type="hidden" id="followerUsername" name="username">
                    <div class="mb-3">
                        <label for="followerService" class="form-label">Service</label>
                        <select class="form-control bg-dark text-light border-secondary" id="followerService" name="service_id" required>
                            <option value="">Loading services...</option>
                        </select>
                        <small class="form-text text-muted">Select the follower service you want to use.</small>
                    </div>
                    <div class="mb-3">
                        <label for="followerQuantity" class="form-label">Quantity</label>
                        <input type="number" class="form-control bg-dark text-light border-secondary" id="followerQuantity" name="quantity" min="1" required>
                        <small id="quantityHelp" class="form-text text-muted">Enter the number of followers you want to purchase.</small>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Instagram Profile</label>
                        <p id="instagramProfileUrl" class="form-control-static text-info"></p>
                    </div>
                </form>
            </div>
            <div class="modal-footer border-secondary">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-primary" onclick="submitBuyFollowers()">Buy Followers</button>
            </div>
        </div>
    </div>
</div>
```

### JavaScript (full)
```javascript
let followerServices = [];

document.addEventListener('DOMContentLoaded', function() {
    fetchFollowerServices();
    const submitButton = document.getElementById('submitBuyFollowers');
    if (submitButton) submitButton.addEventListener('click', submitBuyFollowers);
});

function fetchFollowerServices() {
    fetch('/api/jap/services')
        .then(response => response.json())
        .then(data => {
            if (data.error) { console.error('Error fetching services:', data.error); return; }
            followerServices = data;
            populateServicesDropdown();
        })
        .catch(error => console.error('Error fetching services:', error));
}

function populateServicesDropdown() {
    const dropdown = document.getElementById('followerService');
    dropdown.innerHTML = '';
    if (!followerServices || followerServices.length === 0 || followerServices.error) {
        dropdown.innerHTML = '<option value="">No services available or API key not configured</option>';
        return;
    }
    const instagramFollowerServices = followerServices.filter(service => {
        const name = (service.name || '').toLowerCase();
        const category = (service.category || '').toLowerCase();
        const type = (service.type || '').toLowerCase();
        return (name.includes('instagram') && (name.includes('follower') || name.includes('followers'))) ||
               (category.includes('instagram') && (name.includes('follower') || name.includes('followers') || type.includes('follower'))) ||
               (name.includes('instagram') && type.includes('follower')) ||
               ((name.includes('ig ') || name.includes('ig_') || name.startsWith('ig ')) && (name.includes('follower') || name.includes('followers')));
    });
    let servicesToShow = instagramFollowerServices;
    if (servicesToShow.length === 0) {
        servicesToShow = followerServices.filter(s => {
            const n = (s.name || '').toLowerCase();
            const t = (s.type || '').toLowerCase();
            return n.includes('follower') || n.includes('followers') || t.includes('follower');
        });
    }
    servicesToShow.sort((a, b) => parseFloat(a.rate) - parseFloat(b.rate));
    servicesToShow.forEach(service => {
        const option = document.createElement('option');
        option.value = service.service;
        option.textContent = `${service.name} - $${service.rate} per 1000 (Min: ${service.min}, Max: ${service.max})`;
        option.dataset.min = service.min;
        option.dataset.max = service.max;
        option.dataset.rate = service.rate;
        if (service.service == 8839) option.selected = true;
        dropdown.appendChild(option);
    });
    updateQuantityHelp();
}

function updateQuantityHelp() {
    const sel = document.getElementById('followerService');
    const help = document.getElementById('quantityHelp');
    const inp = document.getElementById('followerQuantity');
    if (sel.selectedIndex > -1) {
        const opt = sel.options[sel.selectedIndex];
        if (opt.dataset.min && opt.dataset.max) {
            help.textContent = `Enter a value between ${opt.dataset.min} and ${opt.dataset.max}. Cost: $${opt.dataset.rate} per 1000 followers.`;
            inp.min = opt.dataset.min;
            inp.max = opt.dataset.max;
            if (!inp.value || inp.value < opt.dataset.min) inp.value = opt.dataset.min;
        }
    }
}

function showBuyFollowersModal(accountId, username) {
    document.getElementById('followerAccountId').value = accountId;
    document.getElementById('followerUsername').value = username;
    document.getElementById('instagramProfileUrl').textContent = `https://instagram.com/${username}`;
    document.getElementById('buyFollowersForm').reset();
    document.getElementById('buyFollowersError').style.display = 'none';
    document.getElementById('buyFollowersSuccess').style.display = 'none';
    if (followerServices.length === 0) fetchFollowerServices();
    else populateServicesDropdown();
    new bootstrap.Modal(document.getElementById('buyFollowersModal')).show();
}

document.getElementById('followerService').addEventListener('change', updateQuantityHelp);

function submitBuyFollowers() {
    const form = document.getElementById('buyFollowersForm');
    const formData = new FormData(form);
    const serviceId = formData.get('service_id');
    const quantity = formData.get('quantity');
    if (!serviceId) { showBuyFollowersError('Please select a service'); return; }
    if (!quantity || quantity <= 0) { showBuyFollowersError('Please enter a valid quantity'); return; }
    const btn = document.querySelector('#buyFollowersModal .modal-footer .btn-primary');
    const orig = btn.textContent;
    btn.textContent = 'Processing...'; btn.disabled = true;
    fetch('/api/jap/order-followers', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (data.error) showBuyFollowersError(data.error);
            else if (data.order) {
                showBuyFollowersSuccess(`Order placed! Order ID: ${data.order}`);
                setTimeout(() => { bootstrap.Modal.getInstance(document.getElementById('buyFollowersModal')).hide(); }, 3000);
            } else showBuyFollowersError('Unknown error');
        })
        .catch(() => showBuyFollowersError('Error placing order.'))
        .finally(() => { btn.textContent = orig; btn.disabled = false; });
}

function showBuyFollowersError(msg) {
    document.getElementById('buyFollowersError').textContent = msg;
    document.getElementById('buyFollowersError').style.display = 'block';
    document.getElementById('buyFollowersSuccess').style.display = 'none';
}
function showBuyFollowersSuccess(msg) {
    document.getElementById('buyFollowersSuccess').textContent = msg;
    document.getElementById('buyFollowersSuccess').style.display = 'block';
    document.getElementById('buyFollowersError').style.display = 'none';
}
```
