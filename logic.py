import os
import json
import glob
import pandas as pd
import google.generativeai as genai
from pypdf import PdfReader, PdfWriter
from google.api_core import exceptions
import time

# --- CONFIGURATION ---
SCHEDULE_MAPPING = {
    "Revenue Schedule": ["Revenue", "Sales", "Income", "Room", "Walking", "Breakfast", "Online"],
    "Direct Costs Schedule": ["Cost of Sales", "Direct Costs", "Food Cost", "Beverage Cost"],
    "Indirect Costs Schedule": ["Administrative", "Selling", "Other expenses", "Operating", "Marketing", "Rent", "Utilities"],
    "Bank Borrowings Schedule": ["Bank borrowings", "Loans", "Long term liabilities"],
    "PPE Schedule": ["Property and equipment", "Fixed Assets", "Depreciation"],
    "Intangible Assets Schedule": ["Intangible", "Amortisation", "Goodwill"],
    "Working Capital Schedule": ["Trade and other receivables", "Inventories", "Trade and other payables", "Prepayments"]
}

def configure_genai(api_key):
    genai.configure(api_key=api_key)

# ==========================================
# 1. PDF EXTRACTION (From your newFinanceRead.py)
# ==========================================
def filter_relevant_pages(input_path, output_path):
    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        statement_keywords = ["statement of financial position", "balance sheet", "profit or loss", "income statement", "cash flows"]
        notes_started = False
        pages_to_include = set()

        for i, page in enumerate(reader.pages):
            text = page.extract_text().lower() if page.extract_text() else ""
            if any(kw in text for kw in statement_keywords):
                pages_to_include.add(i)
            if "notes to the financial statements" in text:
                notes_started = True
            if notes_started:
                pages_to_include.add(i)

        if not pages_to_include: return input_path # Fallback

        for page_num in sorted(list(pages_to_include)):
            writer.add_page(reader.pages[page_num])
        
        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path
    except Exception as e:
        print(f"PDF Filter Error: {e}")
        return input_path

def extract_financial_data_ai(pdf_path, year):
    temp_path = pdf_path.replace(".pdf", "_filtered.pdf")
    processed_path = filter_relevant_pages(pdf_path, temp_path)
    
    model = genai.GenerativeModel("gemini-1.5-flash") # Use Flash for speed/quota
    
    # Retry logic
    for attempt in range(3):
        try:
            sample_file = genai.upload_file(path=processed_path, display_name="FinReport")
            while sample_file.state.name == "PROCESSING":
                time.sleep(1)
                sample_file = genai.get_file(sample_file.name)

            prompt = f"""
            Extract 'Statement of Financial Position', 'Profit or Loss', 'Cash Flows', and 'Notes' for year {year}.
            Return strictly JSON with keys: "financial_position", "profit_loss", "cash_flow", "notes".
            Rows structure: {{"line_item": "name", "current_year": 123.00, "note_ref": "5"}}
            Notes structure: Key=NoteNum, Value={{"text": "...", "table_data": [...]}}
            Ensure numbers are raw floats (no commas).
            """
            
            response = model.generate_content([sample_file, prompt], generation_config={"response_mime_type": "application/json"})
            return json.loads(response.text)
        except Exception as e:
            time.sleep(5 * (attempt + 1))
    
    raise Exception("AI Extraction failed after retries")

# ==========================================
# 2. TB MAPPING
# ==========================================
def map_trial_balance(tb_path, fs_json_path, year):
    # 1. Load TB
    df = pd.read_excel(tb_path, header=0) # Assume Row 1 is header
    # Normalize cols
    df.columns = df.columns.str.strip().str.lower()
    # Simple column mapper
    col_map = {}
    for c in df.columns:
        if "description" in c: col_map[c] = "Description"
        elif "debit" in c: col_map[c] = "Debit"
        elif "credit" in c: col_map[c] = "Credit"
    
    df.rename(columns=col_map, inplace=True)
    df["Net_Amount"] = pd.to_numeric(df["Debit"], errors='coerce').fillna(0) - pd.to_numeric(df["Credit"], errors='coerce').fillna(0)

    # 2. Get FS Targets
    with open(fs_json_path) as f:
        fs_data = json.load(f)
    targets = []
    for cat in ["financial_position", "profit_loss"]:
        if cat in fs_data:
            targets += [x["line_item"] for x in fs_data[cat]]
    
    # 3. AI Mapping (Simplified for batching)
    model = genai.GenerativeModel("gemini-1.5-flash")
    unique_accts = df["Description"].dropna().unique().tolist()
    
    prompt = f"""
    Map these TB accounts to these FS line items.
    FS Items: {json.dumps(targets[:50])} ... (and more)
    TB Accounts: {json.dumps(unique_accts)}
    Return JSON: {{"TB Account Name": "FS Line Item"}}
    """
    
    try:
        resp = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        mapping = json.loads(resp.text)
        df["Mapped_FS_Line"] = df["Description"].map(mapping).fillna("Unclassified")
        
        output_path = f"outputs/mapped_tb_{year}.xlsx"
        df.to_excel(output_path, index=False)
        return output_path
    except Exception as e:
        print(f"Mapping Error: {e}")
        return None

