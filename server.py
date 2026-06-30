#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""
Plivo XML Server
- Serves XML webhook for inbound calls → WebSocket streaming
- Provides /outbound-call endpoint to dial +91 80 3133 9945
- AI agent greets, collects Order ID, checks Zoho API, reads status
"""

import base64
import json
import os
from contextlib import asynccontextmanager

import plivo
import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket
from starlette import status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.responses import Response

# Load environment variables from .env file
load_dotenv()

# Import bot at startup to pre-warm VAD and libraries before any call comes in
from bot import bot
from database import (
    db_check_user_credentials,
    db_create_session,
    db_delete_session,
    db_get_all_calls,
    db_set_forwarded_transcript_by_uuid,
    db_verify_session,
    init_db,
    db_get_settings,
    db_update_settings,
    db_get_overall_stats,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Plivo AI Voice Agent",
    description="AI Voice Agent for Order Status — powered by Pipecat + Plivo",
    lifespan=lifespan,
)

# Allow cross-origin requests (useful for frontend triggers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve built React frontend assets if compiled
dist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
assets_path = os.path.join(dist_path, "assets")

if os.path.exists(assets_path):
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")


# ─── Helpers ──────────────────────────────────────────────────────────────────


def get_plivo_client() -> plivo.RestClient:
    """Return an authenticated Plivo REST client."""
    auth_id = os.getenv("PLIVO_AUTH_ID")
    auth_token = os.getenv("PLIVO_AUTH_TOKEN")
    if not auth_id or not auth_token:
        raise ValueError("PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN must be set in environment variables")
    return plivo.RestClient(auth_id, auth_token)


def get_websocket_url(host: str, body_data: dict | None = None) -> str:
    """Construct WebSocket URL based on environment variables with query parameters."""
    env = os.getenv("ENV", "local").lower()

    query_params = []

    if env == "production":
        agent_name = os.getenv("AGENT_NAME")
        org_name = os.getenv("ORGANIZATION_NAME")

        if not agent_name or not org_name:
            raise ValueError(
                "AGENT_NAME and ORGANIZATION_NAME must be set in environment variables for production"
            )

        service_host = f"{agent_name}.{org_name}"
        query_params.append(f"serviceHost={service_host}")
        print("If deployed in a region other than us-west (default), update websocket url!")
        base_url = "wss://api.pipecat.daily.co/ws/plivo"
        # Uncomment appropriate region URL if needed:
        # base_url = "wss://us-east.api.pipecat.daily.co/ws/plivo"
        # base_url = "wss://eu-central.api.pipecat.daily.co/ws/plivo"
        # base_url = "wss://ap-south.api.pipecat.daily.co/ws/plivo"
    else:
        base_url = f"wss://{host}/ws"

    if body_data:
        body_json = json.dumps(body_data)
        body_encoded = base64.b64encode(body_json.encode("utf-8")).decode("utf-8")
        query_params.append(f"body={body_encoded}")

    if query_params:
        joined = "&".join(query_params)
        return f"{base_url}?{joined}"
    else:
        return base_url


def build_stream_xml(websocket_url: str) -> str:
    """Return Plivo XML that starts bidirectional WebSocket audio streaming."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">
    {websocket_url}
  </Stream>
