# tensorbot
Tensorboard as a Telegram Chatbot.

![Demo Image](demo.jpeg)


## Getting started

### Getting a token
- You obviously need a Telegram account
- Read https://core.telegram.org/bots
- Chat with [`@botfather`](https://telegram.me/botfather) to create a new bot and get a associated token
- Save token as file with name token in the root directory

### Running tensorbot and tensorboard
- Start tensorboard
- Adapt url in `tensorbot.py` to your Tensorboard url
- Run `python tensorbot.py`

### Communicating with tensorbot
- `/start` to initiate chat
- `/plot <scalar name>` to pull most recent plot
- `/scalar <scalar name>` to get most recent iteration and value
- `/update' to update the list of available scalars
- `/interval <interval in seconds>` to update the interval time

