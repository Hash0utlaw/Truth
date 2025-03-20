from flask import Flask
from threading import Thread
import os
import discord
import aiosqlite
import asyncio
import aiohttp
import json
from datetime import datetime
from discord.ext import commands, tasks
from apify_client import ApifyClient
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# Keep-alive server
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot Status: Online"

Thread(target=lambda: app.run(
    host='0.0.0.0',
    port=8080,
    debug=False,
    use_reloader=False
)).start()

# Load environment variables
load_dotenv()

class TruthSocialScraper:
    def __init__(self):
        # Get the API token from environment variables
        self.api_token = os.getenv("APIFY_API_TOKEN")
        if not self.api_token:
            logging.critical("Missing APIFY_API_TOKEN environment variable")
            raise ValueError("APIFY_API_TOKEN not set in environment")
        
        # Check if token has the proper format
        if not self.api_token.startswith("apify_api_"):
            logging.warning("API token doesn't have the expected 'apify_api_' prefix. This might indicate an invalid token.")
            
        self.actor_id = "muhammetakkurtt~truth-social-scraper"
        self.base_url = "https://api.apify.com/v2"
        
        # Log token validation attempt (without revealing the full token)
        masked_token = self.api_token[:10] + "..." if len(self.api_token) > 10 else "***"
        logging.info(f"Initializing Apify client with token starting with {masked_token}")
        
        # Initialize as a fallback, but we'll use direct API calls first
        self.client = ApifyClient(self.api_token)
    
    async def test_token_validity(self):
        """Test if the API token is valid by making a simple API call"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get user info (a simple endpoint to test token validity)
                url = f"{self.base_url}/users/me"
                headers = {"Authorization": f"Bearer {self.api_token}"}
                
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        logging.info(f"Apify token validated successfully for user: {data.get('data', {}).get('username', 'unknown')}")
                        return True
                    else:
                        error_text = await response.text()
                        logging.error(f"Token validation failed: {response.status} - {error_text}")
                        return False
        except Exception as e:
            logging.error(f"Token validation error: {str(e)}")
            return False

    async def get_user_data_direct(self, username, last_post_id=None):
        """Fetch user data using direct API calls"""
        try:
            # Prepare the run input
            run_input = {
                "username": username,
                "maxPosts": 20,  # Changed from 15 to 20 to meet API requirements
                "useLastPostId": bool(last_post_id),
                "onlyReplies": False,
                "onlyMedia": False,
                "cleanContent": True,
                "startPostId": last_post_id or ""
            }
            
            # Initiate the synchronous run and get dataset items directly
            async with aiohttp.ClientSession() as session:
                # Use the run-sync-get-dataset-items endpoint for efficiency
                url = f"{self.base_url}/acts/{self.actor_id}/run-sync-get-dataset-items"
                
                # Add authorization header instead of token in URL (more secure)
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_token}"
                }
                
                async with session.post(url, json=run_input, headers=headers) as response:
                    # Accept both 200 and 201 status codes as success
                    if response.status not in [200, 201]:
                        error_text = await response.text()
                        logging.error(f"API Error: {response.status} - {error_text}")
                        return None
                    
                    items = await response.json()
                    
                    # Log what we received from the API
                    if items and isinstance(items, list):
                        logging.info(f"API returned {len(items)} items")
                        if items:
                            logging.info(f"First item ID: {items[0].get('id', 'None')}")
                    
                    # Process the returned data
                    if items and isinstance(items, list) and len(items) > 0:
                        # Format the response to match what the bot expects
                        first_item = items[0]
                        if isinstance(first_item, dict) and first_item.get('account'):
                            # This is a single post format
                            return {
                                "profile": {
                                    "followers_count": first_item.get("account", {}).get("followers_count", 0),
                                    "statuses_count": first_item.get("account", {}).get("statuses_count", 0),
                                    "verified": first_item.get("account", {}).get("verified", False),
                                    "display_name": first_item.get("account", {}).get("display_name", username),
                                    "avatar": first_item.get("account", {}).get("avatar", "")
                                },
                                "posts": items
                            }
                        else:
                            # This is likely already in the expected format
                            return first_item
                    
                    return None
        except Exception as e:
            logging.error(f"Scraper Direct API Error: {str(e)}")
            return await self.get_user_data_fallback(username, last_post_id)
    
    async def get_user_data_fallback(self, username, last_post_id=None):
        """Fallback method using the Apify client library"""
        try:
            logging.info("Using fallback method to fetch user data")
            run_input = {
                "username": username,
                "maxPosts": 20,  # Changed from 15 to 20 to meet API requirements
                "useLastPostId": bool(last_post_id),
                "onlyReplies": False,
                "onlyMedia": False,
                "cleanContent": True,
                "startPostId": last_post_id or ""
            }
            
            # Create run with proper client configuration
            actor = self.client.actor(self.actor_id)
            run = actor.call(run_input=run_input)
            
            if not run or not run.get("defaultDatasetId"):
                logging.error("Failed to get defaultDatasetId from actor run")
                return None
            
            # Wait for the run to finish
            logging.info(f"Waiting for Apify run {run.get('id')} to finish...")
            
            # Use REST API to get dataset items directly instead of using the async iterator
            dataset_id = run.get("defaultDatasetId")
            url = f"{self.base_url}/datasets/{dataset_id}/items"
            
            # Get dataset items directly with HTTP request
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.api_token}"}
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logging.error(f"Dataset API Error: {response.status} - {error_text}")
                        return None
                    
                    items = await response.json()
                    
                    # Process the response and format it as expected
                    if items and isinstance(items, list) and len(items) > 0:
                        # Format the response to match what the bot expects
                        return {
                            "profile": {
                                "followers_count": items[0].get("account", {}).get("followers_count", 0),
                                "statuses_count": items[0].get("account", {}).get("statuses_count", 0),
                                "verified": items[0].get("account", {}).get("verified", False),
                                "display_name": items[0].get("account", {}).get("display_name", username),
                                "avatar": items[0].get("account", {}).get("avatar", "")
                            },
                            "posts": items
                        }
                    return None
        except Exception as e:
            logging.error(f"Scraper Fallback Error: {str(e)}")
            return None
            
    async def get_user_data(self, username, last_post_id=None):
        """Main method to fetch user data, tries direct API first, then fallback"""
        # Try the direct API method first
        result = await self.get_user_data_direct(username, last_post_id)
        
        # If direct method fails, use the fallback
        if result is None:
            result = await self.get_user_data_fallback(username, last_post_id)
            
        return result

# Initialize scraper
scraper = TruthSocialScraper()

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    intents=intents,
    case_insensitive=True
)

# Configuration
NOTIFICATION_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", 0))
COOLDOWN_TIME = 30

async def init_db():
    async with aiosqlite.connect("tracked_users.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                last_post_id TEXT,
                last_post_content TEXT,
                track_since TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notification_count INTEGER DEFAULT 0
            )""")
        await db.commit()