</Response>"""


# ─── Inbound Call Webhook ──────────────────────────────────────────────────────


@app.api_route("/", methods=["GET", "POST"])
async def start_inbound_call(
    request: Request,
    CallUUID: str = Query(None, description="Plivo call UUID"),
    From: str = Query(None, description="Caller's phone number"),
    To: str = Query(None, description="Called phone number"),
):
    """
    Webhook for Plivo inbound calls.
    Returns XML to start WebSocket audio streaming to the AI agent.

    Configure this URL as the Answer URL in your Plivo application/number.
    Example: https://your-ngrok-url.ngrok.io/
    """
    # If the user opens the root URL in a browser, redirect them to the dashboard
    accept_header = request.headers.get("accept", "")
    if request.method == "GET" and not CallUUID and not From and not To and "text/html" in accept_header:
        return RedirectResponse(url="/dashboard")

    # Plivo can send params in query or POST form data
    form_data = {}
    if request.method == "POST":
        try:
            form_data = await request.form()
        except Exception:
            pass

    raw_call_uuid = CallUUID or form_data.get("CallUUID")
    raw_from_number = From or form_data.get("From")
    raw_to_number = To or form_data.get("To")

    call_uuid = str(raw_call_uuid) if raw_call_uuid else None
    from_number = str(raw_from_number) if raw_from_number else None
    to_number = str(raw_to_number) if raw_to_number else None

    print(f"Inbound call — From: {from_number}, To: {to_number}, UUID: {call_uuid}")

    body_data = {}
    if call_uuid:
        body_data["call_uuid"] = call_uuid
    if from_number:
        body_data["from"] = from_number
    if to_number:
        body_data["to"] = to_number

    env = os.getenv("ENV", "local").lower()
    if env == "production":
        if not os.getenv("AGENT_NAME") or not os.getenv("ORGANIZATION_NAME"):
            raise HTTPException(
                status_code=500,
                detail="AGENT_NAME and ORGANIZATION_NAME must be set for production deployment",
            )

    host = request.headers.get("host")
    if not host:
        raise HTTPException(status_code=400, detail="Unable to determine server host")

    websocket_url = get_websocket_url(host, body_data if body_data else None)
    xml = build_stream_xml(websocket_url)
    return Response(content=xml, media_type="application/xml")


async def get_current_user(authorization: str = Header(None)):
    """FastAPI dependency to secure API routes using a Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication token"
        )
    token = authorization.split(" ")[1]
    username = db_verify_session(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid"
        )
    return username


# ─── Outbound Call Trigger ─────────────────────────────────────────────────────


class OutboundCallRequest(BaseModel):
    """Optional request body to override the default customer number."""
    customer_number: str | None = None  # defaults to PLIVO_CALLER_NUMBER from .env


@app.post("/outbound-call")
async def make_outbound_call(
    request: Request,
    body: OutboundCallRequest | None = None,
    username: str = Depends(get_current_user)
):
    """
    Trigger an outbound call to the customer (+91 80 3133 9945 by default).

    The call connects the customer to the AI voice agent which will:
    1. Greet the customer
    2. Ask for their Order ID
    3. Fetch order status from Zoho API
    4. Read out whether the order has been dispatched

    Request body (optional JSON):
    {
        "customer_number": "+919876543210"  // override the default customer number
    }
    """
    from_number = os.getenv("PLIVO_CALLER_NUMBER")
    if not from_number:
        raise HTTPException(
            status_code=500,
            detail="PLIVO_CALLER_NUMBER is not configured in environment variables",
        )

    # Resolve the TO number
    to_number = (body.customer_number if body and body.customer_number else None) or os.getenv(
        "PLIVO_CALLER_NUMBER", "+918031339945"
    )

    # The answer URL for the outbound call — routes through the same WebSocket agent
    host = request.headers.get("host")
    if not host:
        raise HTTPException(status_code=400, detail="Unable to determine server host")

    answer_url = f"https://{host}/outbound-answer"

    print(f"Initiating outbound call: {from_number} → {to_number}")
    print(f"Answer URL: {answer_url}")

    try:
        client = get_plivo_client()
        response = client.calls.create(
            from_=from_number,
            to_=to_number,
            answer_url=answer_url,
            answer_method="GET",
        )
        call_uuid = response[1].get("request_uuid") if isinstance(response, tuple) else str(response)
        print(f"Outbound call created — request UUID: {call_uuid}")
        return {
            "success": True,
            "message": f"Outbound call initiated to {to_number}",
            "from": from_number,
            "to": to_number,
            "request_uuid": call_uuid,
        }
    except Exception as e:
        print(f"Failed to initiate outbound call: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate call: {str(e)}")


