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

url = 'http://localhost:6006/data/plugin/scalars/scalars?run=.&tag='
# url = 'http://localhost:6006/data/plugin/scalars/scalars?run=.&tag=RMSE'


token = None
with open("token", "r") as f:
    token = f.read().splitlines()[0]

def get_scalar(scalar):
    """
    Get scalar values from Tensorboard.
    """
    logger.info("Calling Tensorboard to get scalar %s" % scalar)
    response = None
    try:
        response = requests.get(url + scalar)
    except requests.exceptions.RequestException as e:
        logger.error(e)
        return None

    if response.ok:
        json_data = json.loads(response.content)
        df = pd.DataFrame(json_data, columns=["walltime", "iteration", "value"])
        return df

def create_plot(df, scalar_name):
    """
    Plot scalar value over iterations.
    """
    fig, axs = plt.subplots(1, 1)

    axs.plot(df["iteration"], df["value"])
    fig.savefig("%s.png" % scalar_name)

    #last_iteration, last_value = df[["iteration", "value"]].tail(1).values[0]


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

        # scalars that will be send periodically
        self.auto_scalars = ["RMSE"]

        self.start_handler = CommandHandler('start', self.start)
        self.plot_handler = CommandHandler('plot', self.send_scalar_plot, pass_args=True)
        self.scalar_handler = CommandHandler('scalar', self.send_scalar_value, pass_args=True)
        self.dispatcher.add_handler(self.start_handler)
        self.dispatcher.add_handler(self.plot_handler)
        self.dispatcher.add_handler(self.scalar_handler)
        self.updater.start_polling()
        self.job_queue.run_repeating(self.callback_auto_scalars, interval=self.update_interval_mins * 60)

        self.updater.idle()

    def start(self, bot, update):
        bot.send_message(chat_id=update.message.chat_id, text="Hey, I am now your tensorbot")
        self.chat_id = update.message.chat_id

    def send_scalar_value(self, bot, update, args):
        """
        Sends mesage with scalar iteration and value
        """
        if len(args) == 1:
            df = get_scalar(args[0])
            if df is not None:
                last_iteration, last_value = df[["iteration", "value"]].tail(1).values[0]
                bot.send_message(chat_id=self.chat_id, text="{} - Iteration: {}, Value: {}".format(
                    args[0], last_iteration, last_value))
        else:
            bot.send_message(chat_id=update.message.chat_id, text="Specify single scalar")

    def send_scalar_plot(self, bot, update, args):
        """
        Sends plot of scalar value over iterations
        """
        if len(args) == 1:
            df = get_scalar(args[0])
            create_plot(df, args[0])
            if df is not None:
                last_iteration, last_value = df[["iteration", "value"]].tail(1).values[0]
                bot.send_message(chat_id=self.chat_id, text="{} - Iteration: {}, Value: {}".format(
                    args[0], last_iteration, last_value))
                bot.send_photo(chat_id=self.chat_id, photo=open(str(args[0]) + ".png", "rb"))
        else:
            bot.send_message(chat_id=update.message.chat_id, text="Specify single scalar")

    def send_auto_scalars(self, bot, update=None):
        if self.chat_id:
            for scalar in self.auto_scalars:
                df = get_scalar(scalar)
                if df is not None:
                    create_plot(df, scalar)
                    last_iteration, last_value = df[["iteration", "value"]].tail(1).values[0]
                    bot.send_message(chat_id=self.chat_id, text="{} - Iteration: {}, Value: {}".format(
                        scalar, last_iteration, last_value))
                    bot.send_photo(chat_id=self.chat_id, photo=open(scalar + ".png", "rb"))
        else:
            logger.info("Chat id is not set yet, use /start first")

    def callback_auto_scalars(self, bot, job):
        last_iteration, _ = call_tensorboard()
        if last_iteration != self.last_iteration:
            self.send_plot(bot)

def main():
    bot = TensorBot()

if __name__ == "__main__":
    main()
