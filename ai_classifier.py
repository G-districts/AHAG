
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
    ]

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
    "vk.com", "vk",    "x.com", "twitter.com", "twitter", "x",
    "discord.com", "discord",
    "whatsapp.com", "whatsapp",
    "wechat.com", "wechat",
    "qq.com", "qq",
    "line.me", "line",
    "wechat.com", "wechat",
    "weibo.com", "weibo",
    "medium.com", "medium",
    "mastodon.social", "mastodon",
    "bluesky.social", "bluesky",
    "gab.com", "gab",
    "truthsocial.com", "truth social",
    "parler.com", "parler",
    "gettr.com", "gettr",
    "flickr.com", "flickr",
    "vimeo.com", "vimeo",
    "dailymotion.com", "dailymotion",
    "quora.com", "quora",
    "nextdoor.com", "nextdoor",
    "bereal.com", "bereal",
    "mewe.com", "mewe",
    "wechat.com", "wechat",
    "fark.com", "fark",
    "imgur.com", "imgur",
    "deviantart.com", "deviantart",
    "dribbble.com", "dribbble",
    "behance.net", "behance",
    "ravelry.com", "ravelry",
    "soundcloud.com", "soundcloud",
    "bandcamp.com", "bandcamp",
    "mix.com", "mix",
    "vk.ru", "vkontakte",
    "odnoklassniki.ru", "odnoklassniki", "ok.ru",
    "goodreads.com", "goodreads",
    "cafe24.com", "cafe24",
    "wattpad.com", "wattpad",
    "fanfiction.net", "fanfiction",
    "archiveofourown.org", "ao3",
    "gaiaonline.com", "gaiaonline",
    "minoapp.com", "mino",
    "plurk.com", "plurk",
    "ello.co", "ello",
    "flipboard.com", "flipboard",
    "peach.cool", "peach",
    "vsco.co", "vsco",
    "taringa.net", "taringa",
    "kakao.com", "kakao",
    "vero.co", "vero",
    "untappd.com", "untappd",
    "ameblo.jp", "ameblo",
    "livejournal.com", "livejournal"
]


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
    "huggingface.co", "huggingface",
    "stability.ai", "stable diffusion", 
    "anthropic.com", "anthropic",
    "runwayml.com", "runway",
    "leonardo.ai", "leonardo",
    "pika.art", "pika",
    "recraft.ai", "recraft",
    "suno.ai", "suno",
    "elevenlabs.io", "elevenlabs",
    "deepai.org", "deepai",
    "you.com", "youchat",
    "gpt4all.io", "gpt4all",
    "mistral.ai", "mistral",
    "tabnine.com", "tabnine",
    "deepmind.google", "deepmind",
    "cognosys.ai", "cognosys",
    "character.ai", "characterai",
    "blackbox.ai", "blackbox",
    "krisp.ai", "krisp",
    "otter.ai", "otter",
    "scribehow.com", "scribe",
    "descript.com", "descript",
    "quillbot.com", "quillbot",
    "grammarly.com", "grammarly",
    "replika.com", "replika",
    "writesonic.com", "writesonic",
    "notion.so", "notion ai",
    "tome.app", "tome",
    "beautiful.ai", "beautifulai",
    "heygen.com", "heygen",
    "d-id.com", "did",
    "synthesia.io", "synthesia",
    "openrouter.ai", "openrouter",
    "grok.com", "grok",
    "pi.ai", "pi",
    "cohere.com", "cohere",
    "ai21.com", "ai21",
    "luma.ai", "luma",
    "play.ht", "playht",
    "podcastle.ai", "podcastle",
    "movmi.ai", "movmi",
    "flash.info", "flash ai",
    "codium.ai", "codium",
    "phind.com", "phind",
    "together.ai", "together",
    "uncopilot.com", "uncopilot",
    "toonator.ai", "toonator",
    "genmo.ai", "genmo",
    "wondercraft.ai", "wondercraft"
]


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
    "battlenet.com", "blizzard",
    "ea.com", "electronicarts",
    "gog.com", "gog",
    "itch.io", "itch",
    "ubisoft.com", "ubisoft",
    "rockstargames.com", "rockstargames",

    "activision.com", "activision",
    "bethesda.net", "bethesda",
    "cdprojekt.com", "cdprojekt",
    "bandainamcoent.com", "bandai",
    "sega.com", "sega",
    "capcom.com", "capcom",
    "square-enix.com", "squareenix",
    "konami.com", "konami",
    "valvesoftware.com", "valve",
    "supercell.com", "supercell",
    "riot.com", "riot",
    "garena.com", "garena",
    "riotgames.com/league-of-legends", "lol",
    "blizzard.com/overwatch", "overwatch",
    "bungie.net", "bungie",
    "diablo.com", "diablo",
    "worldofwarcraft.com", "wow",
    "starcraft.com", "starcraft",
    "hearthstone.com", "hearthstone",
    "heroesofthestorm.com", "hots",
    "dota2.com", "dota2",
    "csgo.com", "counter-strike",
    "tf2.com", "teamfortress2",
    "paladins.com", "paladins",
    "smashbros.com", "smash",
    "animalcrossing.com", "animalcrossing",
    "splatoon.com", "splatoon",
    "mariokart.com", "mariokart",
    "zelda.com", "zelda",
    "pokemongo.com", "pokemongo",
    "pokemon.com", "pokemon",
    "fireemblem.com", "fireemblem",
    "xcom.com", "xcom",
    "ageofempires.com", "ageofempires",
    "civilization.com", "civilization",
    "totalwar.com", "totalwar",
    "forzahorizon.com", "forzahorizon",
    "gran-turismo.com", "granturismo",
    "fifa.com", "fifa",
    "pes-pes.com", "pes",
    "apexlegends.com", "apex",
    "pubg.com", "pubg",
    "csgo.com", "csgo",
    "valorant.com", "valorant",
    "overwatchleague.com", "overwatchleague",
    "rocketleague.com", "rocketleague",
    "fortnite.com", "fortnite",
    "roblox.com/games", "robloxgames",
]

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


    "homedepot.com", "homedepot",
    "lowes.com", "lowes",
    "kohls.com", "kohls",
    "macys.com", "macys",
    "jcpenney.com", "jcpenney",
    "sears.com", "sears",
    "newegg.com", "newegg",
    "overstock.com", "overstock",
    "qvc.com", "qvc",
    "hsn.com", "hsn",
    "samsclub.com", "samsclub",
    "aldi.us", "aldi",
    "harborfreight.com", "harborfreight",
    "costplusworldmarket.com", "worldmarket",
    "bedbathandbeyond.com", "bedbathandbeyond",
    "crateandbarrel.com", "crateandbarrel",
    "ikea.com", "ikea",
    "zara.com", "zara",
    "hm.com", "hm",
    "uniqlo.com", "uniqlo",
    "primark.com", "primark",
    "urbanoutfitters.com", "urbanoutfitters",
    "victoriassecret.com", "victoriassecret",
    "sephora.com", "sephora",
    "ulta.com", "ulta",
    "glossier.com", "glossier",
    "lush.com", "lush",
    "drmartens.com", "drmartens",
    "converse.com", "converse",
    "puma.com", "puma",
    "underarmour.com", "underarmour",
    "lululemon.com", "lululemon",
    "rei.com", "rei",
    "dickssportinggoods.com", "dickssportinggoods",
    "gamestop.com", "gamestop",
    "microcenter.com", "microcenter",
    "bhphotovideo.com", "bhphotovideo",
    "adorama.com", "adorama",
    "barnesandnoble.com", "barnesandnoble",
    "chewy.com", "chewy",
    "petsmart.com", "petsmart",
    "petco.com", "petco",
    "walgreens.com", "walgreens",
    "cvs.com", "cvs",
    "riteaid.com", "riteaid",
    "instacart.com", "instacart",
    "doordash.com", "doordash store",
    "ubereats.com", "ubereats store",
    "grubhub.com", "grubhub",
    "alibaba.com", "alibaba"
]


    # ------------------------------------------------------
    # Streaming Services (brand-based)
    # ------------------------------------------------------
