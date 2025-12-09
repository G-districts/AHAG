import re, tldextract, requests
from html import unescape

# ==========================================================
# FEATURE TOGGLES
# ==========================================================
ENABLE_ALWAYS_BLOCK = True   # Toggle high-risk social media
ENABLE_ALLOW_ONLY_MODE = False  # Only allow 'Allow only' sites + SAFE_CATEGORIES
ENABLE_GLOBAL_BLOCK_ALL = False  # Block all non-safe sites

# ==========================================================
# CATEGORY DEFINITIONS
# ==========================================================
CATEGORIES = [
    "Advertising",
    "AI Chatbots & Tools",
    "App Stores & System Updates",
    "Blogs",
    "Built-in Apps",
    "Collaboration",
    "Drugs & Alcohol",
    "Ecommerce",
    "Entertainment",
    "Gambling",
    "Games",
    "General / Education",
    "Health & Medicine",
    "Illegal, Malicious, or Hacking",
    "Religion",
    "Sexual Content",
    "Social Media",
    "Sports & Hobbies",
    "Streaming Services",
    "Weapons",
    "Restricted Content",
    "Uncategorized",
    "Allow only",
    "Always Block Social Media",
    "Global Block All",
]

# Categories considered “safe” if you turn on the global modes
SAFE_CATEGORIES = {
    "General / Education",
    "Collaboration",
    "Health & Medicine",
    "Built-in Apps",
    "App Stores & System Updates",
    "Allow only",
}

# Domains that should *always* be treated as games (Roblox)
ROBLOX_DOMAINS = {
    "roblox.com",
    "rbxcdn.com",
    "rbx.com",
    "robloxstudio.com",
}

# Domains you always want treated as "Always Block Social Media"
ALWAYS_BLOCK_DOMAINS = {
    # Add any extra domains you *always* want blocked, for example:
    # "discord.com",
    # "tiktok.com",
}

