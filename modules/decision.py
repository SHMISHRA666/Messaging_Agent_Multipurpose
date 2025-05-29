from typing import List, Optional
from modules.perception import PerceptionResult
from modules.memory import MemoryItem
from modules.model_manager import ModelManager
from dotenv import load_dotenv
from google import genai
import os
import asyncio

# Optional: import logger if available
try:
    from agent import log
except ImportError:
    import datetime
    def log(stage: str, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{stage}] {msg}")

model = ModelManager()


async def generate_plan(
    perception: PerceptionResult,
    memory_items: List[MemoryItem],
    tool_descriptions: Optional[str] = None,
    step_num: int = 1,
    max_steps: int = 3,
    user_email: str = None,
    spreadsheet_id: str = None,
    table_data: str = None
) -> str:
    """Generates the next step plan for the agent: either tool usage or final answer."""

    memory_texts = "\n".join(f"- {m.text}" for m in memory_items) or "None"
    tool_context = f"\nYou have access to the following tools:\n{tool_descriptions}" if tool_descriptions else ""
    email_line = f"- The user's email address is: {user_email}" if user_email else ""
    spreadsheet_line = f"- The current spreadsheet_id is: {spreadsheet_id}" if spreadsheet_id else ""
    table_line = f"- The extracted table data is: {table_data}" if table_data else ""
    email_rule = "- For any tool that requires an email, always use the user's email address exactly as provided above." if user_email else ""
    update_rule = "- If you have both a spreadsheet_id and table data, you MUST call update_sheet with spreadsheet_id, range_name='A1', and the table data as values." if spreadsheet_id and table_data else ""

    prompt = f"""
You are a reasoning-driven AI agent with access to tools and memory.
Your job is to solve the user's request step-by-step by reasoning through the problem, selecting a tool if needed, and continuing until the FINAL_ANSWER is produced.

Respond in **exactly one line** using one of the following formats:

- FUNCTION_CALL: tool_name|param1=value1|param2=value2
- FINAL_ANSWER: [your final result] *(Not description, but actual final answer)

🧠 Context:
- Step: {step_num} of {max_steps}
- Memory: 
{memory_texts}
{tool_context}
{email_line}
{spreadsheet_line}
{table_line}

🎯 Input Summary:
- User input: "{perception.user_input}"
- Intent: {perception.intent}
- Entities: {', '.join(perception.entities)}
- Tool hint: {perception.tool_hint or 'None'}

{email_rule}
{update_rule}

📏 CRITICAL RULES FOR SPREADSHEET OPERATIONS:
1. After extracting webpage data, you MUST call update_sheet before any other operations
2. The update_sheet function requires:
   - spreadsheet_id (from create_spreadsheet result)
   - range_name (usually "A1")
   - values (the extracted data)
3. Never share or send email before updating the sheet
4. If you have both spreadsheet_id and table_data, update_sheet MUST be your next action

✅ Example Workflow for F1 standings:
1. FUNCTION_CALL: search|query="current F1 standings"
2. FUNCTION_CALL: extract_webpage|url="https://www.formula1.com/en/results/2025/drivers"
3. FUNCTION_CALL: create_spreadsheet|title="F1 Standings 2025"
4. FUNCTION_CALL: update_sheet|spreadsheet_id="123456"|range="A1"|values=extracted_data
5. FUNCTION_CALL: share_sheet|spreadsheet_id="123456"|email="user@example.com"|role="reader"
6. FUNCTION_CALL: send_email_with_link|to="user@example.com"|subject="F1 Standings 2025"|body="Here is the F1 standings spreadsheet:"|link="https://docs.google.com/spreadsheets/d/123456"
7. FINAL_ANSWER: [Spreadsheet created, updated, shared, and email sent successfully]

✅ Other Examples:
- FUNCTION_CALL: add|a=5|b=3
- FUNCTION_CALL: strings_to_chars_to_int|input.string=INDIA
- FUNCTION_CALL: int_list_to_exponential_sum|input.int_list=[73,78,68,73,65]
- FINAL_ANSWER: [42] → Always mention final answer to the query, not that some other description.

✅ Examples:
- User asks: "Send a message "hello bot" on Telegram"
- FUNCTION_CALL: get_updates
- FUNCTION_CALL: send_message|chat_id="123456"|text="hello bot"
- FINAL_ANSWER: [Message sent successfully]

✅ Examples:
- User asks: "Send email to "John_doe@gmail.com" with subject "Hello" and body "How are you?""
- FUNCTION_CALL: send_email|to="John_doe@gmail.com"|subject="Hello"|body="How are you?"
- FINAL_ANSWER: [Email sent successfully]

✅ Examples:
- User asks: "Create Spreadsheet in Google Sheets in google drive"
- FUNCTION_CALL: create_spreadsheet|title="New Spreadsheet"
- FINAL_ANSWER: [Spreadsheet created successfully]

✅ Examples:
- User asks: "Update the spreadsheet in Google Sheets in google drive"
- FUNCTION_CALL: update_sheet|spreadsheet_id="123456"|range="A1"|values=[[1,2],[3,4]]
- FINAL_ANSWER: [Spreadsheet updated successfully]

✅ Examples:
- User asks: "Create a new folder in Google Drive"
- FUNCTION_CALL: create_folder|name="New Folder"
- FINAL_ANSWER: [Folder created successfully]

✅ Examples:
- User asks: "Share the spreadsheet in Google Sheets in google drive with "John_doe@gmail.com" as a viewer"
- FUNCTION_CALL: share_sheet|spreadsheet_id="123456"|email="John_doe@gmail.com"|role="reader"
- FINAL_ANSWER: [Spreadsheet shared successfully]

✅ Examples:
- User asks: "Find F1 standings and update a spreadsheet"
- FUNCTION_CALL: search|query="current F1 standings"
- FUNCTION_CALL: extract_webpage|url="https://www.formula1.com/en/results/2025/drivers"
- FUNCTION_CALL: create_spreadsheet|title="F1 Standings 2025"
- FUNCTION_CALL: update_sheet|spreadsheet_id="123456"|range="A1"|values=extracted_data
- FUNCTION_CALL: share_sheet|spreadsheet_id="123456"|email="user@example.com"|role="reader"
- FUNCTION_CALL: send_email_with_link|to="user@example.com"|subject="F1 Standings 2025"|body="Here is the F1 standings spreadsheet:"|link="https://docs.google.com/spreadsheets/d/123456"
- FINAL_ANSWER: [Spreadsheet created, updated, shared, and email sent successfully]

✅ Examples:
- User asks: "What's the relationship between Cricket and Sachin Tendulkar"
  - FUNCTION_CALL: search_documents|query="relationship between Cricket and Sachin Tendulkar"
  - [receives a detailed document]
  - FINAL_ANSWER: [Sachin Tendulkar is widely regarded as the "God of Cricket" due to his exceptional skills, longevity, and impact on the sport in India. He is the leading run-scorer in both Test and ODI cricket, and the first to score 100 centuries in international cricket. His influence extends beyond his statistics, as he is seen as a symbol of passion, perseverance, and a national icon. ]

---

📏 IMPORTANT Rules:

- 🚫 Do NOT invent tools. Use only the tools listed above. Tool description has useage pattern, only use that.
- 📄 If the question may relate to public/factual knowledge (like companies, people, places), use the `search_documents` tool to look for the answer.
- 🧮 If the question is mathematical, use the appropriate math tool.
- 🔁 Analyze that whether you have already got a good factual result from a tool, do NOT search again — summarize and respond with FINAL_ANSWER.
- ❌ NEVER repeat tool calls with the same parameters unless the result was empty. When searching rely on first reponse from tools, as that is the best response probably.
- ❌ NEVER output explanation text — only structured FUNCTION_CALL or FINAL_ANSWER.
- ✅ Use nested keys like `input.string` or `input.int_list`, and square brackets for lists.
- 💡 If no tool fits or you're unsure, end with: FINAL_ANSWER: [unknown]
- For Telegram, use the `get_updates` tool to get the latest updates and then use any other tool to send or receive a message.
- For sending email, use the email address that is provided in the user input that has '@' in it.
- When working with spreadsheets and data:
  1. First search for the data
  2. Then extract the webpage content
  3. Create the spreadsheet
  4. Always always update the spreadsheet with the extracted data
  5. Share the spreadsheet
  6. Send email with the link
- IMPORTANT: After extracting webpage data, you MUST always call update_sheet with the extracted data before sharing or sending email
- IMPORTANT: The update_sheet function requires: spreadsheet_id, range (usually "A1"), and values (the extracted data)
- IMPORTANT: If you have extracted data and a spreadsheet_id, you MUST necessarily call update_sheet before proceeding
- ⏳ You have 7 attempts. Final attempt must end with FINAL_ANSWER.
"""

    try:
        raw = (await model.generate_text(prompt)).strip()
        log("plan", f"LLM output: {raw}")

        for line in raw.splitlines():
            if line.strip().startswith("FUNCTION_CALL:") or line.strip().startswith("FINAL_ANSWER:"):
                return line.strip()

        return "FINAL_ANSWER: [unknown]"

    except Exception as e:
        log("plan", f"⚠️ Planning failed: {e}")
        return "FINAL_ANSWER: [unknown]"