"Streaming Services": [
    "netflix.com", "netflix",
    "hulu.com", "hulu",
    "vimeo.com", "vimeo",
    "twitch.tv", "twitch",
    "soundcloud.com", "soundcloud",
    "peacocktv.com", "peacock",
    "max.com", "hbomax.com",
    "disneyplus.com", "disneyplus",
    "paramountplus.com",
    "deezer.com",
    "pandora.com",
    "audible.com",
    "amazon.com/video", "primevideo.com", "primevideo",
    "crunchyroll.com", "crunchyroll",
    "funimation.com", "funimation",
    "starz.com", "starz",
    "showtime.com", "showtime",
    "discoveryplus.com", "discoveryplus",
    "britbox.com", "britbox",
    "acorn.tv", "acorn",
    "plex.tv", "plex",
    "pluto.tv", "pluto",
    "tubi.tv", "tubi",
    "sling.com", "sling",
    "fubo.tv", "fubo",
    "roku.com", "theroku channel",
    "curiositystream.com", "curiositystream",
    "crackle.com", "crackle",
    "kanopy.com", "kanopy",
    "shudder.com", "shudder",
    "mubi.com", "mubi",
    "cineplex.com", "cineplex",
    "filmocracy.com", "filmocracy",
    "pocketcasts.com", "pocketcasts",
    "iheartradio.com", "iheartradio",
    "tidal.com", "tidal",
    "napster.com", "napster",
    "gaana.com", "gaana",
    "jiosaavn.com", "jiosaavn",
    "anghami.com", "anghami",
    "wynk.in", "wynk",
    "boomplay.com", "boomplay",
    "vevo.com", "vevo",
    "dailymotion.com", "dailymotion",
    "ustvgo.tv", "ustvgo",
    "hayu.com", "hayu",
    "sundance.tv", "sundance",
    "rifftrax.com", "rifftrax",
    "vrv.co", "vrv",
    "retrocrush.tv", "retrocrush",
    "bet.com/live-tv", "betplus",
    "nbc.com/live", "nbc",
    "cbs.com/live", "cbs",
    "abc.com/watch", "abc",
    "fox.com/live", "fox",
    "mlb.tv", "mlbtv",
    "nba.com/watch", "nbatv",
    "nhl.com/tv", "nhltv",
    "ufc.tv", "ufc",
    "wwe.com/network", "wwenetwork"
]


    # ------------------------------------------------------
    # Restricted Content (strong but limited generic words)
    # ------------------------------------------------------
