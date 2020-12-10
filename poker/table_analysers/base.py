import logging
import re
import sys
import time

import cv2  # opencv 3.0
import numpy as np
import pytesseract
from PIL import Image, ImageFilter
from configobj import ConfigObj

from  decisionmaker.genetic_algorithm import GeneticAlgorithm
from  scraper.recognize_table import TableScraper
from  tools.vbox_manager import VirtualBoxController


class Table(TableScraper):
    # General tools that are used to operate the pokerbot and are valid for all tables
    def __init__(self, p, game_logger, version):
        self.version = version
        self.ip = ''
        self.logger = logging.getLogger('table')
        self.logger.setLevel(logging.DEBUG)
        self.game_logger = game_logger

    def call_genetic_algorithm(self, p):
        n = self.game_logger.get_game_count(p.current_strategy)
        lg = int(p.selected_strategy['considerLastGames'])  # only consider lg last games to see if there was a loss
        f = self.game_logger.get_strategy_return(p.current_strategy, lg)

        total_winnings = self.game_logger.get_strategy_return(p.current_strategy, 9999999)

        winnings_per_bb_100 = total_winnings / p.selected_strategy['bigBlind'] / n * 100 if n > 0 else 0

        self.logger.info("Total Strategy winnings: %s", total_winnings)
        self.logger.info("Winnings in BB per 100 hands: %s", np.round(winnings_per_bb_100, 2))

        self.logger.info("Game #" + str(n) + " - Last " + str(lg) + ": $" + str(f))

        if n % int(p.selected_strategy['strategyIterationGames']) == 0 and f < float(
                p.selected_strategy['minimumLossForIteration']):
            self.logger.info("***Improving current strategy***")
            # winsound.Beep(500, 100)
            GeneticAlgorithm(True, self.game_logger)
            p.read_strategy()
        else:
            pass
            # self.logger.debug("Criteria not met for running genetic algorithm. Recommendation would be as follows:")
            # if n % 50 == 0: GeneticAlgorithm(False, logger, L)

    def get_utg_from_abs_pos(self, abs_pos, dealer_pos):
        utg_pos = (abs_pos - dealer_pos + 4) % 6
        return utg_pos

    def get_abs_from_utg_pos(self, utg_pos, dealer_pos):
        abs_pos = (utg_pos + dealer_pos - 4) % 6
        return abs_pos

    def get_raisers_and_callers(self, p, reference_pot):
        first_raiser = np.nan
        second_raiser = np.nan
        first_caller = np.nan

        for n in range(5):  # n is absolute position of other player, 0 is player after bot
            i = (
                        self.table.dealer_position + n + 3 - 2) % 5  # less myself as 0 is now first other player to my left and no longer myself
            self.logger.debug("Go through pots to find raiser abs: {0} {1}".format(i, self.other_players[i]['pot']))
            if self.other_players[i]['pot'] != '':  # check if not empty (otherwise can't convert string)
                if self.other_players[i]['pot'] > reference_pot:
                    # reference pot is bb for first round and bot for second round
                    if np.isnan(first_raiser):
                        first_raiser = int(i)
                        first_raiser_pot = self.other_players[i]['pot']
                    else:
                        if self.other_players[i]['pot'] > first_raiser_pot:
                            second_raiser = int(i)

        first_raiser_utg = self.get_utg_from_abs_pos(first_raiser, self.table.dealer_position)
        highest_raiser = np.nanmax([first_raiser, second_raiser])
        second_raiser_utg = self.get_utg_from_abs_pos(second_raiser, self.table.dealer_position)

        first_possible_caller = int(self.big_blind_position_abs_op + 1) if np.isnan(highest_raiser) else int(
            highest_raiser + 1)
        self.logger.debug("First possible potential caller is: " + str(first_possible_caller))

        # get first caller after raise in preflop
        for n in range(first_possible_caller, 5):  # n is absolute position of other player, 0 is player after bot
            self.logger.debug(
                "Go through pots to find caller abs: " + str(n) + ": " + str(self.other_players[n]['pot']))
            if self.other_players[n]['pot'] != '':  # check if not empty (otherwise can't convert string)
                if (self.other_players[n]['pot'] == float(
                        p.selected_strategy['bigBlind']) and not n == self.big_blind_position_abs_op) or \
                        self.other_players[n]['pot'] > float(p.selected_strategy['bigBlind']):
                    first_caller = int(n)
                    break

        first_caller_utg = self.get_utg_from_abs_pos(first_caller, self.table.dealer_position)

        # check for callers between bot and first raiser. If so, first raiser becomes second raiser and caller becomes first raiser
        first_possible_caller = 0
        if self.position_utg_plus == 3: first_possible_caller = 1
        if self.position_utg_plus == 4: first_possible_caller = 2
        if not np.isnan(first_raiser):
            for n in range(first_possible_caller, first_raiser):
                if self.other_players[n]['status'] == 1 and \
                        not (self.other_players[n]['utg_position'] == 5 and p.selected_strategy['bigBlind']) and \
                        not (self.other_players[n]['utg_position'] == 4 and p.selected_strategy['smallBlind']) and \
                        not (self.other_players[n]['pot'] == ''):
                    second_raiser = first_raiser
                    first_raiser = n
                    first_raiser_utg = self.get_utg_from_abs_pos(first_raiser, self.table.dealer_position)
                    second_raiser_utg = self.get_utg_from_abs_pos(second_raiser, self.table.dealer_position)
                    break

        self.logger.debug("First raiser abs: " + str(first_raiser))
        self.logger.info("First raiser utg+" + str(first_raiser_utg))
        self.logger.debug("Second raiser abs: " + str(second_raiser))
        self.logger.info("Highest raiser abs: " + str(highest_raiser))
        self.logger.debug("First caller abs: " + str(first_caller))
        self.logger.info("First caller utg+" + str(first_caller_utg))

        return first_raiser, second_raiser, first_caller, first_raiser_utg, second_raiser_utg, first_caller_utg

    def derive_preflop_sheet_name(self, t, h, first_raiser_utg, first_caller_utg, second_raiser_utg):
        first_raiser_string = 'R' if not np.isnan(first_raiser_utg) else ''
        first_raiser_number = str(first_raiser_utg + 1) if first_raiser_string != '' else ''

        second_raiser_string = 'R' if not np.isnan(second_raiser_utg) else ''
        second_raiser_number = str(second_raiser_utg + 1) if second_raiser_string != '' else ''

        first_caller_string = 'C' if not np.isnan(first_caller_utg) else ''
        first_caller_number = str(first_caller_utg + 1) if first_caller_string != '' else ''

        round_string = '2' if h.round_number == 1 else ''

        sheet_name = str(t.position_utg_plus + 1) + \
                     round_string + \
                     str(first_raiser_string) + str(first_raiser_number) + \
                     str(second_raiser_string) + str(second_raiser_number) + \
                     str(first_caller_string) + str(first_caller_number)

        if h.round_number == 2:
            sheet_name = 'R1R2R1A2'

        self.preflop_sheet_name = sheet_name
        return self.preflop_sheet_name
