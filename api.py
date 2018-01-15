import requests
import json
import pandas as pd
import telegram
from telegram.ext import Updater, CommandHandler, JobQueue, MessageHandler, Filters

import matplotlib
import matplotlib.pyplot as plt
import logging
from fuzzywuzzy import process

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
plt.switch_backend("Agg")

base_url = 'http://localhost:6006'
url = base_url + '/data/plugin/scalars/scalars?run=.&tag='

with open("token", "r") as f:
    token = f.read().splitlines()[0]


def get_all_scalars():
    """
    Get a list of all available scalars from Tensorboard.
    """
    scalar_url = base_url + '/data/plugin/scalars/tags'
    try:
        response = requests.get(scalar_url)
    except requests.exceptions.RequestException as e:
        logger.error(e)
        return []

    scalar_list = []
    if response.ok:
        json_data = json.loads(response.content)
        for v in json_data.values()[0]:
            scalar_list.append(v)

    return scalar_list


def get_scalar(scalar):
    """
    Get scalar values from Tensorboard.
    """
    logger.info("Calling Tensorboard to get scalar %s" % scalar)
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
    logger.info("Creating plot for scalar %s" % scalar_name)
    fig, axs = plt.subplots(1, 1)

    axs.plot(df["iteration"], df["value"])
    fig.savefig("%s.png" % scalar_name)


class TensorBot:
    """
    Main class for Telegram bot.
    """
    def __init__(self):
        self.bot = telegram.Bot(token=token)
        self.updater = Updater(token=token)
        self.dispatcher = self.updater.dispatcher
        self.job_queue = self.updater.job_queue
        self.chat_id = None
        self.update_interval_mins = 30
        self.last_iteration = None

        # auto_scalars are scalars that will be send periodically
        self.auto_scalars = ["RMSE"]
        self.scalar_list = get_all_scalars()

        self.start_handler = CommandHandler('start', self.start)
        self.plot_handler = CommandHandler('plot', self.send_scalar_plot, pass_args=True)
        self.scalar_handler = CommandHandler('scalar', self.send_scalar_value, pass_args=True)
        self.interval_update_handler = CommandHandler('interval', self.update_interval, pass_args=True)
        self.shutdown_handler = CommandHandler('stop', self.shutdown)
        self.text_handler = MessageHandler(Filters.text, self.message_reply)

        self.dispatcher.add_handler(self.start_handler)
        self.dispatcher.add_handler(self.plot_handler)
        self.dispatcher.add_handler(self.scalar_handler)
        self.dispatcher.add_handler(self.text_handler)
        self.dispatcher.add_handler(self.interval_update_handler)
        self.dispatcher.add_handler(self.shutdown_handler)
        self.updater.start_polling()
        self.job_queue.run_repeating(self.send_auto_scalars, interval=self.update_interval_mins * 60)

        self.updater.idle()

    def start(self, bot, update):
        """
        Initial command, required for setting the chat_id.
        """
        bot.send_message(chat_id=update.message.chat_id, text="Hey, I am now your tensorbot")
        self.chat_id = update.message.chat_id

    def message_reply(self, bot, update):
        """
        Handle messages that are not commands.
        Fuzzy match message string to available scalars and
        send a plot for the matching scalar.
        """
        msg = update.message.text
        scalar_match = process.extractOne(msg, self.scalar_list)[0]
        logger.info("Matched message '%s' with scalar %s" % (msg, scalar_match))
        self.send_scalar_plot(bot, update, args=[scalar_match])

    def send_scalar_value(self, bot, update, args):
        """
        Sends message with scalar iteration and value.
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
        Sends plot of scalar value over iterations.
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

    def send_auto_scalars(self, bot):
        """
        Callback for periodically updating the list of all scalars
        and sending a plot for all scalars in self.auto_scalars.

        This needs the chat_id to be set, via an initial /start command.
        """
        self.scalar_list = get_all_scalars()
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

    def update_interval(self, bot, update, args):
        """
        Update the interval for periodically sending updates.
        """
        if args[0].isdigit():
            interval = int(args[0])
            self.update_interval_mins = interval
            
            # TODO: Potentially there could be multiple jobs in the queue
            self.job_queue.jobs()[0].interval = interval * 60
            bot.send_message(chat_id=update.message.chat_id, text="Updated interval")
            logger.info("Updated interval: %f minutes" % self.update_interval_mins)
        else:
            bot.send_message(chat_id=update.message.chat_id, text="Could not update interval. Please provide a number")

    def shutdown(self, bot, update):
        logger.info("Shutting down")
        bot.send_message(chat_id=update.message.chat_id, text="Shutting down. Goodbye")
        exit()


def main():
    TensorBot()


if __name__ == "__main__":
    main()
