import os
import sys
import json
from flask import Flask, render_template, jsonify, request

# Add parent directory to path to import modules from the main application
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import database functions from the main application
from flask.databases_flask import devicedb, accountsinfodb, accountsettings, accountstats

app = Flask(__name__)

@app.route('/')
def index():
    """Render the main dashboard page"""
    return render_template('index.html')

@app.route('/api/devices')
def get_devices():
    """Get all devices from the database"""
    devices = devicedb.query('all')
    # Remove SQLAlchemy state
    for device in devices:
        if '_sa_instance_state' in device:
            del device['_sa_instance_state']
    return jsonify(devices)

@app.route('/api/accounts')
def get_all_accounts():
    """Get all accounts from all devices"""
    devices = devicedb.query('all')
    all_accounts = []
    
    for device in devices:
        deviceid = device['deviceid']
        devicename = device['devicename']
        
        try:
            accounts = accountsinfodb(deviceid).query('all')
            
            for account in accounts:
                if '_sa_instance_state' in account:
                    del account['_sa_instance_state']
                
                # Add device info to account
                account['deviceid'] = deviceid
                account['devicename'] = devicename
                
                # Get account stats if available
                try:
                    stats = accountstats(deviceid, account['account']).query('first')
                    if stats and '_sa_instance_state' in stats:
                        del stats['_sa_instance_state']
                    account['stats'] = stats if stats else {}
                except Exception as e:
                    account['stats'] = {}
                    print(f"Error getting stats for {account['account']}: {str(e)}")
                
                all_accounts.append(account)
        except Exception as e:
            print(f"Error getting accounts for device {deviceid}: {str(e)}")
    
    return jsonify(all_accounts)

@app.route('/api/accounts/<deviceid>')
def get_device_accounts(deviceid):
    """Get all accounts for a specific device"""
    try:
        accounts = accountsinfodb(deviceid).query('all')
        for account in accounts:
            if '_sa_instance_state' in account:
                del account['_sa_instance_state']
        return jsonify(accounts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/account/<deviceid>/<account>')
def get_account(deviceid, account):
    """Get details for a specific account"""
    try:
        account_info = accountsinfodb(deviceid).query('first', account=account)
        if '_sa_instance_state' in account_info:
            del account_info['_sa_instance_state']
        
        # Try to get account settings
        try:
            settings = accountsettings(deviceid, account).query('first')
            if settings and '_sa_instance_state' in settings:
                del settings['_sa_instance_state']
            account_info['settings'] = settings if settings else {}
        except Exception as e:
            account_info['settings'] = {}
            print(f"Error getting settings for {account}: {str(e)}")
        
        # Try to get account stats
        try:
            stats = accountstats(deviceid, account).query('first')
            if stats and '_sa_instance_state' in stats:
                del stats['_sa_instance_state']
            account_info['stats'] = stats if stats else {}
        except Exception as e:
            account_info['stats'] = {}
            print(f"Error getting stats for {account}: {str(e)}")
            
        return jsonify(account_info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5050)
