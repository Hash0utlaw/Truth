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

# Custom API Class with enhanced error handling
class EnhancedApi(Api):
    async def safe_pull_statuses(self, username, retries=3):
        for attempt in range(retries):
            try:
                posts = list(super().pull_statuses(
                    username,
                    with_media=True,
                    extended=True
                ))
                return posts
            except Exception as e:
                logging.error(f"API Error (attempt {attempt+1}): {str(e)}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return None

# Initialize API
api = EnhancedApi(
    username=os.getenv("TRUTHSOCIAL_USERNAME"),
    password=os.getenv("TRUTHSOCIAL_PASSWORD"),
)

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
COOLDOWN_TIME = 30  # Seconds between commands per user

### 🗄 Database Setup ###
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

### 🚀 Bot Events ###
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

### 💬 Commands ###
@bot.command(name="track")
@commands.cooldown(1, COOLDOWN_TIME, commands.BucketType.user)
async def add_user(ctx, username: str):
    """Track a Truth Social user"""
    try:
        username = username.strip().lower()
        if not username.isalnum():
            await ctx.send("⚠️ Invalid username format")
            return

        async with aiosqlite.connect("tracked_users.db") as db:
            cursor = await db.execute(
                "SELECT username FROM tracked_users WHERE username = ?",
                (username,)
            )
            if await cursor.fetchone():
                await ctx.send(f"ℹ️ Already tracking @{username}")
                return

            posts = await api.safe_pull_statuses(username)
            if not posts:
                await ctx.send(f"⚠️ User @{username} not found or has no posts")
                return

            await db.execute(
                "INSERT INTO tracked_users (username, last_post_id) VALUES (?, ?)",
                (username, posts[0]['id'])
            await db.commit()
            
            embed = discord.Embed(
                title="🔔 Tracking Started",
                description=f"Now monitoring [@{username}](https://truthsocial.com/@{username})",
                color=0x1DA1F2
            )
            embed.add_field(
                name="Features",
                value="• Post notifications\n• Media previews\n• Engagement metrics",
                inline=False
            )
            embed.set_footer(text=f"Notification channel: #{ctx.channel.name}")
            await ctx.send(embed=embed)

    except Exception as e:
        logging.error(f"Track Error: {str(e)}")
        await ctx.send("⚠️ Error processing request")

@bot.command(name="untrack")
async def remove_user(ctx, username: str):
    """Stop tracking a user"""
    async with aiosqlite.connect("tracked_users.db") as db:
        cursor = await db.execute(
            "DELETE FROM tracked_users WHERE username=?", (username,)
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
            "SELECT username, track_since FROM tracked_users ORDER BY track_since DESC"
        ) as cursor:
            users = await cursor.fetchall()

    if not users:
        await ctx.send("📭 No tracked users")
        return

    embed = discord.Embed(
        title="Tracked Accounts",
        color=0x1DA1F2,
        description=f"Total tracked: {len(users)}"
    )
    
    for username, track_since in users:
        embed.add_field(
            name=f"@{username}",
            value=f"Tracking since: {track_since.split()[0]}",
            inline=False
        )
        
    await ctx.send(embed=embed)

### 🔄 Background Checker ###
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
                if not posts or posts[0]['id'] == last_post_id:
                    continue

                latest_post = posts[0]
                await send_post_notification(channel, username, latest_post)
                await update_tracking_record(username, latest_post)

            except Exception as e:
                logging.error(f"Post Check Error ({username}): {str(e)}")

    except Exception as e:
        logging.error(f"Background Task Error: {str(e)}")

async def send_post_notification(channel, username, post):
    """Create Twitter-style embed with media"""
    embed = discord.Embed(
        color=0x1DA1F2,
        description=f"[View Post](https://truthsocial.com/@{username}/posts/{post['id']})",
        timestamp=datetime.strptime(post["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
    )
    
    # Author Header
    embed.set_author(
        name=f"{post['account']['display_name']} (@{username})",
        icon_url=post["account"].get("avatar", ""),
        url=f"https://truthsocial.com/@{username}"
    )

    # Content with Truncation
    content = post["content"]
    if len(content) > 250:
        content = f"{content[:250]}... [View More](https://truthsocial.com/@{username}/posts/{post['id']})"
    embed.add_field(name="\u200b", value=content, inline=False)

    # Media Handling
    if post.get("media_attachments"):
        media = post["media_attachments"][0]
        if media["type"] == "image":
            embed.set_image(url=media["url"])
            
            # Additional Media Counter
            if len(post["media_attachments"]) > 1:
                embed.add_field(
                    name="Media",
                    value=f"Contains {len(post['media_attachments'])} images",
                    inline=False
                )

    # Engagement Metrics
    engagement = [
        f"♻️ {post.get('reblogs_count', 0)}",
        f"❤️ {post.get('favourites_count', 0)}",
        f"💬 {post.get('replies_count', 0)}"
    ]
    embed.set_footer(text=" • ".join(engagement))

    # Twitter-style Footer
    embed.add_field(
        name="\u200b",
        value=f"🐦 Tweet Tracker | 📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        inline=False
    )

    await channel.send(embed=embed)
    
    # Send additional images as separate messages
    if post.get("media_attachments") and len(post["media_attachments"]) > 1:
        for media in post["media_attachments"][1:]:
            if media["type"] == "image":
                await channel.send(
                    f"Additional image from @{username}: {media['url']}"
                )

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

### 🛑 Error Handling ###
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("⚠️ Missing required argument")
    else:
        logging.error(f"Command Error: {str(error)}")

### 🏁 Entry Point ###
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        logging.critical("Missing Discord bot token")
        exit(1)

    try:
        logging.info("Starting Truth Social Tracker...")
        bot.run(TOKEN)
    except Exception as e:
        logging.critical(f"Failed to start bot: {str(e)}")
