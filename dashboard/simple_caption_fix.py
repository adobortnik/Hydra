# This is a simple fix for the caption template functionality
# The issue is that emojis in the captions might be causing problems

# Here's how to fix it:

# 1. Find this code in the api_batch_schedule function (around line 3160):

'''
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
'''

# 2. Replace it with this code:

'''
# If caption template ID is provided, get a random caption from the template
if caption_template_id:
    try:
        print(f"Getting random caption from template ID: {caption_template_id}")
        
        # Get random caption
        random_captions = get_random_captions(caption_template_id, 1)
        print(f"Random captions retrieved: {random_captions}")
        
        if random_captions and len(random_captions) > 0:
            # Handle potential emoji issues by ensuring the caption is properly encoded
            try:
                new_caption = random_captions[0]
                # Test if the caption can be properly encoded/decoded
                test_encode = new_caption.encode('utf-8').decode('utf-8')
                item_caption = new_caption
                print(f"Using random caption: {item_caption}")
            except Exception as encoding_error:
                print(f"Error with caption encoding: {encoding_error}")
                # Fall back to the original caption template
                print("Falling back to original caption template due to encoding issues")
        else:
            print(f"No captions found for template ID: {caption_template_id}")
    except Exception as e:
        print(f"Error getting random caption from template {caption_template_id}: {e}")
        traceback.print_exc()
'''

# 3. Also modify the get_random_captions function to handle potential encoding issues:

'''
def get_random_captions(template_id, count=1):
    try:
        db_path = init_caption_templates_db()
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT caption FROM captions WHERE template_id = ? ORDER BY RANDOM() LIMIT ?', (template_id, count))
        captions = []
        for row in cursor.fetchall():
            try:
                caption = row[0]
                # Test if the caption can be properly encoded/decoded
                test_encode = caption.encode('utf-8').decode('utf-8')
                captions.append(caption)
            except Exception as e:
                print(f"Skipping caption due to encoding issues: {e}")
        
        conn.close()
        return captions
    except Exception as e:
        print(f"Error getting random captions from template {template_id}: {e}")
        return []
'''

# This fix should handle any potential issues with emojis or special characters in the captions
