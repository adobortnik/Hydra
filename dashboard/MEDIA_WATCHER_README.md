# Media Folder Watcher for The Live House Dashboard

This tool allows you to easily add media files and folders to your dashboard by simply copying them to a folder on your PC. No need to use the dashboard's upload or folder creation features anymore!

## How It Works

1. The watcher monitors the `data/media_library/original` folder in your dashboard directory
2. Any files or folders you add to this directory will be automatically imported into the dashboard
3. The folder structure you create will be preserved in the dashboard

## Getting Started

1. Run `install_media_watcher.bat` to install the required dependencies
2. Run `start_media_watcher.bat` to start the folder watcher
3. Keep the watcher running while you add files to the folder
4. Open your dashboard as usual to see the imported media

## Tips

- You can organize your media by creating folders within the `data/media_library/original` directory
- Supported file types: JPG, JPEG, PNG, GIF, MP4, MOV
- The watcher will automatically detect new files and folders as you add them
- The dashboard will show your folder structure exactly as you've organized it on your PC

## Troubleshooting

If you don't see your files in the dashboard:
- Make sure the watcher is running (the command window should be open)
- Check that you've added files to the correct folder (`data/media_library/original`)
- Refresh the dashboard page
- Restart the watcher if needed

## Technical Details

The watcher uses the Python watchdog library to monitor file system events and automatically updates the dashboard's SQLite database when changes are detected.
