import time, hmac, hashlib, base64
from aiortc import RTCIceServer
import os, asyncio, uuid
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
import db
from bot import run
app=FastAPI(); db.init(); sessions={}
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['*'],allow_headers=['*'])
@app.get('/api/dashboard')
def dashboard():
    with db.connect() as c: doctors=[dict(r) for r in c.execute('SELECT * FROM doctors')]
    a=db.appointments()
    for x in a: x['phone']='••••••'+x['phone'][-4:]
    return {'doctors':doctors,'slots':db.availability(),'appointments':a}

def turn_credentials():
    secret = os.getenv("TURN_SECRET")
    url = os.getenv("TURN_URL")

    if not secret or not url:
        return []

    username = str(int(time.time()) + 3600) + ":caredesk"
    credential = base64.b64encode(
        hmac.new(
            secret.encode(),
            username.encode(),
            hashlib.sha1
        ).digest()
    ).decode()

    return [{
        "urls": url,
        "username": username,
        "credential": credential
    }]

@app.get("/api/ice-config")
def ice_config():
    return {"iceServers": turn_credentials()}

def backend_ice_servers():
    servers = turn_credentials()
    backend_url = os.getenv("TURN_BACKEND_URL")
    if backend_url:
        for server in servers:
            server["urls"] = backend_url
    return [RTCIceServer(**server) for server in servers]

@app.post('/api/offer')
async def offer(data:dict):
    if not all(os.getenv(k) for k in ('ELEVENLABS_API_KEY','GOOGLE_API_KEY')): raise HTTPException(503,'Configure API keys in backend/.env')
    connection=SmallWebRTCConnection(ice_servers=backend_ice_servers()); await connection.initialize(sdp=data['sdp'],type=data['type']); sid=uuid.uuid4().hex; events=[]
    async def worker():
        try: await run(connection,events)
        except Exception as e: events.append({'role':'error','text':str(e)})
    task=asyncio.create_task(worker()); sessions[sid]=(connection,events,task)
    return {**connection.get_answer(),'session_id':sid}
@app.get('/api/events/{sid}')
def events(sid:str,after:int=0):
    if sid not in sessions: raise HTTPException(404)
    return sessions[sid][1][after:]
@app.delete('/api/session/{sid}')
async def end(sid:str):
    entry=sessions.pop(sid,None)
    if entry:
        connection,_,task=entry; await connection.disconnect(); task.cancel(); await asyncio.gather(task,return_exceptions=True)
    return {'ok':True}
