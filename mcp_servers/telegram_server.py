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

# Load credentials
with open("config/credentials.yaml", "r") as f:
    credentials = yaml.safe_load(f)

TELEGRAM_TOKEN = credentials["telegram"]["bot_token"]

# Initialize FastMCP for stdio communication
mcp = FastMCP("Telegram")

# Store for SSE clients
sse_clients: Dict[str, asyncio.Queue] = {}

@mcp.tool()
async def send_message(chat_id: str, text: str) -> TextContent:
    """Send a message to a Telegram chat. Usage: send_message|chat_id="123456"|text="Hello!"""
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        await app.initialize()
        await app.bot.send_message(chat_id=chat_id, text=text)
        await app.shutdown()
        return TextContent(type="text", text="Message sent successfully")
    except Exception as e:
        return TextContent(type="text", text=f"Error sending message: {str(e)}")

@mcp.tool()
async def get_updates() -> TextContent:
    """Get latest updates from Telegram. Usage: get_updates"""
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        await app.initialize()
        updates = await app.bot.get_updates()
        await app.shutdown()
        return TextContent(type="text", text=json.dumps([update.to_dict() for update in updates]))
    except Exception as e:
        return TextContent(type="text", text=f"Error getting updates: {str(e)}")

def start_sse_server():
    """Start the FastAPI server for SSE in a separate process"""
    app = FastAPI()
    
    @app.get("/sse/{chat_id}")
    async def sse_endpoint(request: Request, chat_id: str):
        async def event_generator():
            if chat_id not in sse_clients:
                sse_clients[chat_id] = asyncio.Queue()
            
            while True:
                if await request.is_disconnected():
                    break
                
                try:
                    message = await asyncio.wait_for(sse_clients[chat_id].get(), timeout=30.0)
                    yield {
                        "event": "message",
                        "data": json.dumps(message)
                    }
                except asyncio.TimeoutError:
                    yield {
                        "event": "ping",
                        "data": "ping"
                    }
        
        return EventSourceResponse(event_generator())
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

def start_telegram_bot():
    """Start the Telegram bot in a separate process"""
    async def run_bot():
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        async def telegram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            message = update.message
            if message and message.text:
                chat_id = str(message.chat_id)
                if chat_id not in sse_clients:
                    sse_clients[chat_id] = asyncio.Queue()
                await sse_clients[chat_id].put({
                    "type": "message",
                    "text": message.text,
                    "chat_id": chat_id
                })
        
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_handler))
        await app.initialize()
        await app.start()
        await app.run_polling()
    
    asyncio.run(run_bot())

if __name__ == "__main__":
    # Check if we're being run as an MCP server
    if os.environ.get("MCP_SERVER") == "1":
        # Run only the MCP server
        mcp.run()
    else:
        # Start SSE server and Telegram bot in separate processes
        import multiprocessing
        
        sse_process = multiprocessing.Process(target=start_sse_server)
        bot_process = multiprocessing.Process(target=start_telegram_bot)
        
        sse_process.start()
        bot_process.start()
        
        try:
            sse_process.join()
            bot_process.join()
        except KeyboardInterrupt:
            sse_process.terminate()
            bot_process.terminate()