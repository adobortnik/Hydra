# The Live House - Instagram Account Dashboard

A comprehensive dashboard for monitoring and managing Instagram accounts across multiple devices.

## Features

### Dashboard
- Real-time statistics visualization
- Charts showing account distribution and settings
- Recent activity tracking
- Responsive dark-themed UI

### Account Management
- View all Instagram accounts across devices
- Filter and search accounts
- Sort accounts by various criteria
- Detailed account information modal
- Edit account settings directly from the dashboard
- Bulk account settings management

### Scheduled Posts
- Create and manage scheduled posts
- Support for images, videos, and stories
- Schedule posts for multiple accounts
- Track post status (scheduled, published)

### Media Library
- Drag-and-drop media upload interface
- Anti-detection image processing
- Batch processing for multiple images
- Tag-based organization system
- Search and filter by media type, tags, or filename

## Installation

### Windows

1. Create a virtual environment:
```
python -m venv venv
venv\Scripts\activate
```

2. Install dependencies:
```
pip install -r requirements.txt
```

3. Run the application:
```
python simple_app.py
```

### macOS/Linux

1. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python simple_app.py
```

## Usage

Access the dashboard by opening a web browser and navigating to:
```
http://localhost:5050
```

## Technical Stack
- Backend: Flask (Python)
- Frontend: HTML, CSS, JavaScript
- UI Framework: Bootstrap 5
- Database: SQLite
- Charting: Chart.js
- Icons: Font Awesome

## Database Integration

The dashboard reads from and writes to the same database files used by the Instagram bot:
- `devices.db`: Device information
- `deviceid/accounts.db`: Account details
- `deviceid/account/stats.db`: Account statistics
- `scheduled_posts/scheduled_posts.db`: Scheduled posts
- `media_library/media_library.db`: Media library

## Security Considerations
- Thread-safe SQLite database access
- Minimal external dependencies
- Secure API endpoints for data retrieval and updates
