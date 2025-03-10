import os
import discord
import aiosqlite
import asyncio
from datetime import datetime
from discord.ext import commands, tasks
from truthbrush.api import Api
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

# Load environment variables
load_dotenv()

# Initialize Truthbrush API with error handling
class EnhancedApi(Api):
    async def safe_pull_statuses(self, username, retries=3):
        for attempt in range(retries):
            try:
                posts = list(super().pull_statuses(username))
                return posts
            except Exception as e:
                logging.error(f"API Error (attempt {attempt+1}): {str(e)}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return None

api = EnhancedApi(
    username=os.getenv("TRUTHSOCIAL_USERNAME"),
    password=os.getenv("TRUTHSOCIAL_PASSWORD"),
)

# Setup Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    intents=intents,
    case_insensitive=True
)

# Configuration
NOTIFICATION_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", 0))
COOLDOWN_TIME = 30  # Seconds between commands per user

### 🔄 Enhanced Database Setup ###
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )""")
        await db.commit()

### ✅ Improved Bot Events ###
@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await init_db()
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="Truth Social"
    ))
    if not check_for_new_posts.is_running():
        check_for_new_posts.start()

### 🛠 Enhanced Commands ###
@bot.command(name="track")
@commands.cooldown(1, COOLDOWN_TIME, commands.BucketType.user)
async def add_user(ctx, username: str):
    """Track a Truth Social user"""
    try:
        # Sanitize username
        username = username.strip().lower()
        if not username.isalnum():
            await ctx.send("⚠️ Invalid username format")
            return

        async with aiosqlite.connect("tracked_users.db") as db:
            # Check existing tracking
            cursor = await db.execute(
                "SELECT username FROM tracked_users WHERE username = ?",
                (username,)
            )
            if await cursor.fetchone():
                await ctx.send(f"ℹ️ Already tracking @{username}")
                return

            # Verify user exists
            posts = await api.safe_pull_statuses(username)
            if not posts:
                await ctx.send(f"⚠️ User @{username} not found or has no posts")
                return

            # Insert new user
            await db.execute(
                "INSERT INTO tracked_users (username, last_post_id) VALUES (?, ?)",
                (username, posts[0]['id'])
            )
            await db.commit()
            
            embed = discord.Embed(
                title="✅ Tracking Started",
                description=f"Now tracking @{username}",
                color=0x00ff00
            )
            embed.add_field(name="First Post ID", value=posts[0]['id'])
            embed.set_footer(text=f"Requested by {ctx.author.display_name}")
            await ctx.send(embed=embed)

    except Exception as e:
        logging.error(f"Track Error: {str(e)}")
        await ctx.send("⚠️ Error processing request")

@bot.command(name="stats")
async def bot_stats(ctx):
    """Show bot statistics"""
    async with aiosqlite.connect("tracked_users.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM tracked_users")
        total_users = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT SUM(notification_count) FROM tracked_users")
        total_notifications = (await cursor.fetchone())[0] or 0

    embed = discord.Embed(
        title="Bot Statistics",
        color=0x7289da,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Tracked Users", value=total_users)
    embed.add_field(name="Total Notifications", value=total_notifications)
    embed.add_field(name="Uptime", value=str(bot.latency * 1000)[:5] + "ms")
    await ctx.send(embed=embed)

### 🔄 Enhanced Background Task ###
@tasks.loop(minutes=5)
async def check_for_new_posts():
    """Check for new posts from tracked users"""
    try:
        async with aiosqlite.connect("tracked_users.db") as db:
            cursor = await db.execute(
                "SELECT username, last_post_id FROM tracked_users"
            )
            tracked_users = await cursor.fetchall()

        channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not channel:
            logging.error(f"Invalid notification channel: {NOTIFICATION_CHANNEL_ID}")
            return

        for username, last_post_id in tracked_users:
            try:
                posts = await api.safe_pull_statuses(username)
                if not posts:
                    continue

                latest_post = posts[0]
                if latest_post['id'] != last_post_id:
                    await send_post_notification(channel, username, latest_post)
                    await update_tracking_record(username, latest_post)

            except Exception as e:
                logging.error(f"Post Check Error ({username}): {str(e)}")

    except Exception as e:
        logging.error(f"Background Task Error: {str(e)}")

async def send_post_notification(channel, username, post):
    """Send enriched post notification"""
    embed = discord.Embed(
        title=f"New Post from @{username}",
        description=post["content"][:2000],  # Discord limit
        color=0x00ff00,
        url=f"https://truthsocial.com/@{username}/posts/{post['id']}",
        timestamp=datetime.strptime(post["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
    )
    
    # Add media if available
    if post.get("media_attachments"):
        embed.set_image(url=post["media_attachments"][0]["url"])
    
    # Add engagement metrics
    engagement = [
        f"♥️ {post.get('favourites_count', 0)}",
        f"🔄 {post.get('reblogs_count', 0)}",
        f"💬 {post.get('replies_count', 0)}"
    ]
    embed.add_field(name="Engagement", value="\n".join(engagement))
    
    # Add author info
    embed.set_author(
        name=f"@{username}",
        icon_url=post["account"].get("avatar", "")
    )
    
    await channel.send(embed=embed)

async def update_tracking_record(username, post):
    """Update database with new post info"""
    async with aiosqlite.connect("tracked_users.db") as db:
        await db.execute(
            """UPDATE tracked_users 
            SET last_post_id = ?, 
                last_post_content = ?,
                notification_count = notification_count + 1
            WHERE username = ?""",
            (post['id'], post['content'], username)
        )
        await db.commit()

### 🆕 New Features ###
@bot.command(name="search")
async def search_posts(ctx, username: str, *, query: str):
    """Search posts from a user"""
    try:
        posts = await api.safe_pull_statuses(username)
        if not posts:
            await ctx.send(f"No posts found for @{username}")
            return

        matches = [p for p in posts if query.lower() in p['content'].lower()]
        
        embed = discord.Embed(
            title=f"Search Results for '{query}'",
            description=f"Found {len(matches)} posts from @{username}",
            color=0x7289da
        )
        
        for post in matches[:3]:
            embed.add_field(
                name=f"Post {post['id']}",
                value=f"{post['content'][:200]}...",
                inline=False
            )
            
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"Error searching posts: {str(e)}")

### 🛡 Error Handling ###
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⚠️ Command on cooldown. Try again in {error.retry_after:.1f}s")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("⚠️ Missing required argument")
    else:
        logging.error(f"Command Error: {str(error)}")

### 🚀 Run Setup ###
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        logging.critical("Missing Discord bot token")
        exit(1)

    try:
        logging.info("Starting bot...")
        bot.run(TOKEN)
    except Exception as e:
        logging.critical(f"Failed to start bot: {str(e)}")
