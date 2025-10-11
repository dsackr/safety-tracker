from flask import Flask, render_template, request, redirect, url_for, send_file
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import os
import json
import requests

# Configuration variables for easy positioning adjustments
# Font sizes
FONT_SIZE_DAYS = 400
FONT_SIZE_PRIOR_COUNT = 150
FONT_SIZE_INCIDENT = 100
FONT_SIZE_CHECKMARK = 80

# Position adjustments for main days counter
DAYS_Y_POSITION = 160
DAYS_X_OFFSET = 0

# Position adjustments for prior count (blue box)
PRIOR_COUNT_X = 220
PRIOR_COUNT_Y = 630

# Position adjustments for incident number (red box)
INCIDENT_X_OFFSET = 70
INCIDENT_Y = 650

# Position adjustments for checkmarks (right box)
CHECKMARK_X = 940
CHECKMARK_CHANGE_Y = 575
CHECKMARK_DEPLOY_Y = 645
CHECKMARK_MISSED_Y = 705

app = Flask(__name__)

# Data file
DATA_FILE = 'data.json'
BACKGROUND_IMAGE = 'static/background.png'
OUTPUT_IMAGE = 'static/current_sign.png'

# E-Paper Display Configuration (Pi Zero)
EINK_DISPLAY_IP = "192.168.86.120"  # Replace with your Pi Zero IP address
EINK_DISPLAY_PORT = 5000

# 6-color palette for E-Paper display
PALETTE = {
    'black': (0, 0, 0, 0x0),
    'white': (255, 255, 255, 0x1),
    'yellow': (255, 255, 0, 0x2),
    'red': (200, 80, 50, 0x3),
    'blue': (100, 120, 180, 0x5),
    'green': (200, 200, 80, 0x6)
}

def rgb_to_palette_code(r, g, b):
    """Find closest color in 6-color palette"""
    min_distance = float('inf')
    closest_code = 0x1
    
    for color_name, (pr, pg, pb, code) in PALETTE.items():
        distance = (r - pr)**2 + (g - pg)**2 + (b - pb)**2
        if distance < min_distance:
            min_distance = distance
            closest_code = code
    
    return closest_code

def convert_image_to_binary(img):
    """Convert PIL Image to binary format for E-Paper display"""
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    img_ratio = img.width / img.height
    display_ratio = 800 / 480
    
    if img_ratio > display_ratio:
        new_height = 480
        new_width = int(480 * img_ratio)
    else:
        new_width = 800
        new_height = int(800 / img_ratio)
    
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - 800) // 2
    top = (new_height - 480) // 2
    img = img.crop((left, top, left + 800, top + 480))
    
    # Use dithering with the 6-color palette
    palette_data = [
        0, 0, 0, 255, 255, 255, 255, 255, 0,
        200, 80, 50, 100, 120, 180, 200, 200, 80
    ]
    palette_img = Image.new('P', (1, 1))
    palette_img.putpalette(palette_data + [0] * (256 * 3 - len(palette_data)))
    img = img.quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)
    img = img.convert('RGB')
    
    binary_data = bytearray(192000)
    
    for row in range(480):
        for col in range(0, 800, 2):
            r1, g1, b1 = img.getpixel((col, row))
            r2, g2, b2 = img.getpixel((col + 1, row))
            
            code1 = rgb_to_palette_code(r1, g1, b1)
            code2 = rgb_to_palette_code(r2, g2, b2)
            
            byte_index = row * 400 + col // 2
            binary_data[byte_index] = (code1 << 4) | code2
    
    return bytes(binary_data)

