#
# Copyright (c) 2025, Daily
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

import plivo
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import Response

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="Plivo AI Voice Agent",
    description="AI Voice Agent for Order Status — powered by Pipecat + Plivo",
)

# Allow cross-origin requests (useful for frontend triggers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def get_plivo_client() -> plivo.RestClient:
    """Return an authenticated Plivo REST client."""
    auth_id = os.getenv("PLIVO_AUTH_ID")
    auth_token = os.getenv("PLIVO_AUTH_TOKEN")
    if not auth_id or not auth_token:
        raise ValueError("PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN must be set in environment variables")
    return plivo.RestClient(auth_id, auth_token)


def get_websocket_url(host: str, body_data: dict = None) -> str:
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
    # Plivo can send params in query or POST form data
    form_data = {}
    if request.method == "POST":
        try:
            form_data = await request.form()
        except Exception:
            pass

    call_uuid = CallUUID or form_data.get("CallUUID")
    from_number = From or form_data.get("From")
    to_number = To or form_data.get("To")

    print(f"Inbound call — From: {from_number}, To: {to_number}, UUID: {call_uuid}")

    body_data = {}
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
    print(f"Returning XML for inbound call: {xml}")
    return Response(content=xml, media_type="application/xml")


# ─── Outbound Call Trigger ─────────────────────────────────────────────────────


class OutboundCallRequest(BaseModel):
    """Optional request body to override the default customer number."""
    customer_number: str | None = None  # defaults to CUSTOMER_NUMBER from .env


@app.post("/outbound-call")
async def make_outbound_call(request: Request, body: OutboundCallRequest = None):
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
        "CUSTOMER_NUMBER", "+918031339945"
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

    call_uuid = CallUUID or form_data.get("CallUUID")
    from_number = From or form_data.get("From")
    to_number = To or form_data.get("To")

    print(f"Outbound call answered — From: {from_number}, To: {to_number}, UUID: {call_uuid}")

    body_data = {"call_type": "outbound"}
    if from_number:
        body_data["from"] = from_number
    if to_number:
        body_data["to"] = to_number

    host = request.headers.get("host")
    if not host:
        raise HTTPException(status_code=400, detail="Unable to determine server host")

    websocket_url = get_websocket_url(host, body_data)
    xml = build_stream_xml(websocket_url)
    print(f"Returning XML for outbound answer: {xml}")
    return Response(content=xml, media_type="application/xml")


# ─── WebSocket Handler ─────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Handle WebSocket connections from Plivo (both inbound and outbound calls)."""
    await websocket.accept()
    print("WebSocket connection accepted")
    print(f"Query params — body: {body[:50] + '...' if body and len(body) > 50 else body}, serviceHost: {serviceHost}")

    body_data = {}
    if body:
        try:
            decoded_json = base64.b64decode(body).decode("utf-8")
            body_data = json.loads(decoded_json)
            print(f"Decoded body data: {body_data}")
        except Exception as e:
            print(f"Error decoding body parameter: {e}")
    else:
        print("No body parameter received")

    try:
        from pipecat.runner.types import WebSocketRunnerArguments
        from bot import bot

        runner_args = WebSocketRunnerArguments(websocket=websocket)
        runner_args.handle_sigint = False

        await bot(runner_args)

    except Exception as e:
        print(f"Error in WebSocket endpoint: {e}")
        import traceback
        traceback.print_exc()
        await websocket.close()


# ─── Health Check ──────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Plivo AI Voice Agent",
        "caller_number": os.getenv("PLIVO_CALLER_NUMBER", "not configured"),
        "customer_number": os.getenv("CUSTOMER_NUMBER", "not configured"),
        "env": os.getenv("ENV", "local"),
    }


# ─── Entry Point ───────────────────────────────────────────────────────────────


if __name__ == "__main__":
    # Run the server on port 7860
    # Use with ngrok: ngrok http 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)