"Restricted Content": [
    "nsfw",
    "age-restricted",
    "18plus",
    "adult",
    "porn",
    "xxx",
    "erotic",
    "sex",
    "nudity",
    "nude",
    "hardcore",
    "fetish",
    "bdsm",
    "gayporn",
    "lesbianporn",
    "hentai",
    "animehentai",
    "cartoonporn",
    "camgirl",
    "camsite",
    "webcamsex",
    "escort",
    "prostitute",
    "sexwork",
    "adultvideo",
    "adultsite",
    "pornhub.com", "pornhub",
    "xvideos.com", "xvideos",
    "xhamster.com", "xhamster",
    "redtube.com", "redtube",
    "youporn.com", "youporn",
    "tube8.com", "tube8",
    "spankwire.com", "spankwire",
    "xnxx.com", "xnxx",
    "eroprofile.com", "eroprofile",
    "playboy.com", "playboy",
    "hustler.com", "hustler",
    "onlyfans.com", "onlyfans",
    "adultfriendfinder.com", "aff",
    "cam4.com", "cam4",
    "chaturbate.com", "chaturbate",
    "stripchat.com", "stripchat",
    "livejasmin.com", "livejasmin",
    "bangbros.com", "bangbros",
    "digitalplayground.com", "digitalplayground",
    "evilangel.com", "evilangel",
    "brazzers.com", "brazzers",
    "xart.com", "xart",
    "sex.com", "sex",
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
    "bingo",
    "lottery",
    "scratchcard",
    "scratchoff",
    "keno",
    "craps",
    "texasholdem",
    "videopoker",
    "betting",
    "wagering",
    "gamblingonline",
    "onlinecasino",
    "casinogames",
    "jackpotcity",
    "bet365.com", "bet365",
    "draftkings.com", "draftkings",
    "fanduel.com", "fanduel",
    "paddypower.com", "paddypower",
    "williamhill.com", "williamhill",
    "betfair.com", "betfair",
    "unibet.com", "unibet",
    "888casino.com", "888casino",
    "partycasino.com", "partycasino",
    "betway.com", "betway",
    "goldenpalace.com", "goldenpalace",
    "casinocom.com", "casino.com",
    "slots.lv", "slotslv",
    "ignitioncasino.eu", "ignitioncasino",
    "mansioncasino.com", "mansioncasino",
    "luckynuggetcasino.com", "luckynugget",
    "spinpalace.com", "spinpalace",
    "vegas.com", "vegas",
    "gamblingsites.com", "gamblingsites",
    "casinomeister.com", "casinomeister",
    "pokersites.com", "pokersites",
    "sportsbet.com", "sportsbet",
    "bovada.lv", "bovada",
    "betsson.com", "betsson",
    "betfred.com", "betfred",
    "coral.co.uk", "coral",
    "skybet.com", "skybet",
    "betvictor.com", "betvictor",
    "ladbrokes.com", "ladbrokes",
    "casino.org", "casinoorg",
    "pokerstars.com", "pokerstars",
    "partypoker.com", "partypoker",
    "888poker.com", "888poker",
]


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
    "phishing",
    "ransomware",
    "malware",
    "spyware",
    "trojan",
    "virus",
    "rootkit",
    "exploit",
    "backdoor",
    "zero-day",
    "adware",
    "scam",
    "fraud",
    "pirated",
    "torrentpirate",
    "wareztorrent",
    "crackz",
    "serialkey",
    "activator",
    "patcher",
    "hacktool",
    "injector",
    "bot",
    "scriptkiddie",
    "darkweb",
    "onionlink",
    "deepweb",
    "carding",
    "stolenaccount",
    "accountstealer",
    "keylogger",
    "phishingsite",
    "exploitkit",
    "maliciousdownload",
    "illegalsoftware",
    "hackforum",
    "hacktheplanet",
    "gamehacking",
    "cheathub",
    "ddostool",
    "proxybypass",
    "vpnbypass",
    "maliciousscript",
    "xssattack",
    "csrfattack",
    "bruteforce",
    "passwordstealer",
    "cryptojacking",
    "skid",
    "cracker",
    "darkmarket",
]


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
    "cocaine",
    "methamphetamine",
    "meth",
    "heroin",
    "lsd",
    "acid",
    "mushrooms",
    "psilocybin",
    "ecstasy",
    "mdma",
    "pcp",
    "ketamine",
    "cannabidiol",
    "cbg",
    "thc",
    "hemp",
    "rollingpapers",
    "blunt",
    "joint",
    "hookah",
    "shisha",
    "wine",
    "beer",
    "lager",
    "ale",
    "gin",
    "rum",
    "brandy",
    "cognac",
    "tequila blanco",
    "tequila reposado",
    "liqueur",
    "absinthe",
    "moonshine",
    "schnapps",
    "cocktail",
    "martini",
    "margarita",
    "whisky",
    "bourbon",
    "scotch",
    "rumchata",
    "edibles",
    "dab",
    "vaporizer",
    "penvape",
    "hookahpen",
    "dabrig",
    "hash",
    "wax",
    "oil",
    "shatter",
    "kush",
]


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

    "asana.com", "asana",
    "trello.com", "trello",
    "clickup.com", "clickup",
    "monday.com", "monday",
    "airtable.com", "airtable",
    "confluence.atlassian.com", "confluence",
    "atlassian.com", "atlassian",
    "jira.com", "jira",
    "figma.com", "figma",
    "miro.com", "miro",
    "lucidchart.com", "lucidchart",
    "loom.com", "loom",
    "discord.com", "discord",
    "skype.com", "skype",
    "webex.com", "webex",
    "gotomeeting.com", "gotomeeting",
    "bluejeans.com", "bluejeans",
    "googlesites.com", "googlesites",
    "quora.com/work", "quoraforbusiness",
    "evernote.com", "evernote",
    "onenote.com", "onenote",
    "zoho.com", "zoho",
    "zoho.com/mail", "zohomail",
    "box.com", "box",
    "wetransfer.com", "wetransfer",
    "protonmail.com", "protonmail",
    "icloud.com", "icloud",
    "basecamp.com", "basecamp",
    "smartsheet.com", "smartsheet",
    "wrike.com", "wrike",
    "bitrix24.com", "bitrix24",
    "teamviewer.com", "teamviewer",
    "anydesk.com", "anydesk",
    "notability.com", "notability",
    "goodnotes.com", "goodnotes",
    "overleaf.com", "overleaf",
    "bitbucket.org", "bitbucket",
    "replit.com", "replit",
    "zoomgov.com", "zoomgov",
    "meet.jit.si", "jitsi",
    "whereby.com", "whereby",
    "todoist.com", "todoist",
    "workflowy.com", "workflowy",
    "papercut.com", "papercut",
    "whiteboard.microsoft.com", "mswhiteboard",
    "figjam.com", "figjam",
    "kahoot.com", "kahoot",
    "mentimeter.com", "mentimeter"
]


    # ------------------------------------------------------
    # General / Education (specific edu sites)
    # ------------------------------------------------------