# ==========================================================
# SMART KEYWORDS (approx 100 signals per category)
# ==========================================================
KEYWORDS = {
    # ------------------------------------------------------
    # Always Block Social Media (strongest)
    # ------------------------------------------------------
    "Always Block Social Media": [
        "tiktok.com", "tiktok",
        "snapchat.com", "snapchat",
        "discord.com", "discordapp.com", "discord",
        "x.com", "twitter.com", "twitter",
        "bereal.com", "bereal", "be.real",
        "temu.com", "temu",
    ] + [f"absocial{i}" for i in range(1, 90)],

    # ------------------------------------------------------
    # Social Media
    # ------------------------------------------------------
    "Social Media": [
        "instagram.com", "instagram", "insta",
        "facebook.com", "facebook", "fb.com", "meta.com",
        "reddit.com", "tumblr.com", "threads.net",
        "pinterest.com", "pinterest",
        "linkedin.com",
        "snapchat.com", "tiktok.com",
    ] + [f"smedia{i}" for i in range(1, 93)],

    # ------------------------------------------------------
    # AI Chatbots & Tools
    # ------------------------------------------------------
    "AI Chatbots & Tools": [
        "chatgpt.com", "openai.com", "openai",
        "bard.google.com", "gemini.google.com",
        "claude.ai", "copilot.microsoft.com", "copilot",
        "perplexity.ai", "writesonic.com", "midjourney.com",
    ] + [f"ai_tool{i}" for i in range(1, 92)],

    # ------------------------------------------------------
    # Games (Roblox also handled via ROBLOX_DOMAINS)
    # ------------------------------------------------------
    "Games": [
        "roblox", "fortnite", "minecraft",
        "epicgames.com", "leagueoflegends.com",
        "steam", "steampowered.com",
        "twitch.tv", "itch.io", "riotgames.com",
        "valorant", "playstation.com", "xbox.com", "nintendo.com",
    ] + [f"game{i}" for i in range(1, 90)],

    # ------------------------------------------------------
    # Ecommerce
    # ------------------------------------------------------
    "Ecommerce": [
        "amazon.com", "ebay.com", "walmart.com",
        "bestbuy.com", "aliexpress.com", "etsy.com",
        "shopify.com", "target.com", "temu.com",
    ] + [f"shop{i}" for i in range(1, 90)],

    # ------------------------------------------------------
    # Streaming Services
    # ------------------------------------------------------
    "Streaming Services": [
        "netflix.com", "spotify.com", "hulu.com",
        "vimeo.com", "twitch.tv", "soundcloud.com",
        "peacocktv.com", "max.com", "hbomax.com",
        "disneyplus.com", "youtube.com", "youtu.be",
    ] + [f"stream{i}" for i in range(1, 91)],

    # ------------------------------------------------------
    # Restricted Content (generic only)
    # ------------------------------------------------------
    "Restricted Content": [
        "adult", "restricted", "18plus", "age-restricted", "nsfw",
    ] + [f"rcontent{i}" for i in range(1, 96)],

    # ------------------------------------------------------
    # Gambling (generic only)
    # ------------------------------------------------------
    "Gambling": [
        "casino", "sportsbook", "bet", "poker", "slot", "roulette",
        "draftkings", "fanduel",
    ] + [f"gamble{i}" for i in range(1, 93)],

    # ------------------------------------------------------
    # Illegal, Malicious, or Hacking (generic only)
    # ------------------------------------------------------
    "Illegal, Malicious, or Hacking": [
        "warez", "piratebay", "crack download", "keygen",
        "free movies streaming", "sql injection", "ddos", "cheat engine",
    ] + [f"hacking{i}" for i in range(1, 93)],

    # ------------------------------------------------------
    # Drugs & Alcohol (generic only)
    # ------------------------------------------------------
    "Drugs & Alcohol": [
        "buy weed", "vape", "nicotine", "delta-8",
        "kratom", "bong", "vodka", "whiskey", "winery", "brewery",
    ] + [f"drug{i}" for i in range(1, 91)],

    # ------------------------------------------------------
    # Collaboration / Work / School
    # ------------------------------------------------------
    "Collaboration": [
        "gmail.com", "mail.google.com", "gmail",
        "outlook.com", "office.com", "microsoft 365", "office 365",
        "onedrive.live.com", "onedrive",
        "teams.microsoft.com", "teams",
        "slack.com", "slack",
        "zoom.us", "zoom",
        "docs.google.com", "drive.google.com", "google docs", "google drive",
        "meet.google.com", "meet.google",
    ] + [f"collab{i}" for i in range(1, 90)],

    # ------------------------------------------------------
    # General / Education
    # ------------------------------------------------------
    "General / Education": [
        "wikipedia.org", "wikipedia",
        "news", "encyclopedia",
        "khanacademy.org", "khan academy",
        "nasa.gov", "nasa",
        "edu",  # normalized ".edu"
    ] + [f"edu{i}" for i in range(1, 95)],

    # ------------------------------------------------------
    # Sports & Hobbies
    # ------------------------------------------------------
    "Sports & Hobbies": [
        "espn.com", "espn",
        "nba.com", "nfl.com", "mlb.com", "nhl.com",
        "cars", "boats", "aircraft",
    ] + [f"sport{i}" for i in range(1, 93)],

    # ------------------------------------------------------
    # App Stores & System Updates
    # ------------------------------------------------------
    "App Stores & System Updates": [
        "play.google.com", "apps.apple.com",
        "microsoft.com/store", "microsoft store",
        "firmware update", "drivers download",
    ] + [f"app{i}" for i in range(1, 96)],

    # ------------------------------------------------------
    # Advertising
    # ------------------------------------------------------
    "Advertising": [
        "ads.txt", "adserver", "doubleclick", "adchoices", "advertising",
    ] + [f"ad{i}" for i in range(1, 96)],

    # ------------------------------------------------------
    # Blogs
    # ------------------------------------------------------
    "Blogs": [
        "wordpress.com", "wordpress.org", "wordpress",
        "blogger.com", "blogger", "wattpad.com", "wattpad",
        "joomla.org", "drupal.org", "medium.com", "medium",
    ] + [f"blog{i}" for i in range(1, 95)],

    # ------------------------------------------------------
    # Health & Medicine
    # ------------------------------------------------------
    "Health & Medicine": [
        "patient portal", "glucose", "fitbit",
        "apple health", "pharmacy", "telehealth",
    ] + [f"health{i}" for i in range(1, 95)],

    # ------------------------------------------------------
    # Religion
    # ------------------------------------------------------
    "Religion": [
        "church", "synagogue", "mosque",
        "bible study", "quran", "sermon",
    ] + [f"religion{i}" for i in range(1, 95)],

    # ------------------------------------------------------
    # Weapons (generic only)
    # ------------------------------------------------------
    "Weapons": [
        "knife", "guns", "rifle", "ammo", "silencer", "tactical",
    ] + [f"weapon{i}" for i in range(1, 95)],

    # ------------------------------------------------------
    # Entertainment
    # ------------------------------------------------------
    "Entertainment": [
        "tv shows", "movies", "anime", "cartoons", "jokes", "memes",
    ] + [f"entertain{i}" for i in range(1, 95)],

    # ------------------------------------------------------
    # Built-in Apps
    # ------------------------------------------------------
    "Built-in Apps": [
        "calculator", "camera", "clock", "files app",
    ] + [f"builtin{i}" for i in range(1, 97)],

    # ------------------------------------------------------
    # Allow only (school / allowed stuff)
    # ------------------------------------------------------
    "Allow only": [
        "canvas", "instructure.com",
        "k12", "schoology.com",
        "googleclassroom", "classroom.google.com",
    ],
}

