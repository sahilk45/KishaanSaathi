# Krishi-Sarthii 🌾

**Full-Stack Agri-Intelligence Platform** — A complete solution for Indian farmers featuring yield prediction, crop health scoring, loan eligibility assessment, and an AI-powered chatbot, built with a React (Vite/TypeScript) frontend and a FastAPI Python backend.

![Krishi-Sarthii Preview](Frontend/public/readme.png)

---

## Repository Structure

```
Krishi-Sarthii/
├── Frontend/         # React + TypeScript + Vite frontend (KrishiMitra)
└── krishisarthi-api/ # FastAPI Python backend
```

---

## Frontend — KrishiMitra

See [`Frontend/README.md`](Frontend/README.md) for frontend-specific documentation.

### Quick Start (Frontend)
```bash
cd Frontend
npm install
npm run dev
```

---

## Backend — KrishiSarthi API

See [`krishisarthi-api/README.md`](krishisarthi-api/README.md) for full backend documentation.

### Quick Start (Backend)
```bash
cd krishisarthi-api
pip install -r requirements.txt
cp env.example .env
# Fill in: DATABASE_URL, GROQ_API_KEY, AGRO_API_KEY
uvicorn main:app --reload --port 8000
```

Interactive API docs: **http://localhost:8000/docs**
