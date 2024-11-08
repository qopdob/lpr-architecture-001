import json
import os
import re
from flask import Flask, request, send_file, send_from_directory
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
import io
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

app = Flask(__name__)

# Initialize Chrome options
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

def check_license_plate(plate):
    patterns = [
        (r'^([a-ce-z])(\d{3})([a-ce-z]{2})(\d{2,3})$', "car"),  # 'a000aa00'
        (r'^([a-ce-z]{2})(\d{3})(\d{2,3})$', "public"),  # 'aa00000'
        (r'^(\d{4})([a-ce-z]{2})(\d{2,3})$', "military"),  # '0000aa00'
        (r'^(\d{3})(d)(\d{3})(\d{2,3})$', "diplomatic"),  # '000d00000'
        (r'^([a-ce-z])(\d{4})(\d{2,3})$', "police"),  # 'a000000'
    ]

    for pattern, plate_type in patterns:
        match = re.match(pattern, plate)
        if match:
            parts = match.groups()
            return True, plate_type, parts

    return False, None, None


@app.route('/fonts/<path:filename>')
def serve_fonts(filename):
    return send_from_directory('/app/static/fonts', filename)


@app.route('/license_plate')
def serve_license_plate():
    return send_from_directory('/app', 'license_plate_template.html')


@app.route('/generate_image', methods=['GET'])
def generate_image():
    # Get plate from query parameters
    plate = request.args.get('plate')

    if not plate:
        return "No plate provided", 400

    # Check if the image already exists
    image_path = f"/plates/{plate}.jpg"
    if os.path.exists(image_path):
        return send_file(image_path, mimetype='image/jpeg')

    # Validate and process the license plate
    is_valid, plate_type, parts = check_license_plate(plate.lower())
    if not is_valid:
        return "Invalid license plate format", 400

    # Create a new Chrome driver instance
    driver = webdriver.Remote(
        command_executor='http://selenium:4444/wd/hub',
        options=chrome_options
    )

    try:
        # Load the HTML file
        driver.get(f"http://plate:5050/license_plate")

        # Execute JavaScript to set up the license plate
        driver.execute_script(f"setupLicensePlate('{plate_type}', {json.dumps(parts)})")

        # Capture the license plate element
        wait = WebDriverWait(driver, 10)
        license_plate = wait.until(EC.presence_of_element_located((By.ID, "license-plate-wrapper")))

        # Get the screenshot of the element
        png = license_plate.screenshot_as_png

        # Convert PNG to JPEG
        img = Image.open(io.BytesIO(png))
        img.save(image_path, format='JPEG', quality=30)

        return send_file(image_path, mimetype='image/jpeg')

    finally:
        driver.quit()


if __name__ == '__main__':
    os.makedirs("/plates", exist_ok=True)
    app.run(host='0.0.0.0', port=5050)


