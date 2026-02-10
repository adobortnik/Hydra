# Account Runtime Scheduler
# This module adds functionality to respect account runtime hours when batch scheduling

import datetime
import random

# Function to get account runtime hours (placeholder - integrate with your actual system)
def get_account_runtime_hours(device_id, account_name):
    """
    Get the runtime hours for a specific account
    Returns a list of tuples with (start_hour, end_hour) in 24-hour format
    """
    # This is a placeholder - replace with your actual implementation
    # that retrieves runtime hours from your database or settings
    
    # Example: Return a default runtime of 10am-12pm and 2pm-4pm
    # In a real implementation, you would fetch this from your database
    return [(10, 12), (14, 16)]

# Function to adjust scheduled time to fit within runtime hours
def adjust_time_to_runtime_hours(scheduled_time, runtime_hours):
    """
    Adjust the scheduled time to fit within the account's runtime hours
    If the time is already within runtime hours, it's returned unchanged
    Otherwise, it's moved to the next available runtime slot
    """
    # If no runtime hours defined, return the original time
    if not runtime_hours:
        return scheduled_time
    
    # Get the hour of the scheduled time
    hour = scheduled_time.hour
    
    # Check if the hour is already within any runtime slot
    for start_hour, end_hour in runtime_hours:
        if start_hour <= hour < end_hour:
            # Time is already within runtime hours
            return scheduled_time
    
    # If we're here, the time is outside runtime hours
    # Find the next available runtime slot
    
    # Sort runtime hours by start time
    sorted_runtime = sorted(runtime_hours)
    
    # Try to find a slot later today
    for start_hour, end_hour in sorted_runtime:
        if hour < start_hour:
            # Found a slot later today
            # Set time to the start of this slot plus a random offset (0-30 minutes)
            random_minutes = random.randint(0, 30)
            new_time = scheduled_time.replace(
                hour=start_hour,
                minute=random_minutes
            )
            return new_time
    
    # If no slot found later today, use the first slot tomorrow
    start_hour, end_hour = sorted_runtime[0]
    random_minutes = random.randint(0, 30)
    new_time = scheduled_time + datetime.timedelta(days=1)
    new_time = new_time.replace(
        hour=start_hour,
        minute=random_minutes
    )
    return new_time

# Function to integrate with batch scheduling
def schedule_within_runtime_hours(device_id, account_name, scheduled_time):
    """
    Ensure a post is scheduled within an account's runtime hours
    """
    # Get runtime hours for this account
    runtime_hours = get_account_runtime_hours(device_id, account_name)
    
    # Adjust the scheduled time to fit within runtime hours
    adjusted_time = adjust_time_to_runtime_hours(scheduled_time, runtime_hours)
    
    return adjusted_time

# Example of how to integrate this with your batch scheduling function:
"""
In your api_batch_schedule function, replace:

post_data = {
    'deviceid': device_id,
    'account': account['account'] if isinstance(account, dict) and 'account' in account else account,
    'post_type': 'photo' if media['media_type'] == 'image' else 'video',
    'caption': item_caption,
    'scheduled_time': current_time.isoformat()
}

With:

# Get account name properly
account_name = account['account'] if isinstance(account, dict) and 'account' in account else account

# Adjust scheduled time to fit within account's runtime hours
adjusted_time = schedule_within_runtime_hours(device_id, account_name, current_time)

post_data = {
    'deviceid': device_id,
    'account': account_name,
    'post_type': 'photo' if media['media_type'] == 'image' else 'video',
    'caption': item_caption,
    'scheduled_time': adjusted_time.isoformat()
}
"""