"General / Education": [
    "wikipedia.org", "wikipedia",
    "khanacademy.org", "khanacademy",
    "nasa.gov",
    "edu",
    "edx.org", "edx",
    "coursera.org", "coursera",
    "udemy.com", "udemy",
    "scratch.mit.edu", "scratch",
    "code.org",
    "mit.edu",
    "stanford.edu",
    "harvard.edu",
    "ocw.mit.edu", "mitocw",
    "saylor.org", "saylor",
    "futurelearn.com", "futurelearn",
    "alison.com", "alison",
    "openlearning.com", "openlearning",
    "academicearth.org", "academicearth",
    "academic.oup.com", "oxford academic",
    "plato.stanford.edu", "stanford encyclopedia",
    "britannica.com", "britannica",
    "howstuffworks.com", "howstuffworks",
    "thoughtco.com", "thoughtco",
    "science.org", "science",
    "nature.com", "nature",
    "sciencedirect.com", "sciencedirect",
    "researchgate.net", "researchgate",
    "jstor.org", "jstor",
    "projectgutenberg.org", "gutenberg",
    "archive.org", "archive",
    "libguides.com", "libguides",
    "ted.com", "ted",
    "teded.com", "teded",
    "nationalgeographic.com", "natgeo",
    "smithsonianmag.com", "smithsonian",
    "edutopia.org", "edutopia",
    "pbs.org", "pbs",
    "bbc.co.uk/education", "bbc education",
    "k12.com", "k12",
    "openstax.org", "openstax",
    "preply.com", "preply",
    "italki.com", "italki",
    "quizlet.com", "quizlet",
    "chegg.com", "chegg",
    "brilliant.org", "brilliant",
    "mathsisfun.com", "mathsisfun",
    "wolframalpha.com", "wolframalpha",
    "desmos.com", "desmos",
    "geogebra.org", "geogebra",
    "codeacademy.com", "codecademy",
    "freecodecamp.org", "freecodecamp",
    "lewagon.com", "lewagon",
    "hackerrank.com", "hackerrank",
    "topcoder.com", "topcoder",
    "edureka.co", "edureka",
    "coursera.org/specializations", "coursera specializations",
    "unacademy.com", "unacademy",
    "byjus.com", "byjus",
    "study.com", "study",
    "khanacademy.org/science", "khanacademy science",
    "mit.edu/research", "mit research",
    "harvard.edu/academics", "harvard academics",
]


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
    "uefa.com", "uefa",
    "premierleague.com", "premierleague",
    "ligue1.com", "ligue1",
    "bundesliga.com", "bundesliga",
    "seriea.com", "seriea",
    "nascar.com", "nascar",
    "f1.com", "formula1",
    "olympics.com", "olympics",
    "golfdigest.com", "golfdigest",
    "pgatour.com", "pgatour",
    "tennis.com", "tennis",
    "atptour.com", "atptour",
    "wta.com", "wta",
    "cyclingnews.com", "cyclingnews",
    "redbull.com/sports", "redbull sports",
    "skysports.com", "skysports",
    "cbssports.com", "cbssports",
    "foxsports.com", "foxsports",
    "bleacherreport.com", "bleacherreport",
    "sportsillustrated.com", "si",
    "rotoworld.com", "rotoworld",
    "fantasypros.com", "fantasypros",
    "fanatics.com", "fanatics",
    "mls.com", "mls",
    "ncaasports.com", "ncaa",
    "espncricinfo.com", "cricinfo",
    "icc-cricket.com", "icc",
    "ufc.com", "ufc",
    "wwe.com", "wwe",
    "pga.com", "pga",
    "toursoftheworld.com", "toursoftheworld",
    "marvel.com/hobbies", "marvel hobbies",
    "lego.com", "lego",
    "boardgamegeek.com", "boardgamegeek",
    "chess.com", "chess",
    "lichess.org", "lichess",
    "pokemontcg.com", "pokemontcg",
    "pokemon.com", "pokemon",
    "f1fantasy.com", "f1fantasy",
    "cricbuzz.com", "cricbuzz",
    "rugbyworldcup.com", "rugbyworldcup",
    "athletic.net", "athleticnet",
    "speedwaygp.com", "speedwaygp",
    "badmintonworld.tv", "badmintonworld",
    "usaarchery.org", "usaarchery",
    "surfline.com", "surfline",
    "skateparkoftampa.com", "skateparkoftampa",
    "ultimatefrisbee.com", "ultimatefrisbee"
]


    # ------------------------------------------------------
    # App Stores & System Updates (brand-based)
    # ------------------------------------------------------
    "App Stores & System Updates": [
        "play.google.com",
        "apps.apple.com",
        "microsoft.com/store",
        "store.steampowered.com",
        "epicgames.com/store",
    ]

    # ------------------------------------------------------
    # Advertising (specific ad tech)
    # ------------------------------------------------------
