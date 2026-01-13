import React, { useState, useEffect } from 'react';
import { Upload, FileText, AlertTriangle, ChevronDown, ChevronRight, CheckCircle, RefreshCw, DollarSign } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

// --- API CONFIG ---
const API_URL = 'http://127.0.0.1:5000/api';

const App = () => {
  const [activeTab, setActiveTab] = useState('upload');
  const [year, setYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState(null);

  // Data States
  const [drilldownData, setDrilldownData] = useState([]);
  const [valuationData, setValuationData] = useState(null);
  
  // Valuation Assumptions
  const [assumptions, setAssumptions] = useState({
    wacc: 0.10,
    growth_rate: 0.02,
    ebitda_multiple: 8.0
  });

  const showNotify = (msg, type = 'success') => {
    setNotification({ msg, type });
    setTimeout(() => setNotification(null), 3000);
  };

  // --- COMPONENT: FILE UPLOAD ---
  const UploadSection = () => {
    const handleUpload = async (type, file) => {
      if (!file) return;
      setLoading(true);
      const formData = new FormData();
      formData.append('file', file);
      formData.append('year', year);

      const endpoint = type === 'pdf' ? '/upload-report' : '/upload-tb';
      
      try {
        const res = await fetch(`${API_URL}${endpoint}`, { method: 'POST', body: formData });
        const data = await res.json();
        if (res.ok) {
          showNotify(`${type.toUpperCase()} Uploaded Successfully`);
          if (type === 'tb') fetchDrilldown(); // Auto-refresh data
        } else {
          showNotify(data.error, 'error');
        }
      } catch (e) {
        showNotify("Upload Failed", 'error');
      }
      setLoading(false);
    };

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-6">
        {['pdf', 'tb'].map((type) => (
          <div key={type} className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-blue-500 transition-colors bg-white">
            <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-semibold capitalize mb-2">{type === 'pdf' ? 'Financial Statement (PDF)' : 'Trial Balance (Excel)'}</h3>
            <p className="text-sm text-gray-500 mb-4">Upload the {year} {type.toUpperCase()} file.</p>
            <input 
              type="file" 
              accept={type === 'pdf' ? ".pdf" : ".xlsx"}
              onChange={(e) => handleUpload(type, e.target.files[0])}
              className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
          </div>
        ))}
      </div>
    );
  };

  // --- COMPONENT: DRILL DOWN & REVIEW ---
  const DrillDownSection = () => {
    const [expandedRow, setExpandedRow] = useState(null);
    const [editMode, setEditMode] = useState(null); // { accountName, currentLine }

    const handleReMap = async (account, newLine) => {
      setLoading(true);
      try {
        await fetch(`${API_URL}/update-mapping`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            year,
            updates: [{ account, new_line_item: newLine }]
          })
        });
        showNotify("Mapping Updated");
        fetchDrilldown(); // Refresh
        setEditMode(null);
      } catch (e) {
        showNotify("Update Failed", 'error');
      }
      setLoading(false);
    };

    return (
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <div className="p-4 border-b bg-gray-50 flex justify-between items-center">
          <h2 className="font-bold text-gray-700">Financial Data Review ({year})</h2>
          <button onClick={fetchDrilldown} className="p-2 hover:bg-gray-200 rounded-full"><RefreshCw size={16}/></button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-gray-100 text-gray-600 uppercase font-bold">
              <tr>
                <th className="p-3">Line Item</th>
                <th className="p-3 text-right">Reported (PDF)</th>
                <th className="p-3 text-right">Calculated (TB)</th>
                <th className="p-3 text-right">Delta</th>
                <th className="p-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {drilldownData.map((row) => (
                <React.Fragment key={row.line_item}>
                  <tr 
                    className={`border-b hover:bg-gray-50 cursor-pointer ${row.is_mismatch ? 'bg-red-50' : ''}`}
                    onClick={() => setExpandedRow(expandedRow === row.line_item ? null : row.line_item)}
                  >
                    <td className="p-3 flex items-center font-medium">
                      {expandedRow === row.line_item ? <ChevronDown size={16} className="mr-2"/> : <ChevronRight size={16} className="mr-2"/>}
                      {row.line_item}
                    </td>
                    <td className="p-3 text-right">{row.reported_value.toLocaleString()}</td>
                    <td className="p-3 text-right">{row.calculated_value.toLocaleString()}</td>
                    <td className={`p-3 text-right font-bold ${row.is_mismatch ? 'text-red-600' : 'text-green-600'}`}>
                      {row.delta.toFixed(2)}
                    </td>
                    <td className="p-3 text-center">
                      {row.is_mismatch ? <AlertTriangle className="text-red-500 mx-auto" size={18}/> : <CheckCircle className="text-green-500 mx-auto" size={18}/>}
                    </td>
                  </tr>
                  
                  {/* Expanded Drill Down */}
                  {expandedRow === row.line_item && (
                    <tr className="bg-gray-50">
                      <td colSpan={5} className="p-4 pl-10">
                        <div className="text-xs font-bold text-gray-500 mb-2 uppercase tracking-wide">Contributing TB Accounts</div>
                        <table className="w-full text-xs">
                          <tbody>
                            {row.contributing_accounts.map((acc, idx) => (
                              <tr key={idx} className="border-b border-gray-200 last:border-0">
                                <td className="py-2 text-gray-700 w-1/2">{acc.account}</td>
                                <td className="py-2 text-right w-1/4">{acc.amount.toLocaleString()}</td>
                                <td className="py-2 text-right">
                                  {editMode?.account === acc.account ? (
                                    <div className="flex items-center justify-end space-x-2">
                                      <input 
                                        className="border rounded px-2 py-1" 
                                        placeholder="New Line Item..."
                                        onKeyDown={(e) => e.key === 'Enter' && handleReMap(acc.account, e.target.value)}
                                      />
                                      <button onClick={() => setEditMode(null)} className="text-red-500">X</button>
                                    </div>
                                  ) : (
                                    <button 
                                      onClick={() => setEditMode({ account: acc.account })}
                                      className="text-blue-600 hover:underline"
                                    >
                                      Edit Mapping
                                    </button>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  // --- COMPONENT: VALUATION ---
  const ValuationSection = () => {
    const handleRunValuation = async () => {
      setLoading(true);
      try {
        // First ensure schedules are generated
        await fetch(`${API_URL}/generate-schedules`);
        
        // Then run valuation
        const res = await fetch(`${API_URL}/calculate-valuation`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(assumptions)
        });
        const data = await res.json();
        
        // Add EBITDA Method Calculation (Client-side logic or enhanced backend)
        const ebitdaVal = (data.projections[0]?.fcfe || 1000) * assumptions.ebitda_multiple; // Simplified proxy
        setValuationData({ ...data, ebitda_valuation: ebitdaVal });
      } catch (e) {
        showNotify("Valuation Error", 'error');
      }
      setLoading(false);
    };

    return (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Assumptions Sidebar */}
        <div className="bg-white p-6 rounded-lg shadow h-fit">
          <h3 className="font-bold text-gray-700 mb-4 flex items-center"><DollarSign size={18} className="mr-2"/> Assumptions</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-500">WACC (%)</label>
              <input 
                type="number" step="0.01" value={assumptions.wacc} 
                onChange={(e) => setAssumptions({...assumptions, wacc: parseFloat(e.target.value)})}
                className="w-full border rounded p-2 mt-1"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-500">Growth Rate (%)</label>
              <input 
                type="number" step="0.01" value={assumptions.growth_rate} 
                onChange={(e) => setAssumptions({...assumptions, growth_rate: parseFloat(e.target.value)})}
                className="w-full border rounded p-2 mt-1"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-500">EBITDA Multiple (x)</label>
              <input 
                type="number" step="0.5" value={assumptions.ebitda_multiple} 
                onChange={(e) => setAssumptions({...assumptions, ebitda_multiple: parseFloat(e.target.value)})}
                className="w-full border rounded p-2 mt-1"
              />
            </div>
            <button 
              onClick={handleRunValuation}
              className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 font-semibold"
            >
              Calculate Valuation
            </button>
          </div>
        </div>

        {/* Results Area */}
        <div className="lg:col-span-2 space-y-6">
          {valuationData ? (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-gradient-to-br from-blue-500 to-blue-700 text-white p-6 rounded-lg shadow">
                  <div className="text-blue-100 text-sm mb-1">DCF Valuation</div>
                  <div className="text-3xl font-bold">${valuationData.dcf_value.toLocaleString()}</div>
                </div>
                <div className="bg-gradient-to-br from-indigo-500 to-indigo-700 text-white p-6 rounded-lg shadow">
                  <div className="text-indigo-100 text-sm mb-1">EBITDA Multiple Valuation</div>
                  <div className="text-3xl font-bold">${valuationData.ebitda_valuation.toLocaleString()}</div>
                </div>
              </div>

              {/* Chart */}
              <div className="bg-white p-6 rounded-lg shadow">
                <h3 className="font-bold text-gray-700 mb-4">Projected Free Cash Flow</h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={valuationData.projections}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="fcfe" fill="#3b82f6" name="FCF to Equity" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </>
          ) : (
            <div className="bg-gray-50 border-2 border-dashed border-gray-200 rounded-lg h-full flex items-center justify-center text-gray-400">
              Run valuation to see results
            </div>
          )}
        </div>
      </div>
    );
  };

  // --- MAIN RENDER ---
  const fetchDrilldown = async () => {
    try {
      const res = await fetch(`${API_URL}/get-drilldown/${year}`);
      if (res.ok) setDrilldownData(await res.json());
    } catch(e) { console.error(e); }
  };

  return (
    <div className="min-h-screen bg-gray-100 text-slate-800 font-sans">
      {/* Header */}
      <nav className="bg-slate-900 text-white p-4 shadow-lg">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <div className="font-bold text-xl tracking-tight">FinVal<span className="text-blue-400">AI</span></div>
          <div className="flex items-center space-x-4">
            <span className="text-sm text-gray-400">Analysis Year:</span>
            <input 
              type="number" 
              value={year} 
              onChange={(e) => setYear(e.target.value)} 
              className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm w-20 text-center"
            />
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Navigation Tabs */}
        <div className="flex space-x-4 border-b border-gray-300 pb-2">
          {['upload', 'analysis', 'valuation'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 font-medium capitalize transition-colors ${
                activeTab === tab ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Notification Toast */}
        {notification && (
          <div className={`fixed top-20 right-6 px-6 py-3 rounded shadow-lg text-white ${notification.type === 'error' ? 'bg-red-500' : 'bg-green-600'}`}>
            {notification.msg}
          </div>
        )}

        {/* Conditional Views */}
        {loading && <div className="text-center py-10"><div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full mx-auto"></div><p className="mt-4 text-gray-500">Processing...</p></div>}
        
        {!loading && (
          <>
            {activeTab === 'upload' && <UploadSection />}
            {activeTab === 'analysis' && <DrillDownSection />}
            {activeTab === 'valuation' && <ValuationSection />}
          </>
        )}
      </main>
    </div>
  );
};

export default App;