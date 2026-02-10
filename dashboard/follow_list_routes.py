"""
Follow List API Routes
=======================
CRUD for follow lists + items used by FollowFromListAction.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request
from automation.actions.follow_from_list import (
    create_follow_list, get_follow_lists, get_follow_list,
    update_follow_list, delete_follow_list,
    get_list_items, add_list_items, remove_list_item, clear_list_items,
    reset_list_items,
)

follow_list_bp = Blueprint('follow_lists', __name__, url_prefix='/api/follow-lists')


# ---------------------------------------------------------------------------
# List CRUD
# ---------------------------------------------------------------------------

@follow_list_bp.route('', methods=['GET'])
def api_list_all():
    """List all follow lists with item counts."""
    return jsonify(get_follow_lists())


@follow_list_bp.route('', methods=['POST'])
def api_create():
    """Create a follow list. Body: {name, description?}"""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    lid = create_follow_list(name, data.get('description', ''))
    return jsonify({'id': lid, 'name': name}), 201


@follow_list_bp.route('/<int:list_id>', methods=['GET'])
def api_get_one(list_id):
    """Get a single follow list."""
    fl = get_follow_list(list_id)
    if not fl:
        return jsonify({'error': 'not found'}), 404
    return jsonify(fl)


@follow_list_bp.route('/<int:list_id>', methods=['PUT'])
def api_update(list_id):
    """Update list name/description. Body: {name?, description?}"""
    data = request.get_json(silent=True) or {}
    ok = update_follow_list(list_id, data.get('name'), data.get('description'))
    if not ok:
        return jsonify({'error': 'update failed'}), 400
    fl = get_follow_list(list_id)
    return jsonify(fl) if fl else jsonify({'updated': True})


@follow_list_bp.route('/<int:list_id>', methods=['DELETE'])
def api_delete(list_id):
    """Delete a list and all its items."""
    delete_follow_list(list_id)
    return jsonify({'deleted': True})


# ---------------------------------------------------------------------------
# List items
# ---------------------------------------------------------------------------

@follow_list_bp.route('/<int:list_id>/items', methods=['GET'])
def api_get_items(list_id):
    """Get items in a list, optionally filtered by ?status=pending."""
    status_filter = request.args.get('status')
    items = get_list_items(list_id, status=status_filter)
    return jsonify(items)


@follow_list_bp.route('/<int:list_id>/items', methods=['POST'])
def api_add_items(list_id):
    """Add usernames to a list.

    Accepts:
      {username: "user1"}                    (single)
      {usernames: ["user1", "user2"]}        (array)
      {text: "user1\\nuser2\\nuser3"}          (newline/comma separated)
    """
    data = request.get_json(silent=True) or {}
    usernames = list(data.get('usernames', []))

    # Single username shorthand
    single = data.get('username', '').strip()
    if single:
        usernames.append(single)

    # Also accept raw text block
    text = data.get('text', '')
    if text:
        import re
        usernames.extend(re.split(r'[,\n\r]+', text))

    if not usernames:
        return jsonify({'error': 'usernames, username, or text required'}), 400

    added = add_list_items(list_id, usernames)

    # If single add, return the item details
    if single and not data.get('usernames') and not text:
        clean = single.lstrip('@').strip()
        items = get_list_items(list_id)
        item = next((i for i in items if i['username'] == clean), None)
        if item:
            return jsonify(item), 201

    total = len(get_list_items(list_id))
    return jsonify({'added': added, 'total': total})


@follow_list_bp.route('/<int:list_id>/import', methods=['POST'])
def api_bulk_import(list_id):
    """Bulk import usernames. Deduplicates within the list."""
    data = request.get_json(silent=True) or {}
    usernames = data.get('usernames', [])
    if not usernames:
        return jsonify({'error': 'usernames required'}), 400
    # Count all non-empty usernames submitted (before dedup)
    submitted = sum(1 for u in usernames if u.strip().lstrip('@').strip())
    added = add_list_items(list_id, usernames)
    total = len(get_list_items(list_id))
    duplicates = submitted - added
    return jsonify({'added': added, 'total': total, 'duplicates': max(0, duplicates)})


@follow_list_bp.route('/<int:list_id>/items/<int:item_id>', methods=['DELETE'])
def api_remove_item(list_id, item_id):
    """Remove a single item from a list."""
    remove_list_item(item_id)
    return jsonify({'removed': True})


@follow_list_bp.route('/<int:list_id>/items', methods=['DELETE'])
def api_clear_items(list_id):
    """Clear all items from a list."""
    clear_list_items(list_id)
    return jsonify({'cleared': True})


@follow_list_bp.route('/<int:list_id>/reset', methods=['POST'])
def api_reset_items(list_id):
    """Reset all non-pending items back to 'pending' status."""
    all_items = get_list_items(list_id)
    non_pending = sum(1 for i in all_items if i.get('status', 'pending') != 'pending')
    reset_list_items(list_id)
    return jsonify({'reset': True, 'reset_count': non_pending})


@follow_list_bp.route('/<int:list_id>/stats', methods=['GET'])
def api_list_stats(list_id):
    """Get stats for a follow list (pending/followed/skipped/error counts)."""
    all_items = get_list_items(list_id)
    stats = {'total': len(all_items), 'pending': 0, 'followed': 0, 'skipped': 0, 'error': 0}
    for item in all_items:
        s = item.get('status', 'pending')
        if s in stats:
            stats[s] += 1
        else:
            stats[s] = stats.get(s, 0) + 1
    return jsonify(stats)
