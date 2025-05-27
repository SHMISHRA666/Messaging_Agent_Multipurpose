# Messaging Agent Telegram

A multi-functional messaging agent that integrates Telegram, Gmail, and Google Drive services with various utility tools.

## Project Structure

```
Messaging_Agent_Telegram/
├── mcp_servers/              # MCP server implementations
│   ├── telegram_server.py    # Telegram bot functionality
│   ├── gmail_server.py       # Gmail email services
│   └── gdrive_server.py      # Google Drive operations
├── config/                   # Configuration files
├── core/                     # Core functionality
├── documents/               # Document storage
├── faiss_index/            # Vector search index
├── modules/                # Additional modules
└── requirements.txt        # Project dependencies
```

## Features

### 1. Telegram Integration
- Send messages to Telegram chats
- Get updates from Telegram bot
- Real-time message handling
- SSE (Server-Sent Events) support for live updates

### 2. Gmail Integration
- Send plain text emails
- Send HTML emails with clickable links
- OAuth2 authentication
- Secure token management

### 3. Google Drive Integration
- Create new spreadsheets
- Update spreadsheet cells
- Share spreadsheets with users
- OAuth2 authentication

### 4. Utility Tools (MCP Server 1)
- Mathematical operations (add, subtract, multiply, divide)
- Trigonometric functions (sin, cos, tan)
- Advanced math (power, factorial, log)
- Python sandbox execution
- Shell command execution
- SQL query execution

### 5. Document Processing (MCP Server 2)
- Document search functionality
- Webpage content extraction
- PDF content extraction
- Document indexing

### 6. Search and Fetch (MCP Server 3)
- Content search capabilities
- Web content fetching
- Information retrieval

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure credentials:

### Telegram Setup
1. Create a new bot:
   - Open Telegram and search for "@BotFather"
   - Send `/newbot` command
   - Follow instructions to create bot
   - Save the API token provided

2. Configure Telegram credentials:
   ```yaml
   # config/credentials.yaml
   telegram:
     bot_token: "YOUR_BOT_TOKEN_HERE"
   ```

### Google Services Setup
1. Create Google Cloud Project:
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project
   - Enable required APIs:
     - Gmail API
     - Google Drive API
     - Google Sheets API

2. Configure OAuth2 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Create OAuth 2.0 Client ID
   - Download client secret JSON file
   - Place in project root:
     - `Gmailclient_secret_*.json`
     - `Gdriveclient_secret_*.json`

3. Configure Google credentials:
   ```yaml
   # config/credentials.yaml
   google:
     gmail:
       client_id: "YOUR_GMAIL_CLIENT_ID"
       client_secret: "YOUR_GMAIL_CLIENT_SECRET"
     drive:
       client_id: "YOUR_DRIVE_CLIENT_ID"
       client_secret: "YOUR_DRIVE_CLIENT_SECRET"
     redirect_uri: "http://localhost:8080"
   gmail:
     user: "your-email@gmail.com"
   ```

3. Run the agent:
```bash
python agent.py
```

## Core Components

### Core Module
The core module (`core/`) contains essential functionality:
- Agent initialization and configuration
- Session management
- Tool registration and management
- Error handling and logging
- Authentication management
- State management

### Modules
The `modules/` directory contains additional functionality:
- Document processing utilities
- Search and indexing tools
- Data transformation functions
- Custom utility functions
- Integration adapters

## Usage Examples

### Telegram
```python
# Send a message
send_message|chat_id="123456789"|text="Hello!"

# Get updates
get_updates
```

### Gmail
```python
# Send plain text email
send_email|to="recipient@example.com"|subject="Hello"|body="Message body"

# Send email with link
send_email_with_link|to="recipient@example.com"|subject="Hello"|body="Message body"|link="https://example.com"
```

### Google Drive
```python
# Create spreadsheet
create_spreadsheet|title="My Sheet"

# Update cells
update_sheet|spreadsheet_id="123"|range_name="A1:B2"|values=[[1,2],[3,4]]

# Share spreadsheet
share_sheet|spreadsheet_id="123"|email="user@example.com"|role="writer"
```

## Security

- OAuth2 authentication for Google services
- Secure token storage
- Environment-based configuration
- No hardcoded credentials
- Token refresh mechanism
- Secure credential management

## Dependencies

- python-telegram-bot
- google-api-python-client
- google-auth-oauthlib
- fastapi
- uvicorn
- sse-starlette
- pyyaml

