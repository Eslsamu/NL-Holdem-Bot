import datetime
import inspect
import logging
import re
import sys
import threading
import time
from copy import copy

import numpy as np
import pytesseract
from PIL import Image

from  decisionmaker.montecarlo_python import MonteCarlo
from .base import Table

# some_file.py
import sys
# insert at 1, 0 is the script path (or '' in REPL)
sys.path.insert(1, '../scraper')
from scraper.recognize_table import TableScraper

log = logging.getLogger(__name__)
import json
from types import SimpleNamespace

class TableScreenBased(Table):
    def __init__(self, p, game_logger, version):
        Table.__init__(self, p, game_logger, version)
        TableScraper.__init__(self)

    def load_table(self):
        self.mt_tm = time.time()
        with open('test_table.json') as json_file:
            self.table = json.load(json_file, object_hook=lambda d: SimpleNamespace(**d))
        log.info('xxxxxx Current Table xxxxx')
        for key, item in self.table.__dict__.items():
            log.info(str(key) + ': ' + str(item))
        return True
        #table_cards
        #mycards
        #lost_everything
        #player_funds
        #dealer position """Determines position of dealer, where 0=myself, continous counter clockwise"""
        #is_my_turn
        #checkButton
        #players_in_game
        #bot_pot
        #player_names
        #current_round_pot
        #total_pot
        #player_pots (zero if not in game)
        #callButton
        #bet_button_found
        #allInCallButton
        #currentCallValue
        #raise_value

    def check_for_button(self):
        return self.table.is_my_turn

    def get_table_cards(self):
        self.cardsOnTable = self.table.table_cards

        self.gameStage = ''

        if len(self.cardsOnTable) < 1:
            self.gameStage = "PreFlop"
        elif len(self.cardsOnTable) == 3:
            self.gameStage = "Flop"
        elif len(self.cardsOnTable) == 4:
            self.gameStage = "Turn"
        elif len(self.cardsOnTable) == 5:
            self.gameStage = "River"
        if self.gameStage == '':
            log.critical("Table cards not recognised correctly: " + str(len(self.cardsOnTable)))
            self.gameStage = "River"

        log.info("---")
        log.info("Gamestage: " + self.gameStage)
        log.info("Cards on table: " + str(self.cardsOnTable))
        log.info("---")

        self.max_X = 1 if self.gameStage != 'PreFlop' else 0.86

        return True

    def check_fast_fold(self, h):
        if self.gameStage == "PreFlop":
            m = MonteCarlo()
            crd1, crd2 = m.get_two_short_notation(self.table.mycards)
            crd1 = crd1.upper()
            crd2 = crd2.upper()
            sheet_name = str(self.position_utg_plus + 1)
            if sheet_name == '6': return True
            sheet = h.preflop_sheet[sheet_name]
            sheet['Hand'] = sheet['Hand'].apply(lambda x: str(x).upper())
            handlist = set(sheet['Hand'].tolist())

            found_card = ''

            if crd1 in handlist:
                found_card = crd1
            elif crd2 in handlist:
                found_card = crd2
            elif crd1[0:2] in handlist:
                found_card = crd1[0:2]
            if found_card == '':
                log.info("-------- FAST FOLD -------")
                return False

        return True

    def init_get_other_players_info(self):
        other_player = dict()
        other_player['utg_position'] = ''
        other_player['name'] = ''
        other_player['status'] = ''
        other_player['funds'] = ''
        other_player['pot'] = ''
        other_player['decision'] = ''
        self.other_players = []
        for i in range(self.total_players - 1):
            op = copy(other_player)
            op['abs_position'] = i
            self.other_players.append(op)
        return True

    def get_other_player_names(self, p):
        if p.selected_strategy['gather_player_names'] == 1:
            for i in range(1,self.total_players):
                self.other_players[i - 1]['name'] = self.table.player_names[i]
        return True

    def get_other_player_funds(self, p):
        if p.selected_strategy['gather_player_names'] == 1:
            for i in range(1, self.total_players):
                value = self.table.player_funds[i]
                self.other_players[i - 1]['funds'] = value
        return True

    def get_other_player_pots(self):
        for i in range(1, self.total_players):
            if self.table.player_pots[i] != "":
                try:
                    self.other_players[i - 1]['pot'] = float(self.table.player_pots[n])
                except:
                    self.other_players[i - 1]['pot'] = 0

                log.debug("FINAL POT after regex: " + str(self.other_players[i - 1]))

        return True


    def get_other_player_status(self, p, h):
        self.covered_players = 0
        for i in range(1, self.total_players):
            if i in self.table.players_in_game:
                self.covered_players += 1
                self.other_players[i - 1]['status'] = 1
            else:
                self.other_players[i - 1]['status'] = 0

            self.other_players[i - 1]['utg_position'] = self.get_utg_from_abs_pos(
                self.other_players[i - 1]['abs_position'],
                self.table.dealer_position)

        self.other_active_players = sum([v['status'] for v in self.other_players])
        if self.gameStage == "PreFlop":
            self.playersBehind = sum(
                [v['status'] for v in self.other_players if v['abs_position'] >= self.table.dealer_position + 3 - 1])
        else:
            self.playersBehind = sum(
                [v['status'] for v in self.other_players if v['abs_position'] >= self.table.dealer_position + 1 - 1])
        self.playersAhead = self.other_active_players - self.playersBehind
        self.isHeadsUp = True if self.other_active_players < 2 else False
        log.debug("Other players in the game: " + str(self.other_active_players))
        log.debug("Players behind: " + str(self.playersBehind))
        log.debug("Players ahead: " + str(self.playersAhead))

        if h.round_number == 0:
            reference_pot = float(p.selected_strategy['bigBlind'])
        else:
            reference_pot = self.table.player_pots[0]

        # get first raiser in (tested for preflop)
        self.first_raiser, \
        self.second_raiser, \
        self.first_caller, \
        self.first_raiser_utg, \
        self.second_raiser_utg, \
        self.first_caller_utg = \
            self.get_raisers_and_callers(p, reference_pot)

        if ((h.previous_decision == "Call" or h.previous_decision == "Call2") and str(h.lastRoundGameID) == str(
                h.GameID)) and \
                not (self.table.checkButton == True and self.playersAhead == 0):
            self.other_player_has_initiative = True
        else:
            self.other_player_has_initiative = False

        log.info("Other player has initiative: " + str(self.other_player_has_initiative))

        return True

    def get_round_number(self, h):
        if h.histGameStage == self.gameStage and h.lastRoundGameID == h.GameID:
            h.round_number += 1
        else:
            h.round_number = 0
        return True

    def get_dealer_position(self):
        self.position_utg_plus = (self.total_players + 3 - self.table.dealer_position) % self.total_players

        log.info('Bot position is UTG+' + str(self.position_utg_plus))  # 0 mean bot is UTG

        self.big_blind_position_abs_all = (self.table.dealer_position + 2) % 6  # 0 is myself, 1 is player to my left
        self.big_blind_position_abs_op = self.big_blind_position_abs_all - 1

        return True

    def get_total_pot_value(self):
        self.totalPotValue = self.table.total_pot
        log.info("Final Total Pot Value: " + str(self.totalPotValue))
        return True

    def get_round_pot_value(self):
        self.round_pot_value = self.table.current_round_pot
        return True

    def get_my_funds(self):
        self.myFunds = self.table.player_funds[0]
        log.info("my_funds: " + str(self.myFunds))
        return True

    def get_current_call_value(self):
        if self.table.checkButton:
            self.table.currentCallValue = 0

        self.getCallButtonValueSuccess = True
        return True

    def get_current_bet_value(self):
        self.currentBetValue = self.table.raise_value

        if self.currentBetValue == '':
            log.warning("No bet value")
            self.currentBetValue = 9999999.0

        if self.currentBetValue < self.table.currentCallValue and not self.table.allInCallButton:
            self.table.currentCallValue = self.currentBetValue / 2
            self.BetValueReadError = True

        if self.currentBetValue < self.table.currentCallValue and self.table.allInCallButton:
            self.currentBetValue = self.table.currentCallValue + 0.01
            self.BetValueReadError = True

        log.info("Final call value: " + str(self.table.currentCallValue))
        log.info("Final bet value: " + str(self.currentBetValue))
        return True

    def get_lost_everything(self, h, t, p):
        lost_everything = self.table.lost_everything
        if lost_everything:
            h.lastGameID = str(h.GameID)
            self.myFundsChange = float(0) - float(h.myFundsHistory[-1])
            self.game_logger.mark_last_game(t, h, p)
            log.warning("Game over")
            sys.exit()
        else:
            return True

    def get_new_hand(self, h, p):
        if h.previousCards != self.table.mycards:
            log.info("+++========================== NEW HAND ==========================+++")
            self.time_new_cards_recognised = datetime.datetime.utcnow()
            self.get_my_funds()

            h.lastGameID = str(h.GameID)
            h.GameID = int(round(np.random.uniform(0, 999999999), 0))
            cards = ' '.join(self.table.mycards)

            if not len(h.myFundsHistory) == 0:
                self.myFundsChange = float(self.myFunds) - float(h.myFundsHistory[-1])
                self.game_logger.mark_last_game(self, h, p)

            t_algo = threading.Thread(name='Algo', target=self.call_genetic_algorithm, args=(p,))
            t_algo.daemon = True
            t_algo.start()

            h.myLastBet = 0
            h.myFundsHistory.append(self.myFunds)
            h.previousCards = self.table.mycards
            h.lastSecondRoundAdjustment = 0
            h.last_round_bluff = False  # reset the bluffing marker
            h.round_number = 0
        else:
            self.get_my_funds()

        return True