"Advertising": [
    "ads.txt",
    "adserver",
    "doubleclick",
    "adchoices",
    "googletagmanager.com", "gtm",
    "googleads.g.doubleclick.net", "googleads",
    "adroll.com", "adroll",
    "criteo.com", "criteo",
    "taboola.com", "taboola",
    "outbrain.com", "outbrain",
    "media.net", "medianet",
    "revcontent.com", "revcontent",
    "pubmatic.com", "pubmatic",
    "openx.com", "openx",
    "rubiconproject.com", "rubicon",
    "indexexchange.com", "indexexchange",
    "appnexus.com", "appnexus",
    "sovrn.com", "sovrn",
    "brightcom.com", "brightcom",
    "infolinks.com", "infolinks",
    "adform.com", "adform",
    "gumgum.com", "gumgum",
    "spotx.tv", "spotx",
    "triplelift.com", "triplelift",
    "sharethrough.com", "sharethrough",
    "teads.tv", "teads",
    "adcolony.com", "adcolony",
    "chartboost.com", "chartboost",
    "vungle.com", "vungle",
    "ironSource.com", "ironsource",
    "unityads.unity3d.com", "unityads",
    "mobvista.com", "mobvista",
    "mintegral.com", "mintegral",
    "smaato.com", "smaato",
    "pubg.com/ads", "pubgads",
    "facebook.com/ads", "facebookads",
    "instagram.com/ads", "instagramads",
    "twitter.com/ads", "twitterads",
    "snapchat.com/ads", "snapads",
    "tiktok.com/business", "tiktokads",
    "linkedin.com/ads", "linkedinads",
    "bing.com/ads", "bingads",
    "yahoo.com/ads", "yahooads",
    "taboola.com", "taboola",
    "outbrain.com", "outbrain",
    "adverity.com", "adverity",
    "adthrive.com", "adthrive",
    "mediavine.com", "mediavine",
    "monetizeMore.com", "monetizemore",
    "propellerads.com", "propellerads",
    "adcash.com", "adcash",
    "revcontent.com", "revcontent",
    "epom.com", "epom",
]


    # ------------------------------------------------------
    # Blogs (platforms only)
    # ------------------------------------------------------
