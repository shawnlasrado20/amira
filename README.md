# Koralyn × Cake N More Voice Demo

A client-facing AI receptionist demo for Cake N More. Visitors can speak with Lina in the browser and test birthday-cake, custom-design, and delivery enquiries.

## Architecture

- **Frontend:** Vite + Pipecat JavaScript client, deployed on Vercel
- **Realtime transport:** Pipecat browser WebSocket
- **Backend:** Pipecat on Railway
- **Voice pipeline:** Smallest AI STT → Groq LLM → Murf Falcon TTS
- **Knowledge:** Cake N More facts are loaded server-side from `pipecat-amira/knowledge/cake-n-more.md`

The public demo is limited to three minutes per browser session. It never confirms real orders, payments, or deliveries.

## Local frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Set `VITE_API_URL` to the backend URL. For production, use the Railway public domain.

## Local backend

```bash
cd pipecat-amira
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py --host 0.0.0.0 --port 7860 -t websocket --ws-auth none
```

Required backend variables:

- `SMALLEST_API_KEY`
- `MURF_API_KEY`
- `KORALYN_GROQ_API_KEY` (or `GROQ_API_KEY`)
- `ALLOWED_ORIGINS` (the Vercel URL)

## Deploy

1. Connect this repository to Railway. Railway uses the root `Dockerfile` and `railway.json`.
2. Add the backend variables above and generate a Railway public domain.
3. Import the same repository into Vercel. Vercel uses `vercel.json` and builds only the Cake N More demo.
4. Set `VITE_API_URL=https://your-service.up.railway.app` in Vercel, then redeploy.

`pipecat-amira/server.py` remains available as the local SmallWebRTC development server. The Railway demo uses Pipecat's browser WebSocket runner and needs no separate realtime-transport account.

## Security

Real API keys belong only in local `.env` files or hosting-provider environment settings. They are ignored by Git and must never be added to frontend variables.
