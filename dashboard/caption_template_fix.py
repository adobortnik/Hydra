# Fix for caption templates in batch scheduling

"""
This file contains the fix for the caption templates not working properly in batch scheduling.

The issue is that while the caption template ID is correctly passed from the frontend to the API endpoint,
it's not being used in the batch scheduling process.

Here's the code that needs to be added to the api_batch_schedule function in simple_app.py,
specifically around line 3155-3158 where it generates the caption.
"""

# Replace the following code in api_batch_schedule:

'''
# Generate caption with template
item_caption = caption_template
if hashtags:
    item_caption += f"\n\n{hashtags}"
'''

# With this code:

'''
# Generate caption with template
item_caption = caption_template

# If caption template ID is provided, get a random caption from the template
if caption_template_id:
    try:
        print(f"Getting random caption from template ID: {caption_template_id}")
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