def display_on_epaper(img_path):
    """Send image to Pi Zero e-paper display"""
    try:
        print(f"Converting and sending image: {img_path}")
        
        if not os.path.exists(img_path):
            print(f"ERROR: Image file not found at {img_path}")
            return False
        
        # Load and convert image
        img = Image.open(img_path)
        binary_data = convert_image_to_binary(img)
        
        # Send to Pi Zero E-Paper Display
        print(f"Sending to E-Paper Display at {EINK_DISPLAY_IP}:{EINK_DISPLAY_PORT}...")
        response = requests.post(
            f'http://{EINK_DISPLAY_IP}:{EINK_DISPLAY_PORT}/display/binary',
            files={'file': ('sign.bin', binary_data)},
            headers={'Connection': 'keep-alive'},
            timeout=120
        )
        
        if response.status_code == 200:
            print("Successfully sent to E-Paper Display!")
            return True
        else:
            print(f"Error from E-Paper Display: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"EXCEPTION in display_on_epaper: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def load_data():
    """Load tracking data from JSON file"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        'days_since': 1,
        'prior_count': 2,
        'incident_number': '540',
        'incident_date': '2025-10-03',
        'prior_incident_date': '2025-10-01',
        'reason': 'Deploy',
        'last_reset': datetime.now().isoformat()
    }

def save_data(data):
    """Save tracking data to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def generate_sign(auto_display=False):
    """Generate the safety sign with current data"""
    data = load_data()
    
    # Calculate days since current incident date
    if 'incident_date' in data:
        incident_date = datetime.fromisoformat(data['incident_date'])
        today = datetime.now()
        days_since = (today.date() - incident_date.date()).days
    else:
        days_since = data.get('days_since', 0)
    
    # Calculate prior count
    if 'prior_incident_date' in data and 'incident_date' in data:
        prior_date = datetime.fromisoformat(data['prior_incident_date'])
        current_date = datetime.fromisoformat(data['incident_date'])
        prior_count = (current_date.date() - prior_date.date()).days
    else:
        prior_count = data.get('prior_count', 0)
    
    data['days_since'] = days_since
    data['prior_count'] = prior_count
    
    # Open background image
    img = Image.open(BACKGROUND_IMAGE)
    draw = ImageDraw.Draw(img)
    
    img_width, img_height = img.size
    
    # Load fonts
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
    
    # Draw main days count
    days_text = str(data['days_since'])
    days_bbox = draw.textbbox((0, 0), days_text, font=days_font)
    days_width = days_bbox[2] - days_bbox[0]
    days_x = (img_width - days_width) // 2 + DAYS_X_OFFSET
    days_y = DAYS_Y_POSITION
    draw.text((days_x, days_y), days_text, font=days_font, fill='black')
    
    # Draw prior count
    prior_text = str(data['prior_count'])
    prior_bbox = draw.textbbox((0, 0), prior_text, font=count_font)
    prior_width = prior_bbox[2] - prior_bbox[0]
    prior_x = PRIOR_COUNT_X - (prior_width // 2)
    prior_y = PRIOR_COUNT_Y
    draw.text((prior_x, prior_y), prior_text, font=count_font, fill='white')
    
    # Draw incident number
    inc_text = data['incident_number']
    inc_bbox = draw.textbbox((0, 0), inc_text, font=inc_font)
    inc_width = inc_bbox[2] - inc_bbox[0]
    inc_x = (img_width // 2) - (inc_width // 2) + INCIDENT_X_OFFSET
    inc_y = INCIDENT_Y
    draw.text((inc_x, inc_y), inc_text, font=inc_font, fill='white')
    
    # Draw checkmark
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

@app.route('/send_to_display', methods=['POST'])
def send_to_display():
    """Manually send the current sign to the e-paper display"""
    if display_on_epaper(OUTPUT_IMAGE):
        return 'Sign sent to E-Paper display successfully! <a href="/">Go back</a>'
    else:
        return 'Error sending to display. Check logs. <a href="/">Go back</a>'

@app.route('/')
def index():
    data = load_data()
    
    if 'incident_date' in data:
        incident_date = datetime.fromisoformat(data['incident_date'])
        today = datetime.now()
        data['days_since'] = (today.date() - incident_date.date()).days
    
    if 'prior_incident_date' in data and 'incident_date' in data:
        prior_date = datetime.fromisoformat(data['prior_incident_date'])
        current_date = datetime.fromisoformat(data['incident_date'])
        data['prior_count'] = (current_date.date() - prior_date.date()).days
    
    return render_template('index.html', data=data)

@app.route('/update', methods=['POST'])
def update():
    data = load_data()
    
    if 'incident_date' in data:
        data['prior_incident_date'] = data['incident_date']
    
    data['incident_number'] = request.form.get('incident_number', '')
    data['incident_date'] = request.form.get('incident_date', '')
    data['reason'] = request.form.get('reason', 'Change')
    data['last_reset'] = datetime.now().isoformat()
    
    incident_date = datetime.fromisoformat(data['incident_date'])
    today = datetime.now()
    data['days_since'] = (today.date() - incident_date.date()).days
    
    if 'prior_incident_date' in data:
        prior_date = datetime.fromisoformat(data['prior_incident_date'])
        current_date = datetime.fromisoformat(data['incident_date'])
        data['prior_count'] = (current_date.date() - prior_date.date()).days
    
    save_data(data)
    generate_sign()
    
    return redirect(url_for('index'))

@app.route('/display')
def display():
    """Serve the current sign image"""
    return send_file(OUTPUT_IMAGE, mimetype='image/png')

if __name__ == '__main__':
    generate_sign()
    app.run(host='0.0.0.0', port=5001, debug=False)
