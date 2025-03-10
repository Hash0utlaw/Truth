# Truth Social Bot Setup Guide

## 1. Required Accounts
- Discord Developer Portal: [Create Bot](https://discord.com/developers/applications)
- Truth Social Account: For API access

## 2. Configuration
1. Create `.env` file with:
```env
DISCORD_BOT_TOKEN=your_token_here
TRUTHSOCIAL_USERNAME=your@email.com
TRUTHSOCIAL_PASSWORD=your_password
DISCORD_CHANNEL_ID=1234567890
```

2. In Replit:
- Click 🔒 **Secrets**
- Add all .env variables as secrets

## 3. First Run
1. Click "Run" in Replit
2. Wait for dependencies to install
3. Check console for "Logged in as [Bot Name]"

## 4. Commands
```bash
!track [username]  # Start tracking
!untrack [username] # Stop tracking
!list              # Show tracked users
!stats             # Bot statistics
!search [user] [query] # Search posts
```

## 5. Maintenance
- Logs: `bot.log`
- Database: `tracked_users.db` (auto-created)
- Keep alive: Use UptimeRobot for 24/7 operation
