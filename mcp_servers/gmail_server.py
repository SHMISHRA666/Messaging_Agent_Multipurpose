from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent
import yaml
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64
import os.path
import pickle
import json

# Load credentials
with open("config/credentials.yaml", "r") as f:
    credentials = yaml.safe_load(f)

SCOPES = ['https://www.googleapis.com/auth/gmail.send',
          'https://www.googleapis.com/auth/gmail.compose']

mcp = FastMCP("Gmail")

def get_credentials():
    """Get or refresh Google API credentials with timeout handling"""
    try:
        creds = None
        if os.path.exists('gmail_token.pickle'):
            try:
                with open('gmail_token.pickle', 'rb') as token:
                    creds = pickle.load(token)
            except Exception as e:
                print(f"Error loading token: {e}")
                return None
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"Error refreshing token: {e}")
                    return None
            else:
                try:
                    flow = InstalledAppFlow.from_client_config(
                        {
                            "installed": {
                                "client_id": credentials["google"]["gmail"]["client_id"],
                                "client_secret": credentials["google"]["gmail"]["client_secret"],
                                "redirect_uris": [credentials["google"]["redirect_uri"]],
                                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                                "token_uri": "https://oauth2.googleapis.com/token"
                            }
                        },
                        SCOPES
                    )
                    creds = flow.run_local_server(port=0, timeout=30)  # 30 second timeout
                except Exception as e:
                    print(f"Error in authentication flow: {e}")
                    return None
            
            try:
                with open('gmail_token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                print(f"Error saving token: {e}")
                return None
        
        return creds
    except Exception as e:
        print(f"Error in get_credentials: {e}")
        return None

def create_message(sender, to, subject, message_text):
    """Create a message for an email."""
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    
    msg = MIMEText(message_text)
    message.attach(msg)
    
    return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}

@mcp.tool()
def send_email(to: str, subject: str, body: str) -> TextContent:
    """Send an email using Gmail. Usage: send_email|to="recipient@example.com"|subject="Hello"|body="Message body"""
    try:
        creds = get_credentials()
        if not creds:
            return TextContent(type="text", text="Error: Could not authenticate with Gmail")

        service = build('gmail', 'v1', credentials=creds)
        
        message = create_message(
            credentials["gmail"]["user"],
            to,
            subject,
            body
        )
        
        sent_message = service.users().messages().send(
            userId='me',
            body=message
        ).execute()
        
        return TextContent(type="text", text=json.dumps({
            'message_id': sent_message['id'],
            'thread_id': sent_message['threadId']
        }))
    except Exception as e:
        return TextContent(type="text", text=f"Error sending email: {str(e)}")

@mcp.tool()
def send_email_with_link(to: str, subject: str, body: str, link: str) -> TextContent:
    """Send an email with a link using Gmail. Usage: send_email_with_link|to="recipient@example.com"|subject="Hello"|body="Message body"|link="https://example.com"""
    try:
        creds = get_credentials()
        if not creds:
            return TextContent(type="text", text="Error: Could not authenticate with Gmail")

        service = build('gmail', 'v1', credentials=creds)
        
        # Create HTML body with link
        html_body = f"""
        <html>
            <body>
                <p>{body}</p>
                <p><a href="{link}">Click here</a></p>
            </body>
        </html>
        """
        
        message = MIMEMultipart('alternative')
        message['to'] = to
        message['from'] = credentials["gmail"]["user"]
        message['subject'] = subject
        
        # Attach both plain text and HTML versions
        message.attach(MIMEText(body, 'plain'))
        message.attach(MIMEText(html_body, 'html'))
        
        raw_message = {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
        
        sent_message = service.users().messages().send(
            userId='me',
            body=raw_message
        ).execute()
        
        return TextContent(type="text", text=json.dumps({
            'message_id': sent_message['id'],
            'thread_id': sent_message['threadId']
        }))
    except Exception as e:
        return TextContent(type="text", text=f"Error sending email with link: {str(e)}")

if __name__ == "__main__":
    mcp.run() 