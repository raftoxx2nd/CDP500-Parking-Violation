import aiohttp
from aiohttp import web
import json
import os
import weakref

print("Dashboard Server starting...")

# This set will store all active WebSocket connections (browsers)
WS_CLIENTS = weakref.WeakSet()

async def websocket_handler(request):
    """Handles new browser WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    print("Browser connected to WebSocket.")
    WS_CLIENTS.add(ws)

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                if msg.data == 'close':
                    await ws.close()
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f'WebSocket connection closed with exception {ws.exception()}')
    finally:
        print("Browser disconnected.")
        WS_CLIENTS.discard(ws)

    return ws

async def violation_handler(request):
    """
    Handles incoming violation data (HTTP POST) from the detection script.
    """
    try:
        data = await request.json()
        print(f"Received violation for ID: {data.get('track_id')}")
        
        # Broadcast the new violation data to all connected browsers
        for ws in WS_CLIENTS:
            try:
                await ws.send_json(data)
            except ConnectionResetError:
                print("Failed to send to a closed WebSocket.")
        
        return web.Response(text="OK", status=200)
    except json.JSONDecodeError:
        return web.Response(text="Bad Request: Invalid JSON", status=400)
    except Exception as e:
        print(f"Error in violation_handler: {e}")
        return web.Response(text="Internal Server Error", status=500)

async def index_handler(request):
    """Serves the main dashboard.html file."""
    return web.FileResponse('./src/templates/dashboard.html')

def setup_app():
    """Configures and returns the aiohttp application."""
    app = web.Application()
    
    # --- Routes ---
    # Serves the main HTML page
    app.router.add_get('/', index_handler)
    
    # Endpoint for browsers to connect to
    app.router.add_get('/ws', websocket_handler)
    
    # Endpoint for the Python script to POST violations to
    app.router.add_post('/violation', violation_handler)
    
    # --- Static File Serving ---
    # This makes the 'output' directory (snapshots, logs) 
    # web-accessible at http://localhost:8080/output/
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'output'))
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created static directory: {output_dir}")
        
    app.router.add_static('/output', path=output_dir, name='output')
    print(f"Serving static files from: {output_dir}")
    
    return app

if __name__ == '__main__':
    app = setup_app()
    print("Starting server on http://localhost:8080")
    print("View dashboard at http://localhost:8080")
    web.run_app(app, host='localhost', port=8080)
