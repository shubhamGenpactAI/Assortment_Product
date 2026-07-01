# Terminal 1 — Backend
cd Assortment
python -m uvicorn Backend.main:app --reload --port 8000

# Terminal 2 — Frontend
cd Assortment/frontend
npm run dev
# → http://localhost:5173