"Blogs": [
    "wordpress.com", "wordpress.org", "wordpress",
    "blogger.com", "blogger",
    "medium.com", "medium",
    "wattpad.com", "wattpad",
    "substack.com", "substack",
    "tumblr.com", "tumblr",
    "ghost.org", "ghost",
    "typepad.com", "typepad",
    "weebly.com", "weebly",
    "jimdo.com", "jimdo",
    "livejournal.com", "livejournal",
    "penzu.com", "penzu",
    "vox.com", "vox",
    "hubpages.com", "hubpages",
    "bighugelabs.com", "bighugelabs",
    "edublogs.org", "edublogs",
    "postach.io", "postachio",
    "blot.im", "blot",
    "write.as", "writeas",
    "bearblog.dev", "bearblog",
    "svbtle.com", "svbtle",
    "telegra.ph", "telegraph",
    "gawker.com", "gawker",
    "techcrunch.com", "techcrunch",
    "huffpost.com", "huffpost",
    "buzzfeed.com", "buzzfeed blogs",
    "quora.com", "quora",
    "dev.to", "devto",
    "medium.freecodecamp.org", "freecodecamp",
    "stackabuse.com", "stackabuse",
    "codeburst.io", "codeburst",
    "towardsdatascience.com", "towardsdatascience",
    "habr.com", "habr",
    "sitepoint.com", "sitepoint",
    "smashingmagazine.com", "smashingmagazine",
    "css-tricks.com", "csstricks",
    "problogger.com", "problogger",
    "copyblogger.com", "copyblogger",
    "nichepursuits.com", "nichepursuits",
    "bloglovin.com", "bloglovin",
    "bloglines.com", "bloglines",
    "alltop.com", "alltop",
    "blogengage.com", "blogengage",
    "blogarama.com", "blogarama",
    "technorati.com", "technorati",
    "blogcatalog.com", "blogcatalog",
    "medium.datadriveninvestor.com", "datadriveninvestor",
    "overblog.com", "overblog",
    "liveinternet.ru", "liveinternet",
    "typepad.com", "typepad",
    "journals.sagepub.com", "sage journals",
    "researchgate.net", "researchgate",
]


    # ------------------------------------------------------
    # Health & Medicine (limited & specific)
    # ------------------------------------------------------
