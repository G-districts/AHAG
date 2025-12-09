import re, tldextract, requests
from html import unescape

# ==========================================================
# FEATURE TOGGLES
# ==========================================================
ENABLE_ALWAYS_BLOCK = True          # Toggle high-risk social media
ENABLE_ALLOW_ONLY_MODE = False      # Only allow 'Allow only' sites (used outside classify)
ENABLE_GLOBAL_BLOCK_ALL = False     # Block all non-categorized sites (used outside classify)

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

# Domains that should *always* be treated as Games (Roblox)
ROBLOX_DOMAINS = {
    "roblox.com",
    "rbxcdn.com",
    "rbx.com",
    "robloxstudio.com",
}

# Optional: domains you always want treated as "Always Block Social Media"
ALWAYS_BLOCK_DOMAINS = {
    # "discord.com",
    # "tiktok.com",
}

# ==========================================================
# HIGHLY SPECIFIC KEYWORDS PER CATEGORY
# (mostly brands / domains, very few generic words)
# ==========================================================
KEYWORDS = {
    # ------------------------------------------------------
    # Strong always-block social media (small + specific)
    # ------------------------------------------------------
    "Always Block Social Media": [
        "tiktok.com", "tiktok",
        "snapchat.com", "snapchat",
        "discord.com", "discordapp.com", "discord",
        "x.com", "twitter.com", "twitter",
        "bereal.com", "bereal", "be.real",
        "temu.com", "temu",
    ],

    # ------------------------------------------------------
    # Social Media (brand-based)
    # ------------------------------------------------------
    "Social Media": [
        "instagram.com", "instagram", "insta",
        "facebook.com", "facebook", "fb.com",
        "meta.com",
        "reddit.com", "reddit",
        "tumblr.com", "tumblr",
        "threads.net", "threads",
        "pinterest.com", "pinterest",
        "linkedin.com", "linkedin",
        "snapchat.com", "snapchat",
        "tiktok.com", "tiktok",
        "telegram.org", "telegram",
        "vk.com", "vk",
    ],

    # ------------------------------------------------------
    # AI Chatbots & Tools (brand-based)
    # ------------------------------------------------------
    "AI Chatbots & Tools": [
        "chatgpt.com", "chatgpt",
        "openai.com", "openai",
        "gemini.google.com", "bard.google.com", "gemini", "bard",
        "claude.ai", "claude",
        "copilot.microsoft.com", "copilot",
        "perplexity.ai", "perplexity",
        "writesonic.com", "writesonic",
        "midjourney.com", "midjourney",
        "jasper.ai", "jasper",
    ],

    # ------------------------------------------------------
    # Games (brand/platform-based)
    # ------------------------------------------------------
    "Games": [
        "roblox.com", "roblox",
        "minecraft.net", "minecraft",
        "epicgames.com", "fortnite",
        "leagueoflegends.com", "leagueoflegends",
        "playvalorant.com", "valorant",
        "steampowered.com", "store.steampowered.com", "steam",
        "riotgames.com", "riotgames",
        "playstation.com", "playstation",
        "xbox.com", "xbox",
        "nintendo.com", "nintendo",
        "battlenet.com",
        "ea.com",
        "gog.com",
        "itch.io",
        "ubisoft.com", "ubisoft",
        "rockstargames.com", "rockstargames",
    ],

    # ------------------------------------------------------
    # Ecommerce (brand-based)
    # ------------------------------------------------------
    "Ecommerce": [
        "amazon.com", "amazon",
        "ebay.com", "ebay",
        "walmart.com", "walmart",
        "bestbuy.com", "bestbuy",
        "aliexpress.com", "aliexpress",
        "etsy.com", "etsy",
        "shopify.com", "shopify",
        "target.com", "target",
        "costco.com", "costco",
        "shein.com", "shein",
        "wayfair.com", "wayfair",
        "apple.com", "store.apple.com",
        "store.google.com",
        "nike.com",
        "adidas.com",
    ],

    # ------------------------------------------------------
    # Streaming Services (brand-based)
    # ------------------------------------------------------
    "Streaming Services": [
        "netflix.com", "netflix",
        "spotify.com", "spotify",
        "hulu.com", "hulu",
        "vimeo.com", "vimeo",
        "twitch.tv", "twitch",
        "soundcloud.com", "soundcloud",
        "peacocktv.com", "peacock",
        "max.com", "hbomax.com",
        "disneyplus.com", "disneyplus",
        "youtube.com", "youtu.be", "youtube",
        "music.apple.com",
        "paramountplus.com",
        "deezer.com",
        "pandora.com",
        "audible.com",
    ],

    # ------------------------------------------------------
    # Restricted Content (strong but limited generic words)
    # ------------------------------------------------------
    "Restricted Content": [
        "nsfw",
        "age-restricted",
        "18plus",
    ],

    # ------------------------------------------------------
    # Gambling (strong but limited words)
    # ------------------------------------------------------
    "Gambling": [
        "casino",
        "sportsbook",
        "poker",
        "roulette",
        "jackpot",
        "blackjack",
        "slotmachine",
        "slots",
    ],

    # ------------------------------------------------------
    # Illegal, Malicious, or Hacking (technical terms)
    # ------------------------------------------------------
    "Illegal, Malicious, or Hacking": [
        "warez",
        "keygen",
        "crackdownload",
        "crackedsoftware",
        "sqlinjection",
        "ddos",
        "cheatengine",
        "botnet",
        "rattool",
    ],

    # ------------------------------------------------------
    # Drugs & Alcohol (limited strong terms)
    # ------------------------------------------------------
    "Drugs & Alcohol": [
        "marijuana",
        "cannabis",
        "vape",
        "vaping",
        "nicotine",
        "bong",
        "vodka",
        "whiskey",
        "tequila",
    ],

    # ------------------------------------------------------
    # Collaboration (brand-based)
    # ------------------------------------------------------
    "Collaboration": [
        "gmail.com", "gmail", "mail.google.com",
        "outlook.com", "outlook",
        "office.com", "microsoft365", "office365",
        "onedrive.live.com", "onedrive",
        "teams.microsoft.com", "teams",
        "slack.com", "slack",
        "zoom.us", "zoom",
        "docs.google.com",
        "drive.google.com",
        "meet.google.com",
        "dropbox.com", "dropbox",
        "notion.so", "notion",
    ],

    # ------------------------------------------------------
    # General / Education (specific edu sites)
    # ------------------------------------------------------
    "General / Education": [
        "wikipedia.org", "wikipedia",
        "khanacademy.org", "khanacademy",
        "nasa.gov",
        "edu",  # from .edu after normalize
        "edx.org", "edx",
        "coursera.org", "coursera",
        "udemy.com", "udemy",
        "scratch.mit.edu", "scratch",
        "code.org",
        "mit.edu",
        "stanford.edu",
        "harvard.edu",
    ],

    # ------------------------------------------------------
    # Sports & Hobbies (brand-based)
    # ------------------------------------------------------
    "Sports & Hobbies": [
        "espn.com", "espn",
        "nba.com", "nba",
        "nfl.com", "nfl",
        "mlb.com", "mlb",
        "nhl.com", "nhl",
        "fifa.com", "fifa",
    ],

    # ------------------------------------------------------
    # App Stores & System Updates (brand-based)
    # ------------------------------------------------------
    "App Stores & System Updates": [
        "play.google.com",
        "apps.apple.com",
        "microsoft.com/store",
        "store.steampowered.com",
        "epicgames.com/store",
    ],

    # ------------------------------------------------------
    # Advertising (specific ad tech)
    # ------------------------------------------------------
    "Advertising": [
        "ads.txt",
        "adserver",
        "doubleclick",
        "adchoices",
        "googletagmanager.com",
    ],

    # ------------------------------------------------------
    # Blogs (platforms only)
    # ------------------------------------------------------
    "Blogs": [
        "wordpress.com", "wordpress.org", "wordpress",
        "blogger.com", "blogger",
        "medium.com", "medium",
        "wattpad.com", "wattpad",
        "substack.com", "substack",
    ],

    # ------------------------------------------------------
    # Health & Medicine (limited & specific)
    # ------------------------------------------------------
    "Health & Medicine": [
        "mychart",
        "patientportal",
        "telehealth",
        "webmd.com",
        "mayoclinic.org",
    ],

    # ------------------------------------------------------
    # Religion (specific)
    # ------------------------------------------------------
    "Religion": [
        "biblegateway.com",
        "quran.com",
        "biblehub.com",
    ],

    # ------------------------------------------------------
    # Weapons (few strong terms)
    # ------------------------------------------------------
    "Weapons": [
        "ammunition",
        "gunshop",
        "tacticalgear",
    ],

    # ------------------------------------------------------
    # Entertainment (brand-based)
    # ------------------------------------------------------
    "Entertainment": [
        "imdb.com", "imdb",
        "rottentomatoes.com",
        "fandom.com", "fandom",
    ],

    # ------------------------------------------------------
    # Built-in Apps (names)
    # ------------------------------------------------------
    "Built-in Apps": [
        "calculator",
        "camera",
        "clock",
        "filesapp",
        "notesapp",
    ],

    # ------------------------------------------------------
    # Sexual Content (short + strong)
    # ------------------------------------------------------
    "Sexual Content": [
        "porn",
        "pornhub",  # still a strong indicator if seen
        "xxx",
        "onlyfans",
        "nsfw",
    ],

    # ------------------------------------------------------
    # Allow only (school / allowed)
    # ------------------------------------------------------
    "Allow only": [
        "canvas",
        "instructure.com",
        "k12",
        "schoology",
        "schoology.com",
        "googleclassroom",
        "classroom.google.com",
    ],
}

