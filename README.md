# palbot
A simple discord bot based on the latest [discord.py](https://github.com/Rapptz/discord.py)

Documentation is terrible.
requirements.txt should be pretty good.
It's set up entirely as a docker container

trivia data comes from my fork of [j-archive jeopardy-parser](https://github.com/iamsix/jeopardy-parser) (modified to show the links for discord) forked from [the original](https://github.com/whymarrh/jeopardy-parser)

Currently uses config.py file to set the token and other bot info - I've provided a config.py.example file inside the config folder

## GLM images

`!glm <question>` and `!sglm <question>` send supported image attachments,
embed images, and image URLs using the same collection and downscaling helpers
as `!clai`. The configured OpenAI-compatible endpoint must support vision.
`!sglm` also includes web search results.

With `context on`, `image_lookback` (default 10) scans that many prior channel
messages **plus the command message**. `image_lookback 0` or `context off`
disables all images, including those on the command message. Bot Admins can
change these shared settings with `!claiconfig`.
Selected messages are processed oldest-to-newest, preserving attachment order
within each message, with command-message images last.

GLM omits images that would exceed the remaining `max_context_tokens` budget,
omitting historical images oldest-first and prioritizing command-message images.
Image costs are heuristic estimates, not exact GLM token counts.
Admin debug output reports included image
counts/estimates and budget omissions; API-reported usage takes precedence.
Text-only requests keep their original string payload, and images are treated
as background context unless the question specifically asks about them.
