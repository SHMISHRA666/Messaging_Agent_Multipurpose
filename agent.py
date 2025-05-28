# agent.py

import asyncio
import yaml
from core.loop import AgentLoop
from core.session import MultiMCP

def log(stage: str, msg: str):
    """Simple timestamped console logger."""
    import datetime
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{stage}] {msg}")


async def handle_spreadsheet_update(agent: AgentLoop, user_input: str):
    """Handle spreadsheet creation and update based on user input."""
    # Extract spreadsheet title from user input
    import re
    title_match = re.search(r'title\s*["\']([^"\']+)["\']', user_input)
    if not title_match:
        return "Error: Could not find spreadsheet title in the query. Please specify title in quotes."
    spreadsheet_title = title_match.group(1)
    
    # Extract data source from user input
    data_source_match = re.search(r'found from\s+([^,.]+)', user_input)
    if not data_source_match:
        return "Error: Could not find data source in the query. Please specify where to find the data."
    data_source = data_source_match.group(1).strip()
    
    # First create the spreadsheet
    create_response = await agent.dispatcher.call_tool("create_spreadsheet", {"title": spreadsheet_title})
    if "Error" in create_response:
        return f"Failed to create spreadsheet: {create_response}"
    
    # Parse the spreadsheet ID from the response
    import json
    spreadsheet_data = json.loads(create_response)
    spreadsheet_id = spreadsheet_data.get('spreadsheet_id')
    
    # Search for data
    search_response = await agent.dispatcher.call_tool("search", {"query": data_source})
    if "Error" in search_response:
        return f"Failed to search for data: {search_response}"
    
    # Extract webpage content - using the first search result URL
    search_results = json.loads(search_response)
    if not search_results or not search_results.get('results'):
        return "Error: No search results found."
    
    first_result_url = search_results['results'][0].get('url')
    if not first_result_url:
        return "Error: Could not find URL in search results."
    
    extract_response = await agent.dispatcher.call_tool("extract_webpage", {"url": first_result_url})
    if "Error" in extract_response:
        return f"Failed to extract data: {extract_response}"
    
    # Parse the data
    standings_text = extract_response
    standings_data = []
    
    # Add headers
    standings_data.append(["Driver Name", "Team", "Points"])
    
    # Parse each line of standings
    for line in standings_text.split('\n'):
        if '|' in line:
            parts = line.split('|')
            if len(parts) >= 4:
                driver_info = parts[1].strip()
                team = parts[3].strip()
                points = parts[4].strip()
                
                # Extract driver name (remove country code and driver code)
                driver_name = re.sub(r'[A-Z]{3}$', '', driver_info).strip()
                standings_data.append([driver_name, team, points])
    
    # Update the sheet with the data
    update_response = await agent.dispatcher.call_tool(
        "update_sheet",
        {
            "spreadsheet_id": spreadsheet_id,
            "range_name": "A1:C" + str(len(standings_data)),
            "values": standings_data
        }
    )
    
    if "Error" in update_response:
        return f"Failed to update spreadsheet: {update_response}"
    
    return f"Successfully created and updated spreadsheet '{spreadsheet_title}'. URL: {spreadsheet_data.get('url')}"

async def main():
    print("🧠 Cortex-R Agent Ready")
    user_input = input("🧑 What do you want to solve today? → ")

    # Load MCP server configs from profiles.yaml
    with open("config/profiles.yaml", "r") as f:
        profile = yaml.safe_load(f)
        mcp_servers = profile.get("mcp_servers", [])

    multi_mcp = MultiMCP(server_configs=mcp_servers)
    print("Agent before initialize")
    await multi_mcp.initialize()

    agent = AgentLoop(
        user_input=user_input,
        dispatcher=multi_mcp
    )

    try:
        if "spreadsheet" in user_input.lower() and "update" in user_input.lower():
            final_response = await handle_spreadsheet_update(agent, user_input)
        else:
            final_response = await agent.run()
        print("\n💡 Final Answer:\n", final_response.replace("FINAL_ANSWER:", "").strip())

    except Exception as e:
        log("fatal", f"Agent failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())


# Find the ASCII values of characters in INDIA and then return sum of exponentials of those values.
# How much Anmol singh paid for his DLF apartment via Capbridge? 
# What do you know about Don Tapscott and Anthony Williams?
# What is the relationship between Gensol and Go-Auto?
# which course are we teaching on Canvas LMS?
# Summarize this page: https://theschoolof.ai/
# What is the log value of the amount that Anmol singh paid for his DLF apartment via Capbridge? 