@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await init_db()
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="Truth Social Posts"
    ))
    
    # Test if the Apify token is valid
    token_valid = await scraper.test_token_validity()
    if not token_valid:
        logging.critical("Apify token validation failed. Please check your token.")
        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            await channel.send("⚠️ **ERROR**: Apify API token validation failed. The bot will not be able to fetch posts until this is fixed.")
    else:
        logging.info("Apify token validated successfully.")
        if not check_for_new_posts.is_running():
            check_for_new_posts.start()

@bot.command(name="track")
@commands.cooldown(1, COOLDOWN_TIME, commands.BucketType.user)
async def add_user(ctx, username: str):
    """Track a Truth Social user"""
    try:
        username = username.strip().lower()
        # Allow alphanumeric characters plus underscores for Truth Social usernames
        if not all(c.isalnum() or c == '_' for c in username):
            await ctx.send("⚠️ Invalid username format. Usernames can only contain letters, numbers, and underscores.")
            return

        async with aiosqlite.connect("tracked_users.db") as db:
            cursor = await db.execute(
                "SELECT username FROM tracked_users WHERE LOWER(username) = LOWER(?)",
                (username,)
            )
            if await cursor.fetchone():
                await ctx.send(f"ℹ️ Already tracking @{username}")
                return

            # Show a processing message to the user
            status_message = await ctx.send(f"📡 Looking up @{username} on Truth Social...")
            
            # Fetch user data
            data = await scraper.get_user_data(username)
            
            # Check for valid response
            if not data:
                await status_message.edit(content=f"⚠️ User @{username} not found or there was an error connecting to Truth Social")
                return
                
            if not data.get('posts') or len(data['posts']) == 0:
                await status_message.edit(content=f"⚠️ User @{username} has no posts or their account is private")
                return

            # Get the latest post
            latest_post = data['posts'][0]
            
            # Insert the user into the database
            await db.execute(
                "INSERT INTO tracked_users (username, last_post_id, last_post_content) VALUES (?, ?, ?)",
                (username, latest_post['id'], latest_post.get('content', ''))
            )
            await db.commit()
            
            # Send confirmation embed
            profile = data['profile']
            embed = discord.Embed(
                title="🔔 Tracking Started",
                description=f"Now monitoring [@{username}](https://truthsocial.com/@{username})",
                color=0x3A8FD9
            )
            
            # Add stats if available
            if profile:
                embed.add_field(
                    name="Profile Stats",
                    value=f"Followers: {profile.get('followers_count', 'Unknown')}\n"
                          f"Posts: {profile.get('statuses_count', 'Unknown')}\n"
                          f"Verified: {'✅' if profile.get('verified', False) else '❌'}",
                    inline=False
                )
                
            # Add example of latest post
            if latest_post.get('content'):
                content = latest_post['content']
                if len(content) > 100:
                    content = f"{content[:100]}..."
                embed.add_field(
                    name="Latest Post",
                    value=content or "(No text content)",
                    inline=False
                )
                
            # Delete the processing message and send the confirmation
            await status_message.delete()
            await ctx.send(embed=embed)
            logging.info(f"Started tracking @{username}")

    except Exception as e:
        logging.error(f"Track Error: {str(e)}")
        await ctx.send(f"⚠️ Error processing request: {str(e)}")

