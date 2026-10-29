"""CI smoke test for the RSS sources.

The bot is useless if nothing parses, but one flaky source should not redden a
build, so this fails only when every feed comes back empty.
"""

import sys

import bot_poster

reachable = []
for url in bot_poster.RSS_FEEDS:
    feed = bot_poster.feedparser.parse(url)
    print(f"{len(feed.entries):3d} entries  bozo={feed.bozo}  {url}")
    if feed.entries:
        reachable.append(url)

if not reachable:
    sys.exit("no RSS feed returned any entries")

print(f"{len(reachable)}/{len(bot_poster.RSS_FEEDS)} feeds reachable")