# Make sure every category in CATEGORIES has an entry in KEYWORDS
for cat in CATEGORIES:
    if cat not in KEYWORDS:
        KEYWORDS[cat] = []

# ==========================================================
# NORMALIZE & CLEAN HTML
# ==========================================================
def normalize(text: str):
    text = text.lower()
    return re.sub(r"[^a-z0-9]", "", text)

def _fetch_html(url: str, timeout=3):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if r.ok and "text" in r.headers.get("Content-Type", ""):
            return r.text
    except Exception:
        return ""
    return ""

def _textify(html: str):
    if not html:
        return ""
    txt = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.I)
    txt = re.sub(r"<style[\\s\\S]*?</style>", " ", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = unescape(txt)
    return normalize(txt)

# ==========================================================
# CLASSIFIER
# ==========================================================
def classify(url: str, html: str = None):
    # Normalize URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    ext = tldextract.extract(url)
    domain = ".".join([p for p in [ext.domain, ext.suffix] if p])
    host = ".".join([p for p in [ext.subdomain, ext.domain, ext.suffix] if p])

    # ------------------------------------------------------
    # HARD DOMAIN OVERRIDES (ROBLOX + optional always-block)
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

    # Build tokens (URL / host / domain / body)
    url_norm = normalize(url)
    host_norm = normalize(host)
    domain_norm = normalize(domain)
    tokens = [url_norm, host_norm, domain_norm]
    body_norm = _textify(html) if html else _textify(_fetch_html(url))
    if body_norm:
        tokens.append(body_norm)

    # ======================================================
    # Score each category (specific keywords only)
    # ======================================================
    scores = {c: 0 for c in CATEGORIES}

    for cat, kws in KEYWORDS.items():
        for kw in kws:
            kwn = normalize(kw)
            if not kwn:
                continue
            for i, t in enumerate(tokens):
                if kwn in t:
                    # URL / host / domain are strong;
                    # body is weaker, but still counts.
                    if i <= 2:
                        scores[cat] += 5
                    else:
                        scores[cat] += 1

    # ======================================================
    # Always Block Social Media
    # ======================================================
    if ENABLE_ALWAYS_BLOCK and scores.get("Always Block Social Media", 0) > 0:
        return {
            "category": "Always Block Social Media",
            "confidence": 1.0,
            "domain": domain,
            "host": host,
        }

    # ======================================================
    # Allow only override
    # ======================================================
    if scores.get("Allow only", 0) > 0:
        return {
            "category": "Allow only",
            "confidence": 1.0,
            "domain": domain,
            "host": host,
        }

    # ======================================================
    # Pick best category
    # ======================================================
    best_cat = max(scores, key=lambda x: scores[x])
    if scores[best_cat] == 0:
        best_cat = "Uncategorized"

    total = sum(scores.values()) or 1
    confidence = scores[best_cat] / total

    return {
        "category": best_cat,
        "confidence": float(confidence),
        "domain": domain,
        "host": host,
    }

# Quick tests if you run this file directly
if __name__ == "__main__":
    print("Minecraft:", classify("https://www.minecraft.net/en-us"))
    print("Roblox:", classify("https://www.roblox.com"))
    print("YouTube:", classify("https://www.youtube.com"))
    print("Khan Academy:", classify("https://www.khanacademy.org"))
    print("Random news site:", classify("https://www.bbc.com/news"))
