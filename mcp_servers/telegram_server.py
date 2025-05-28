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
from typing import Dict, Any
import os
import datetime
from multiprocessing import Queue, Process
import multiprocessing

# Load credentials
with open("config/credentials.yaml", "r") as f:
    credentials = yaml.safe_load(f)

TELEGRAM_TOKEN = credentials["telegram"]["bot_token"]

# Initialize FastMCP for stdio communication
mcp = FastMCP("Telegram")

# Store for SSE clients
sse_clients: Dict[str, Queue] = {}

# Initialize a default queue for testing
sse_clients["default"] = Queue()

# Store active chat_id
active_chat_id: str = None

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
        
        # Store the message in the queue for the specified chat
        if chat_id not in sse_clients:
            sse_clients[chat_id] = Queue()
            
        # Store outgoing message
        outgoing_message = {
            "type": "message",
            "text": text,
            "chat_id": chat_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "direction": "outgoing",
            "source": "user"
        }
        sse_clients[chat_id].put(outgoing_message)
        print(f"[DEBUG] Outgoing message stored in queue: {outgoing_message}")
        
        # Always try to send via Telegram
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
        
        # Extract chat IDs from updates
        chat_ids = []
        global active_chat_id
        for update in updates:
            if update.message and update.message.chat:
                chat_id = str(update.message.chat.id)
                chat_ids.append(chat_id)
                # Store the most recent chat_id as active
                active_chat_id = chat_id
        
        print(f"[DEBUG] Found chat IDs: {chat_ids}")
        print(f"[DEBUG] Active chat_id set to: {active_chat_id}")
        return TextContent(type="text", text=json.dumps({
            "updates": [update.to_dict() for update in updates],
            "chat_ids": chat_ids,
            "active_chat_id": active_chat_id
        }, indent=2))
    except Exception as e:
        print(f"[ERROR] Error getting updates: {str(e)}")
        return TextContent(type="text", text=f"Error getting updates: {str(e)}")

@mcp.tool()
async def inspect_queue(chat_id: str) -> TextContent:
    """Inspect the contents of the message queue for a specific chat.
    Usage: inspect_queue|chat_id="123456"
    """
    try:
        if chat_id not in sse_clients:
            return TextContent(type="text", text=f"No queue exists for chat_id: {chat_id}")
        
        # Create a temporary list to store messages
        messages = []
        while True:
            try:
                message = sse_clients[chat_id].get_nowait()
                messages.append(message)
            except:
                break
        
        # Put all messages back in the queue
        for message in messages:
            sse_clients[chat_id].put(message)
        
        return TextContent(type="text", text=json.dumps({
            "chat_id": chat_id,
            "queue_size": len(messages),
            "messages": messages
        }, indent=2))
    except Exception as e:
        return TextContent(type="text", text=f"Error inspecting queue: {str(e)}")

@mcp.tool()
async def receive_message(chat_id: str, direction: str = None) -> TextContent:
    """Receive a message from a Telegram chat. 
    Usage: 
    - receive_message|chat_id="123456" (receives all messages)
    - receive_message|chat_id="123456"|direction="incoming" (receives only incoming messages)
    - receive_message|chat_id="123456"|direction="outgoing" (receives only outgoing messages)
    """
    try:
        print(f"[DEBUG] ====== Receive Message Debug ======")
        print(f"[DEBUG] Chat ID: {chat_id}")
        print(f"[DEBUG] Requested direction: {direction}")
        print(f"[DEBUG] Available chat_ids: {list(sse_clients.keys())}")
        
        # If no chat_id is provided, use default
        if not chat_id:
            chat_id = "default"
            print(f"[DEBUG] Using default chat_id: {chat_id}")
            
        if chat_id not in sse_clients:
            print(f"[DEBUG] Creating new queue for chat_id: {chat_id}")
            sse_clients[chat_id] = Queue()
        
        try:
            print(f"[DEBUG] Attempting to get message from queue...")
            # Use non-blocking get with timeout
            try:
                message = sse_clients[chat_id].get_nowait()
                print(f"[DEBUG] Raw message from queue: {json.dumps(message, indent=2)}")
                print(f"[DEBUG] Message direction: {message.get('direction')}")
                
                # Filter by direction if specified
                if direction:
                    direction = direction.lower().strip()  # Normalize direction
                    message_direction = message.get('direction', '').lower().strip()  # Normalize message direction
                    print(f"[DEBUG] Direction comparison:")
                    print(f"[DEBUG] - Requested: '{direction}'")
                    print(f"[DEBUG] - Message: '{message_direction}'")
                    print(f"[DEBUG] - Match: {message_direction == direction}")
                    
                    if message_direction != direction:
                        print(f"[DEBUG] Direction mismatch - putting message back in queue")
                        sse_clients[chat_id].put(message)
                        return TextContent(type="text", text="No new messages matching the specified direction")
                
                print(f"[DEBUG] Message matches criteria - putting back in queue")
                sse_clients[chat_id].put(message)
                return TextContent(type="text", text=json.dumps(message, indent=2))
            except:
                print(f"[DEBUG] No message available in queue")
                return TextContent(type="text", text="No new messages")
        except Exception as e:
            print(f"[DEBUG] Error reading from queue: {str(e)}")
            return TextContent(type="text", text="Error reading from queue")
    except Exception as e:
        print(f"[DEBUG] Error in receive_message: {str(e)}")
        return TextContent(type="text", text=f"Error receiving message: {str(e)}")
    finally:
        print(f"[DEBUG] ====== End Receive Message Debug ======")