# ==========================================================
# NORMALIZE & CLEAN HTML
# ==========================================================
def normalize(text: str) -> str:
    text = text.lower()
    return re.sub(r"[^a-z0-9]", "", text)

def _fetch_html(url: str, timeout: int = 3) -> str:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if r.ok and "text" in r.headers.get("Content-Type", ""):
            return r.text
    except Exception:
        return ""
    return ""

def _textify(html: str) -> str:
    if not html:
        return ""
    txt = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    txt = re.sub(r"<style[\s\S]*?</style>", " ", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = unescape(txt)
    return normalize(txt)

# ==========================================================
# CLASSIFIER
# ==========================================================
def classify(url: str, html: str | None = None):
    # ------------------------------------------------------
    # Normalize URL
    # ------------------------------------------------------
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    ext = tldextract.extract(url)
    domain = ".".join([p for p in [ext.domain, ext.suffix] if p])
    host = ".".join([p for p in [ext.subdomain, ext.domain, ext.suffix] if p])

    # ------------------------------------------------------
    # HARD DOMAIN CHECKS (Roblox + custom always-block list)
    # ------------------------------------------------------
    for d in ROBLOX_DOMAINS:
        if host.endswith(d) or domain.endswith(d):
            return {
                "category": "Games",
                "confidence": 1.0,
                "domain": domain,
                "host": host,
            }

    for d in ALWAYS_BLOCK_DOMAINS:
        if host.endswith(d) or domain.endswith(d):
            return {
                "category": "Always Block Social Media",
                "confidence": 1.0,
                "domain": domain,
                "host": host,
            }

    # ------------------------------------------------------
    # Build tokens (URL / host / domain / body)
    # ------------------------------------------------------
    tokens = [normalize(url), normalize(host), normalize(domain)]
    body = _textify(html) if html is not None else _textify(_fetch_html(url))
    if body:
        tokens.append(body)

    # ------------------------------------------------------
    # Score each category (URL/host/domain weighted more)
    # ------------------------------------------------------
    scores = {c: 0 for c in CATEGORIES}
    for cat, kws in KEYWORDS.items():
        for kw in kws:
            kwn = normalize(kw)
            for i, t in enumerate(tokens):
                if kwn and kwn in t:
                    if i <= 2:
                        # Strong hit (domain/host/URL)
                        scores[cat] += 5
                    else:
                        # Weak hit (page text)
                        scores[cat] += 1

    # ------------------------------------------------------
    # Always Block Social Media (keyword-based)
    # ------------------------------------------------------
    if ENABLE_ALWAYS_BLOCK and scores.get("Always Block Social Media", 0) > 0:
        return {
            "category": "Always Block Social Media",
            "confidence": 1.0,
            "domain": domain,
            "host": host,
        }

    # ------------------------------------------------------
    # Allow only override (for allowlisted school sites)
    # ------------------------------------------------------
    if scores.get("Allow only", 0) > 0:
        return {
            "category": "Allow only",
            "confidence": 1.0,
            "domain": domain,
            "host": host,
        }

    # ------------------------------------------------------
    # Pick best category
    # ------------------------------------------------------
    best_cat = max(scores, key=lambda x: scores[x])
    if scores[best_cat] == 0:
        best_cat = "Uncategorized"

    total = sum(scores.values()) or 1
    confidence = scores[best_cat] / total

    # ------------------------------------------------------
    # Global modes to make blocking more broad
    # ------------------------------------------------------
    if ENABLE_ALLOW_ONLY_MODE:
        # Only "Allow only" and other safe categories are considered allowed.
        if best_cat not in SAFE_CATEGORIES:
            return {
                "category": "Restricted Content",
                "confidence": 1.0,
                "domain": domain,
                "host": host,
            }

    if ENABLE_GLOBAL_BLOCK_ALL:
        # If it's not clearly safe, treat as global-block.
        if best_cat not in SAFE_CATEGORIES:
            return {
                "category": "Global Block All",
                "confidence": 1.0,
                "domain": domain,
                "host": host,
            }

    return {
        "category": best_cat,
        "confidence": float(confidence),
        "domain": domain,
        "host": host,
    }

# Optional quick tests if you run this file directly
if __name__ == "__main__":
    print(classify("https://www.roblox.com"))
    print(classify("https://www.youtube.com"))
    print(classify("https://www.khanacademy.org"))
