from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent
import yaml
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os.path
import json
import pickle
import os
import sys
import logging
import time

# Set up logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP with error handling and timeout
try:
    logger.info("Initializing FastMCP...")
    mcp = FastMCP("GoogleDrive")
    logger.info("FastMCP initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize FastMCP: {e}")
    sys.exit(1)

# Defer credential loading until needed
def load_credentials():
    try:
        logger.info("Loading credentials from file...")
        credentials_path = os.path.join(os.path.dirname(__file__), "..", "config", "credentials.yaml")
        if not os.path.exists(credentials_path):
            logger.error(f"Credentials file not found at {credentials_path}")
            return None
            
        with open(credentials_path, "r") as f:
            credentials = yaml.safe_load(f)
            logger.info("Credentials loaded successfully")
            return credentials
    except Exception as e:
        logger.error(f"Error loading credentials: {e}")
        return None

SCOPES = ['https://www.googleapis.com/auth/drive.file',
          'https://www.googleapis.com/auth/spreadsheets']

def get_credentials():
    """Get or refresh Google API credentials with timeout handling"""
    try:
        logger.info("Getting Google API credentials...")
        start_time = time.time()
        timeout = 30  # 30 seconds timeout

        credentials = load_credentials()
        if not credentials:
            logger.error("No credentials available")
            return None

        creds = None
        token_path = os.path.join(os.path.dirname(__file__), "..", "drive_token.pickle")
        
        if os.path.exists(token_path):
            logger.info("Found existing token file, attempting to load...")
            try:
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
                logger.info("Token loaded successfully")
            except Exception as e:
                logger.error(f"Error loading token: {e}")
        
        if not creds or not creds.valid:
            logger.info("Token invalid or expired, refreshing...")
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Token refreshed successfully")
                except Exception as e:
                    logger.error(f"Error refreshing token: {e}")
                    return None
            else:
                logger.info("Starting new authentication flow...")
                try:
                    flow = InstalledAppFlow.from_client_config(
                        {
                            "installed": {
                                "client_id": credentials["google"]["drive"]["client_id"],
                                "client_secret": credentials["google"]["drive"]["client_secret"],
                                "redirect_uris": [credentials["google"]["redirect_uri"]],
                                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                                "token_uri": "https://oauth2.googleapis.com/token"
                            }
                        },
                        SCOPES
                    )
                    creds = flow.run_local_server(port=0, timeout=timeout)
                    logger.info("New authentication completed successfully")
                except Exception as e:
                    logger.error(f"Error in authentication flow: {e}")
                    return None
            
            try:
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
                logger.info("Token saved successfully")
            except Exception as e:
                logger.error(f"Error saving token: {e}")
        
        if time.time() - start_time > timeout:
            logger.error("Authentication process timed out")
            return None
            
        return creds
    except Exception as e:
        logger.error(f"Error in get_credentials: {e}")
        return None

@mcp.tool()
def create_spreadsheet(title: str) -> TextContent:
    """Create a new Google Spreadsheet. Usage: create_spreadsheet|title="My Sheet"""
    try:
        creds = get_credentials()
        if not creds:
            return TextContent(type="text", text="Error: Could not authenticate with Google Drive")

        service = build('sheets', 'v4', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Create the spreadsheet
        spreadsheet = {
            'properties': {
                'title': title
            }
        }
        spreadsheet = service.spreadsheets().create(body=spreadsheet).execute()
        
        # Move to specified folder if folder_id is provided
        credentials = load_credentials()
        if credentials and credentials.get("drive", {}).get("folder_id"):
            file = drive_service.files().update(
                fileId=spreadsheet['spreadsheetId'],
                addParents=credentials["drive"]["folder_id"],
                fields='id, parents'
            ).execute()
        
        response = {
            'spreadsheet_id': spreadsheet['spreadsheetId'],
            'url': f"https://docs.google.com/spreadsheets/d/{spreadsheet['spreadsheetId']}"
        }
        return TextContent(type="text", text=json.dumps(response))
    except Exception as e:
        logger.error(f"Error creating spreadsheet: {e}")
        return TextContent(type="text", text=f"Error creating spreadsheet: {str(e)}")

@mcp.tool()
def update_sheet(spreadsheet_id: str, range_name: str, values: list) -> TextContent:
    """Update values in a Google Sheet. Usage: update_sheet|spreadsheet_id="123"|range_name="A1:B2"|values=[[1,2],[3,4]]"""
    try:
        creds = get_credentials()
        if not creds:
            return TextContent(type="text", text="Error: Could not authenticate with Google Drive")

        service = build('sheets', 'v4', credentials=creds)
        
        body = {
            'values': values
        }
        
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()
        
        return TextContent(type="text", text=json.dumps({
            'updated_cells': result.get('updatedCells'),
            'updated_range': result.get('updatedRange')
        }))
    except Exception as e:
        logger.error(f"Error updating sheet: {e}")
        return TextContent(type="text", text=f"Error updating sheet: {str(e)}")

@mcp.tool()
def share_sheet(spreadsheet_id: str, email: str, role: str = 'reader') -> TextContent:
    """Share a Google Sheet with someone. Usage: share_sheet|spreadsheet_id="123"|email="user@example.com"|role="writer"""
    try:
        creds = get_credentials()
        if not creds:
            return TextContent(type="text", text="Error: Could not authenticate with Google Drive")

        drive_service = build('drive', 'v3', credentials=creds)
        
        user_permission = {
            'type': 'user',
            'role': role,
            'emailAddress': email
        }
        
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body=user_permission,
            fields='id'
        ).execute()
        
        return TextContent(type="text", text=f"Successfully shared with {email}")
    except Exception as e:
        logger.error(f"Error sharing sheet: {e}")
        return TextContent(type="text", text=f"Error sharing sheet: {str(e)}")

if __name__ == "__main__":
    try:
        logger.info("Starting Google Drive server...")
        # Check if we're being run as an MCP server
        if os.environ.get("MCP_SERVER") == "1":
            logger.info("Running in MCP server mode")
            # Run only the MCP server
            mcp.run(transport="stdio")
        else:
            logger.info("Running in development mode")
            # Run in development mode
            mcp.run()
        logger.info("Server shutdown complete")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)