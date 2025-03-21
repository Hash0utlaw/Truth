Truth Social Tracker
A Discord bot that monitors Truth Social accounts in real-time and posts updates to a Discord channel.
Overview
Truth Social Tracker automatically fetches new posts from Truth Social accounts and shares them in your Discord server. The bot displays complete posts with media attachments, engagement metrics, and profile information.
Features

Track multiple Truth Social accounts simultaneously
Real-time updates posted to your Discord channel (checks every 5 minutes)
Display full post content, media attachments, and engagement metrics
Support for images, videos, and links in posts
Easy-to-use commands for managing tracked accounts
Case-insensitive username handling
Fallback mechanisms for reliable operation

Installation
Prerequisites

Python 3.8 or higher
A Discord bot token
An Apify API token

Setup

Clone this repository:
bashCopygit clone https://github.com/yourusername/truth-social-tracker.git
cd truth-social-tracker

Install the required packages:
bashCopypip install -r requirements.txt

Create a .env file in the project root with your tokens:
CopyDISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_CHANNEL_ID=your_discord_channel_id_here
APIFY_API_TOKEN=apify_api_your_apify_token_here

Run the bot:
bashCopypython main.py


Configuration
Environment Variables

DISCORD_BOT_TOKEN: Your Discord bot token (from Discord Developer Portal)
DISCORD_CHANNEL_ID: The Discord channel ID where posts will be sent
APIFY_API_TOKEN: Your Apify API token (from Apify Console)

Database
The bot uses a SQLite database (tracked_users.db) to store information about tracked accounts. This is created automatically when the bot first runs.
Commands
All commands use the ! prefix by default:

!track [username] - Start tracking a Truth Social user

Example: !track realDonaldTrump


!untrack [username] - Stop tracking a user

Example: !untrack realDonaldTrump


!list - Show all currently tracked accounts with statistics
!bothelp - Display help information about the bot

Troubleshooting
Common Issues

"Unauthorized" or "401" errors:

Check your APIFY_API_TOKEN is correct and starts with "apify_api_"
Regenerate your token in the Apify Console if needed


Bot not posting new content:

Check if the DISCORD_CHANNEL_ID is correct
Verify the bot has permission to post in the channel
Use !list to confirm accounts are being tracked


Mock data appearing instead of real posts:

The bot automatically filters out mock/test data
This may occur when Truth Social's API has no new posts available


Profile information errors:

The bot implements multiple fallback mechanisms to get accurate profile data
Try deleting and re-adding the account with !untrack and !track



Advanced Debugging
The bot logs information to both the console and a bot.log file. Check these for detailed error messages and debugging information.
Architecture
The bot consists of several core components:

Discord Interface: Handles commands and posts content to Discord
Truth Social Scraper: Connects to Truth Social's API via Apify
Database Manager: Keeps track of monitored accounts and their last posts
Flask Server: Keeps the bot alive if running on a hosting service like Replit

The bot uses a task loop that checks for new posts every 5 minutes.
Credits

Built with discord.py
Truth Social data provided by Apify's Truth Social Scraper

License
This project is licensed under the MIT License - see the LICENSE file for details.

Developed with ❤️ by Hash0utlaw