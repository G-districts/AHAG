import re, tldextract, requests
from html import unescape

# ==========================================================
# FEATURE TOGGLES
# ==========================================================
ENABLE_ALWAYS_BLOCK = True # Toggle high-risk social media
ENABLE_ALLOW_ONLY_MODE = False # Only allow 'Allow only' sites (used outside classify)
ENABLE_GLOBAL_BLOCK_ALL = False # Block all non-categorized sites (used outside classify)

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
# SPECIAL DOMAIN OVERRIDES
# ==========================================================
ROBLOX_DOMAINS = {
"roblox.com",
"rbxcdn.com",
"rbx.com",
"robloxstudio.com",
}

ALWAYS_BLOCK_DOMAINS = {
# add more if you want
# "discord.com",
# "tiktok.com",
}

# Hints for "this is probably education"
EDU_HINTS = {"edu", "school", "k12", "classroom", "campus"}

# ==========================================================
# HIGHLY SPECIFIC KEYWORDS PER CATEGORY (brands & strong terms)
# ==========================================================
KEYWORDS = {
# ------------------------------------------------------
# Strong always-block social media
# ------------------------------------------------------
"Always Block Social Media": [
"tiktok.com", "tiktok",
"snapchat.com", "snapchat",
"discord.com", "discordapp.com", "discord",
"x.com", "twitter.com", "twitter",
"bereal.com", "bereal", "be.real",
],

# ------------------------------------------------------
# Social Media
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
# AI Chatbots & Tools
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
# Games
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
# Ecommerce
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
"adidas.com", "temu"
],

# ------------------------------------------------------
# Streaming Services
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
# Restricted Content (minimal but strong)
# ------------------------------------------------------
"Restricted Content": [
"nsfw",
"age-restricted",
"18plus",
],

# ------------------------------------------------------
# Gambling (limited but strong)
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
# Illegal, Malicious, or Hacking
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
# Drugs & Alcohol
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
# Collaboration
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
# General / Education
# ------------------------------------------------------
"General / Education": [
"wikipedia.org", "wikipedia",
"khanacademy.org", "khanacademy",
"nasa.gov",
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
# Sports & Hobbies
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
# App Stores & System Updates
# ------------------------------------------------------
"App Stores & System Updates": [
"play.google.com",
"apps.apple.com",
"microsoft.com/store",
"store.steampowered.com",
"epicgames.com/store",
],

# ------------------------------------------------------
# Advertising
# ------------------------------------------------------
"Advertising": [
"ads.txt",
"adserver",
"doubleclick",
"adchoices",
"googletagmanager.com",
],

# ------------------------------------------------------
# Blogs
# ------------------------------------------------------
"Blogs": [
"wordpress.com", "wordpress.org", "wordpress",
"blogger.com", "blogger",
"medium.com", "medium",
"wattpad.com", "wattpad",
"substack.com", "substack",
],

# ------------------------------------------------------
# Health & Medicine
# ------------------------------------------------------
"Health & Medicine": [
"mychart",
"patientportal",
"telehealth",
"webmd.com",
"mayoclinic.org",
],

# ------------------------------------------------------
# Religion
# ------------------------------------------------------
"Religion": [
"biblegateway.com",
"quran.com",
"biblehub.com",
],

# ------------------------------------------------------
# Weapons
# ------------------------------------------------------
"Weapons": [
"ammunition",
"gunshop",
"tacticalgear",
],

# ------------------------------------------------------
# Entertainment
# ------------------------------------------------------
"Entertainment": [
"imdb.com", "imdb",
"rottentomatoes.com",
"fandom.com", "fandom",
],

# ------------------------------------------------------
# Built-in Apps
# ------------------------------------------------------
"Built-in Apps": [
"calculator",
"camera",
"clock",
"filesapp",
"notesapp",
],

# ------------------------------------------------------
# Sexual Content
# ------------------------------------------------------
"Sexual Content": [
"porn",
"pornhub",
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

# Ensure every category has at least an empty list
for cat in CATEGORIES:
if cat not in KEYWORDS:
KEYWORDS[cat] = []

# ==========================================================
# HTML HELPERS
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

def _extract_title(html: str) -> str:
if not html:
return ""
m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
if not m:
return ""
title = m.group(1)
return unescape(title)

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
# Normalize URL
if not url.startswith(("http://", "https://")):
url = "https://" + url

ext = tldextract.extract(url)
domain = ".".join([p for p in [ext.domain, ext.suffix] if p])
host = ".".join([p for p in [ext.subdomain, ext.domain, ext.suffix] if p])

# ------------------------------------------------------
# HARD DOMAIN OVERRIDES
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

# Fetch HTML if not provided
if html is None:
html = _fetch_html(url)

# Extract title and normalize all parts
raw_title = _extract_title(html)
url_norm = normalize(url)
host_norm = normalize(host)
domain_norm = normalize(domain)
title_norm = normalize(raw_title)
body_norm = _textify(html)

# tokens dict so we can weight them differently
tokens = {
"domain": domain_norm,
"host": host_norm,
"url": url_norm,
"title": title_norm,
"body": body_norm,
}

# ======================================================
# Score each category with weighted signals
# ======================================================
scores = {c: 0 for c in CATEGORIES}

# weights: domain > host > url > title > body
WEIGHTS = {
"domain": 10,
"host": 8,
"url": 6,
"title": 5,
"body": 1,
}

for cat, kws in KEYWORDS.items():
for kw in kws:
kwn = normalize(kw)
if not kwn:
continue
for part_name, text in tokens.items():
if not text:
continue
if kwn in text:
scores[cat] += WEIGHTS.get(part_name, 1)

# ------------------------------------------------------
# Soft "this looks like education" hint if nothing else
# ------------------------------------------------------
# If nothing strong matched, but domain looks like .edu etc.,
# bump General / Education a bit to avoid mis-blocking schools.
if ext.suffix == "edu" or any(hint in host_norm for hint in EDU_HINTS):
scores["General / Education"] += 5

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

# Extra safety: if best_cat is something sketchy but
# its score is tiny, you can treat as Uncategorized in
# your calling code if you want.
return {
"category": best_cat,
"confidence": float(confidence),
"domain": domain,
"host": host,
"raw_scores": scores, # helpful for debugging/logging
}
