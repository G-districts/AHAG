import re, tldextract, requests
from html import unescape

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
    "Uncategorized",
    "Allow only",
    "Global Block All",
]

KEYWORDS = {
    "AI Chatbots & Tools": [
        "chatgpt",
        "openai",
        "bard",
        "claude",
        "copilot",
        "perplexity.ai",
        "writesonic",
        "midjourney",
        "deepseek",
        "huggingface",
        "replit",
        "notion ai",
        "character.ai",
        "stability ai",
        "runwayml",
        "you.com",
        "phind",
        "leonardo ai",
        "tabnine",
        "ai21",
        "civitai",
        "kobold ai",
        "mistral ai",
        "gemini ai",
        "openrouter",
        "anthropic",
        "gradio",
        "langchain",
        "ollama",
        "lmsys",
        "bolt ai",
        "flowise",
        "scribe",
        "superhuman ai",
        "pi.ai",
        "quora poe",
        "jasper ai",
        "tome ai",
        "descript ai",
        "gamma ai",
        "loom ai",
        "chatpdf",
        "chatdoc",
        "sensei ai",
        "metavoice",
        "invideo ai",
        "veed ai",
        "kapwing ai",
        "dall-e",
        "canva ai",
        "github copilot",
        "codeium",
        "adobe firefly",
        "ai art generator",
        "ai voice generator",
        "ai music",
        "paperpal",
        "khanmigo",
        "wolfram alpha",
        "ai assistant",
        "ai chatbot",
        "neural network tool",
        "ai generator",
        "ai playground",
        "ai translator",
        "speech-to-text ai",
        "text-to-speech ai",
        "ai summarizer",
        "ai editor",
        "ai productivity",
        "ai image creator",
        "ai research tool",
        "ai code assistant",
        "ai programming",
        "virtual assistant ai",
        "ai writing tool",
        "ai automation",
        "ai helper",
        "machine learning tools",
        "deep learning tools",
        "nlp tools",
        "ai optimizer",
        "ai detector",
        "ai classifier",
        "ai search",
        "ai notes",
        "ai planner",
        "ai tutor",
        "ai_extra_1",
        "ai_extra_2",
        "ai_extra_3",
        "ai_extra_4",
        "ai_extra_5",
        "ai_extra_6",
        "ai_extra_7",
        "ai_extra_8",
        "ai_extra_9",
        "ai_extra_10",
        "ai_extra_11",
        "ai_extra_12",
    ],
    "Social Media": [
        "tiktok",
        "instagram",
        "snapchat",
        "facebook",
        "x.com",
        "twitter",
        "reddit",
        "discord",
        "tumblr",
        "be.real",
        "pinterest",
        "threads",
        "telegram",
        "whatsapp",
        "wechat",
        "line",
        "viber",
        "kik",
        "mastodon",
        "clubhouse",
        "quora",
        "messenger",
        "youtube",
        "linkedin",
        "nextdoor",
        "signal",
        "band.us",
        "mino",
        "houseparty",
        "yubo",
        "mewe",
        "telegram channels",
        "pinterest boards",
        "reddit communities",
        "instagram reels",
        "facebook groups",
        "snap map",
        "discord servers",
        "twitch chat",
        "imgur",
        "flickr",
        "deviantart",
        "pixiv",
        "gaiaonline",
        "facebook marketplace",
        "snap stories",
        "tiktok live",
        "instagram stories",
        "social feed",
        "social messaging",
        "social platform",
        "chat platform",
        "online communities",
        "video sharing",
        "microblogging",
        "fan communities",
        "creator platforms",
        "stream chats",
        "message apps",
        "status updates",
        "story posts",
        "followers list",
        "friend requests",
        "group chats",
        "social timeline",
        "post feed",
        "reaction buttons",
        "comment threads",
        "livestream chat",
        "voice channels",
        "video calls social",
        "community servers",
        "fan pages",
        "creator pages",
        "verified accounts",
        "trending topics",
        "hashtags",
        "for you page",
        "discover page",
        "social notifications",
        "direct messages",
        "social profile",
        "user bio",
        "avatar editor",
        "friends list",
        "social explore",
        "creator studio",
        "social analytics",
        "short video app",
        "social media hub",
        "content feed",
        "comment section",
        "social_extra_1",
        "social_extra_2",
        "social_extra_3",
        "social_extra_4",
        "social_extra_5",
    ],
    "Games": [
        "roblox",
        "fortnite",
        "minecraft",
        "epicgames",
        "leagueoflegends",
        "steam",
        "twitch",
        "itch.io",
        "riot games",
        "genshin impact",
        "valorant",
        "overwatch",
        "runescape",
        "osu",
        "call of duty",
        "battlefield",
        "apex legends",
        "pubg",
        "brawl stars",
        "pokemon",
        "minecraft realms",
        "minecraft servers",
        "halo",
        "forza",
        "nba2k",
        "fifa",
        "rocket league",
        "among us",
        "stardew valley",
        "animal crossing",
        "zelda",
        "mario kart",
        "super smash bros",
        "splatoon",
        "metroid",
        "fire emblem",
        "nintendo eshop",
        "xbox live",
        "playstation network",
        "origin",
        "uplay",
        "battle.net",
        "hearthstone",
        "diablo",
        "starcraft",
        "counter strike",
        "team fortress",
        "portal",
        "subnautica",
        "terraria",
        "ark survival",
        "rust game",
        "paladins",
        "dead by daylight",
        "rainbow six siege",
        "game pass",
        "vr games",
        "oculus",
        "meta quest",
        "vrchat",
        "unity games",
        "unreal engine games",
        "mobile games",
        "ios games",
        "android games",
        "gacha games",
        "strategy games",
        "sandbox games",
        "horror games",
        "roleplaying games",
        "mmo games",
        "fps games",
        "racing games",
        "casual games",
        "indie games",
        "esports",
        "speedrun",
        "game mods",
        "game launcher",
        "online lobbies",
        "clan pages",
        "guild forums",
        "matchmaking",
        "leaderboards",
        "achievement tracker",
        "game wiki",
        "patch notes",
        "update server",
        "game marketplace",
        "in-game events",
        "season pass",
        "battle pass",
        "skin store",
        "controller support",
        "games_extra_1",
        "games_extra_2",
        "games_extra_3",
        "games_extra_4",
        "games_extra_5",
    ],
    "Ecommerce": [
        "amazon",
        "ebay",
        "walmart",
        "bestbuy",
        "aliexpress",
        "etsy",
        "shopify",
        "mercado libre",
        "target.com",
        "newegg",
        "costco",
        "homedepot",
        "lowes",
        "flipkart",
        "rakuten",
        "jd.com",
        "shein",
        "zalando",
        "wayfair",
        "overstock",
        "kroger",
        "tesco",
        "argos",
        "asda",
        "carrefour",
        "ikea",
        "biglots",
        "kohls",
        "sephora",
        "ulta",
        "doordash",
        "ubereats",
        "grubhub",
        "instacart",
        "chewy",
        "petco",
        "toysrus",
        "gamestop",
        "nike.com",
        "adidas.com",
        "puma",
        "under armour",
        "lululemon",
        "apple store",
        "google store",
        "samsung store",
        "sony store",
        "hp store",
        "dell outlet",
        "lenovo store",
        "microcenter",
        "bhinneka",
        "shopee",
        "lazada",
        "vinted",
        "depop",
        "poshmark",
        "wish",
        "shop.app",
        "klarna",
        "afterpay",
        "affirm",
        "retail store",
        "online shopping",
        "digital marketplace",
        "marketplace app",
        "shopping cart",
        "checkout page",
        "discount code",
        "promo code",
        "deal of the day",
        "flash sale",
        "holiday sale",
        "clearance",
        "refurbished store",
        "used items",
        "classifieds",
        "buy now pay later",
        "wishlist page",
        "order history",
        "shipping tracker",
        "store pickup",
        "grocery delivery",
        "online pharmacy store",
        "electronics store",
        "fashion boutique",
        "home goods store",
        "office supplies store",
        "bookstore online",
        "music store online",
        "toy store online",
        "pet supply store",
        "sports store online",
        "ecom_extra_1",
        "ecom_extra_2",
        "ecom_extra_3",
        "ecom_extra_4",
        "ecom_extra_5",
    ],
    "Streaming Services": [
        "netflix",
        "spotify",
        "hulu",
        "vimeo",
        "twitch",
        "soundcloud",
        "peacocktv",
        "max.com",
        "disneyplus",
        "paramountplus",
        "apple tv",
        "apple music",
        "crunchyroll",
        "pluto tv",
        "tubi",
        "audible",
        "iheartradio",
        "amazon prime video",
        "youtube music",
        "youtube tv",
        "roku",
        "sling",
        "filmrise",
        "kanopy",
        "hoopla",
        "plex",
        "crackle",
        "starz",
        "showtime",
        "britbox",
        "acorn tv",
        "espn+",
        "nhl.tv",
        "mlb.tv",
        "nba league pass",
        "ufc fight pass",
        "wwe network",
        "tidal",
        "deezer",
        "pandora",
        "radio.com",
        "podcasts",
        "streaming app",
        "video service",
        "music service",
        "tv streaming",
        "movie streaming",
        "anime streaming",
        "live streaming",
        "game streaming",
        "audiobook streaming",
        "internet radio",
        "concert streaming",
        "documentary streaming",
        "news streaming",
        "kids streaming",
        "learning streaming",
        "sports streaming",
        "film library",
        "digital tv",
        "on-demand tv",
        "binge watch",
        "watch list",
        "continue watching",
        "recommended shows",
        "original series",
        "exclusive movies",
        "streaming subscription",
        "free with ads",
        "ad-supported streaming",
        "premium streaming",
        "streaming trial",
        "offline download",
        "watch offline",
        "4k streaming",
        "family plan streaming",
        "student plan streaming",
        "soundtrack station",
        "music playlist",
        "curated playlist",
        "radio station online",
        "video playlist",
        "episode list",
        "season list",
        "stream schedule",
        "live channel",
        "stream archive",
        "highlight clips",
        "clip share",
        "stream chat replay",
        "stream_extra_1",
        "stream_extra_2",
        "stream_extra_3",
        "stream_extra_4",
        "stream_extra_5",
    ],

    # Restricted categories – kept empty (Option C)
    "Sexual Content": [ "Bareback", "Bareback", "Big dick energy", "porn","xxx","xvideos","redtube","xnxx","brazzers","onlyfans","camgirl","pornhub", ahole
Got it. You want the list formatted with a beginning quote mark, the word, and then an ending quote mark followed by a comma, like this: "Word",.

Here is the complete list reformatted exactly as requested:

"Fukk",

"Fukkah",

"Fukken",

"Fukker",

"Fukkin",

"g00k",

"gay",

"gayboy",

"gaygirl",

"gays",

"gayz",

"God-damned",

"h00r",

"h0ar",

"h0re",

"hells",

"hoar",

"hoor",

"hoore",

"jackoff",

"jap",

"japs",

"jerk-off",

"jisim",

"jiss",

"jizm",

"jizz",

"knob",

"knobs",

"knobz",

"kunt",

"kunts",

"kuntz",

"kurba",

"kurva",

"kurec",

"Lesbian",

"Lezzian",

"Lipshits",

"Lipshitz",

"masochist",

"masokist",

"massterbait",

"masstrbait",

"masstrbate",

"masterbaiter",

"masterbate",

"masterbates",

"Motha Fucker",

"Motha Fuker",

"Motha Fukker",

"Mother Fucker",

"Mother Fukah",

"Mother Fuker",

"Mother Fukker",

"mother-fucker",

"Mutha Fucker",

"Mutha Fukah",

"Mutha Fuker",

"Mutha Fukker",

"n1gr",

"nastt",

"nigger",

"nigur",

"niiger",

"niigr",

"orafis",

"orgasim",

"orgasm",

"orgasum",

"oriface",

"orifice",

"orifiss",

"packi",

"packie'",

"packy",

"paki",

"pakie",

"paky",

"pecker",

"peeenus",

"peeenusss",

"peenus",

"peinus",

"pen1s",

"penas",

"penis",

"penis-breath",

"penus",

"penuus'",

"Phuc",

"Phuck",

"Phuk",

"Phuker",

"Phukker",

"polac",

"polack",

"polak",

"Poonan",

"pr1c",

"pr1ck",

"pr1k",

"pusse",

"pussee",

"pussy",

"puuke",

"puuker",

"queer",

"queers",

"queerz",

"qweers",

"qweerz",

"qweir",

"recktum",

"rectum",

"retard",

"sadist",

"scank",

"schlong",

"screwin",

"semen",

"sex",

"seks",

"sexy",

"Sh!t",

"sh1t",

"sh1ter",

"sh1ts",

"sh1tter",

"sh1tz",

"shit",

"shits",

"shitter",

"Shitty",

"Shity",

"shitz",

"Shyt",

"Shyte",

"Shytty",

"Shyty",

"skanck",

"skank",

"skankee",

"skankey",

"skanks",

"Skanky",

"slut",

"sluts",

"Slutty",

"slutz",

"son-of-a-bitch",

"tit",

"turd",

"va1jina",

"vag1na",

"vagiina",

"vagina",

"vaj1na",

"vajina",

"vullva",

"vulva",

"w0p",

"wh00r",

"wh0re",

"whore",

"xrated",

"xxx",

"b!+ch",

"bitch",

"blowjob",

"clit",

"arschloch",

"fuck",

"shit",

"ass",

"asshole",

"b!tch",

"b17ch",

"b1tch",

"bastard",

"bi+ch",

"boiolas",

"buceta",

"c0ck",

"cawk",

"chink",

"cipa",

"clits",

"cock",

"cum",

"cunt",

"dildo",

"dirsa",

"ejakulate",

"fatass",

"fcuk",

"fuk",

"fux0r",

"hoer",

"hore",

"jism",

"kawk",

"l3itch",

"l3i+ch",

"lesbian",

"masturbate",

"masterbat",

"masterbat3",

"motherfucker",

"s.o.b.",

"mofo",

"nazi",

"nigga",

"nigger",

"nutsack",

"phuck",

"pimpis",

"pusse",

"pussy",

"scrotum",

"sh!t",

"shemale",

"shi+",

"sh!+",

"slut",

"smut",

"teets",

"tits",

"boobs",

"b00bs",

"teez",

"testical",

"testicle",

"titt",

"w00se",

"jackoff",

"wank",

"whoar",

"whore",

"damn",

"dyke",

"fuck",

"shit",

"@$$",

"amcik",

"andskota",

"arse",

"assrammer",

"ayir",

"bi7ch",

"bitch",

"bollock",

"breasts",

"butt-pirate",

"cabron",

"cazzo",

"chraa",

"chuj",

"Cock",

"cunt",

"d4mn",

"daygo",

"dego",

"dick",

"dike",

"dupa",

"dziwka",

"ejackulate",

"Ekrem",

"Ekto",

"enculer",

"faen",

"fag",

"fanculo",

"fanny",

"feces",

"feg",

"Felcher",

"ficken",

"fitt*",

"Flikker",

"foreskin",

"Fotze",

"Fu(*",

"fuk*",

"futkretzn",

"gay",

"gook",

"guiena",

"h0r",

"h4x0r",

"hell",

"helvete",

"hoer*",

"honkey",

"Huevon",

"hui",

"injun",

"jizz",

"kanker*",

"kike",

"klootzak",

"kraut",

"knulle",

"kuk",

"kuksuger",

"Kurac",

"kurwa",

"kusi",

"kyrpa",

"lesbo",

"mamhoon",

"masturbat",

"merd",

"mibun",

"monkleigh",

"mouliewop",

"muie",

"mulkku",

"muschi",

"nazis",

"nepesaurio",

"nigger",

"orospu",

"paska",

"perse",

"picka",

"pierdol",

"pillu",

"pimmel",

"piss",

"pizda",

"poontsee",

"poop",

"porn",

"p0rn",

"pr0n",

"preteen",

"pula",

"pule",

"puta",

"puto",

"qahbeh",

"queef",

"rautenberg",

"schaffer",

"scheiss",

"schlampe",

"schmuck",

"screw",

"sh!t",

"sharmuta",

"sharmute",

"shipal",

"shiz",

"skribz",

"skurwysyn",

"sphencter",

"spic",

"spierdalaj",

"splooge",

"suka",

"b00b",

"titt",

"twat",

"vittu",

"wank",

"wetback*",

"wichser",

"wop",

"yed",

"zabourah"
    ],
    "Gambling": ["casino","sportsbook","bet","poker","slot","roulette","draftkings","fanduel"
    ],
    "Illegal, Malicious, or Hacking": ["warez","piratebay","crack download","keygen","free movies streaming","sql injection","ddos","cheat engine"
    ],
    "Drugs & Alcohol": ["buy weed","vape","nicotine","delta-8","kratom","bong","vodka","whiskey","winery","brewery","weed","coke", "cocaine","heroine", 
    ],

    "Collaboration": [
        "gmail",
        "outlook",
        "office 365",
        "onedrive",
        "teams",
        "slack",
        "zoom",
        "google docs",
        "google drive",
        "meet.google",
        "notion",
        "trello",
        "asana",
        "monday",
        "figma",
        "miro",
        "mural",
        "dropbox",
        "box.com",
        "evernote",
        "airtable",
        "webex",
        "gotomeeting",
        "jira",
        "confluence",
        "sharepoint",
        "github",
        "gitlab",
        "bitbucket",
        "codepen",
        "replit",
        "stackblitz",
        "loom",
        "tome",
        "google sheets",
        "google slides",
        "forms",
        "classroom",
        "edmodo",
        "schoology",
        "canvas",
        "pdf share",
        "file sharing",
        "video calls",
        "team chat",
        "project boards",
        "kanban",
        "workspace",
        "team hub",
        "calendar",
        "calendar share",
        "task manager",
        "org wiki",
        "team wiki",
        "meeting notes",
        "collab notes",
        "shared document",
        "shared folder",
        "comment thread",
        "suggesting mode",
        "version history",
        "cloud drive",
        "remote work",
        "online whiteboard",
        "brainstorm board",
        "scrum board",
        "agile board",
        "product roadmap",
        "project plan",
        "status update",
        "standup notes",
        "retrospective notes",
        "assignment submission",
        "group project",
        "peer review",
        "shared inbox",
        "team email",
        "channel chat",
        "voice channel",
        "screen share",
        "breakout rooms",
        "conference room link",
        "meeting lobby",
        "collab_extra_1",
        "collab_extra_2",
        "collab_extra_3",
        "collab_extra_4",
        "collab_extra_5",
    ],
    "General / Education": [
        "wikipedia",
        "news",
        "encyclopedia",
        "khan academy",
        "nasa.gov",
        ".edu",
        "britannica",
        "quizlet",
        "coursera",
        "edx",
        "mit opencourseware",
        "stackexchange",
        "stackoverflow",
        "code.org",
        "duolingo",
        "anki",
        "national geographic",
        "science daily",
        "smithsonian",
        "history.com",
        "pbs learning",
        "library of congress",
        "project gutenberg",
        "open textbook",
        "math is fun",
        "brilliant.org",
        "wolfram alpha",
        "dictionary.com",
        "thesaurus.com",
        "grammar check",
        "writing help",
        "study guide",
        "math solver",
        "citation generator",
        "research database",
        "science.org",
        "nature.com",
        "arxiv",
        "pubmed",
        "kids learning",
        "abcya",
        "coolmath",
        "typing club",
        "hour of code",
        "geogebra",
        "reading practice",
        "language learning",
        "biology resources",
        "chemistry resources",
        "physics resources",
        "engineering resources",
        "geography tools",
        "astronomy tools",
        "science experiments",
        "education games",
        "homework help",
        "study tools",
        "learning portal",
        "school tools",
        "historical archives",
        "world atlas",
        "maps",
        "data sets",
        "public domain texts",
        "essay planner",
        "flashcards app",
        "test prep",
        "sat prep",
        "act prep",
        "ap exam prep",
        "college board",
        "open course",
        "lecture notes",
        "class notes",
        "lab manual",
        "science fair ideas",
        "school project ideas",
        "presentation templates",
        "study timer",
        "focus timer",
        "note taking app",
        "reading list",
        "book summary site",
        "education podcast",
        "learning videos",
        "tutorial website",
        "how-to guide",
        "reference site",
        "student portal",
        "edu_extra_1",
        "edu_extra_2",
        "edu_extra_3",
        "edu_extra_4",
        "edu_extra_5",
    ],
    "Sports & Hobbies": [
        "espn",
        "nba",
        "nfl",
        "mlb",
        "nhl",
        "cars",
        "boats",
        "aircraft",
        "fifa",
        "formula1",
        "ufc",
        "motogp",
        "pga",
        "premier league",
        "la liga",
        "bundesliga",
        "cycling",
        "swimming",
        "track and field",
        "tennis",
        "badminton",
        "volleyball",
        "hiking",
        "camping",
        "fishing",
        "photography",
        "gardening",
        "baking",
        "cooking",
        "skateboarding",
        "bmx",
        "sports news",
        "team rosters",
        "athlete stats",
        "scoreboards",
        "fantasy sports",
        "car reviews",
        "bike reviews",
        "drone hobby",
        "3d printing",
        "lego",
        "cosplay",
        "crafts",
        "painting",
        "drawing",
        "woodworking",
        "metalworking",
        "robotics",
        "coding hobby",
        "model airplanes",
        "rc cars",
        "rock climbing",
        "kayaking",
        "canoeing",
        "sailing",
        "guitar",
        "piano",
        "music theory",
        "dance",
        "yoga",
        "pilates",
        "running",
        "marathon",
        "chess",
        "puzzles",
        "strategy board games",
        "collectibles",
        "trading cards",
        "model trains",
        "astronomy stargazing",
        "birdwatching",
        "origami",
        "calligraphy",
        "knitting",
        "crochet",
        "sewing",
        "scrapbooking",
        "journaling",
        "comic collecting",
        "coin collecting",
        "stamp collecting",
        "home brewing hobby",
        "home barista hobby",
        "aquarium hobby",
        "reptile hobby",
        "pet training hobby",
        "rc boats",
        "slot car racing",
        "hobby_extra_1",
        "hobby_extra_2",
        "hobby_extra_3",
        "hobby_extra_4",
        "hobby_extra_5",
    ],
    "App Stores & System Updates": [
        "play.google",
        "apps.apple",
        "microsoft store",
        "firmware update",
        "drivers download",
        "ubuntu updates",
        "debian repos",
        "snapcraft",
        "f-droid",
        "chrome web store",
        "firefox addons",
        "edge addons",
        "android system update",
        "ios update",
        "windows update",
        "macos update",
        "linux updates",
        "package manager",
        "software repository",
        "android apk",
        "app marketplace",
        "developer beta",
        "system patch",
        "security patch",
        "software install",
        "software upgrade",
        "device support",
        "device update",
        "firmware patch",
        "manufacturer update",
        "driver utility",
        "hp drivers",
        "dell drivers",
        "lenovo drivers",
        "nvidia drivers",
        "amd drivers",
        "intel drivers",
        "graphics driver",
        "audio driver",
        "keyboard firmware",
        "mouse firmware",
        "system maintenance",
        "system repair",
        "software hub",
        "app downloads",
        "mobile apps",
        "desktop apps",
        "system utilities",
        "update checker",
        "version update",
        "stable release",
        "beta release",
        "software catalog",
        "os release notes",
        "changelog page",
        "system restore",
        "recovery mode",
        "bootloader unlock",
        "developer options",
        "debug tools",
        "diagnostic tools",
        "bios update",
        "uefi update",
        "microcode update",
        "patch tuesday",
        "service pack",
        "feature update",
        "lts release",
        "rolling release",
        "driver download center",
        "support portal",
        "device tools page",
        "utility suite",
        "pc cleaner",
        "optimizer app",
        "performance monitor",
        "system monitor",
        "usage stats",
        "data saver",
        "update reminder",
        "support assistant",
        "tech support page",
        "system_extra_1",
        "system_extra_2",
        "system_extra_3",
        "system_extra_4",
        "system_extra_5",
        "crosh",
    ],
    "Advertising": [
        "ads.txt",
        "adserver",
        "doubleclick",
        "adchoices",
        "advertising",
        "adsense",
        "admob",
        "taboola",
        "outbrain",
        "bing ads",
        "google ads",
        "facebook ads",
        "instagram ads",
        "tiktok ads",
        "reddit ads",
        "pinterest ads",
        "sponsored content",
        "paid promotion",
        "display ads",
        "native ads",
        "ad tracking",
        "ad campaign",
        "digital marketing",
        "seo",
        "sem",
        "affiliate links",
        "ad targeting",
        "cookie tracking",
        "retargeting",
        "ad impressions",
        "ad network",
        "dsp",
        "ssp",
        "programmatic ads",
        "ad analytics",
        "ad manager",
        "brand promotions",
        "media buying",
        "ad placement",
        "ad inventory",
        "advertiser tools",
        "search ads",
        "video ads",
        "banner ads",
        "mobile ads",
        "campaign manager",
        "brand awareness",
        "market research",
        "keyword ads",
        "ad optimization",
        "advertising platform",
        "ad marketplace",
        "social media ads",
        "pre-roll ads",
        "mid-roll ads",
        "post-roll ads",
        "ad-supported app",
        "in-stream ads",
        "sponsored posts",
        "influencer ads",
        "tracking pixel",
        "conversion tracking",
        "utm tracking",
        "click-through rate",
        "cpm pricing",
        "cpc pricing",
        "paid search",
        "paid social",
        "remarketing",
        "lookalike audiences",
        "ad creative",
        "ad copy",
        "landing page",
        "split testing",
        "multivariate testing",
        "ad policy",
        "ad review",
        "ad approval",
        "ad disapproval",
        "ads dashboard",
        "campaign budget",
        "cost cap",
        "bid strategy",
        "ad schedule",
        "frequency cap",
        "ads_extra_1",
        "ads_extra_2",
        "ads_extra_3",
        "ads_extra_4",
        "ads_extra_5",
    ],
    "Blogs": [
        "wordpress",
        "blogger",
        "wattpad",
        "joomla",
        "drupal",
        "medium",
        "ghost.org",
        "substack",
        "typepad",
        "weebly",
        "tumblr blogs",
        "write.as",
        "hashnode",
        "dev.to",
        "notion blogs",
        "personal blog",
        "tech blog",
        "journal entries",
        "creative writing",
        "story blog",
        "reviews blog",
        "travel blog",
        "food blog",
        "lifestyle blog",
        "study blog",
        "coding blog",
        "science blog",
        "art blog",
        "photography blog",
        "blog feed",
        "blog reader",
        "rss feed",
        "web publishing",
        "blog themes",
        "blog templates",
        "content management",
        "cms",
        "blog comments",
        "blog posts",
        "guest posts",
        "longform reading",
        "newsletter",
        "online writing",
        "portfolio site",
        "creative journal",
        "article platform",
        "reading app",
        "community posts",
        "microblog",
        "blog index",
        "blogging platform",
        "how-to articles",
        "opinion pieces",
        "daily journal",
        "reflection blog",
        "learning blog",
        "student blog",
        "school blog",
        "club blog",
        "project blog",
        "dev blog",
        "design blog",
        "parenting blog",
        "hobby blog",
        "fan blog",
        "series blog",
        "photo diary",
        "sketch blog",
        "writing prompts blog",
        "flash fiction blog",
        "nonfiction essays",
        "book review blog",
        "movie review blog",
        "music review blog",
        "product review blog",
        "tutorial blog",
        "guide blog",
        "announcement blog",
        "update log",
        "changelog blog",
        "release notes blog",
        "blog_extra_1",
        "blog_extra_2",
        "blog_extra_3",
        "blog_extra_4",
        "blog_extra_5",
    ],
    "Health & Medicine": [
        "patient portal",
        "glucose",
        "fitbit",
        "apple health",
        "pharmacy",
        "telehealth",
        "webmd",
        "cdc.gov",
        "who.int",
        "mayoclinic",
        "cleveland clinic",
        "johns hopkins",
        "nih.gov",
        "healthline",
        "myfitnesspal",
        "calorie counter",
        "step tracker",
        "heart rate monitor",
        "sleep tracker",
        "exercise log",
        "water tracker",
        "meditation apps",
        "yoga app",
        "wellness app",
        "healthy habits",
        "first aid info",
        "injury care",
        "nutrition facts",
        "vitamins",
        "health education",
        "wellness tips",
        "fitness routines",
        "workout planner",
        "gym tracker",
        "hydration reminder",
        "eye care",
        "dental care",
        "skin care",
        "dermatology",
        "pediatrics",
        "teen health",
        "sports injury prevention",
        "healthy recipes",
        "food allergies",
        "medical encyclopedia",
        "health database",
        "symptom lookup",
        "health apps",
        "fitness coaching",
        "health monitoring",
        "health data",
        "doctor finder",
        "urgent care",
        "online clinics",
        "sleep hygiene",
        "stress management",
        "mindfulness practice",
        "breathing exercises",
        "posture coach",
        "step challenge",
        "activity rings",
        "health journal",
        "mood tracker",
        "period tracker",
        "headache diary",
        "water log",
        "meal planner",
        "grocery list healthy",
        "allergy tracker",
        "immunization record",
        "school nurse info",
        "health classes",
        "first responder info",
        "emergency contacts",
        "safety guidelines",
        "public health info",
        "local clinic site",
        "insurance portal",
        "health newsletter",
        "fitness blog",
        "nutrition blog",
        "wellness podcast",
        "health_extra_1",
        "health_extra_2",
        "health_extra_3",
        "health_extra_4",
        "health_extra_5",
    ],
    "Religion": [
        "church",
        "synagogue",
        "mosque",
        "bible study",
        "quran",
        "sermon",
        "daily devotional",
        "bible gateway",
        "torah study",
        "hadith resources",
        "interfaith dialogue",
        "religious podcasts",
        "worship music",
        "hymns",
        "religious lectures",
        "prayer times",
        "religious education",
        "faith learning",
        "catechism",
        "youth ministry",
        "church events",
        "religion history",
        "religious books",
        "spiritual reflection",
        "religious community",
        "religious classes",
        "holy days",
        "scripture reading",
        "faith traditions",
        "religious symbols",
        "religion articles",
        "church website",
        "temple website",
        "religion resources",
        "online sermons",
        "religious library",
        "worship guides",
        "prayer journal",
        "religious teachings",
        "religious discussions",
        "spiritual growth",
        "religious study tools",
        "religious media",
        "faith-based videos",
        "religious apps",
        "religious livestreams",
        "religious blogs",
        "religious forums",
        "scripture app",
        "prayer reminder",
        "devotional app",
        "youth group site",
        "mission trip info",
        "charity organization faith",
        "religious calendar",
        "holiday services",
        "sacred texts",
        "commentaries",
        "religion Q and A",
        "religious FAQ",
        "catechism class",
        "confirmation class",
        "bar mitzvah info",
        "bat mitzvah info",
        "sunday school",
        "religion lesson plans",
        "religious schools",
        "seminary site",
        "theology articles",
        "religion podcast",
        "sermon archive",
        "hymn lyrics clean",
        "worship schedule",
        "religious volunteer",
        "faith-based camp",
        "religion conference",
        "pilgrimage info",
        "chapel site",
        "religious counseling",
        "religion_extra_1",
        "religion_extra_2",
        "religion_extra_3",
        "religion_extra_4",
        "religion_extra_5",
    ],

    # Restricted again (Weapons) – kept empty
    "Weapons": ["knife","guns","rifle","ammo","silencer","tactical"
    ],

    "Entertainment": [
        "tv shows",
        "movies",
        "anime",
        "cartoons",
        "jokes",
        "memes",
        "imdb",
        "rottentomatoes",
        "letterboxd",
        "fandom.com",
        "funny or die",
        "cracked",
        "screenrant",
        "variety",
        "the onion",
        "comic vine",
        "movie reviews",
        "show reviews",
        "episode guide",
        "fan wiki",
        "comic books",
        "animation",
        "animated shows",
        "kids shows",
        "manga",
        "graphic novels",
        "pop culture",
        "celebrity news",
        "music videos",
        "trailers",
        "soundtracks",
        "fan art",
        "fan theories",
        "entertainment podcasts",
        "top 10 lists",
        "media analysis",
        "comedy clips",
        "sketch comedy",
        "dance videos",
        "viral videos",
        "internet culture",
        "reaction videos",
        "movie databases",
        "character lists",
        "tv schedules",
        "film festival",
        "indie films",
        "cartoon channels",
        "animation studios",
        "kids entertainment",
        "all-ages media",
        "family movies",
        "family shows",
        "clean comedy",
        "fun videos",
        "game shows",
        "talent shows",
        "variety shows",
        "stream highlights",
        "clip compilations",
        "music charts",
        "song rankings",
        "concert footage",
        "behind the scenes",
        "bloopers",
        "interviews cast",
        "panel discussions",
        "fan conventions",
        "comic con",
        "anime expo",
        "film critique blog",
        "tv recap blog",
        "entertainment column",
        "late night clips",
        "talk show clips",
        "parody videos",
        "spoiler discussions",
        "theory videos",
        "character rankings",
        "ship charts clean",
        "episode recap",
        "ent_extra_1",
        "ent_extra_2",
        "ent_extra_3",
        "ent_extra_4",
        "ent_extra_5",
    ],
    "Built-in Apps": [
        "calculator",
        "crosh",
        "camera",
        "clock",
        "files app",
        "weather app",
        "notes app",
        "contacts app",
        "calendar app",
        "maps app",
        "photos app",
        "mail app",
        "messages app",
        "reminders",
        "safari",
        "chrome",
        "voice memos",
        "compass",
        "measure app",
        "screen time",
        "settings app",
        "find my",
        "shortcuts",
        "health app",
        "activity app",
        "translate app",
        "app store",
        "system preferences",
        "file manager",
        "gallery",
        "video player",
        "audio recorder",
        "task manager",
        "browser",
        "device tools",
        "device utilities",
        "built-in widgets",
        "system apps",
        "default apps",
        "phone app",
        "dialer",
        "recent calls",
        "search app",
        "spotlight search",
        "dock apps",
        "launcher apps",
        "system panel",
        "quick settings",
        "notification center",
        "basic utilities",
        "default widgets",
        "system tools",
        "core apps",
        "device info",
        "app manager",
        "music app",
        "podcast app",
        "books app",
        "wallet app",
        "payment app",
        "downloads folder",
        "screenshots folder",
        "status bar",
        "control center",
        "lock screen",
        "home screen",
        "widget screen",
        "power menu",
        "restart menu",
        "bluetooth settings",
        "wifi settings",
        "mobile data settings",
        "personal hotspot",
        "accessibility settings",
        "display settings",
        "sound settings",
        "privacy settings",
        "battery settings",
        "storage settings",
        "language settings",
        "region settings",
        "keyboard settings",
        "backup settings",
        "restore settings",
        "reset options",
        "builtin_extra_1",
        "builtin_extra_2",
        "builtin_extra_3",
        "builtin_extra_4",
        "builtin_extra_5",
    ],

  "Allow only": ["canvas", "k12", "instructure.com"],

}

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
    txt = re.sub(r"\s+", " ", txt).strip().lower()
    return txt

