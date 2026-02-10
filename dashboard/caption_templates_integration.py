# Caption Templates Integration for Batch Scheduling
import os
import datetime
from io import BytesIO

def schedule_folder_posts_with_templates(folder_id, schedule_data, get_media_in_folder, get_media_item, 
                                        get_random_captions, create_scheduled_post, MEDIA_LIBRARY_DIR):
    """Enhanced version of schedule_folder_posts that supports caption templates"""
    try:
        # Get schedule parameters
        device_id = schedule_data.get('device_id')
        account = schedule_data.get('account')
        caption_template_id = schedule_data.get('caption_template_id', '')
        caption_template = schedule_data.get('caption_template', '')
        hashtags = schedule_data.get('hashtags', '')
        start_time = schedule_data.get('start_time')
        interval_hours = int(schedule_data.get('interval_hours', 24))
        repurpose = schedule_data.get('repurpose', False)
        
        if not all([device_id, start_time]) or (not account):
            return {'success': False, 'message': 'Missing required parameters', 'scheduled_count': 0}
        
        # Get all media in the folder
        media_items = get_media_in_folder(folder_id)
        if not media_items:
            return {'success': False, 'message': 'No media found in folder', 'scheduled_count': 0}
        
        # Schedule posts for each media item
        scheduled_posts = []
        current_datetime = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        
        for media in media_items:
            # Get media file
            media_id = media['id']
            media_item = get_media_item(media_id)
            
            if not media_item:
                continue
            
            # Get media filename
            media_filename = media_item['filename']
            
            # Get media file path
            media_path = os.path.join(MEDIA_LIBRARY_DIR, 'original', media_filename)
            if not os.path.exists(media_path):
                print(f"Media file not found: {media_path}")
                # Try processed folder as fallback
                media_path = os.path.join(MEDIA_LIBRARY_DIR, 'processed', media_filename)
                if not os.path.exists(media_path):
                    print(f"Media file not found in processed folder either: {media_path}")
                    continue
            
            # Prepare caption
            post_caption = caption_template
            
            # If caption template ID is provided, get a random caption from the template
            if caption_template_id:
                try:
                    random_captions = get_random_captions(caption_template_id, 1)
                    if random_captions and len(random_captions) > 0:
                        post_caption = random_captions[0]
                        print(f"Using random caption from template: {post_caption}")
                except Exception as e:
                    print(f"Error getting random caption from template {caption_template_id}: {e}")
            
            # Replace placeholders in caption
            if post_caption:
                # Replace filename without extension
                filename_without_ext = os.path.splitext(os.path.basename(media_filename))[0]
                post_caption = post_caption.replace('{filename}', filename_without_ext)
                
                # Replace date and time
                post_date = current_datetime.strftime('%Y-%m-%d')
                post_time = current_datetime.strftime('%H:%M')
                post_caption = post_caption.replace('{date}', post_date)
                post_caption = post_caption.replace('{time}', post_time)
            
            # Add hashtags if provided
            if hashtags:
                if post_caption:
                    post_caption += '\n\n'
                post_caption += hashtags
            
            # Determine post type
            post_type = 'photo'
            if media_item['media_type'] == 'video':
                post_type = 'video'
            
            # Read the media file
            with open(media_path, 'rb') as f:
                file_content = f.read()
            
            # Create a temporary file-like object
            file_obj = BytesIO(file_content)
            file_obj.filename = media_filename
            
            # Create post data
            post_data = {
                'deviceid': device_id,
                'account': account,
                'post_type': post_type,
                'caption': post_caption,
                'location': '',
                'scheduled_time': current_datetime.isoformat(),
                'media': file_obj
            }
            
            # Create scheduled post
            post_id = create_scheduled_post(post_data)
            if post_id:
                scheduled_posts.append(post_id)
            
            # Increment time for next post
            current_datetime += datetime.timedelta(hours=interval_hours)
        
        return {
            'success': True,
            'message': f'Successfully scheduled {len(scheduled_posts)} posts',
            'scheduled_count': len(scheduled_posts),
            'post_ids': scheduled_posts
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': f'Error scheduling posts: {str(e)}', 'scheduled_count': 0}
