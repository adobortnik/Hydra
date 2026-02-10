# Integration script for caption templates

def integrate_caption_templates(app, simple_app):
    """
    Integrates caption templates functionality into the main Flask app
    
    Args:
        app: The Flask app instance
        simple_app: The simple_app module containing all the functions
    """
    from flask import render_template, jsonify, request
    
    # Add route for caption templates page
    @app.route('/caption-templates')
    def caption_templates_page():
        """Caption Templates page"""
        return render_template('caption_templates.html')
    
    # API endpoints for caption templates
    @app.route('/api/caption-templates', methods=['GET'])
    def api_get_caption_templates():
        try:
            templates = simple_app.get_all_caption_templates()
            return jsonify(templates)
        except Exception as e:
            print(f"Error getting caption templates: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/caption-templates/<template_id>', methods=['GET'])
    def api_get_caption_template(template_id):
        try:
            template = simple_app.get_caption_template(template_id)
            if template:
                return jsonify(template)
            return jsonify({'error': 'Caption template not found'}), 404
        except Exception as e:
            print(f"Error getting caption template {template_id}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/caption-templates', methods=['POST'])
    def api_create_caption_template():
        try:
            data = request.json
            name = data.get('name')
            description = data.get('description', '')
            captions_text = data.get('captions', '')
            
            if not name:
                return jsonify({'error': 'Name is required'}), 400
            
            # Split captions by newline and filter out empty lines
            captions = [caption.strip() for caption in captions_text.split('\n') if caption.strip()]
            
            if not captions:
                return jsonify({'error': 'At least one caption is required'}), 400
            
            template_id = simple_app.create_caption_template(name, description, captions)
            if template_id:
                return jsonify({
                    'id': template_id,
                    'message': 'Caption template created successfully'
                })
            return jsonify({'error': 'Failed to create caption template'}), 500
        except Exception as e:
            print(f"Error creating caption template: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/caption-templates/<template_id>', methods=['PUT'])
    def api_update_caption_template(template_id):
        try:
            data = request.json
            name = data.get('name')
            description = data.get('description', '')
            captions_text = data.get('captions', '')
            
            if not name:
                return jsonify({'error': 'Name is required'}), 400
            
            # Split captions by newline and filter out empty lines
            captions = [caption.strip() for caption in captions_text.split('\n') if caption.strip()]
            
            if not captions:
                return jsonify({'error': 'At least one caption is required'}), 400
            
            success = simple_app.update_caption_template(template_id, name, description, captions)
            if success:
                return jsonify({'message': 'Caption template updated successfully'})
            return jsonify({'error': 'Failed to update caption template'}), 500
        except Exception as e:
            print(f"Error updating caption template {template_id}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/caption-templates/<template_id>', methods=['DELETE'])
    def api_delete_caption_template(template_id):
        try:
            success = simple_app.delete_caption_template(template_id)
            if success:
                return jsonify({'message': 'Caption template deleted successfully'})
            return jsonify({'error': 'Failed to delete caption template'}), 500
        except Exception as e:
            print(f"Error deleting caption template {template_id}: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/caption-templates/<template_id>/random', methods=['GET'])
    def api_get_random_caption(template_id):
        try:
            count = request.args.get('count', 1, type=int)
            captions = simple_app.get_random_captions(template_id, count)
            if captions:
                return jsonify(captions)
            return jsonify({'error': 'No captions found for this template'}), 404
        except Exception as e:
            print(f"Error getting random caption from template {template_id}: {e}")
            return jsonify({'error': str(e)}), 500
    
    print("Caption templates functionality integrated successfully")
    return app
