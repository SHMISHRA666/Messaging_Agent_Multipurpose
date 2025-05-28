from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent
import yaml
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from sse_starlette.sse import EventSourceResponse
from fastapi import FastAPI, Request
import uvicorn
import json
from typing import Dict, Any, List
import os
import datetime
from multiprocessing import Queue, Process
import multiprocessing
from collections import deque
import threading
import queue

# Load credentials
with open("config/credentials.yaml", "r") as f:
    credentials = yaml.safe_load(f)

TELEGRAM_TOKEN = credentials["telegram"]["bot_token"]

# Initialize FastMCP for SSE communication
mcp = FastMCP("Telegram")

# Store for SSE clients
sse_clients: Dict[str, Queue] = {}

# Message history for each chat
message_history: Dict[str, deque] = {}

# Initialize a default queue for testing
sse_clients["default"] = Queue()
message_history["default"] = deque(maxlen=100)  # Keep last 100 messages

# Store active chat_id
active_chat_id: str = None

# Lock for thread-safe operations
message_lock = threading.Lock()

def store_message(chat_id: str, message: dict):
    """Store a message in both queue and history."""
    with message_lock:
        if chat_id not in sse_clients:
            sse_clients[chat_id] = Queue()
        if chat_id not in message_history:
            message_history[chat_id] = deque(maxlen=100)
        
        sse_clients[chat_id].put(message)
        message_history[chat_id].append(message)

@mcp.tool()
async def send_message(text: str, chat_id: str = None) -> TextContent:
    """Send a message to a Telegram chat. Usage: send_message|text="Hello!"|chat_id="5456846809" """
    try:
        # Use provided chat_id or fall back to active_chat_id
        chat_id = chat_id or active_chat_id
        if not chat_id:
            return TextContent(type="text", text="Error: No chat_id provided and no active chat_id found")
            
        print(f"[DEBUG] Attempting to send message to chat_id: {chat_id}")
        print(f"[DEBUG] Message text: {text}")
        
        # Create outgoing message
        outgoing_message = {
            "type": "message",
            "text": text,
            "chat_id": chat_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "direction": "outgoing",
            "source": "user"
        }
        
        # Store the message
        store_message(chat_id, outgoing_message)
        
        # Send via Telegram
        try:
            print("[DEBUG] Initializing Telegram bot...")
            app = Application.builder().token(TELEGRAM_TOKEN).build()
            await app.initialize()
            
            # Verify bot connection
            bot_info = await app.bot.get_me()
            print(f"[DEBUG] Bot connected successfully! Bot username: @{bot_info.username}")
            
            # Send the message
            print(f"[DEBUG] Sending message to Telegram...")
            await app.bot.send_message(chat_id=chat_id, text=text)
            print("[DEBUG] Message sent successfully to Telegram")
            
            await app.shutdown()
        except Exception as e:
            print(f"[ERROR] Failed to send message via Telegram: {str(e)}")
            return TextContent(type="text", text=f"Error sending message via Telegram: {str(e)}")
            
        return TextContent(type="text", text="Message sent successfully")
    except Exception as e:
        print(f"[DEBUG] Error in send_message: {str(e)}")
        return TextContent(type="text", text=f"Error sending message: {str(e)}")

@mcp.tool()
async def get_updates() -> TextContent:
    """Get latest updates from Telegram. Usage: get_updates"""
    try:
        print("[DEBUG] Getting updates from Telegram...")
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        await app.initialize()
        
        # Verify bot connection
        bot_info = await app.bot.get_me()
        print(f"[DEBUG] Bot connected successfully! Bot username: @{bot_info.username}")
        
        updates = await app.bot.get_updates()
        await app.shutdown()
        
        # Process updates and store in queue
        for update in updates:
            if update.message and update.message.chat:
                chat_id = str(update.message.chat.id)
                
                # Store incoming message
                incoming_message = {
                    "type": "message",
                    "text": update.message.text,
                    "chat_id": chat_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "direction": "incoming",
                    "source": "telegram"
                }
                
                # Store the message
                store_message(chat_id, incoming_message)
                
                # Update active chat_id
                global active_chat_id
                active_chat_id = chat_id
        
        return TextContent(type="text", text=json.dumps({
            "updates": [update.to_dict() for update in updates],
            "active_chat_id": active_chat_id
        }, indent=2))
    except Exception as e:
        print(f"[ERROR] Error getting updates: {str(e)}")
        return TextContent(type="text", text=f"Error getting updates: {str(e)}")

@mcp.tool()
async def receive_message(chat_id: str = None) -> TextContent:
    """Receive a message from a Telegram chat. Usage: receive_message|chat_id="123456" """
    try:
        chat_id = chat_id or active_chat_id
        if not chat_id:
            return TextContent(type="text", text="No active chat_id found")
            
        # Initialize if not exists
        with message_lock:
            if chat_id not in message_history:
                message_history[chat_id] = deque(maxlen=100)
                
            # Get the latest message from history
            if message_history[chat_id]:
                latest_message = message_history[chat_id][-1]
                return TextContent(type="text", text=json.dumps(latest_message))
                
        return TextContent(type="text", text="No new messages")
            
    except Exception as e:
        print(f"[ERROR] Error in receive_message: {str(e)}")
        return TextContent(type="text", text=f"Error receiving message: {str(e)}")

def start_sse_server():
    app = FastAPI()
    
    @app.get("/sse/{chat_id}")
    async def sse_endpoint(request: Request, chat_id: str):
        async def event_generator():
            with message_lock:
                if chat_id not in sse_clients:
                    sse_clients[chat_id] = Queue()
                    message_history[chat_id] = deque(maxlen=100)
                
            while True:
                try:
                    if await request.is_disconnected():
                        break
                        
                    message = sse_clients[chat_id].get_nowait()
                    yield {
                        "event": "message",
                        "data": json.dumps(message)
                    }
                except queue.Empty:
                    await asyncio.sleep(0.1)
                except Exception as e:
                    print(f"[ERROR] SSE error: {str(e)}")
                    await asyncio.sleep(0.1)
                    
        return EventSourceResponse(event_generator())
    
    uvicorn.run(app, host="0.0.0.0", port=8002)

async def start_telegram_bot():
    async def run_bot():
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        async def telegram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if update.message and update.message.chat:
                chat_id = str(update.message.chat.id)
                
                # Store incoming message
                incoming_message = {
                    "type": "message",
                    "text": update.message.text,
                    "chat_id": chat_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "direction": "incoming",
                    "source": "telegram"
                }
                
                # Store the message
                store_message(chat_id, incoming_message)
                
                # Update active chat_id
                global active_chat_id
                active_chat_id = chat_id
        
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_handler))
        await app.initialize()
        await app.start()
        await app.run_polling()
    
    # Start the bot in a separate process
    Process(target=lambda: asyncio.run(run_bot())).start()

if __name__ == "__main__":
    # Check if we're being run as an MCP server
    if os.environ.get("MCP_SERVER") == "1":
        print("[DEBUG] Running in MCP server mode")
        # Run only the MCP server
        mcp.run()
    else:
        print("[DEBUG] Running in full server mode")
        # Start SSE server and Telegram bot in separate processes
        sse_process = Process(target=start_sse_server)
        bot_process = Process(target=lambda: asyncio.run(start_telegram_bot()))
        
        sse_process.start()
        bot_process.start()
        
        try:
            sse_process.join()
            bot_process.join()
        except KeyboardInterrupt:
            sse_process.terminate()
            bot_process.terminate()