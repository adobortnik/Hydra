# Caption Templates routes and API endpoints — uses Phone Farm DB

import os
import sys
import json
import random
import uuid
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request

# Use Phone Farm DB
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db.models import get_connection, row_to_dict

caption_templates_bp = Blueprint('caption_templates', __name__)


def _get_all_templates():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM caption_templates ORDER BY name").fetchall()
    templates = []
    for r in rows:
        t = row_to_dict(r)
        caps = conn.execute(
            "SELECT * FROM captions WHERE template_id=? ORDER BY created_at", (t['id'],)
        ).fetchall()
        t['captions'] = [row_to_dict(c) for c in caps]
        t['caption_count'] = len(caps)
        templates.append(t)
    conn.close()
    return templates


# API endpoints
@caption_templates_bp.route('/api/caption-templates', methods=['GET'])
def api_get_caption_templates():
    try:
        return jsonify(_get_all_templates())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@caption_templates_bp.route('/api/caption-templates/<template_id>', methods=['GET'])
def api_get_caption_template(template_id):
    try:
        conn = get_connection()
        row = conn.execute("SELECT * FROM caption_templates WHERE id=?", (template_id,)).fetchone()
        if not row:
            conn.close()
            return jsonify({'error': 'Not found'}), 404
        t = row_to_dict(row)
        caps = conn.execute("SELECT * FROM captions WHERE template_id=?", (template_id,)).fetchall()
        t['captions'] = [row_to_dict(c) for c in caps]
        t['caption_count'] = len(caps)
        conn.close()
        return jsonify(t)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@caption_templates_bp.route('/api/caption-templates', methods=['POST'])
def api_create_caption_template():
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description', '')
        captions_text = data.get('captions', '')
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        captions_list = [c.strip() for c in captions_text.split('\n') if c.strip()]
        if not captions_list:
            return jsonify({'error': 'At least one caption is required'}), 400

        template_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        conn = get_connection()
        conn.execute(
            "INSERT INTO caption_templates (id, name, description, created_at, updated_at) VALUES (?,?,?,?,?)",
            (template_id, name, description, now, now)
        )
        for cap in captions_list:
            conn.execute(
                "INSERT INTO captions (id, template_id, caption, created_at) VALUES (?,?,?,?)",
                (str(uuid.uuid4()), template_id, cap, now)
            )
        conn.commit()
        conn.close()
        return jsonify({'id': template_id, 'message': 'Created'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@caption_templates_bp.route('/api/caption-templates/<template_id>', methods=['PUT'])
def api_update_caption_template(template_id):
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description', '')
        captions_text = data.get('captions', '')
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        captions_list = [c.strip() for c in captions_text.split('\n') if c.strip()]
        if not captions_list:
            return jsonify({'error': 'At least one caption is required'}), 400

        now = datetime.now().isoformat()
        conn = get_connection()
        conn.execute(
            "UPDATE caption_templates SET name=?, description=?, updated_at=? WHERE id=?",
            (name, description, now, template_id)
        )
        conn.execute("DELETE FROM captions WHERE template_id=?", (template_id,))
        for cap in captions_list:
            conn.execute(
                "INSERT INTO captions (id, template_id, caption, created_at) VALUES (?,?,?,?)",
                (str(uuid.uuid4()), template_id, cap, now)
            )
        conn.commit()
        conn.close()
        return jsonify({'message': 'Updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@caption_templates_bp.route('/api/caption-templates/<template_id>', methods=['DELETE'])
def api_delete_caption_template(template_id):
    try:
        conn = get_connection()
        conn.execute("DELETE FROM captions WHERE template_id=?", (template_id,))
        conn.execute("DELETE FROM caption_templates WHERE id=?", (template_id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@caption_templates_bp.route('/api/caption-templates/<template_id>/random', methods=['GET'])
def api_get_random_caption(template_id):
    try:
        count = request.args.get('count', 1, type=int)
        conn = get_connection()
        caps = conn.execute(
            "SELECT caption FROM captions WHERE template_id=?", (template_id,)
        ).fetchall()
        conn.close()
        if not caps:
            return jsonify({'error': 'No captions found'}), 404
        selected = random.sample([c['caption'] for c in caps], min(count, len(caps)))
        return jsonify(selected)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
