#!/bin/bash

cd /home/dsackr/safety-tracker
source venv/bin/activate

python3 << 'EOF'
from datetime import datetime
from app import generate_sign, display_on_epaper, OUTPUT_IMAGE

# Regenerate sign (it will auto-calculate days from incident date)
generate_sign(auto_display=False)
display_on_epaper(OUTPUT_IMAGE)

print(f"Daily update completed at {datetime.now()}")
EOF