@bot.command(name="untrack")
async def remove_user(ctx, username: str):
    """Stop tracking a user"""
    async with aiosqlite.connect("tracked_users.db") as db:
        cursor = await db.execute(
            "DELETE FROM tracked_users WHERE LOWER(username)=LOWER(?)", (username,)
        )
        if cursor.rowcount > 0:
            await db.commit()
            embed = discord.Embed(
                description=f"🚫 Stopped tracking [@{username}](https://truthsocial.com/@{username})",
                color=0xFF0000
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"⚠️ @{username} was not being tracked.")

@bot.command(name="list")
async def list_users(ctx):
    """List tracked users"""
    async with aiosqlite.connect("tracked_users.db") as db:
        async with db.execute(
            """SELECT username, track_since, notification_count, last_post_id 
               FROM tracked_users ORDER BY track_since DESC"""
        ) as cursor:
            users = await cursor.fetchall()

    if not users:
        await ctx.send("📝 No accounts are currently being tracked.")
        return
        
    embed = discord.Embed(
        title="📋 Tracked Accounts",
        color=0x3A8FD9,
        description=f"Currently tracking {len(users)} account{'s' if len(users) != 1 else ''}"
    )
    
    for username, track_since, notification_count, last_post_id in users:
        # Format the tracking date
        track_date = track_since.split()[0] if track_since else "Unknown"
        
        # Create a value field with stats
        value = f"📅 Since: {track_date}\n📤 Posts tracked: {notification_count or 0}"
        
        # Add link to the account
        embed.add_field(
            name=f"@{username}",
            value=f"{value}\n🔗 [View on Truth Social](https://truthsocial.com/@{username})",
            inline=True
        )
        
    await ctx.send(embed=embed)

