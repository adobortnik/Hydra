import uiautomator2 as u2
import time
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

d = u2.connect('10.1.11.4:5555')

# First check the comment input still has text
comment_input = d(resourceId='com.instagram.androif:id/layout_comment_thread_edittext')
if comment_input.exists(timeout=2):
    print("Comment input exists")
else:
    print("Comment input NOT found - we may have left the comment screen")

# Click the Post button
post_btn = d(resourceId='com.instagram.androif:id/layout_comment_thread_post_button_icon')
if post_btn.exists(timeout=2):
    post_btn.click()
    print("CLICKED POST BUTTON!")
    time.sleep(3)
    print("Comment should be posted!")
else:
    # Try by description
    post_desc = d(description='Post', className='android.widget.ImageView')
    if post_desc.exists(timeout=2):
        post_desc.click()
        print("CLICKED POST via description!")
        time.sleep(3)
    else:
        print("Post button not found")
