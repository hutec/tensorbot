import requests
import json
import pandas as pd
import telegram
from telegram.ext import Updater, CommandHandler, JobQueue

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

url = 'http://localhost:6006/data/plugin/scalars/scalars?run=.&tag=RMSE'

token = None
with open("token", "r") as f:
    token = f.read().splitlines()[0]


def call_tensorboard():
    logger.info("Calling Tensorboard")
    response = None
    try:
        response = requests.get(url)
    except requests.exceptions.RequestException as e:
        logger.error(e)
        return None, None

    if response.ok:
        json_data = json.loads(response.content)
        df = pd.DataFrame(json_data, columns=["walltime", "iteration", "value"])

        fig, axs = plt.subplots(1, 1)

        axs.plot(df["iteration"], df["value"])
        fig.savefig("rmse.png")

        last_iteration, last_value = df[["iteration", "value"]].tail(1).values[0]

        return last_iteration, last_value

class TensorBot():
    def __init__(self):
        self.bot = telegram.Bot(token=token)
        self.updater = Updater(token=token)
        self.dispatcher = self.updater.dispatcher
        self.job_queue = self.updater.job_queue
        self.chat_id = None
        self.update_interval_mins = 15
        self.last_iteration = None

        self.start_handler = CommandHandler('start', self.start)
        self.plot_handler = CommandHandler('plot', self.send_plot)
        self.dispatcher.add_handler(self.start_handler)
        self.dispatcher.add_handler(self.plot_handler)
        self.updater.start_polling()
        self.job_queue.run_repeating(self.callback_plot, interval=self.update_interval_mins * 60)

        self.updater.idle()

    def start(self, bot, update):
        bot.send_message(chat_id=update.message.chat_id, text="Hey, I am now your tensorbot")
        self.chat_id = update.message.chat_id

    def send_plot(self, bot, update=None):
        if self.chat_id:
            last_iteration, last_value = call_tensorboard()
            if last_iteration is None or last_value is None:
                logger.error("Tensorboard can not be reached")
                bot.send_message(chat_id=self.chat_id, text="Tensorboard can not be reached")
                return

            self.last_iteration = last_iteration
            bot.send_message(chat_id=self.chat_id, text="Iteration: {}, Value: {}".format(
                last_iteration, last_value))
            bot.send_photo(chat_id=self.chat_id, photo=open("rmse.png", "rb"))
        else:
            logger.info("Chat id is not set yet, use /start first")

    def callback_plot(self, bot, job):
        last_iteration, _ = call_tensorboard()
        if last_iteration != self.last_iteration:
            self.send_plot(bot)

def main():
    bot = TensorBot()

if __name__ == "__main__":
    main()
