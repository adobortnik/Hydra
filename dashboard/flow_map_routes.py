"""
flow_map_routes.py - Automation Flows Visual Documentation
===========================================================
Interactive Mermaid.js flowcharts showing how each automation flow works
step-by-step. Visual documentation of the actual codebase.
"""

from flask import Blueprint, render_template

flow_map_bp = Blueprint('flow_map', __name__)


@flow_map_bp.route('/automation-flows')
def automation_flows_page():
    """Render the Automation Flows visual documentation page."""
    return render_template('flow_map.html')