@app.api_route("/outbound-answer", methods=["GET", "POST"])
async def outbound_answer_webhook(
    request: Request,
    CallUUID: str = Query(None),
    From: str = Query(None),
    To: str = Query(None),
):
    """
    Answer webhook for outbound calls.
    Plivo hits this URL when the customer answers the outbound call.
    Returns XML to connect the call to the AI WebSocket agent.
    """
    form_data = {}
    if request.method == "POST":
        try:
            form_data = await request.form()
        except Exception:
            pass

    raw_call_uuid = CallUUID or form_data.get("CallUUID")
    raw_from_number = From or form_data.get("From")
    raw_to_number = To or form_data.get("To")

    call_uuid = str(raw_call_uuid) if raw_call_uuid else None
    from_number = str(raw_from_number) if raw_from_number else None
    to_number = str(raw_to_number) if raw_to_number else None

    print(f"Outbound call answered — From: {from_number}, To: {to_number}, UUID: {call_uuid}")

    body_data = {"call_type": "outbound"}
    if call_uuid:
        body_data["call_uuid"] = call_uuid
    if from_number:
        body_data["from"] = from_number
    if to_number:
        body_data["to"] = to_number

    host = request.headers.get("host")
    if not host:
        raise HTTPException(status_code=400, detail="Unable to determine server host")

    websocket_url = get_websocket_url(host, body_data)
    xml = build_stream_xml(websocket_url)
    return Response(content=xml, media_type="application/xml")


# ─── Call Forwarding Webhook ──────────────────────────────────────────────────


@app.api_route("/forward-call", methods=["GET", "POST"])
async def forward_call_webhook(
    request: Request,
    ForwardTo: str = Query(None, description="Number to forward to (overrides env default)")
):
    """
    Webhook for forwarding the call.
    Returns XML to dial the support agent number.
    The target number is read from FORWARD_TO_NUMBER .
    """
    # Resolve forward-to number: query param > database settings > env var > hardcoded fallback
    settings = db_get_settings()
    db_forward_number = settings.get("forward_to_number")
    forward_number = ForwardTo or db_forward_number or os.getenv("FORWARD_TO_NUMBER")
    
    # Construct transcription callback URL
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    transcription_url = f"https://{host}/forward-transcription-callback"
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Record 
    startOnDialAnswer="true" 
    redirect="false" 
    transcriptionType="auto" 
    transcriptionUrl="{transcription_url}" 
    transcriptionMethod="POST" />
  <Dial>
    <Number>{forward_number}</Number>
  </Dial>
</Response>"""
    return Response(content=xml, media_type="application/xml")


@app.post("/forward-transcription-callback")
async def forward_transcription_callback(request: Request):
    """
    Callback endpoint where Plivo posts the transcription of the forwarded call.
    """
    try:
        form_data = await request.form()
        payload = dict(form_data)
    except Exception:
        payload = {}

    if not payload:
        try:
            payload = await request.json()
        except Exception:
            pass

    print(f"Received transcription callback: {payload}")

    raw_call_uuid = payload.get("call_uuid") or payload.get("CallUUID")
    raw_transcription = payload.get("transcription") or payload.get("TranscriptionText") or payload.get("transcription_text")

    call_uuid = str(raw_call_uuid) if raw_call_uuid else None
    transcription_text = str(raw_transcription) if raw_transcription else None

    if call_uuid and transcription_text:
        print(f"Saving transcription for call {call_uuid}: {transcription_text}")
        db_set_forwarded_transcript_by_uuid(call_uuid, transcription_text)
        return {"status": "success"}
    else:
        print(f"Missing call_uuid or transcription in callback: {payload}")
        return {"status": "ignored"}



# ─── WebSocket Handler ─────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Handle WebSocket connections from Plivo (both inbound and outbound calls)."""
    await websocket.accept()

    body_data = {}
    if body:
        try:
            decoded_json = base64.b64decode(body).decode("utf-8")
            body_data = json.loads(decoded_json)
        except Exception as e:
            pass

    try:
        from pipecat.runner.types import WebSocketRunnerArguments

        runner_args = WebSocketRunnerArguments(websocket=websocket)
        runner_args.handle_sigint = False

        call_uuid = str(body_data.get("call_uuid")) if body_data.get("call_uuid") else None
        from_number = str(body_data.get("from")) if body_data.get("from") else None
        host = websocket.headers.get("x-forwarded-host") or websocket.headers.get("host") or websocket.url.netloc
        await bot(runner_args, call_uuid=call_uuid, host=host, caller_number=from_number)

    except Exception as e:
        print(f"Error in WebSocket endpoint: {e}")
        import traceback
        traceback.print_exc()
        from starlette.websockets import WebSocketState
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass


