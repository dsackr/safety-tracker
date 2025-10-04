from flask import Flask, render_template, request, redirect, url_for, send_file
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import os
import json
import threading
import time

# Configuration variables for easy positioning adjustments
# Font sizes
FONT_SIZE_DAYS = 400
FONT_SIZE_PRIOR_COUNT = 150
FONT_SIZE_INCIDENT = 100
FONT_SIZE_CHECKMARK = 80

# Position adjustments for main days counter
DAYS_Y_POSITION = 160  # Vertical position (higher = lower on image)
DAYS_X_OFFSET = 0      # Horizontal offset from center

# Position adjustments for prior count (blue box)
PRIOR_COUNT_X = 220    # Horizontal position
PRIOR_COUNT_Y = 630    # Vertical position

# Position adjustments for incident number (red box)
INCIDENT_X_OFFSET = 70  # Offset from center (positive = right, negative = left)
INCIDENT_Y = 650        # Vertical position

# Position adjustments for checkmarks (right box)
CHECKMARK_X = 940

CHECKMARK_CHANGE_Y = 575

CHECKMARK_DEPLOY_Y = 656

CHECKMARK_MISSED_Y = 745

app = Flask(__name__)

# Data file
DATA_FILE = 'data.json'
BACKGROUND_IMAGE = 'static/background.png'
OUTPUT_IMAGE = 'static/current_sign.png'