# ==========================================
# 3. SCHEDULES & VALUATION
# ==========================================
def generate_schedules_logic():
    # Load all mapped TBs
    files = glob.glob("outputs/mapped_tb_*.xlsx")
    data_by_year = {}
    for f in files:
        y = int(f.split('_')[-1].split('.')[0])
        data_by_year[y] = pd.read_excel(f)
    
    if not data_by_year: return None
    
    hist_years = sorted(data_by_year.keys())
    proj_years = [hist_years[-1] + i for i in range(1, 6)]
    
    schedules = []
    
    # Helper to generate rows
    for sched_name, keywords in SCHEDULE_MAPPING.items():
        rows = []
        # Find accounts that match keywords
        all_accts = set()
        for df in data_by_year.values():
            mask = df['Mapped_FS_Line'].astype(str).apply(lambda x: any(k.lower() in x.lower() for k in keywords))
            all_accts.update(df.loc[mask, 'Description'].unique())
            
        for acct in all_accts:
            hist_vals = {}
            for y in hist_years:
                df = data_by_year[y]
                val = df.loc[df['Description'] == acct, "Net_Amount"].sum()
                hist_vals[y] = abs(val)
            
            # Calc Growth
            vals = list(hist_vals.values())
            growth = 0.05
            if len(vals) > 1 and vals[-2] != 0:
                growth = (vals[-1] - vals[-2]) / vals[-2]
            
            # Project
            proj_vals = {}
            curr = vals[-1]
            for py in proj_years:
                curr = curr * (1 + growth)
                proj_vals[py] = round(curr, 2)
            
            rows.append({
                "name": acct,
                "historical": hist_vals,
                "driver": {"type": "growth", "value": round(growth, 4)},
                "projected": proj_vals
            })
        
        schedules.append({"title": sched_name, "rows": rows})
        
    return {"meta": {"historical": hist_years, "projection": proj_years}, "schedules": schedules}

def run_valuation_logic(schedules_data, assumptions):
    # This rebuilds the Income Statement from Schedules and runs DCF
    proj_years = schedules_data["meta"]["projection"]
    
    # 1. Aggregate P&L
    pnl = {y: {"Revenue": 0, "EBITDA": 0, "Depreciation": 0} for y in proj_years}
    
    for sched in schedules_data["schedules"]:
        for row in sched["rows"]:
            for y in proj_years:
                val = row["projected"][str(y)]
                if "Revenue" in sched["title"]: pnl[y]["Revenue"] += val
                elif "Direct" in sched["title"] or "Indirect" in sched["title"]: pnl[y]["EBITDA"] -= val # Expense
                elif "PPE" in sched["title"]: pnl[y]["Depreciation"] += (val * 0.15) # Proxy
    
    # 2. Fix EBITDA (Add Revenue back to the negative costs)
    for y in proj_years:
        pnl[y]["EBITDA"] += pnl[y]["Revenue"]
        
    # 3. DCF
    dcf_res = []
    cumulative_pv = 0
    wacc = assumptions.get("wacc", 0.10)
    
    for i, y in enumerate(proj_years, 1):
        ebitda = pnl[y]["EBITDA"]
        tax = (ebitda - pnl[y]["Depreciation"]) * 0.09
        capex = pnl[y]["Revenue"] * 0.05
        fcfe = (ebitda - tax) - capex # Simplified
        
        pv = fcfe / ((1+wacc)**i)
        cumulative_pv += pv
        dcf_res.append({"year": y, "fcfe": fcfe, "pv": pv})
        
    return {"dcf_value": round(cumulative_pv, 2), "projections": dcf_res}