# ─── Health Check ──────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Plivo AI Voice Agent",
        "caller_number": os.getenv("PLIVO_CALLER_NUMBER", "not configured"),
        "customer_number": os.getenv("PLIVO_CALLER_NUMBER", "not configured"),
        "env": os.getenv("ENV", "local"),
    }



# ─── Dashboard & API Endpoints ──────────────────────────────────────────────────


# ─── Auth Middleware & Models ──────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


# ─── Auth Endpoints ────────────────────────────────────────────────────────────

# (Verify-token endpoint removed. Token validation is performed directly on authenticated resource requests)


@app.post("/api/login")
async def login_api(body: LoginRequest):
    """Authenticate user and return a session token."""
    try:
        username = body.username.strip()
        password = body.password

        is_valid = db_check_user_credentials(username, password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        token = db_create_session(username)
        return {
            "success": True,
            "token": token,
            "username": username
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/logout")
async def logout_api(
    username: str = Depends(get_current_user),
    authorization: str = Header(None)
):
    """Log out user by deleting their session token."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        db_delete_session(token)
    return {"success": True, "message": "Logged out successfully"}


# ─── Dashboard Data Endpoints ──────────────────────────────────────────────────

@app.get("/api/calls")
def get_calls_api(
    search: str | None = None,
    search_term: str | None = None,
    type: str | None = None,
    type_filter: str | None = None,
    filter_type: str | None = None,
    order: str | None = None,
    order_filter: str | None = None,
    username: str = Depends(get_current_user),
):
    resolved_search = search_term or search
    resolved_type = type_filter or filter_type or type or "all"
    resolved_order = order_filter or order or "all"

    return db_get_all_calls(
        search_term=resolved_search,
        type_filter=resolved_type,
        order_filter=resolved_order,
    )


@app.get("/api/calls/stats")
def get_calls_stats_api(username: str = Depends(get_current_user)):
    """Retrieve overall statistics for dashboard cards."""
    try:
        return db_get_overall_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SettingsUpdateRequest(BaseModel):
    welcome_message: str
    system_prompt: str
    forward_to_number: str


@app.get("/api/settings")
async def get_settings_api(username: str = Depends(get_current_user)):
    """Retrieve system configuration settings."""
    try:
        settings = db_get_settings()
        return {
            "welcome_message": settings.get("welcome_message", ""),
            "system_prompt": settings.get("system_prompt", ""),
            "forward_to_number": settings.get("forward_to_number", "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings")
async def update_settings_api(
    body: SettingsUpdateRequest,
    username: str = Depends(get_current_user),
):
    """Update system configuration settings."""
    try:
        success = db_update_settings(
            welcome_message=body.welcome_message,
            system_prompt=body.system_prompt,
            forward_to_number=body.forward_to_number
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update settings in database")
        return {"status": "success", "message": "Settings updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """Return the beautiful React Call History dashboard."""
    react_html_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "frontend", "dist", "index.html"
    )
    if os.path.exists(react_html_path):
        with open(react_html_path, encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)

    # Fallback to legacy dashboard.html if React build is not found
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    if not os.path.exists(html_path):
        raise HTTPException(
            status_code=404,
            detail="Dashboard template not found. Please build the frontend project.",
        )
    with open(html_path, encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


@app.get("/phone.svg")
async def get_favicon():
    """Serve the favicon.svg from the built frontend or public fallback."""
    dist_favicon = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "frontend", "dist", "favicon.svg"
    )
    if os.path.exists(dist_favicon):
        return FileResponse(dist_favicon)

    public_favicon = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "frontend", "public", "favicon.svg"
    )
    if os.path.exists(public_favicon):
        return FileResponse(public_favicon)

    raise HTTPException(status_code=404, detail="Favicon not found")


# ─── Entry Point ───────────────────────────────────────────────────────────────


if __name__ == "__main__":
    # Run the server on port 7860
    # Use with ngrok: ngrok http 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)