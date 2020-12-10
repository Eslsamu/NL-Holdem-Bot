"""Recognize table"""
import logging

from  scraper.screen_operations import take_screenshot, crop_screenshot_with_topleft_corner, \
    is_template_in_search_area, binary_pil_to_cv2, ocr
from  scraper.table_setup import CARD_SUITES, CARD_VALUES

log = logging.getLogger(__name__)


class TableScraper:
    def __init__(self):
        self.screenshot = None

        self.total_players = 6
        self.my_cards = None
        self.table_cards = None
        self.current_round_pot = None
        self.total_pot = None
        self.dealer_position = None
        self.players_in_game = None
        self.player_funds = None
        self.player_pots = None
        self.call_value = None
        self.raise_value = None
        self.call_button = None
        self.raise_button = None
        self.tlc = None

    def take_screenshot2(self):
        """Take a screenshot"""
        self.screenshot = take_screenshot()

    def crop_from_top_left_corner(self):
        """Crop top left corner based on the current selected table dict and replace self.screnshot with it"""
        self.screenshot, self.tlc = crop_screenshot_with_topleft_corner(self.screenshot,
                                                                        binary_pil_to_cv2(
                                                                            self.table_dict['topleft_corner']))
        return self.screenshot


    def fast_fold(self):
        """Find out if fast fold button is present"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'fast_fold_button', 'my_turn_search_area')


    def other_players_names(self):
        """Read other player names"""
        pass

    def get_player_pots(self, skip=[]):
        """Get pots of the players"""
        self.player_pots = []
        for i in range(self.total_players):
            if i in skip:
                funds = 0
            else:
                funds = ocr(self.screenshot, 'player_pot_area', self.table_dict, str(i))
            self.player_pots.append(funds)
        log.info(f"Player pots: {self.player_pots}")

        return True

    def check_button(self):
        """See if check button is avaialble"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'check_button', 'buttons_search_area')


    def has_all_in_call_button(self):
        """Check if all in call button is present"""
        return is_template_in_search_area(self.table_dict, self.screenshot,
                                          'all_in_call_button', 'buttons_search_area')

    def get_call_value(self):
        """Read the call value from the call button"""
        self.call_value = ocr(self.screenshot, 'call_value', self.table_dict)
        log.info(f"Call value: {self.call_value}")
        return self.call_value

    def get_raise_value(self):
        """Read the value of the raise button"""
        self.raise_value = ocr(self.screenshot, 'raise_value', self.table_dict)
        log.info(f"Raise value: {self.raise_value}")
        return self.raise_value

    def get_game_number_on_screen2(self):
        """Game number"""
        self.game_number = ocr(self.screenshot, 'game_number', self.table_dict)
        log.debug(f"Game number: {self.game_number}")
        return self.game_number
