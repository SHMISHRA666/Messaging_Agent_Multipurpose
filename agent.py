# agent.py

import asyncio
import yaml
import re
import json
from core.loop import AgentLoop
from core.session import MultiMCP
from typing import Optional, Tuple
import csv
from io import StringIO

def log(stage: str, msg: str):
    """Simple timestamped console logger."""
    import datetime
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{stage}] {msg}")

def extract_query_and_email(message: str):
    # Improved email regex
    email_pattern = r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    email_match = re.search(email_pattern, message)
    email = email_match.group(0) if email_match else None

    # Remove email from message to get query
    query = re.sub(email_pattern, '', message).strip()

    # Remove common filler phrases after email removal
    query = re.sub(r'(on gmail|and share with|to|for|at|via|by|with)$', '', query, flags=re.IGNORECASE).strip()

    return query, email

async def process_telegram_message(message: str, multi_mcp: MultiMCP) -> str:
    """Process a Telegram message through the agent workflow."""
    try:
        # Extract query and email
        query, email = extract_query_and_email(message)
        if not query or not email or '@' not in email or '.' not in email.split('@')[-1]:
            log("warn", f"Invalid or missing email/query. Query: '{query}', Email: '{email}'")
            return "Please provide both a search query and a valid email address."
        log("info", f"Using email: {email}")

        # Create agent instance
        agent = AgentLoop(
            user_input=query,
            dispatcher=multi_mcp
        )

        # Run the agent, passing the email
        final_response, last_table_data = await agent.run(user_email=email)
        response_text = final_response.replace("FINAL_ANSWER:", "").strip()

        # --- Use the extracted table from extract_webpage, not the final answer ---
        table_data = []
        if last_table_data:
            # Try to parse as markdown table or CSV
            if "|" in last_table_data:
                lines = [line for line in last_table_data.splitlines() if "|" in line]
                for line in lines:
                    row = [cell.strip() for cell in line.split("|") if cell.strip()]
                    if row:
                        table_data.append(row)
            elif "," in last_table_data:
                reader = csv.reader(StringIO(last_table_data))
                table_data = [row for row in reader if row]
            else:
                table_data = [[last_table_data]]
        else:
            # Fallback: just put the text in a single cell
            table_data = [[response_text]]

        # --- Create the spreadsheet ---
        sheet_result = await multi_mcp.call_tool("create_spreadsheet", {
            "title": f"Search Results: {query[:30]}..."
        })
        # Handle both list and object for content
        sheet_info = None
        if hasattr(sheet_result, 'content'):
            content = sheet_result.content
            if isinstance(content, list) and content:
                sheet_info = content[0].text if hasattr(content[0], 'text') else str(content[0])
            elif hasattr(content, 'text'):
                sheet_info = content.text
            else:
                sheet_info = str(content)
        else:
            sheet_info = str(sheet_result)
        try:
            sheet_id = json.loads(sheet_info)["spreadsheet_id"]
        except Exception as e:
            log("error", f"Failed to parse spreadsheet_id: {e}, raw: {sheet_info}")
            return f"❌ Error creating spreadsheet: {sheet_info}"

        # --- Update the sheet with the extracted data ---
        try:
            update_result = await multi_mcp.call_tool("update_sheet", {
                "spreadsheet_id": sheet_id,
                "range_name": "A1",
                "values": table_data
            })
            log("info", f"Sheet update result: {getattr(update_result, 'content', update_result)}")
        except Exception as e:
            log("error", f"Failed to update sheet: {e}")
            return f"❌ Error updating sheet: {str(e)}"

        # --- Share the sheet with the correct email ---
        await multi_mcp.call_tool("share_sheet", {
            "sheet_id": sheet_id,
            "email": email,
            "role": "reader"
        })
        log("info", f"Shared sheet with: {email}")

        # --- Send email with link to the correct email ---
        await multi_mcp.call_tool("send_email_with_link", {
            "to": email,
            "subject": f"Search Results: {query[:30]}...",
            "body": f"Here are the search results for your query: {query}\n\nYou can view the full results in the shared Google Sheet.",
            "sheet_id": sheet_id
        })
        log("info", f"Sent email with link to: {email}")

        return f"✅ Results have been shared with {email}"

    except Exception as e:
        log("error", f"Failed to process message: {e}")
        return f"❌ Error processing your request: {str(e)}"

async def main():
    print("🧠 Cortex-R Agent Ready")
    
    # Load MCP server configs
    with open("config/profiles.yaml", "r") as f:
        profile = yaml.safe_load(f)
        mcp_servers = profile.get("mcp_servers", [])

    # Initialize MultiMCP
    multi_mcp = MultiMCP(server_configs=mcp_servers)
    await multi_mcp.initialize()
    
    # 1. Drain the update queue at startup
    last_update_id = 0
    try:
        updates_result = await multi_mcp.call_tool("get_updates", {"timeout": 0})
        max_update_id = None
        if hasattr(updates_result, 'content'):
            for content in updates_result.content:
                if hasattr(content, 'text'):
                    updates_data = json.loads(content.text)
                    updates = updates_data.get('updates', [])
                    if updates:
                        max_update_id = max(u['update_id'] for u in updates)
        if max_update_id is not None:
            last_update_id = max_update_id
    except Exception as e:
        log("error", f"Error draining update queue: {e}")
        last_update_id = 0

    log("info", f"Starting with update_id: {last_update_id}")

    # 2. Main loop: only process new updates
    while True:
        try:
            updates_result = await multi_mcp.call_tool("get_updates", {
                "offset": last_update_id + 1,
                "timeout": 30
            })
            if hasattr(updates_result, 'content'):
                for content in updates_result.content:
                    if hasattr(content, 'text'):
                        updates_data = json.loads(content.text)
                        updates = updates_data.get('updates', [])
                        if updates:
                            for update in updates:
                                update_id = update['update_id']
                                if update_id > last_update_id:
                                    last_update_id = update_id
                                    if update.get('message') and update['message'].get('text'):
                                        message = update['message']['text']
                                        chat_id = str(update['message']['chat']['id'])
                                        log("info", f"Processing message: {message} from chat: {chat_id} (update_id: {update_id})")
                                        response = await process_telegram_message(message, multi_mcp)
                                        await multi_mcp.call_tool("send_message", {
                                            "text": response,
                                            "chat_id": chat_id
                                        })
            await asyncio.sleep(1)
        except Exception as e:
            log("error", f"Error in main loop: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")


# Find the ASCII values of characters in INDIA and then return sum of exponentials of those values.
# How much Anmol singh paid for his DLF apartment via Capbridge? 
# What do you know about Don Tapscott and Anthony Williams?
# What is the relationship between Gensol and Go-Auto?
# which course are we teaching on Canvas LMS?
# Summarize this page: https://theschoolof.ai/
# What is the log value of the amount that Anmol singh paid for his DLF apartment via Capbridge? 