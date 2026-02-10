# Script to integrate caption templates functionality

import os
import sys

# Add the current directory to the path so we can import the simple_app module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the necessary modules
import simple_app
from app_integration import integrate_caption_templates

# Integrate caption templates functionality
app = simple_app.app
integrate_caption_templates(app, simple_app)

print("Caption templates functionality has been integrated.")
print("Routes added:")
print("  - /caption-templates (Caption Templates page)")
print("  - /api/caption-templates (GET, POST)")
print("  - /api/caption-templates/<template_id> (GET, PUT, DELETE)")
print("  - /api/caption-templates/<template_id>/random (GET)")

# Run the app if this script is executed directly
if __name__ == '__main__':
    # Initialize the caption templates database
    simple_app.init_caption_templates_db()
    
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