"Health & Medicine": [
    # General medical info
    "webmd.com", "webmd",
    "mayoclinic.org", "mayo clinic", "mayo",

    # Portals (generic terms + real domains)
    "mychart", "mychart.com",
    "patientportal", "patient portal",
    "healow", "healow.com",
    "followmyhealth", "follow my health",
    "athenahealth", "athena", "athenahealth.com",

    # Telehealth platforms
    "telehealth", "tele-health",
    "teladoc", "teladoc.com",
    "amwell", "amwell.com",
    "zocdoc", "zocdoc.com",

    # Pharmacy / health brands
    "cvs.com", "cvs health", "cvs",
    "walgreens.com", "walgreens",
    "riteaid.com", "rite aid",
    "goodrx.com", "goodrx",

    # Fitness/health monitoring
    "myfitnesspal.com", "myfitnesspal",
    "fitbit.com", "fitbit",
    "whoop", "whoop.com",
    "garmin health", "garmin.com",
]


    # ------------------------------------------------------
    # Religion (specific)
    # ------------------------------------------------------
"Religion": [
    "biblegateway.com",
    "quran.com",
    "biblehub.com",

    "bible.com", "youversion",
    "blueletterbible.org",
    "christianity.com",
    "catholic.com",
    "vatican.va",
    "lutheranworld.org",
    "anglicancommunion.org",
    "orthodoxwiki.org",
    "desiringgod.org",
    "focusonthefamily.com",
    "crosswalk.com",
    "gotquestions.org",

    
    "chabad.org",
    "myjewishlearning.com",
    "aish.com",
    "sefaria.org",
    "jewishvirtuallibrary.org",

    "islamqa.info",
    "islamicity.org",
    "islamicfinder.org",
    "muslimpro.com",
    "sunnah.com",

    "buddhanet.net",
    "dharmanet.org",
    "thubtenchodron.org",
    "plumvillage.org",
    "dalailama.com",

    "hindupedia.com",
    "isha.sadhguru.org",
    "bharatpedia.org",
    "vedabase.io",
    "chinmayamission.com",

    "sikhnet.com",
    "sgpc.net",
    "sikhs.org",
    "damdamitaksal.org",

    "bahai.org",
    "neopagan.net",
    "wicca.com",
    "scientology.org",
    "unification.org",

    "religionnews.com",
    "religionfacts.com",
    "patheos.com",
    "beliefnet.com",
    "studylight.org",
    "scriptures.lds.org",
    "churchofjesuschrist.org",  
    "watchtower.org",          
    "jw.org",                  
    "al-islam.org",
    "biblia.com",
    "logos.com",
    "accordancebible.com"
]


    # ------------------------------------------------------
    # Weapons (few strong terms)
    # ------------------------------------------------------
    "Weapons": [
        "ammunition",
        "gunshop",
        "tacticalgear",
    ]

    # ------------------------------------------------------
    # Entertainment (brand-based)
    # ------------------------------------------------------