@bot.command(name="bothelp")
async def help_command(ctx):
    """Show command help"""
    embed = discord.Embed(
        title="Truth Social Tracker Help",
        description="Monitor Truth Social accounts in real-time",
        color=0x3A8FD9
    )
    
    # Add bot logo/icon if available
    # embed.set_thumbnail(url="https://truthsocial.com/favicon.ico")
    
    # Command section
    embed.add_field(
        name="📋 Commands",
        value=(
            "**`!track [username]`** - Start tracking a Truth Social user\n"
            "**`!untrack [username]`** - Stop tracking a user\n"
            "**`!list`** - Show all tracked accounts\n"
            "**`!bothelp`** - Show this help message"
        ),
        inline=False
    )
    
    # Examples section
    embed.add_field(
        name="📝 Examples",
        value=(
            "**`!track realDonaldTrump`** - Track Donald Trump's account\n"
            "**`!untrack realDonaldTrump`** - Stop tracking Donald Trump's account\n"
        ),
        inline=False
    )
    
    # Tips section
    embed.add_field(
        name="💡 Tips",
        value=(
            "• Usernames are not case-sensitive\n"
            "• New posts are checked every 5 minutes\n"
            "• The bot will display all media attached to posts\n"
            "• For video posts, click the link to view on Truth Social"
        ),
        inline=False
    )
    
    # Footer with version
    embed.set_footer(text="Truth Social Tracker v1.1.0")
    
    await ctx.send(embed=embed)