@mcp.tool()
async def simulate_incoming_message(chat_id: str, text: str) -> TextContent:
    """Simulate an incoming message from the bot.
    Usage: simulate_incoming_message|chat_id="123456"|text="Hello from bot!"
    """
    try:
        if chat_id not in sse_clients:
            sse_clients[chat_id] = Queue()
            
        message_data = {
            "type": "message",
            "text": text,
            "chat_id": chat_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "direction": "incoming",
            "source": "bot",
            "user": {
                "id": "bot",
                "username": "simulated_bot",
                "first_name": "Simulated",
                "last_name": "Bot"
            }
        }
        
        sse_clients[chat_id].put(message_data)
        print(f"[DEBUG] Simulated incoming message stored in queue: {message_data}")
        return TextContent(type="text", text="Simulated message stored successfully")
    except Exception as e:
        print(f"[DEBUG] Error in simulate_incoming_message: {str(e)}")
        return TextContent(type="text", text=f"Error storing simulated message: {str(e)}")

def start_sse_server():
    """Start the FastAPI server for SSE in a separate process"""
    app = FastAPI()
    
    @app.get("/sse/{chat_id}")
    async def sse_endpoint(request: Request, chat_id: str):
        async def event_generator():
            if chat_id not in sse_clients:
                sse_clients[chat_id] = Queue()
                print(f"[DEBUG] Created new SSE client for chat_id: {chat_id}")
            
            while True:
                if await request.is_disconnected():
                    break
                
                try:
                    # Use non-blocking get with timeout
                    try:
                        message = sse_clients[chat_id].get_nowait()
                        yield {
                            "event": "message",
                            "data": json.dumps(message)
                        }
                    except:
                        yield {
                            "event": "ping",
                            "data": "ping"
                        }
                except Exception as e:
                    print(f"[DEBUG] Error in SSE endpoint: {str(e)}")
                    yield {
                        "event": "error",
                        "data": str(e)
                    }
        
        return EventSourceResponse(event_generator())
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

async def start_telegram_bot():
    """Start the Telegram bot in a separate process"""
    async def run_bot():
        try:
            print("[DEBUG] Initializing Telegram bot...")
            app = Application.builder().token(TELEGRAM_TOKEN).build()
            
            # Verify bot connection
            try:
                await app.initialize()
                bot_info = await app.bot.get_me()
                print(f"[DEBUG] Bot connected successfully! Bot username: @{bot_info.username}")
            except Exception as e:
                print(f"[ERROR] Failed to connect to Telegram: {str(e)}")
                return
            
            async def telegram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
                try:
                    # Convert update to dict to access raw JSON data
                    update_dict = update.to_dict()
                    if 'message' in update_dict and 'chat' in update_dict['message']:
                        chat_id = str(update_dict['message']['chat']['id'])
                        message_text = update_dict['message'].get('text', '')
                        print(f"[DEBUG] Received message from chat_id: {chat_id}")
                        print(f"[DEBUG] Message text: {message_text}")
                        
                        if chat_id not in sse_clients:
                            print(f"[DEBUG] Creating new queue for chat_id: {chat_id}")
                            sse_clients[chat_id] = Queue()
                        
                        # Store the message in the queue
                        message_data = {
                            "type": "message",
                            "text": message_text,
                            "chat_id": chat_id,
                            "timestamp": datetime.datetime.fromtimestamp(update_dict['message']['date']).isoformat(),
                            "direction": "incoming",
                            "source": "bot",
                            "user": {
                                "id": update_dict['message']['from']['id'],
                                "username": update_dict['message']['from'].get('username', ''),
                                "first_name": update_dict['message']['from'].get('first_name', ''),
                                "last_name": update_dict['message']['from'].get('last_name', '')
                            }
                        }
                        print(f"[DEBUG] Incoming message stored in queue: {message_data}")
                        sse_clients[chat_id].put(message_data)
                        print(f"[DEBUG] Message stored successfully")
                        
                        # Send acknowledgment
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="Message received and stored!"
                        )
                except Exception as e:
                    print(f"[ERROR] Error in telegram_handler: {str(e)}")
            
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_handler))
            
            print("[DEBUG] Starting bot polling...")
            await app.start()
            await app.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            print(f"[ERROR] Fatal error in bot: {str(e)}")
            raise
    
    asyncio.run(run_bot())

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
        bot_process = Process(target=start_telegram_bot)
        
        sse_process.start()
        bot_process.start()
        
        try:
            sse_process.join()
            bot_process.join()
        except KeyboardInterrupt:
            sse_process.terminate()
            bot_process.terminate()