import warnings
from sys import platform
import matplotlib.cbook

warnings.filterwarnings("ignore", category=matplotlib.cbook.mplDeprecation)
warnings.filterwarnings("ignore", message="ignoring `maxfev` argument to `Minimizer()`. Use `max_nfev` instead.")
warnings.filterwarnings("ignore", message="DataFrame columns are not unique, some columns will be omitted.")
warnings.filterwarnings("ignore", message="All-NaN axis encountered")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

import matplotlib
import pandas as pd

from tools.helper import init_logger

if not (platform == "linux" or platform == "linux2"):
    matplotlib.use('Qt5Agg')

import logging.handlers
import threading
import sys
from configobj import ConfigObj
from tools.mongo_manager import StrategyHandler, UpdateChecker, GameLogger, MongoManager
from table_analysers.table_screen_based import TableScreenBased
from decisionmaker.current_hand_memory import History, CurrentHandPreflopState
from decisionmaker.montecarlo_python import run_montecarlo_wrapper
from decisionmaker.decisionmaker import Decision,DecisionTypes

version = 4.21


class ThreadManager(threading.Thread):
    def __init__(self, threadID, name, counter, updater):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.updater = updater
        self.name = name
        self.counter = counter
        self.loger = logging.getLogger('main')

        self.game_logger = GameLogger()

    def run(self):
        log = logging.getLogger(__name__)
        h = History()
        preflop_url, preflop_url_backup = self.updater.get_preflop_sheet_url()
        try:
            h.preflop_sheet = pd.read_excel(preflop_url, sheet_name=None)
        except:
            h.preflop_sheet = pd.read_excel(preflop_url_backup, sheet_name=None)

        self.game_logger.clean_database()

        p = StrategyHandler()
        p.read_strategy()

        preflop_state = CurrentHandPreflopState()
        mongo = MongoManager()
        table_scraper_name = None

        #while True:
        for i in range(1):
            # reload table if changed
            config = ConfigObj("config.ini")

            ready = False
            fast_fold = False
            while (not ready):
                p.read_strategy()
                t = TableScreenBased(p, self.game_logger, version)

                ready = t.load_table() and \
                        t.get_lost_everything(h, t, p) and \
                        t.get_new_hand(h, p) and \
                        t.get_table_cards() and \
                        t.get_dealer_position()

                if ready and (not t.check_fast_fold(h)):
                    fast_fold = True
                    break

                ready = ready and\
                        t.check_for_button() and \
                        t.get_round_number(h) and \
                        t.init_get_other_players_info() and \
                        t.get_other_player_status(p, h) and \
                        t.get_other_player_names(p) and \
                        t.get_other_player_funds(p) and \
                        t.get_other_player_pots() and \
                        t.get_total_pot_value() and \
                        t.get_round_pot_value() and \
                        t.get_current_call_value() and \
                        t.get_current_bet_value()

            config = ConfigObj("config.ini")
            if not fast_fold:
                m = run_montecarlo_wrapper(p, config, t, self.game_logger, preflop_state, h)
                d = Decision(t, h, p, self.game_logger)
                d.make_decision(t, h, p, self.game_logger)
                decision = d.decision

                log.info(
                    "Equity: " + str(t.equity * 100) + "% -> " + str(int(t.assumedPlayers)) + " (" + str(
                        int(t.other_active_players)) + "-" + str(int(t.playersAhead)) + "+1) Plr")
                log.info("Final Call Limit: " + str(d.finalCallLimit) + " --> " + str(t.minCall))
                log.info("Final Bet Limit: " + str(d.finalBetLimit) + " --> " + str(t.minBet))
                log.info(
                    "Pot size: " + str((t.totalPotValue)) + " -> Zero EV Call: " + str(round(d.maxCallEV, 2)))
                t_log_db = threading.Thread(name='t_log_db', target=self.game_logger.write_log_file, args=[p, h, t, d])
                t_log_db.daemon = True
                t_log_db.start()

                h.previousPot = t.totalPotValue
                h.histGameStage = t.gameStage
                h.histDecision = d.decision
                h.histEquity = t.equity
                h.histMinCall = t.minCall
                h.histMinBet = t.minBet
                h.hist_other_players = t.other_players
                h.first_raiser = t.first_raiser
                h.first_caller = t.first_caller
                h.previous_decision = d.decision
                h.lastRoundGameID = h.GameID
                h.previous_round_pot_value = t.round_pot_value
                h.last_round_bluff = False if t.currentBluff == 0 else True
                if t.gameStage == 'PreFlop':
                    preflop_state.update_values(t, d.decision, h, d)
                log.info("=========== round end ===========")
            else:
                decision = DecisionTypes.fold


            log.info("+++++++++++++++++++++++ Decision: " + str(decision) + "+++++++++++++++++++++++")




# ==== MAIN PROGRAM =====

def run_poker():
    init_logger(screenlevel=logging.INFO, filename='deepmind_pokerbot', logdir='log')
    # print(f"Screenloglevel: {screenloglevel}")
    log = logging.getLogger("")
    log.info("Initializing program")

    # Back up the reference to the exceptionhook
    sys._excepthook = sys.excepthook
    log.info("Check for auto-update")
    updater = UpdateChecker()
    updater.check_update(version)
    log.info(f"Lastest version already installed: {version}")


    t1 = ThreadManager(1, "Thread-1", 1, updater)
    t1.start()


if __name__ == '__main__':
    run_poker()
