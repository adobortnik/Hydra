# This file contains the fix for the batch scheduling functionality

"""
This fix addresses the 'string indices must be integers, not str' error that occurs when
trying to schedule posts. The issue is related to how account data is handled in the batch
scheduling process.

To fix this issue, follow these steps:

1. Find the api_batch_schedule function in your simple_app.py file
2. Replace it with the code below
"""

@app.route('/api/batch/schedule', methods=['POST'])
def api_batch_schedule():
    """API endpoint to schedule posts for all media in a folder"""
    try:
        data = request.json
        folder_id = data.get('folder_id')
        device_id = data.get('device_id')
        account = data.get('account')
        use_all_accounts = data.get('use_all_accounts', False)
        caption_template_id = data.get('caption_template_id', '')
        caption_template = data.get('caption_template', '')
        hashtags = data.get('hashtags', '')
        start_time = data.get('start_time')
        interval_hours = int(data.get('interval_hours', 24))
        repurpose = data.get('repurpose', False)
        
        if not all([folder_id, device_id, start_time]) or (not use_all_accounts and not account):
            return jsonify({'error': 'Missing required parameters'}), 400
        
        # Get all accounts for the device if use_all_accounts is True
        accounts = []
        if use_all_accounts:
            try:
                # Get accounts for the device using the get_accounts function
                device_accounts = get_accounts(device_id)
                
                if device_accounts:
                    accounts = [{'account': account['account']} for account in device_accounts]
                else:
                    return jsonify({'error': 'No accounts found for this device'}), 404
            except Exception as e:
                return jsonify({'error': f'Error fetching accounts: {str(e)}'}), 500
        else:
            accounts = [{'account': account}]
        
        # Get all media in the folder
        media_items = get_media_in_folder(folder_id)
        if not media_items:
            return jsonify({'error': 'No media found in folder'}), 404
        
        # Schedule posts for each media item
        scheduled_posts = []
        current_time = datetime.datetime.fromisoformat(start_time)
        
        # For each media item, schedule posts for all accounts
        for i, media in enumerate(media_items):
            # Get media file path
            media_id = media['id']
            media_item = get_media_item(media_id)
            
            if not media_item:
                continue
                
            # Generate caption with template
            item_caption = caption_template
            
            # If caption template ID is provided, get a random caption from the template
            if caption_template_id:
                try:
                    print(f"Getting random caption from template ID: {caption_template_id}")
                    
                    # Get random caption
                    random_captions = get_random_captions(caption_template_id, 1)
                    print(f"Random captions retrieved: {random_captions}")
                    
                    if random_captions and len(random_captions) > 0:
                        item_caption = random_captions[0]
                        print(f"Using random caption: {item_caption}")
                    else:
                        print(f"No captions found for template ID: {caption_template_id}")
                except Exception as e:
                    print(f"Error getting random caption from template {caption_template_id}: {e}")
                    traceback.print_exc()
            
            # Replace placeholders in caption
            if item_caption and '{filename}' in item_caption:
                item_caption = item_caption.replace('{filename}', os.path.splitext(media_item['filename'])[0])
            if item_caption and '{date}' in item_caption:
                item_caption = item_caption.replace('{date}', current_time.strftime('%Y-%m-%d'))
            if item_caption and '{time}' in item_caption:
                item_caption = item_caption.replace('{time}', current_time.strftime('%H:%M'))
            
            # Add hashtags
            if hashtags:
                item_caption += f"\n\n{hashtags}"
            
            # If this is not the first media item, increment the date by one day
            # This ensures each new media item starts one day later than the previous one
            if i > 0:
                # Add 24 hours (one day) to the current time for each new media item
                current_time = current_time + datetime.timedelta(days=1)
                print(f"Incrementing date for new media item. New date: {current_time.isoformat()}")
            
            # Save the initial time for this media item to reset after processing all accounts
            media_item_time = current_time
            
            for account_info in accounts:
                account_name = account_info['account']
                
                # Check if we have the original_path in the media_item
                # If not, query it directly from the database
                if 'original_path' not in media_item or not media_item['original_path']:
                    db_path = init_media_library_db()
                    conn = get_db_connection(db_path)
                    cursor = conn.cursor()
                    cursor.execute('SELECT original_path FROM media WHERE id = ?', (media_id,))
                    result = cursor.fetchone()
                    conn.close()
                    
                    if result and result[0]:
                        media_item['original_path'] = result[0]
                        print(f"Using database original_path: {media_item['original_path']}")
                
                # Use the original_path if available, otherwise fall back to filename
                current_file_path = None
                if 'original_path' in media_item and media_item['original_path']:
                    # The original_path is stored as 'original/filename.ext' in the database
                    current_file_path = os.path.normpath(os.path.join(MEDIA_LIBRARY_DIR, media_item['original_path']))
                    print(f"Using original_path from database: {current_file_path}")
                else:
                    # Fall back to the filename approach
                    current_file_path = os.path.normpath(os.path.join(MEDIA_LIBRARY_DIR, 'original', media_item['filename']))
                    print(f"Falling back to filename approach: {current_file_path}")
                
                # Check if the original file exists
                if not os.path.exists(current_file_path):
                    print(f"Warning: Original file {current_file_path} not found for account {account_name}")
                    # Try to find the file using the hash-based naming convention
                    db_path = init_media_library_db()
                    conn = get_db_connection(db_path)
                    cursor = conn.cursor()
                    
                    cursor.execute('SELECT id FROM media WHERE id = ?', (media_id,))
                    result = cursor.fetchone()
                    conn.close()
                    
                    if result:
                        # Try to construct the hash-based filename
                        file_base, file_ext = os.path.splitext(media_item['filename'])
                        hash_filename = f"{result[0]}{file_ext}"
                        hash_path = os.path.normpath(os.path.join(MEDIA_LIBRARY_DIR, 'original', hash_filename))
                        
                        if os.path.exists(hash_path):
                            current_file_path = hash_path
                            print(f"Found file using hash-based name: {current_file_path}")
                        else:
                            print(f"No valid file path found for {media_item['filename']}, skipping this account")
                            continue
                    else:
                        print(f"No valid file path found for {media_item['filename']}, skipping this account")
                        continue
                
                # Create post data
                post_data = {
                    'deviceid': device_id,
                    'account': account_name,  # Use the account name string directly
                    'post_type': 'photo' if media['media_type'] == 'image' else 'video',
                    'caption': item_caption,
                    'scheduled_time': media_item_time.isoformat()
                }
                
                # Add media file if it exists
                if os.path.exists(current_file_path):
                    try:
                        with open(current_file_path, 'rb') as f:
                            file_content = f.read()
                        
                        # Create a temporary file-like object
                        from io import BytesIO
                        file_obj = BytesIO(file_content)
                        file_obj.filename = os.path.basename(current_file_path)
                        
                        # Add the file to post_data
                        post_data['media'] = file_obj
                        
                        # Schedule the post
                        post_id = create_scheduled_post(post_data)
                        if post_id:
                            scheduled_posts.append({
                                'post_id': post_id,
                                'media_id': media['id'],
                                'account': account_name,
                                'scheduled_time': media_item_time.isoformat()
                            })
                            print(f"Successfully scheduled post for account {account_name} with media {os.path.basename(current_file_path)}")
                    except Exception as e:
                        print(f"Error scheduling post with media for account {account_name}: {str(e)}")
                        traceback.print_exc()
                else:
                    print(f"Warning: Cannot schedule post for account {account_name} because media file not found")
                
                # Increment time for next account
                if use_all_accounts and len(accounts) > 1:
                    # If using all accounts, increment time for each account
                    media_item_time += datetime.timedelta(hours=interval_hours / len(accounts))
        
        # If not using all accounts, increment time for next media item
        if not use_all_accounts or len(accounts) <= 1:
            current_time += datetime.timedelta(hours=interval_hours)
        
        return jsonify({
            'message': f'Successfully scheduled {len(scheduled_posts)} posts',
            'scheduled_posts': scheduled_posts
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
