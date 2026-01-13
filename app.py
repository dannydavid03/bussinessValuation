from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Import our logic engine
import logic

# Setup
load_dotenv()
app = Flask(__name__)
CORS(app) # Enable React to talk to Flask

# Config
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Initialize AI
logic.configure_genai(os.getenv("GEMINI_API_KEY"))

# --- ROUTES ---

@app.route('/api/upload-report', methods=['POST'])
def upload_report():
    """
    Step 1: Upload PDF -> Extract JSON.
    Optimization: Checks if analysis for this year already exists to avoid re-processing.
    """
    # 1. Validate Input
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    year = request.form.get('year')

    if not year:
        return jsonify({"error": "Year is required"}), 400
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # 2. Check Cache (Optimization)
    # If we have already analyzed this year, return the existing data immediately.
    json_filename = f"extracted_data_{year}.json"
    json_path = os.path.join(OUTPUT_FOLDER, json_filename)

    if os.path.exists(json_path):
        print(f"[INFO] Analysis for {year} found. Skipping AI extraction.")
        with open(json_path, 'r') as f:
            existing_data = json.load(f)
        return jsonify({
            "message": "Loaded from cache", 
            "data": existing_data,
            "cached": True
        })

    # 3. Process New File
    # Only runs if cache miss
    print(f"[INFO] No data found for {year}. Starting AI extraction...")
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    try:
        # Run AI Extraction (Logic from logic.py)
        data = logic.extract_financial_data_ai(filepath, year)
        
        # Save Result for future caching
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=4)
            
        return jsonify({
            "message": "Extraction Successful", 
            "data": data,
            "cached": False
        })

    except Exception as e:
        print(f"[ERROR] Extraction failed: {e}")
        # Clean up the PDF if it failed to prevent junk buildup
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": str(e)}), 500

@app.route('/api/upload-tb', methods=['POST'])
def upload_tb():
    """Step 2: Upload Excel TB -> Map to FS Lines"""
    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    
    file = request.files['file']
    year = request.form.get('year')
    
    if not year: return jsonify({"error": "Year required"}), 400

    # --- NEW: Check Cache Optimization ---
    # Check if a mapped file already exists for this year
    mapped_filename = f"mapped_tb_{year}.xlsx"
    mapped_path = os.path.join(OUTPUT_FOLDER, mapped_filename)

    if os.path.exists(mapped_path):
        print(f"[INFO] Mapping for {year} found. Skipping AI mapping.")
        return jsonify({
            "message": "Loaded from cache", 
            "mapped_file_url": f"/download/{mapped_filename}",
            "cached": True
        })
    # -------------------------------------
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    # Locate the extracted JSON from Step 1 to map against
    fs_json_path = os.path.join(OUTPUT_FOLDER, f"extracted_data_{year}.json")
    if not os.path.exists(fs_json_path):
        return jsonify({"error": f"Please upload PDF Report for {year} first"}), 400
        
    try:
        mapped_file = logic.map_trial_balance(filepath, fs_json_path, year)
        return jsonify({
            "message": "Mapping Complete", 
            "mapped_file_url": f"/download/{os.path.basename(mapped_file)}",
            "cached": False
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/generate-schedules', methods=['GET'])
def get_schedules():
    """Step 3: Generate Dynamic Schedules from all mapped TBs"""
    try:
        schedules = logic.generate_schedules_logic()
        if not schedules:
            return jsonify({"error": "No mapped data found. Upload TBs first."}), 404
            
        # Save for Valuation step
        with open(os.path.join(OUTPUT_FOLDER, "schedules_data.json"), 'w') as f:
            json.dump(schedules, f)
            
        return jsonify(schedules)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/calculate-valuation', methods=['POST'])
def calculate_valuation():
    """Step 4: Run DCF/EBITDA Valuation"""
    assumptions = request.json or {}
    
    try:
        # Load Schedules
        sched_path = os.path.join(OUTPUT_FOLDER, "schedules_data.json")
        if not os.path.exists(sched_path):
            return jsonify({"error": "Generate schedules first"}), 400
            
        with open(sched_path) as f:
            schedules_data = json.load(f)
            
        valuation = logic.run_valuation_logic(schedules_data, assumptions)
        return jsonify(valuation)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return send_file(os.path.join(OUTPUT_FOLDER, filename), as_attachment=True)

@app.route('/api/get-drilldown/<year>', methods=['GET'])
def get_drilldown(year):
    data = logic.get_mapping_details(year)
    if data is None:
        return jsonify({"error": "Data not found for this year"}), 404
    return jsonify(data)

@app.route('/api/update-mapping', methods=['POST'])
def update_mapping_endpoint():
    req = request.json
    year = req.get('year')
    updates = req.get('updates') # List of changes
    
    success = logic.update_mapping(year, updates)
    if success:
        return jsonify({"message": "Mapping updated successfully"})
    return jsonify({"error": "Update failed"}), 500
if __name__ == '__main__':
    app.run(debug=True, port=5000)