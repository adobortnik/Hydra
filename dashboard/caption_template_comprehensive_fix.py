# Comprehensive fix for caption templates in batch scheduling

"""
This file contains a comprehensive fix for the caption templates not working properly in batch scheduling.

The issue is that the caption template ID is not being used to fetch random captions from the template.
Instead, it's only using the caption template text directly.

Here's how to fix the issue:

1. Find the api_batch_schedule function in simple_app.py (around line 3100)
2. Look for the section where it generates the caption (around lines 3155-3158)
3. Replace the current caption generation code with the code below
"""

# STEP 1: Add this debugging function at the end of the file (before if __name__ == '__main__':)

def debug_caption_template(template_id):
    """Debug function to check if a caption template exists and retrieve its captions"""
    try:
        print(f"\nDEBUG: Checking caption template ID: {template_id}")
        db_path = init_caption_templates_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Check if template exists
        cursor.execute('SELECT * FROM caption_templates WHERE id = ?', (template_id,))
        template = cursor.fetchone()
        
        if template:
            print(f"DEBUG: Template found: {dict(template)}")
            
            # Get captions
            cursor.execute('SELECT * FROM captions WHERE template_id = ?', (template_id,))
            captions = cursor.fetchall()
            
            print(f"DEBUG: Found {len(captions)} captions:")
            for caption in captions:
                print(f"  - {dict(caption)['caption']}")
                
            # Test random selection
            cursor.execute('SELECT caption FROM captions WHERE template_id = ? ORDER BY RANDOM() LIMIT 1', (template_id,))
            random_caption = cursor.fetchone()
            
            if random_caption:
                print(f"DEBUG: Random caption: {random_caption[0]}")
            else:
                print("DEBUG: No random caption found")
        else:
            print(f"DEBUG: Template not found with ID: {template_id}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        traceback.print_exc()
        return False

# STEP 2: Replace the caption generation code in api_batch_schedule
# Find this code (around line 3155):

'''
# Generate caption with template
item_caption = caption_template
if hashtags:
    item_caption += f"\n\n{hashtags}"
'''

# Replace it with this code:

'''
# Generate caption with template
item_caption = caption_template

# If caption template ID is provided, get a random caption from the template
if caption_template_id:
    try:
        print(f"Getting random caption from template ID: {caption_template_id}")
        
        # Debug the template first
        debug_caption_template(caption_template_id)
        
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
'''

# STEP 3: Make sure the caption is being passed correctly to the post_data
# Find this code (around line 3360):

'''
post_data = {
    'deviceid': device_id,
    'account': account_name,
    'post_type': post_type,
    'caption': item_caption,  # Make sure this is using item_caption, not caption
    'location': '',
    'scheduled_time': current_time.isoformat(),
    'media': file_obj
}
'''

# STEP 4: Add debugging to the create_scheduled_post function
# Find this code (around line 1828):

'''
post_data.get('caption', ''),
'''

# Add a print statement before it:

'''
print(f"Saving post with caption: {post_data.get('caption', '')}")
post_data.get('caption', ''),
'''