@tasks.loop(minutes=5)
async def check_for_new_posts():
    async with aiosqlite.connect("tracked_users.db") as db:
        cursor = await db.execute(
            "SELECT username, last_post_id FROM tracked_users"
        )
        tracked_users = await cursor.fetchall()

    channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if not channel:
        return

    for username, last_post_id in tracked_users:
        try:
            # Normalize username to lowercase for case-insensitive matching
            normalized_username = username.lower()
            logging.info(f"Checking for new posts from @{normalized_username}")
            
            data = await scraper.get_user_data(normalized_username, last_post_id)
            if not data:
                logging.warning(f"No data returned for @{normalized_username}")
                continue
                
            if not data.get('posts'):
                logging.warning(f"No posts found for @{normalized_username}")
                continue

            # Debug logging
            logging.info(f"Found {len(data['posts'])} posts for @{normalized_username}")
            
            # Verify the structure of the first post to ensure we can process it
            if data['posts'] and len(data['posts']) > 0:
                first_post = data['posts'][0]
                post_id = first_post.get('id', 'Unknown')
                created_at = first_post.get('created_at', 'Unknown')
                logging.info(f"First post ID: {post_id}, created at: {created_at}")
                logging.info(f"Post content preview: {first_post.get('content', '')[:100]}...")

            # Filter out mock data and posts we've already seen
            new_posts = [post for post in data['posts'] 
                         if post['id'] != last_post_id and not str(post['id']).startswith('mock_')]
            
            # Log filtered posts
            if new_posts:
                logging.info(f"After filtering, found {len(new_posts)} new posts")
                for i, post in enumerate(new_posts):
                    logging.info(f"New post {i+1} ID: {post.get('id')}")
            else:
                logging.info("No new posts after filtering")
                
            if not new_posts:
                logging.info(f"No new posts for @{normalized_username}")
                continue

            logging.info(f"Found {len(new_posts)} new posts for @{normalized_username}")

            # Process posts in reverse order to maintain chronological order
            for post in reversed(new_posts):
                try:
                    # Get profile data
                    profile = data['profile']
                    display_name = profile.get('display_name', normalized_username)
                    verified = profile.get('verified', False)
                    
                    # Create a timestamp for the footer
                    timestamp = datetime.strptime(post["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
                    local_time = timestamp.strftime("%I:%M %p")
                    
                    # Create the embed with improved styling
                    embed = discord.Embed(
                        color=0x3A8FD9,  # Truth Social blue
                        timestamp=timestamp
                    )
                    
                    # Add author information with verification badge if verified
                    author_name = f"{display_name} (@{normalized_username})" + (" ✓" if verified else "")
                    embed.set_author(
                        name=author_name,
                        icon_url=profile.get('avatar', ''),
                        url=f"https://truthsocial.com/@{normalized_username}"
                    )
                    
                    # Add post content - don't truncate unless extremely long
                    content = post.get('content', '')
                    if content:
                        if len(content) > 1500:  # Only truncate if very long (Discord limit is 4096)
                            content = f"{content[:1500]}... [View More](https://truthsocial.com/@{normalized_username}/posts/{post['id']})"
                        embed.description = content
                    
                    # Add media attachments
                    if post.get('media_attachments') and len(post['media_attachments']) > 0:
                        media = post['media_attachments'][0]
                        
                        # Check media type (image or video)
                        if media.get('type') == 'image':
                            embed.set_image(url=media.get('url', ''))
                        elif media.get('type') == 'video':
                            # For videos, use the preview image and add a note
                            if media.get('preview_url'):
                                embed.set_image(url=media.get('preview_url', ''))
                                embed.add_field(
                                    name="🎬 Video",
                                    value=f"[Click to watch](https://truthsocial.com/@{normalized_username}/posts/{post['id']})",
                                    inline=False
                                )
                        
                        # Add indicator for multiple attachments
                        if len(post['media_attachments']) > 1:
                            embed.add_field(
                                name="📁 Media",
                                value=f"Contains {len(post['media_attachments'])} attachments",
                                inline=False
                            )
                    
                    # Add card/link preview if available
                    if post.get('card') and post['card'].get('url'):
                        card = post['card']
                        card_text = f"[{card.get('title', 'Link')}]({card.get('url')})"
                        if card.get('description'):
                            card_desc = card.get('description')
                            if len(card_desc) > 100:
                                card_desc = card_desc[:97] + "..."
                            card_text += f"\n{card_desc}"
                        
                        embed.add_field(
                            name="🔗 Linked Content",
                            value=card_text,
                            inline=False
                        )
                        
                        # Add card image if available
                        if card.get('image') and not embed.image.url:
                            embed.set_image(url=card.get('image'))
                    
                    # Add engagement metrics
                    engagement = [
                        f"♻️ {post.get('reblogs_count', 0):,}",
                        f"❤️ {post.get('favourites_count', 0):,}",
                        f"💬 {post.get('replies_count', 0):,}"
                    ]
                    
                    # Add footer with timestamp and view link
                    embed.set_footer(
                        text=f"{' • '.join(engagement)} • {local_time} • View on Truth Social",
                        icon_url="https://truthsocial.com/favicon.ico"
                    )
                    
                    # Send the embed
                    await channel.send(embed=embed)
                    
                    # If there are additional media attachments, send them as separate messages
                    if post.get('media_attachments') and len(post['media_attachments']) > 1:
                        media_embed = discord.Embed(
                            color=0x3A8FD9,  # Truth Social blue
                            title=f"Additional media from @{normalized_username}"
                        )
                        
                        for i, media in enumerate(post['media_attachments'][1:], 1):
                            if media.get('type') == 'image':
                                media_embed.set_image(url=media.get('url', ''))
                                await channel.send(embed=media_embed)
                            elif media.get('type') == 'video' and media.get('preview_url'):
                                media_embed.set_image(url=media.get('preview_url', ''))
                                media_embed.description = f"[Click to watch video {i+1}](https://truthsocial.com/@{normalized_username}/posts/{post['id']})"
                                await channel.send(embed=media_embed)

                except Exception as e:
                    logging.error(f"Error processing post {post.get('id')}: {str(e)}")
                    continue

            # Update database with latest post
            latest_post = new_posts[-1]
            async with aiosqlite.connect("tracked_users.db") as db:
                await db.execute(
                    """UPDATE tracked_users 
                    SET last_post_id = ?, 
                        last_post_content = ?,
                        notification_count = notification_count + 1
                    WHERE username = ?""",
                    (latest_post['id'], latest_post.get('content', ''), username)
                )
                await db.commit()
                logging.info(f"Updated database with latest post ID {latest_post['id']} for @{normalized_username}")

        except Exception as e:
            logging.error(f"Post Check Error ({username}): {str(e)}")

@check_for_new_posts.before_loop
async def before_check():
    await bot.wait_until_ready()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s")
    else:
        logging.error(f"Command Error: {str(error)}")

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        logging.critical("Missing Discord bot token")
        exit(1)
        
    # Validate Apify token exists
    APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
    if not APIFY_TOKEN:
        logging.critical("Missing Apify API token")
        exit(1)
        
    # Validate Apify token format
    if not APIFY_TOKEN.startswith("apify_api_"):
        logging.warning("Apify token doesn't have the expected format (should start with 'apify_api_')")
        logging.warning("You may need to regenerate your token at https://console.apify.com/account/integrations")

    try:
        logging.info("Starting Enhanced Truth Social Tracker...")
        bot.run(TOKEN)
    except Exception as e:
        logging.critical(f"Failed to start bot: {str(e)}")