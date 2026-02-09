$env:GOOGLE_APPLICATION_CREDENTIALS="C:\Users\harsh\NAVISOUND\config\gcp-key.json"
Set-Location C:\Users\harsh\NAVISOUND\backend\agents
python -m uvicorn orchestrator:app --host 0.0.0.0 --port 8000
