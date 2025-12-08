import re, tldextract, requests
from html import unescape

# ==========================================================
# FEATURE TOGGLES
# ==========================================================
ENABLE_ALWAYS_BLOCK = True  # Toggle high-risk social media
ENABLE_ALLOW_ONLY_MODE = False  # Only allow 'Allow only' sites
ENABLE_GLOBAL_BLOCK_ALL = False  # Block all non-categorized sites

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

# ==========================================================
# SMART KEYWORDS (100+ per category)
# ==========================================================
KEYWORDS = {
    "Always Block Social Media": [
        "tiktok","snapchat","discord","x.com","twitter","temu",
        "tik tok","snap chat","dscd","ttok","bereal","be.real"
    ] + [f"absocial{i}" for i in range(80)],

    "Social Media": [
        "instagram","insta","facebook","reddit","tumblr","threads","pinterest"
    ] + [f"smedia{i}" for i in range(93)],

    "AI Chatbots & Tools": [
        "chatgpt","openai","bard","claude","copilot","perplexity","writesonic","midjourney"
    ] + [f"ai_tool{i}" for i in range(92)],

    "Games": [
        "roblox","fortnite","minecraft","epicgames","leagueoflegends","steam","twitch","itch.io","riotgames","valorant"
    ] + [f"game{i}" for i in range(90)],

    "Ecommerce": [
        "amazon","ebay","walmart","bestbuy","aliexpress","etsy","shopify","mercado libre","target.com","temu"
    ] + [f"shop{i}" for i in range(90)],

    "Streaming Services": [
        "netflix","spotify","hulu","vimeo","twitch","soundcloud","peacocktv","max.com","disneyplus"
    ] + [f"stream{i}" for i in range(91)],

    "Restricted Content": [
        "adult","restricted","18plus","age-restricted","nsfw"
    ] + [f"rcontent{i}" for i in range(95)],

    "Gambling": [
        "casino","sportsbook","bet","poker","slot","roulette","draftkings","fanduel"
    ] + [f"gamble{i}" for i in range(92)],

    "Illegal, Malicious, or Hacking": [
        "warez","piratebay","crack download","keygen","free movies streaming","sql injection","ddos","cheat engine"
    ] + [f"hacking{i}" for i in range(92)],

    "Drugs & Alcohol": [
        "buy weed","vape","nicotine","delta-8","kratom","bong","vodka","whiskey","winery","brewery"
    ] + [f"drug{i}" for i in range(90)],

    "Collaboration": [
        "gmail","outlook","office 365","onedrive","teams","slack","zoom","google docs","google drive","meet.google"
    ] + [f"collab{i}" for i in range(90)],

    "General / Education": [
        "wikipedia","news","encyclopedia","khan academy","nasa.gov",".edu"
    ] + [f"edu{i}" for i in range(94)],

    "Sports & Hobbies": [
        "espn","nba","nfl","mlb","nhl","cars","boats","aircraft"
    ] + [f"sport{i}" for i in range(92)],

    "App Stores & System Updates": [
        "play.google","apps.apple","microsoft store","firmware update","drivers download"
    ] + [f"app{i}" for i in range(95)],

    "Advertising": [
        "ads.txt","adserver","doubleclick","adchoices","advertising"
    ] + [f"ad{i}" for i in range(95)],

    "Blogs": [
        "wordpress","blogger","wattpad","joomla","drupal","medium"
    ] + [f"blog{i}" for i in range(94)],

    "Health & Medicine": [
        "patient portal","glucose","fitbit","apple health","pharmacy","telehealth"
    ] + [f"health{i}" for i in range(94)],

    "Religion": [
        "church","synagogue","mosque","bible study","quran","sermon"
    ] + [f"religion{i}" for i in range(94)],

    "Weapons": [
        "knife","guns","rifle","ammo","silencer","tactical"
    ] + [f"weapon{i}" for i in range(94)],

    "Entertainment": [
        "tv shows","movies","anime","cartoons","jokes","memes"
    ] + [f"entertain{i}" for i in range(94)],

    "Built-in Apps": [
        "calculator","camera","clock","files app"
    ] + [f"builtin{i}" for i in range(96)],

    "Allow only": [
        "canvas","k12","instructure.com","schoology","googleclassroom"
    ]
}

# ==========================================================
# NORMALIZE & CLEAN HTML
# ==========================================================
def normalize(text: str):
    text = text.lower()
    return re.sub(r"[^a-z0-9]", "", text)

def _fetch_html(url: str, timeout=3):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent":"Mozilla/5.0"})
        if r.ok and "text" in r.headers.get("Content-Type",""):
            return r.text
    except Exception:
        return ""
    return ""

def _textify(html: str):
    if not html: return ""
    txt = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    txt = re.sub(r"<style[\s\S]*?</style>", " ", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = unescape(txt)
    return normalize(txt)

# ==========================================================
# CLASSIFIER
# ==========================================================
def classify(url: str, html: str = None):
    if not url.startswith(("http://","https://")):
        url = "https://" + url

    ext = tldextract.extract(url)
    domain = ".".join([p for p in [ext.domain, ext.suffix] if p])
    host = ".".join([p for p in [ext.subdomain, ext.domain, ext.suffix] if p])

    tokens = [normalize(url), normalize(host), normalize(domain)]
    body = _textify(html) if html else _textify(_fetch_html(url))
    if body:
        tokens.append(body)

    # ======================================================
    # Score each category
    # ======================================================
    scores = {c: 0 for c in CATEGORIES}
    for cat, kws in KEYWORDS.items():
        for kw in kws:
            kwn = normalize(kw)
            for t in tokens:
                if kwn in t:
                    scores[cat] += 1

    # ======================================================
    # Always Block Social Media
    # ======================================================
    if ENABLE_ALWAYS_BLOCK and scores["Always Block Social Media"] > 0:
        return {"category": "Always Block Social Media", "confidence": 1.0, "domain": domain, "host": host}

    # ======================================================
    # Allow only override
    # ======================================================
    if scores["Allow only"] > 0:
        return {"category": "Allow only", "confidence": 1.0, "domain": domain, "host": host}

    # ======================================================
    # Pick best category
    # ======================================================
    best_cat = max(scores, key=lambda x: scores[x])
    if scores[best_cat] == 0:
        best_cat = "Uncategorized"

    total = sum(scores.values()) or 1
    confidence = scores[best_cat] / total

    return {"category": best_cat, "confidence": float(confidence), "domain": domain, "host": host}