def load_data():
    """Load tracking data from JSON file"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        'days_since': 1,
        'prior_count': 2,
        'incident_number': '540',
        'reason': 'Deploy',
        'last_reset': datetime.now().isoformat(),
        'last_increment': datetime.now().date().isoformat()
    }

def save_data(data):
    """Save tracking data to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def display_on_epaper(img_path):
    """Send image to e-paper display"""
    try:
        import sys
        
        print(f"Attempting to display: {img_path}")
        
        # Check if image exists
        if not os.path.exists(img_path):
            print(f"ERROR: Image file not found at {img_path}")
            return False
        
        print("Image file exists, loading Waveshare library...")
        
        libdir = os.path.join(os.path.expanduser('~'), 'e-Paper/RaspberryPi_JetsonNano/python/lib')
        print(f"Library directory: {libdir}")
        
        if os.path.exists(libdir):
            sys.path.append(libdir)
            print("Library path added")
        else:
            print(f"ERROR: Library directory not found at {libdir}")
            return False
        
        from waveshare_epd import epd7in3e
        print("Waveshare library imported successfully")
        
        img = Image.open(img_path)
        print(f"Image opened: {img.size}")
        
        epd = epd7in3e.EPD()
        print("EPD object created")
        
        epd.init()
        print("EPD initialized")
        
        epd.Clear()
        print("EPD cleared")
        
        epd.display(epd.getbuffer(img))
        print("Image displayed")
        
        epd.sleep()
        print("EPD put to sleep - SUCCESS!")
        
        return True
        
    except Exception as e:
        print(f"EXCEPTION in display_on_epaper: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def generate_sign(auto_display=False):
    """Generate the safety sign with current data"""
    data = load_data()
    
    # Open background image
    img = Image.open(BACKGROUND_IMAGE)
    draw = ImageDraw.Draw(img)
    
    # Get actual image dimensions
    img_width, img_height = img.size
    
    # Load fonts using configured sizes
    try:
        days_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', FONT_SIZE_DAYS)
        count_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', FONT_SIZE_PRIOR_COUNT)
        inc_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', FONT_SIZE_INCIDENT)
        check_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', FONT_SIZE_CHECKMARK)
    except:
        days_font = ImageFont.load_default()
        count_font = ImageFont.load_default()
        inc_font = ImageFont.load_default()
        check_font = ImageFont.load_default()
    
    # Draw main days count (centered in yellow area)
    days_text = str(data['days_since'])
    days_bbox = draw.textbbox((0, 0), days_text, font=days_font)
    days_width = days_bbox[2] - days_bbox[0]
    days_x = (img_width - days_width) // 2 + DAYS_X_OFFSET
    days_y = DAYS_Y_POSITION
    draw.text((days_x, days_y), days_text, font=days_font, fill='black')
    
    # Draw prior count (left blue box)
    prior_text = str(data['prior_count'])
    prior_bbox = draw.textbbox((0, 0), prior_text, font=count_font)
    prior_width = prior_bbox[2] - prior_bbox[0]
    prior_x = PRIOR_COUNT_X - (prior_width // 2)
    prior_y = PRIOR_COUNT_Y
    draw.text((prior_x, prior_y), prior_text, font=count_font, fill='white')
    
    # Draw incident number (middle red box) - just the number, no "INC-"
    inc_text = data['incident_number']
    inc_bbox = draw.textbbox((0, 0), inc_text, font=inc_font)
    inc_width = inc_bbox[2] - inc_bbox[0]
    inc_x = (img_width // 2) - (inc_width // 2) + INCIDENT_X_OFFSET
    inc_y = INCIDENT_Y
    draw.text((inc_x, inc_y), inc_text, font=inc_font, fill='white')
    
    # Draw checkmark for reason (right red box)
    reason_positions = {
        'Change': (CHECKMARK_X, CHECKMARK_CHANGE_Y),
        'Deploy': (CHECKMARK_X, CHECKMARK_DEPLOY_Y),
        'Missed': (CHECKMARK_X, CHECKMARK_MISSED_Y)
    }
    
    if data['reason'] in reason_positions:
        check_x, check_y = reason_positions[data['reason']]
        draw.text((check_x, check_y), '✓', font=check_font, fill='blue')
    
    # Save the generated image
    img.save(OUTPUT_IMAGE)
    
    # Auto display to e-paper if requested
    if auto_display:
        display_on_epaper(OUTPUT_IMAGE)

def check_and_increment():
    """Background task to increment days at 6 AM and update display"""
    while True:
        now = datetime.now()
        data = load_data()
        last_increment = datetime.fromisoformat(data['last_increment'] + 'T00:00:00')
        
        # Check if it's 6 AM and we haven't incremented today
        if now.hour == 6 and now.date() > last_increment.date():
            data['days_since'] += 1
            data['last_increment'] = now.date().isoformat()
            save_data(data)
            
            # Generate sign and auto-display to e-paper
            generate_sign(auto_display=True)
            print(f"Auto-updated at 6 AM: Days incremented to {data['days_since']} and displayed on e-paper")
        
        # Sleep for 30 minutes before checking again
        time.sleep(1800)
        
@app.route('/send_to_display', methods=['POST'])
def send_to_display():
    """Manually send the current sign to the e-paper display"""
    if display_on_epaper(OUTPUT_IMAGE):
        return 'Sign sent to display successfully! <a href="/">Go back</a>'
    else:
        return 'Error sending to display. Check logs. <a href="/">Go back</a>'
        
@app.route('/')
def index():
    data = load_data()
    return render_template('index.html', data=data)

@app.route('/update', methods=['POST'])
def update():
    data = load_data()
    
    # Move current count to prior count
    data['prior_count'] = data['days_since']
    
    # Reset days to 0
    data['days_since'] = 0
    
    # Update incident details
    data['incident_number'] = request.form.get('incident_number', '')
    data['reason'] = request.form.get('reason', 'Change')
    data['last_reset'] = datetime.now().isoformat()
    data['last_increment'] = datetime.now().date().isoformat()
    
    save_data(data)
    generate_sign()
    
    return redirect(url_for('index'))

@app.route('/display')
def display():
    """Serve the current sign image for the e-paper display"""
    return send_file(OUTPUT_IMAGE, mimetype='image/png')

@app.route('/manual_increment', methods=['POST'])
def manual_increment():
    """Manual increment for testing"""
    data = load_data()
    data['days_since'] += 1
    save_data(data)
    generate_sign()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Generate initial sign
    generate_sign()
    
    # Start background increment thread
    increment_thread = threading.Thread(target=check_and_increment, daemon=True)
    increment_thread.start()
    
    app.run(host='0.0.0.0', port=5001, debug=False)