def classify(url: str, html: str = None):
    """
    Returns dict: {category: str, confidence: float}
    """
    if not (url or "").startswith(("http://","https://")):
        url = "https://" + (url or "")
    ext = tldextract.extract(url)
    domain = ".".join([p for p in [ext.domain, ext.suffix] if p])
    host = ".".join([p for p in [ext.subdomain, ext.domain, ext.suffix] if p if p])

    tokens = [url.lower(), host.lower(), domain.lower()]
    body = _textify(html) if html else _textify(_fetch_html(url))
    if body:
        tokens.append(body)

    scores = {c: 0 for c in CATEGORIES}
    for cat, kws in KEYWORDS.items():
        for kw in kws:
            pat = kw.lower()
            for t in tokens:
                if pat in t:
                    scores[cat] += 1

    # Special-case rules
    if any(s in domain for s in ["edu",".edu"]): scores["General / Education"] += 3
    if any(s in url for s in ["wp-login","/wp-content/"]): scores["Blogs"] += 1

    # ✅ Prioritize Allow only
    if scores["Allow only"] > 0:
        best_cat = "Allow only"
    else:
        best_cat = max(scores, key=lambda c: scores[c])
        if scores[best_cat] == 0:
            best_cat = "Uncategorized"

    total = sum(scores.values()) or 1
    conf = scores[best_cat] / total
    return {"category": best_cat, "confidence": float(conf), "domain": domain, "host": host}