"Entertainment": [
    "imdb.com", "imdb",
    "rottentomatoes.com",
    "fandom.com", "fandom",

    "metacritic.com", "metacritic",
    "letterboxd.com", "letterboxd",
    "tvguide.com", "tvguide",
    "thetvdb.com", "tvdb",
    "allmovie.com", "allmovie",
    "allmusic.com", "allmusic",
    "gamespot.com", "gamespot",
    "ign.com", "ign",
    "comicbook.com", "comicbook",
    "screenrant.com", "screenrant",
    "variety.com", "variety",
    "hollywoodreporter.com", "hollywoodreporter",
    "deadline.com", "deadline",
    "people.com", "people",
    "ew.com", "entertainmentweekly",
    "rollingstone.com", "rollingstone",
    "pitchfork.com", "pitchfork",
    "billboard.com", "billboard",
    "tmz.com", "tmz",
    "buzzfeed.com", "buzzfeed",
    "vulture.com", "vulture",
    "theverge.com", "theverge entertainment",
    "polygon.com", "polygon",
    "cbr.com", "comicbookresources",
    "kotaku.com", "kotaku",
    "gizmodo.com", "gizmodo entertainment",
    "euronews.com/culture", "euronews culture",
    "nme.com", "nme",
    "faroutmagazine.co.uk", "faroutmagazine",
    "empireonline.com", "empire magazine",
    "gamesradar.com", "gamesradar",
    "bloody-disgusting.com", "bloodydisgusting",
    "denofgeek.com", "denofgeek",
    "rottentomatoes.com/critics", "rt critics",
    "filmaffinity.com", "filmaffinity",
    "goodreads.com", "goodreads entertainment",
    "funko.com", "funko",
    "popculture.com", "popculture",
    "watchmojo.com", "watchmojo",
    "looper.com", "looper",
    "insider.com/entertainment", "insider entertainment",
    "parade.com", "parade",
    "cinemablend.com", "cinemablend",
    "slashfilm.com", "slashfilm",
    "giantfreakinrobot.com", "giantfreakinrobot",
    "hypable.com", "hypable",
    "theplaylist.net", "theplaylist",
    "comicvine.gamespot.com", "comicvine",
    "myanimelist.net", "myanimelist",
    "animenewsnetwork.com", "animenewsnetwork"
]


    # ------------------------------------------------------
    # Built-in Apps (names)
    # ------------------------------------------------------
"Built-in Apps": [

    "chrome://calculator",
    "chrome://camera",
    "chrome://calendar",
    "chrome://connectivity-diagnostics",
    "chrome://crosh",
    "chrome://diagnostics",
    "chrome://downloads",
    "chrome://extensions",
    "chrome://files",
    "chrome://file-manager",
    "chrome://flags",
    "chrome://help",
    "chrome://history",
    "chrome://keyboardoverlay",
    "chrome://lock-screen",
    "chrome://media-app",
    "chrome://network",
    "chrome://notifications",
    "chrome://os-settings",
    "chrome://print",
    "chrome://settings",
    "chrome://system",
    "chrome://terms",
    "chrome://usb",
    "chrome://wallpaper",

    "chrome://accessibility",
    "chrome://app-service-internals",
    "chrome://apps",
    "chrome://autofill",
    "chrome://bluetooth",
    "chrome://bookmarks",
    "chrome://chrome-urls",
    "chrome://components",
    "chrome://discards",
    "chrome://dino",
    "chrome://family-link",
    "chrome://gpu",
    "chrome://identity-testing",
    "chrome://inspect",
    "chrome://login",
    "chrome://management",
    "chrome://media-engagement",
    "chrome://net-export",
    "chrome://network-health",
    "chrome://new-tab-page",
    "chrome://password-manager",
    "chrome://policy",
    "chrome://prefs-internals",
    "chrome://quota-internals",
    "chrome://safe-browsing",
    "chrome://sandbox",
    "chrome://serviceworker-internals",
    "chrome://signin-internals",
    "chrome://site-engagement",
    "chrome://suggestions",
    "chrome://sync-internals",
    "chrome://tab-search",
    "chrome://tracing",
    "chrome://usb-internals",
    "chrome://version",
    "chrome://webrtc-internals",
    "chrome-untrusted://camera-app",
    "chrome-untrusted://media-app",
    "chrome-untrusted://projector",
    "chrome-untrusted://family-link",
    "chrome-untrusted://diagnostics",
    "chrome-untrusted://files",
    "chrome-untrusted://crosh",
    "https://canvas.apps.chrome",
    "canvas.apps.chrome",
    "canvas.google.com",
]



    # ------------------------------------------------------
    # Sexual Content (short + strong)
    # ------------------------------------------------------
    "Sexual Content": [
        "porn",
        "pornhub",  
        "xxx",
        "onlyfans",
        "nsfw",
    ]

    # ------------------------------------------------------
    # Allow only (school / allowed)
    # ------------------------------------------------------
    "Allow only": [
        "instructure.com",
        "schoology",
        "schoology.com",
        "googleclassroom",
        "classroom.google.com",
    ]
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

