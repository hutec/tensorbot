import requests
import json
import pandas as pd
import telegram
from telegram.ext import Updater, CommandHandler, JobQueue, MessageHandler, Filters, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from io import BytesIO

import matplotlib
import matplotlib.pyplot as plt
import logging
from fuzzywuzzy import process
import argparse

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TensorboardHelper:
    """Handles communication with Tensorboard"""

    def __init__(self, base_url):
        self.base_url = base_url

    def get_all_runs(self):
        """
        Return list of all runs 
        """
        run_url = self.base_url + '/data/runs'
        try:
            response = requests.get(run_url)
        except requests.exceptions.RequestException as e:
            logger.error(e)
            return []
        runs = []
        if response.ok:
            runs = response.json()
        return runs

    def get_all_scalars(self, run):
        """
        Return list of all scalar names for given run from.
        """
        scalar_url = self.base_url + '/data/plugin/scalars/tags'
        try:
            response = requests.get(scalar_url)
        except requests.exceptions.RequestException as e:
            logger.error(e)
            return []

        scalar_list = []
        if response.ok:
            json_data = response.json()[run]
            for v in json_data.keys():
                scalar_list.append(v)

        return scalar_list

    def get_scalar(self, scalar, run):
        """
        Return pd.DataFrame of given scalar from run.
        """
        logger.info("Calling Tensorboard to get scalar %s" % scalar)
        run_url = self.base_url + '/data/plugin/scalars/scalars?run=' + run + '&tag=' + scalar
        try:
            response = requests.get(run_url)
        except requests.exceptions.RequestException as e:
            logger.error(e)
            return None

        if response.ok:
            json_data = response.json()
            df = pd.DataFrame(json_data, columns=["walltime", "iteration", "value"])
            return df


class TensorBot:
    """
    Main class for Telegram bot.
    """
    def __init__(self, tensorboard, token, run):
        self.bot = telegram.Bot(token=token)
        self.tensorboard = tensorboard
        self.updater = Updater(token=token)
        self.current_run = run
        self.dispatcher = self.updater.dispatcher
        self.scalars = []

        self.start_handler = CommandHandler('start', self.start)
        self.select_run_handler = CommandHandler('run', self.select_run)
        self.value_handler = CommandHandler('value', self.send_scalar_value, pass_args=True)
        self.plot_handler = CommandHandler('plot', self.send_scalar_plot, pass_args=True)
        self.message_handler = MessageHandler(Filters.text, self.message_reply)

        self.dispatcher.add_handler(self.start_handler)
        self.dispatcher.add_handler(self.select_run_handler)
        self.dispatcher.add_handler(self.value_handler)
        self.dispatcher.add_handler(self.plot_handler)
        self.dispatcher.add_handler(self.message_handler)

        self.updater.dispatcher.add_handler(CallbackQueryHandler(self.select_run_callback))
        self.updater.start_polling()
        self.updater.idle()

    # -----------------------Initializing and Selecting run -----------------------------------
    def start(self, bot, update):
        """
        Initial command, required for setting the chat_id.
        """
        chat_id = update.message.chat_id
        bot.send_message(chat_id=chat_id, text="Hey, I am now your tensorbot")
        if not self.current_run:
            bot.send_message(chat_id=chat_id, text="It seems like you have not selected a run please do that now." +
            "You can later switch the run with /run")

            self.select_run(bot, update)
                        
    def select_run(self, bot, update):
        """
        Command for selecting runs.
        """
        runs = self.tensorboard.get_all_runs()
        reply_markup = _build_keyboard(runs)
        bot.send_message(chat_id=update.message.chat_id, text="Please select run",
                         reply_markup=reply_markup)


    def select_run_callback(self, bot, update):
        query = update.callback_query
        chat_id = query.message.chat_id

        bot.edit_message_text(text="Selected run: {}. You can now query scalars".format(query.data),
                              chat_id=chat_id,
                              message_id=query.message.message_id)
        self.current_run = query.data

        self.scalars = self.tensorboard.get_all_scalars(self.current_run)

    # --------------------------------------------------------------------------------------------------

    def send_scalar_plot(self, bot, update, args):
        """
        Sends plot of scalar value over iterations for current run.
        """
        scalar_name = " ".join(args)
        chat_id = update.message.chat_id
        if scalar_name in self.scalars:
            df = self.tensorboard.get_scalar(args[0], self.current_run)
            if df is not None:
                bio = BytesIO()
                bio.name = 'image.jpeg'
                fig, ax = _create_plot(df, "iteration", "value")
                ax.set_ylabel(scalar_name)
                fig.savefig(bio)
                bio.seek(0)
                bot.send_photo(chat_id, photo=bio)
                last_iteration, last_value = df[["iteration", "value"]].tail(1).values[0]
                bot.send_message(chat_id=chat_id, text="{} - Iteration: {}, Value: {}".format(
                    scalar_name, last_iteration, last_value))
        else:
            # Show menu with available scalars
            bot.send_message(chat_id=chat_id, text="%s is not in the list of available scalars" % scalar_name)


    def send_scalar_value(self, bot, update, args):
        """
        Send most recent scalar value for current run.
        """
        scalar_name = " ".join(args)
        chat_id = update.message.chat_id
        if scalar_name in self.scalars:
            df = self.tensorboard.get_scalar(args[0], self.current_run)
            if df is not None:
                last_iteration, last_value = df[["iteration", "value"]].tail(1).values[0]
                bot.send_message(chat_id=chat_id, text="{} - Iteration: {}, Value: {}".format(
                    scalar_name, last_iteration, last_value))
        else:
            # Show menu with available scalars
            bot.send_message(chat_id=chat_id, text="%s is not in the list of available scalars" % scalar_name)


    def message_reply(self, bot, update):
        """
        Handle messages that are not commands.
        Fuzzy match message string to available scalars and
        send a plot for the matching scalar.
        """
        msg = update.message.text
        scalar_match = process.extractOne(msg, self.scalars)[0]
        logger.info("Matched message '%s' with scalar %s" % (msg, scalar_match))
        self.send_scalar_plot(bot, update, args=[scalar_match])


def _build_keyboard(labels):
    """Return InlineKeyboardMarkup of InlineKeyboardButtons with given labels"""
    keyboard = []
    for label in sorted(labels):
        keyboard.append([InlineKeyboardButton(label, callback_data=label)])
    return InlineKeyboardMarkup(keyboard)

def _create_plot(df, x, y):
    """Return fig, ax with plot from Dataframe"""
    logger.info("Creating plot for scalar %s" % y)
    fig, axs = plt.subplots(1, 1)
    axs.plot(df[x], df[y])
    axs.set_xlabel(x)
    axs.set_ylabel(y)
    return fig, axs


def main():
    parser = argparse.ArgumentParser(description='Tensorbot - A simple bot interface for Tensorboard')
    parser.add_argument("-u", "--url", type=str, help="Tensorboard base url", default="http://localhost:6006")
    parser.add_argument("-t", "--token", type=str, help="Telegram token, default is read from file", default=None)
    parser.add_argument("-r", "--run", type=str, help="Use specific run, defaults selects all runs", default=None)

    args = parser.parse_args()
    token = args.token
    run = args.run

    if not token:
        with open("token", "r") as f:
            token = f.read().splitlines()[0]

    board = TensorboardHelper(args.url)
    TensorBot(board, token, run)


if __name__ == "__main__":
    main()
