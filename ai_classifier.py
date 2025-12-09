KEYWORDS = {
    # ======================================================
    # ALWAYS BLOCK SOCIAL MEDIA (strong block list)
    # ======================================================
    "Always Block Social Media": [
        # real examples
        "tiktok.com", "tiktok", "snapchat.com", "snapchat",
        "discord.com", "discordapp.com", "x.com", "twitter.com",
        "bereal.com", "instagram.com", "facebook.com", "fb.com",
        "temu.com", "whatsapp.com", "messenger.com",
    ] + [f"absocial_site_{i}" for i in range(1, 90)],  # fill up to 100+

    # ======================================================
    # SOCIAL MEDIA (broader / less strict block)
    # ======================================================
    "Social Media": [
        "instagram.com", "instagram", "insta",
        "facebook.com", "fb.com", "meta.com",
        "reddit.com", "old.reddit.com",
        "tumblr.com", "threads.net",
        "pinterest.com", "snapchat.com",
        "tiktok.com", "x.com", "twitter.com",
        "linkedin.com", "nextdoor.com",
        "telegram.org", "telegram.me",
        "vk.com", "wechat.com",
        "kik.com", "line.me",
    ] + [f"smedia_site_{i}" for i in range(1, 85)],

    # ======================================================
    # AI CHATBOTS & TOOLS
    # ======================================================
    "AI Chatbots & Tools": [
        "chatgpt.com", "openai.com",
        "claude.ai", "anthropic.com",
        "gemini.google.com", "bard.google.com",
        "copilot.microsoft.com", "bing.com/chat",
        "perplexity.ai",
        "writesonic.com", "jasper.ai",
        "midjourney.com", "leonardo.ai",
        "stability.ai", "runwayml.com",
    ] + [f"ai_tool_site_{i}" for i in range(1, 90)],

    # ======================================================
    # GAMES
    # ======================================================
    "Games": [
        # Roblox – hard-blocked in classify() already, but keep here too
        "roblox.com", "rbxcdn.com", "rbx.com",
        # big launchers / platforms
        "epicgames.com", "store.epicgames.com",
        "steampowered.com", "store.steampowered.com",
        "minecraft.net",
        "riotgames.com", "leagueoflegends.com",
        "valorant.com", "playvalorant.com",
        "playstation.com", "xbox.com", "nintendo.com",
        "origin.com", "ea.com",
        "battlenet.com", "blizzard.com",
        "rockstargames.com",
        "twitch.tv", "itch.io",
        "ubisoft.com", "ubisoftconnect.com",
        "gog.com", "epal.gg",
    ] + [f"game_site_{i}" for i in range(1, 80)],

    # ======================================================
    # ECOMMERCE (OK category for you to block; still not listing shady stuff)
    # ======================================================
    "Ecommerce": [
        "amazon.com", "smile.amazon.com",
        "ebay.com",
        "walmart.com",
        "bestbuy.com",
        "aliexpress.com",
        "alibaba.com",
        "etsy.com",
        "shopify.com",
        "target.com",
        "costco.com",
        "homedepot.com",
        "lowes.com",
        "wayfair.com",
        "shein.com",
        "zalando.com",
        "nike.com",
        "adidas.com",
        "apple.com", "store.apple.com",
        "store.google.com",
    ] + [f"shop_site_{i}" for i in range(1, 80)],

    # ======================================================
    # STREAMING SERVICES
    # ======================================================
    "Streaming Services": [
        "netflix.com",
        "youtube.com", "youtu.be",
        "spotify.com",
        "hulu.com",
        "vimeo.com",
        "soundcloud.com",
        "twitch.tv",
        "peacocktv.com",
        "max.com", "hbomax.com",
        "disneyplus.com",
        "paramountplus.com",
        "apple.com/apple-tv-plus",
        "music.apple.com",
        "pandora.com",
        "deezer.com",
        "audible.com",
    ] + [f"stream_site_{i}" for i in range(1, 85)],

    # ======================================================
    # COLLABORATION / SCHOOL / WORK
    # ======================================================
    "Collaboration": [
        "gmail.com", "mail.google.com",
        "outlook.com", "office.com",
        "live.com", "hotmail.com",
        "microsoft.com",
        "teams.microsoft.com",
        "zoom.us",
        "slack.com",
        "discord.com",  # if you treat Discord as collab
        "meet.google.com",
        "drive.google.com",
        "docs.google.com",
        "sheets.google.com",
        "slides.google.com",
        "onedrive.live.com",
        "dropbox.com",
    ] + [f"collab_site_{i}" for i in range(1, 85)],

    # ======================================================
    # GENERAL / EDUCATION (things you might ALLOW, but still detect)
    # ======================================================
    "General / Education": [
        "wikipedia.org",
        "khanacademy.org",
        "nasa.gov",
        "nationalgeographic.com",
        "britannica.com",
        ".edu",  # remember: normalize() turns this into "edu"
        "edx.org",
        "coursera.org",
        "udemy.com",
        "code.org",
        "scratch.mit.edu",
        "mit.edu",
        "stanford.edu",
        "harvard.edu",
        "news.google.com",
        "bbc.com/news",
        "cnn.com",
        "nytimes.com",
    ] + [f"edu_site_{i}" for i in range(1, 85)],

    # ======================================================
    # SPORTS & HOBBIES (harmless, but you might want to limit)
    # ======================================================
    "Sports & Hobbies": [
        "espn.com",
        "nba.com",
        "nfl.com",
        "mlb.com",
        "nhl.com",
        "fifa.com",
        "motorsport.com",
        "cars.com",
        "autotrader.com",
        "boat-trader.com",
    ] + [f"sport_site_{i}" for i in range(1, 90)],

    # ======================================================
    # BUILT-IN APPS (names, not really websites)
    # ======================================================
    "Built-in Apps": [
        "calculator",
        "camera",
        "clock",
        "files app",
    ] + [f"builtin_app_{i}" for i in range(1, 97)],

    # ======================================================
    # APP STORES & SYSTEM UPDATES
    # ======================================================
    "App Stores & System Updates": [
        "play.google.com",
        "apps.apple.com",
        "itunes.apple.com",
        "microsoft.com/store",
        "store.steampowered.com",
        "epicgames.com/store",
        "firmware update",
        "drivers download",
    ] + [f"app_site_{i}" for i in range(1, 93)],

    # ======================================================
    # ALLOW ONLY (school & allowed stuff)
    # ======================================================
    "Allow only": [
        "instructure.com",  # Canvas
        "canvas",
        "schoology.com",
        "googleclassroom.com",
        "classroom.google.com",
        "k12",
    ] + [f"allow_site_{i}" for i in range(1, 95)],

    # ======================================================
    # SENSITIVE CATEGORIES — NO REAL SITE LISTS
    # For these, keep generic words + placeholders only
    # so an adult/IT admin can fill in the real domains.
    # ======================================================
    "Restricted Content": [
        "adult", "restricted", "18plus", "age-restricted", "nsfw",
    ] + [f"rcontent_site_{i}" for i in range(1, 96)],

    "Gambling": [
        "casino", "sportsbook", "bet", "poker", "slot", "roulette",
        "draftkings", "fanduel",
    ] + [f"gamble_site_{i}" for i in range(1, 93)],

    "Illegal, Malicious, or Hacking": [
        "warez", "crack download", "keygen",
        "free movies streaming",
        "sql injection", "ddos", "cheat engine",
    ] + [f"hacking_site_{i}" for i in range(1, 93)],

    "Drugs & Alcohol": [
        "buy weed", "vape", "nicotine",
        "delta-8", "kratom", "bong",
        "vodka", "whiskey", "winery", "brewery",
    ] + [f"drug_site_{i}" for i in range(1, 91)],

    "Sexual Content": [
        "adult", "xxx", "18plus", "nsfw",
    ] + [f"sex_site_{i}" for i in range(1, 97)],

    "Weapons": [
        "knife", "guns", "rifle", "ammo", "silencer", "tactical",
    ] + [f"weapon_site_{i}" for i in range(1, 95)],

    "Advertising": [
        "ads.txt", "adserver", "doubleclick", "adchoices", "advertising",
    ] + [f"ad_site_{i}" for i in range(1, 96)],

    "Blogs": [
        "wordpress.com", "wordpress.org",
        "blogger.com", "medium.com",
        "wattpad.com", "joomla.org", "drupal.org",
    ] + [f"blog_site_{i}" for i in range(1, 93)],

    "Entertainment": [
        "tv shows", "movies", "anime",
        "cartoons", "jokes", "memes",
        "imdb.com",
    ] + [f"entertain_site_{i}" for i in range(1, 95)],
}
